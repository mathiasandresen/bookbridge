const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../templates/settings.html'), 'utf8');
const start = html.indexOf('let isFormDirty = false;');
const end = html.indexOf('// Initialize dirty check', start);
assert.ok(start >= 0 && end > start);
const checkbox = { name: 'ABS_ENABLED', type: 'checkbox', checked: false };
const text = { name: 'WHISPER_LANGUAGE', type: 'text', value: '' };
const select = { name: 'TRANSCRIPTION_PROVIDER', type: 'select-one', value: 'local' };
const picker = { id: 'shelf_picker', type: 'select-one', value: '' };
const hidden = { name: 'csrf_token', type: 'hidden', value: 'token' };
const fields = [checkbox, text, select, picker, hidden];
for (const field of fields) {
    field.handlers = {};
    field.addEventListener = (name, handler) => { field.handlers[name] = handler; };
}
const note = { style: {}, textContent: '' };
const windowHandlers = {};
const form = { addEventListener() {} };
const context = vm.createContext({
    document: {
        getElementById: () => note,
        querySelectorAll: selector => selector === 'form' ? [form] : fields,
    },
    window: { addEventListener: (name, handler) => { windowHandlers[name] = handler; } },
});
vm.runInContext(html.slice(start, end), context);
context.setupDirtyCheck();
const warning = () => {
    const event = {};
    windowHandlers.beforeunload(event);
    return event.returnValue;
};
assert.equal(warning(), undefined);
checkbox.checked = true;
checkbox.handlers.change();
assert.equal(note.textContent, '1 unsaved change');
assert.ok(warning());
text.value = 'ru';
text.handlers.input();
assert.equal(note.textContent, '2 unsaved changes');
checkbox.checked = false;
checkbox.handlers.change();
assert.equal(note.textContent, '1 unsaved change');
assert.ok(warning());
text.value = '';
text.handlers.input();
assert.equal(note.style.display, 'none');
assert.equal(warning(), undefined);
select.value = 'deepgram';
select.handlers.change();
select.value = 'local';
select.handlers.change();
assert.equal(warning(), undefined);
assert.equal(picker.handlers.change, undefined);
assert.equal(hidden.handlers.input, undefined);

// Shelf pickers update the actual saved input without a native input event.
const pickerStart = html.indexOf('function applyShelfPickerSelection(');
const pickerEnd = html.indexOf('function checkBookloreShelves(', pickerStart);
context.document.querySelector = () => text;
const shelfSelect = { value: 'Want to read' };
context.document.getElementById = id => id === 'dirty_note' ? note : shelfSelect;
vm.runInContext(html.slice(pickerStart, pickerEnd), context);
context.applyShelfPickerSelection(text.name, 'shelf_picker', true);
assert.equal(note.textContent, '1 unsaved change');
text.value = '';
text.handlers.change();
assert.equal(warning(), undefined);

// Connection tests submit the unsaved transcription key and qualify GET reachability.
const connectionStart = html.indexOf('const TEST_CONNECTION_FIELDS =');
const connectionEnd = html.indexOf('function toggleSection(', connectionStart);
assert.ok(connectionStart >= 0 && connectionEnd > connectionStart);
const connectionFields = {
    WHISPER_CPP_URL: { type: 'text', value: 'https://openrouter.ai/api/v1/audio/transcriptions' },
    WHISPER_CPP_API_KEY: { type: 'password', value: 'unsaved-key' },
};
let sentPayload;
let notice;
const connectionContext = vm.createContext({
    document: { querySelector: selector => connectionFields[selector.match(/name="([^"]+)"/)[1]] },
    fetch: (url, options) => {
        sentPayload = JSON.parse(options.body);
        return Promise.resolve({ json: () => Promise.resolve({
            ok: true, reachability_only: true, message: 'GET reachability only; transcription and credentials unverified.',
        }) });
    },
    alert: message => { notice = message; },
    setTimeout: () => {},
});
vm.runInContext(html.slice(connectionStart, connectionEnd), connectionContext);
const connectionButton = { innerHTML: 'Test', disabled: false };
connectionContext.testConnection('whispercpp', connectionButton);
setImmediate(() => {
    assert.equal(sentPayload.WHISPER_CPP_API_KEY, 'unsaved-key');
    assert.equal(connectionButton.innerHTML, '✅ Reachable only');
    assert.ok(notice.includes('credentials unverified'));
    assert.equal(connectionButton.disabled, false);
});
