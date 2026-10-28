"""Regression coverage for authenticated transcription and model catalog discovery."""
import io
import logging
import wave
from unittest.mock import MagicMock, patch

import pytest
import requests
from flask import Flask

from src.api.llm_client import create_llm_client
from src.api.openai_compatible_client import OpenAICompatibleClient
from src.utils.transcription_providers import WhisperCppServerProvider
from src.web_server import _run_test_connection, _test_openai_compatible, _test_whispercpp

KEY = 'test-transcription-secret'
EMBED = 'qwen/qwen3-embedding-8b'
CHAT = 'openai/gpt-6-luna'
BASE = 'https://openrouter.ai/api/v1'


def response(status=200, payload=None):
    result = requests.Response()
    result.status_code = status
    result.json = MagicMock(return_value=payload)
    result._content = b''
    return result


@pytest.mark.parametrize('status,ok', [(200, True), (204, True), (404, True), (405, True),
                                          (401, False), (403, False), (429, False), (500, False), (302, False)])
@pytest.mark.parametrize('key', ['', KEY])
def test_transcription_probe_status_and_auth(status, ok, key):
    with patch('src.web_server.requests.get', return_value=response(status)) as get:
        result = _test_whispercpp(BASE + '/audio/transcriptions', key)
    assert result['ok'] is ok
    assert get.call_args.kwargs['headers'] == ({'Authorization': f'Bearer {key}'} if key else {})
    assert get.call_args.kwargs['allow_redirects'] is False
    assert KEY not in str(result)
    if ok:
        assert result['reachability_only']
        assert 'transcription and credentials unverified' in result['message']
        if status == 404:
            assert 'path may be incorrect' in result['message']


def test_unsaved_key_reaches_probe():
    with Flask(__name__).app_context(), patch('src.web_server._test_whispercpp', return_value={'ok': True}) as probe:
        _run_test_connection('whispercpp', {'WHISPER_CPP_URL': BASE + '/audio/transcriptions', 'WHISPER_CPP_API_KEY': KEY})
    probe.assert_called_once_with(BASE + '/audio/transcriptions', KEY)


@pytest.mark.parametrize('key', ['', KEY])
def test_upload_auth_and_timed_chunks(monkeypatch, tmp_path, key):
    monkeypatch.setenv('WHISPER_CPP_URL', BASE + '/audio/transcriptions')
    monkeypatch.setenv('WHISPER_CPP_API_KEY', key)
    monkeypatch.setenv('WHISPER_CPP_CHUNK_MINUTES', '1')
    path = tmp_path / 'audio.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(100)
        audio.writeframes(b'\0\0' * 9000)
    payload = {'segments': [{'start': 1, 'end': 2, 'text': 'word',
                              'words': [{'word': 'word', 'start': 1, 'end': 2}]}]}
    with patch('requests.post', side_effect=lambda *a, **kw: response(payload=payload)) as post:
        segments = WhisperCppServerProvider().transcribe(path)
    assert post.call_count == 2
    for call in post.call_args_list:
        assert call.kwargs['headers'] == ({'Authorization': f'Bearer {key}'} if key else {})
        assert call.kwargs['allow_redirects'] is False
        assert call.kwargs['data']['response_format'] == 'verbose_json'
    assert [seg['start'] for seg in segments] == [1, 61]
    assert segments[1]['words'][0]['start'] == 61


def test_source_download_never_receives_transcription_key(monkeypatch):
    monkeypatch.setenv('WHISPER_CPP_URL', BASE + '/audio/transcriptions')
    monkeypatch.setenv('WHISPER_CPP_API_KEY', KEY)
    monkeypatch.setenv('WHISPER_CPP_CHUNK_MINUTES', '0')
    source = MagicMock()
    source.__enter__.return_value = source
    source.headers = {}
    source.iter_content.return_value = [b'audio']
    with patch('requests.get', return_value=source) as get, patch('requests.post', return_value=response(payload={'segments': []})) as post:
        WhisperCppServerProvider().transcribe('https://abs.example/audio.mp3')
    assert 'Authorization' not in get.call_args.kwargs['headers']
    assert post.call_args.kwargs['headers']['Authorization'] == f'Bearer {KEY}'


@pytest.mark.parametrize('failure', ['http', 'transport', 'payload'])
def test_upload_errors_do_not_expose_secret(monkeypatch, caplog, failure):
    monkeypatch.setenv('WHISPER_CPP_URL', BASE + '/audio/transcriptions')
    monkeypatch.setenv('WHISPER_CPP_API_KEY', KEY)
    resp = response(401 if failure == 'http' else 200, {'segments': [{'start': KEY}]})
    resp._content = KEY.encode()
    kwargs = {'side_effect': requests.ConnectionError(KEY)} if failure == 'transport' else {'return_value': resp}
    with patch('requests.post', **kwargs), caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError) as error:
            WhisperCppServerProvider()._post(io.BytesIO(b'audio'), 'audio.wav', 'audio/wav')
    assert KEY not in str(error.value)
    assert KEY not in caplog.text


