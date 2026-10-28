# Provider selection fix verification

The canonical UI value `LLM_PROVIDER=openai_compatible` was absent from the runtime provider resolver. It fell through to `ollama`, while the settings Test helper accepted it. Added the canonical value to the existing recognized aliases without changing the other provider paths.

## Regression evidence

Before the fix, the expanded factory regression failed with `ollama != openai_compatible`. After the fix, all canonical and legacy aliases create `OpenAICompatibleClient`; OpenAI and default Ollama selection still pass their existing checks. The settings/runtime URL regression now obtains its runtime client through `create_llm_client()` using the exact UI value.

```sh
UV_CACHE_DIR=/private/tmp/bookbridge-uv-cache uv run --offline --with pytest --with-requirements requirements.txt python -m pytest tests/test_openrouter_support.py tests/test_whispercpp_test_endpoint.py tests/test_openai_compatible_client.py tests/test_ollama_test_endpoint.py tests/test_transcription_providers.py tests/test_settings_comprehensive.py tests/test_settings_save_key_allowlist.py tests/test_settings_taxonomy.py tests/test_credential_encryption.py tests/test_settings_dirty_counter.py -q
```

Result: 154 passed under Python 3.13.9, with one existing SQLAlchemy deprecation warning. The CI syntax/undefined-name gate passed for the three changed Python files:

```sh
UV_CACHE_DIR=/private/tmp/bookbridge-uv-cache uv run --offline --with flake8 --with pytest --with-requirements requirements.txt python -m flake8 src/api/llm_client.py tests/test_openai_compatible_client.py tests/test_openrouter_support.py --select=E9,F63,F7,F82 --show-source --statistics
```

## Live OpenRouter checks

Used the real factory and client with the canonical UI provider value and the explicitly supplied credential. No production configuration was read or changed.

| Operation | Model | Endpoint | HTTP | Result |
| --- | --- | --- | --- | --- |
| Embedding | `qwen/qwen3-embedding-8b` | `/api/v1/embeddings` | 200 | One nonempty 4096-dimensional vector |
| Chat / judge | `openai/gpt-6-luna` | `/api/v1/chat/completions` | 200 | Expected JSON object parsed successfully |

Each operation made one request. No `/api/embeddings` or `/api/chat` requests occurred. Only endpoint paths, status codes, model IDs, dimensions, and success flags were recorded, without the key or generated content.

Live transcription and full-audiobook alignment remain unverified. Judge-failure fallback policy was left unchanged and needs separate investigation. No cluster deployment changes were made.

## Corrected image

Source commit: `53ad0cde24c5bed279c4ee6b2480ca577aee2da1`.

Built the standard CPU image for `linux/amd64` from a `git archive` of that commit using the existing Dockerfile and `APP_VERSION=openrouter-factory-20261028T161746Z-53ad0cd`. The image revision label records the full source commit.

The image passed the packaged transcription feature checks and runtime factory/embedding/chat URL checks with mocked HTTP and network disabled. A fresh-data startup completed migrations and served `/setup` with HTTP 200. The temporary container was removed.

The Dockerfile places version metadata before dependency installation, invalidating dependency-layer caching for each version. This is a separate build-speed improvement; the Dockerfile is unchanged here.

Published and verified from GHCR:

```text
ghcr.io/mathiasandresen/bookbridge:openrouter-factory-20261028T161746Z-53ad0cd@sha256:b9fd675581dc13037a03adfb4141c7f886de24039713df1614f0838a96fedc0a
```

Authenticated remote manifest inspection confirmed `linux/amd64` and this digest. Anonymous pull returned HTTP 401, so deployment needs a GHCR pull secret unless package visibility changes. Temporary Docker publishing credentials were removed after verification. No deployment changes were made.