@pytest.mark.parametrize('base,expected', [(BASE, BASE + '/models?output_modalities=all'),
    (BASE + '/', BASE + '/models?output_modalities=all'),
    ('http://llama:8080/v1', 'http://llama:8080/v1/models'),
    ('https://openrouter.ai.example/v1', 'https://openrouter.ai.example/v1/models'),
    ('https://api.openai.com/v1', 'https://api.openai.com/v1/models')])
def test_discovery_shared_by_settings_and_client(monkeypatch, base, expected):
    # The default text-output catalog lacks the embedding model.
    text_catalog = {'data': [{'id': CHAT}]}
    all_catalog = {'data': [{'id': CHAT}, {'id': EMBED}]}
    def catalog(url, **kwargs):
        return response(payload=all_catalog if url == expected else text_catalog)
    with patch('src.web_server.requests.get', side_effect=catalog) as get:
        result = _test_openai_compatible('openai_compatible', base, '', EMBED, CHAT)
    assert result['ok']
    assert 'IDs found' in result['message']
    assert 'ready' not in result['message']
    assert get.call_args.args[0] == expected
    monkeypatch.setenv('LLM_BASE_URL', base)
    client = OpenAICompatibleClient('openai_compatible')
    client.session = MagicMock()
    client.session.request.return_value = response(payload=all_catalog)
    assert client.list_models() == [CHAT, EMBED]
    assert client.session.request.call_args.args[1] == expected


@pytest.mark.parametrize('payload,status,word', [({'data': [{'id': CHAT}]}, 200, 'embedding'),
    ({'data': [{'id': EMBED}]}, 200, 'chat / judge'), ({'data': []}, 200, 'unverified'),
    ({}, 200, 'Malformed'), ([], 200, 'Malformed'), ({'data': 'wrong'}, 200, 'Malformed'),
    ({'data': [None]}, 200, 'Malformed'), ({}, 401, '401'), ({}, 403, '403')])
def test_catalog_failures(payload, status, word):
    with patch('src.web_server.requests.get', return_value=response(status, payload)):
        result = _test_openai_compatible('openai_compatible', BASE, '', EMBED, CHAT)
    assert not result['ok']
    assert word in result['message']


def test_real_settings_test_path_and_runtime_urls(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'openai_compatible')
    monkeypatch.setenv('LLM_BASE_URL', BASE)
    monkeypatch.setenv('OLLAMA_ENABLED', 'true')
    monkeypatch.setenv('LLM_EMBED_MODEL', EMBED)
    monkeypatch.setenv('LLM_CHAT_MODEL', CHAT)
    payload = {'LLM_PROVIDER': 'openai_compatible', 'OLLAMA_ENABLED': True, 'LLM_BASE_URL': BASE,
               'LLM_EMBED_MODEL': EMBED, 'LLM_CHAT_MODEL': CHAT}
    with Flask(__name__).app_context(), patch('src.web_server.requests.get', return_value=response(payload={'data': [{'id': EMBED}, {'id': CHAT}]})) as get:
        result = _run_test_connection('ollama', payload).get_json()
    assert result['ok']
    assert get.call_args.args[0] == BASE + '/models?output_modalities=all'
    client = create_llm_client()
    assert isinstance(client, OpenAICompatibleClient)
    client.session = MagicMock()
    client.session.request.return_value = response(payload={'data': [{'embedding': [1]}]})
    assert client.embed(['text']) == [[1]]
    assert client.session.request.call_args.args[1] == BASE + '/embeddings'
    client._post_chat('prompt', None, False)
    assert client.session.request.call_args.args[1] == BASE + '/chat/completions'


@pytest.mark.parametrize('failure', ['network', 'json'])
def test_catalog_probe_errors_are_failures(failure):
    resp = response()
    resp.json.side_effect = ValueError('invalid json')
    kwargs = {'side_effect': requests.ConnectionError('offline')} if failure == 'network' else {'return_value': resp}
    with Flask(__name__).app_context(), patch('src.web_server.requests.get', **kwargs):
        result = _run_test_connection('ollama', {'OLLAMA_ENABLED': True, 'LLM_PROVIDER': 'openai_compatible',
            'LLM_BASE_URL': BASE, 'LLM_EMBED_MODEL': EMBED, 'LLM_CHAT_MODEL': CHAT}).get_json()
    assert not result['ok']


@pytest.mark.parametrize('payload,status', [({}, 200), ({'data': []}, 200), ({'data': 'bad'}, 200), ({}, 401)])
def test_client_catalog_failures(monkeypatch, payload, status):
    monkeypatch.setenv('LLM_BASE_URL', BASE)
    client = OpenAICompatibleClient('openai_compatible')
    client.session = MagicMock()
    client.session.request.return_value = response(status, payload)
    assert client.list_models() == []


def test_probe_exception_secret_redaction():
    with patch('src.web_server.requests.get', side_effect=requests.RequestException(KEY)):
        result = _test_whispercpp(BASE, KEY)
    assert not result['ok']
    assert KEY not in str(result)
