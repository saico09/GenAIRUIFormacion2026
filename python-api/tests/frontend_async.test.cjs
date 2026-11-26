// Contratos de coordinación con DOM y transporte mínimos; no abre un navegador ni usa APIs reales.
// vm.SourceTextModule requiere ejecutar con node --experimental-vm-modules.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const staticDir = path.resolve(__dirname, '../app/static');

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
// «Actualizar historia» no devuelve su promesa al listener: se espera a que la vista deje de estar ocupada.
async function refreshHistory(fixture) {
  fixture.fire('#refresh-history', 'click');
  for (let i = 0; i < 100 && fixture.node('#patient-detail').getAttribute('aria-busy') !== 'false'; i++) await tick();
}
const ok = data => ({ok: true, status: 200, data});

function documentFixture() {
  const nodes = new Map();
  const emitted = [];
  const dispatched = [];
  function node(key) {
    if (!nodes.has(key)) nodes.set(key, {
      value: '', textContent: '', hidden: false, disabled: false, children: [], dataset: {}, className: '',
      attributes: new Map(), listeners: new Map(), classList: {add() {}, remove() {}},
      elements: {namedItem: name => node(`${key}:${name}`)},
      get selectedOptions() { return (this.options || []).filter(option => String(option.value) === String(this.value)); },
      addEventListener(type, callback) { this.listeners.set(type, callback); },
      setAttribute(name, value) { this.attributes.set(name, value); },
      getAttribute(name) { return this.attributes.get(name); },
      querySelector: selector => node(`${key} ${selector}`), querySelectorAll: () => [],
      replaceChildren(...children) { this.children = children; this.options = children; },
      append(...children) { this.children.push(...children); },
      focus() {}, scrollIntoView() {}, reset() {}, setCustomValidity() {}, reportValidity: () => true,
      showModal() { this.open = true; }, close() { this.open = false; },
    });
    return nodes.get(key);
  }
  const events = node('document');
  const document = {
    querySelector: node, getElementById: id => node(`#${id}`), querySelectorAll: () => [],
    createElement: tag => node(`created:${tag}:${nodes.size}`),
    addEventListener: (type, callback) => events.addEventListener(type, callback),
    dispatchEvent: event => { emitted.push(event.type); dispatched.push(event); },
  };
  const fire = (selector, type, detail) => node(selector).listeners.get(type)({preventDefault() {}, detail});
  return {document, node, fire, emitted, dispatched};
}

function apiDouble(request) {
  let ids = 0;
  return {
    request, errorMessage: result => result.data?.detail || `HTTP ${result.status}`,
    notice(element, message, tone = 'error') { element.textContent = message; element.hidden = !message; element.className = `notice ${tone}`; },
    confirmAction: async () => true, confirmDelete: async () => true,
    newId: () => `id-${++ids}`, indexError: () => undefined, indexSyncing: () => false, setIndexState() {},
    async syncIndex(id) {
      const result = await request(`/clinical/patients/${id}/sync`, {method: 'POST'});
      if (!result.ok) throw new Error(`HTTP ${result.status}`);
      return result;
    },
  };
}

async function loadModule(name, fixture, request, extra = {}) {
  const context = vm.createContext({document: fixture.document, TextEncoder, CustomEvent, Event, URL, Blob, AbortController, console});
  const api = {...apiDouble(request), ...extra['./api.js']};
  const modules = new Map();
  const synthetic = exports => new vm.SyntheticModule(Object.keys(exports), function () {
    for (const [key, value] of Object.entries(exports)) this.setExport(key, value);
  }, {context});
  function linker(specifier) {
    if (!modules.has(specifier)) {
      const stub = specifier === './api.js' ? api : extra[specifier];
      modules.set(specifier, stub ? synthetic(stub)
        : new vm.SourceTextModule(fs.readFileSync(path.join(staticDir, specifier), 'utf8'), {context, identifier: path.join(staticDir, specifier)}));
    }
    return modules.get(specifier);
  }
  const module = linker(`./${name}`);
  await module.link(linker);
  await module.evaluate();
  return module.namespace;
}

async function historyFixture(apiOverrides = {}) {
  const fixture = documentFixture();
  const calls = [];
  const state = {report: {entries: [], consultations: [], markdown: '# Paciente', revision: 'r1', filename: 'paciente.md'},
    failWrite: false, onRead: null, onWrite: null};
  const request = async (url, options = {}) => {
    const method = options.method || 'GET';
    calls.push({url, method, body: options.body && JSON.parse(options.body)});
    if (url.endsWith('/sync')) return ok({});
    if (method !== 'GET') {
      if (state.failWrite) throw new Error('Escritura rechazada');
      return state.onWrite ? state.onWrite(url, options) : ok(state.report);
    }
    return state.onRead ? state.onRead(url) : ok(state.report);
  };
  const module = await loadModule('history.js', fixture, request, {'./api.js': apiOverrides});
  const history = module.initHistory('http://java.test');
  const patient = {id: 99, name: 'Paciente sintético', email: 'test@example.com'};
  await history.open(patient);
  fixture.node('#disease-form:disease').value = 'Registro sintético';
  const writes = () => calls.filter(call => ['POST', 'PUT', 'DELETE'].includes(call.method) && !call.url.endsWith('/sync'));
  const syncs = () => calls.filter(call => call.url.endsWith('/sync'));
  return {...fixture, calls, state, history, patient, writes, syncs};
}

test('cada refresco de la historia lee sólo /history, que ya trae los registros', async () => {
  const fixture = await historyFixture();
  assert.deepEqual(fixture.calls.map(call => `${call.method} ${call.url}`), ['GET http://java.test/patients/99/history']);
});

for (const operation of ['registro', 'markdown']) {
  test(`${operation}: espera la relectura antes de sincronizar y de habilitar otra escritura`, async () => {
    const fixture = await historyFixture();
    const reread = deferred();
    let rereadStarted = false;
    fixture.state.onRead = () => { rereadStarted = true; return reread.promise; };
    const form = operation === 'registro' ? '#disease-form' : '#history-markdown-form';
    const pending = fixture.fire(form, 'submit');
    await tick();
    assert.equal(rereadStarted, true);
    assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'true');
    assert.equal(fixture.syncs().length, 0);
    await fixture.fire(form, 'submit');
    assert.equal(fixture.writes().length, 1);
    reread.resolve(ok(fixture.state.report));
    await pending;
    assert.equal(fixture.syncs().length, 1);
    assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'false');
  });
}

test('un error al releer después de guardar no deja lista otra alta ni borra el error', async () => {
  const fixture = await historyFixture();
  fixture.state.onRead = async () => { throw new Error('Relectura fallida'); };
  await fixture.fire('#disease-form', 'submit');
  assert.match(fixture.node('#history-notice').textContent, /quedó guardado.*Relectura fallida/);
  assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'false');
  await fixture.fire('#disease-form', 'submit');
  assert.equal(fixture.writes().length, 1);
});

test('un fallo HTTP de guardado se muestra y libera el formulario', async () => {
  const fixture = await historyFixture();
  fixture.state.failWrite = true;
  await fixture.fire('#disease-form', 'submit');
  assert.equal(fixture.node('#disease-form-notice').textContent, 'Escritura rechazada');
  assert.equal(fixture.node('#history-notice').hidden, true);
  assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'false');
  assert.equal(fixture.syncs().length, 0);
});

const header = '# Historia clínica ficticia — Paciente sintético\n\nDatos ficticios para la formación.\n\npatient_id: 99\n';
const record = (id, text) => `\n## Registro ${id}\n\n### Enfermedad\n${text}\n\n### Tratamiento\nSin información registrada.\n\n### Medicamento\nSin información registrada.\n`;
const journal = ids => '\n## Consultas registradas\n\nConversaciones guardadas automáticamente.\n'
  + ids.map(id => `\n### Consulta ${id}\n\n#### Nota reportada\n> Nota ${id}\n`).join('');
const uuidA = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa';
const uuidB = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb';

test('tras un 409 el borrador Markdown se rearma con la cabecera y el diario vigentes y avisa del UUID que falta', async () => {
  const descriptions = [];
  const fixture = await historyFixture({confirmAction: async description => { descriptions.push(description); return true; }});
  fixture.state.report = {...fixture.state.report, revision: 'r1', markdown: header + record(uuidA, 'Reflujo') + journal(['c1'])};
  await refreshHistory(fixture);
  fixture.node('#history-markdown-form').hidden = true;
  fixture.fire('#edit-history', 'click');
  const input = fixture.node('#history-markdown-input');
  input.value = input.value.replace('Reflujo', 'Reflujo revisado');
  fixture.state.onWrite = () => ({ok: false, status: 409, data: {detail: 'La revisión del informe cambió'}});
  await fixture.fire('#history-markdown-form', 'submit');
  assert.match(fixture.node('#history-notice').textContent, /La revisión del informe cambió.*Actualizar historia/);
  // Mientras tanto se guardaron una consulta y un registro nuevo en otra operación.
  fixture.state.onWrite = null;
  fixture.state.report = {...fixture.state.report, revision: 'r2', markdown: header + record(uuidA, 'Reflujo') + record(uuidB, 'Rinitis') + journal(['c1', 'c2'])};
  await refreshHistory(fixture);
  assert.equal(input.value, header + record(uuidA, 'Reflujo revisado') + journal(['c1', 'c2']));
  assert.match(fixture.node('#history-notice').textContent, new RegExp(`no incluye.*${uuidB}`));
  await fixture.fire('#history-markdown-form', 'submit');
  const put = fixture.writes().at(-1);
  assert.equal(put.method, 'PUT');
  assert.equal(put.body.revision, 'r2');
  assert.equal(put.body.markdown, input.value);
  assert.match(descriptions.at(-1), new RegExp(`Se eliminarán.*${uuidB}`, 's'));
});

test('records.js: rearma el borrador y detecta registros eliminados o cambiados en el archivo', async () => {
  const records = await loadModule('records.js', documentFixture(), null);
  const base = header + record(uuidA, 'Reflujo') + record(uuidB, 'Rinitis') + journal(['c1']);
  // Windows puede entregar CRLF: se compara igual que con LF.
  const draft = (header + record(uuidA, 'Reflujo revisado') + record(uuidB, 'Rinitis') + journal(['c1'])).replace(/\n/g, '\r\n');
  const current = header + record(uuidA, 'Reflujo') + record(uuidB, 'Rinitis estacional') + journal(['c1', 'c2']);
  assert.equal(records.rebuildDraft(draft, current), header + record(uuidA, 'Reflujo revisado') + record(uuidB, 'Rinitis') + journal(['c1', 'c2']));
  assert.deepEqual(Array.from(records.recordIds(current)), [uuidA, uuidB]);
  // B cambió en el archivo y el borrador conserva la versión anterior; A sólo la cambió el borrador.
  assert.deepEqual(Array.from(records.changedRecords(base, current, draft)), [uuidB]);
  assert.deepEqual(Array.from(records.changedRecords(base, current, current)), []);
  // Borrado en el archivo pero presente en el borrador: guardarlo lo devolvería.
  assert.deepEqual(Array.from(records.changedRecords(base, header + record(uuidA, 'Reflujo') + journal(['c1']), base)), [uuidB]);
  assert.deepEqual(Array.from(records.missingRecords(current, header + record(uuidA, 'Reflujo') + journal(['c1']))), [uuidB]);
  assert.equal(records.rebuildDraft(header + journal([]), current), header + journal(['c1', 'c2']));
});

test('un registro editado en la tabla con el Markdown abierto se avisa al refrescar y al confirmar', async () => {
  const descriptions = [];
  const fixture = await historyFixture({confirmAction: async description => { descriptions.push(description); return true; }});
  fixture.state.report = {...fixture.state.report, revision: 'r1', markdown: header + record(uuidA, 'Reflujo') + journal(['c1'])};
  await refreshHistory(fixture);
  fixture.node('#history-markdown-form').hidden = true;
  fixture.fire('#edit-history', 'click');
  fixture.state.onWrite = () => {
    fixture.state.report = {...fixture.state.report, revision: 'r2', markdown: header + record(uuidA, 'Reflujo controlado') + journal(['c1'])};
    return ok(fixture.state.report);
  };
  await fixture.fire('#disease-form', 'submit');
  assert.match(fixture.node('#history-notice').textContent, new RegExp(`versión anterior: ${uuidA}`));
  fixture.state.onWrite = null;
  await fixture.fire('#history-markdown-form', 'submit');
  assert.match(descriptions.at(-1), new RegExp(`Volverán a la versión de tu borrador.*${uuidA}`, 's'));
});

test('Cancelar «Preparar con IA» conserva la nota y libera la historia', async () => {
  const fixture = await historyFixture();
  fixture.fire('#new-consultation', 'click');
  fixture.node('#consultation-note').value = 'Enfermedad: reflujo';
  let signal = null;
  fixture.state.onWrite = (url, options) => new Promise((resolve, reject) => {
    signal = options.signal;
    signal.addEventListener('abort', () => { const error = new Error('Petición cancelada.'); error.name = 'AbortError'; reject(error); });
  });
  const pending = fixture.fire('#proposal-form', 'submit');
  await tick();
  assert.equal(fixture.writes().at(-1).url, '/clinical/proposals');
  assert.equal(fixture.node('#cancel-proposal').hidden, false);
  assert.equal(fixture.node('#cancel-proposal').disabled, false);
  assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'true');
  fixture.fire('#cancel-proposal', 'click');
  await pending;
  assert.equal(signal.aborted, true);
  assert.match(fixture.node('#proposal-notice').textContent, /cancelada.*nota se conserva/);
  assert.equal(fixture.node('#consultation-note').value, 'Enfermedad: reflujo');
  assert.equal(fixture.node('#cancel-proposal').hidden, true);
  assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'false');
});

test('la nota abierta no se descarta sin confirmar: «Preparar desde una nota» la enfoca y cerrar pregunta', async () => {
  let accept = false;
  const descriptions = [];
  const fixture = await historyFixture({confirmAction: async description => { descriptions.push(description); return accept; }});
  fixture.fire('#new-consultation', 'click');
  const note = fixture.node('#consultation-note');
  note.value = 'Nota sin guardar';
  fixture.fire('#new-consultation', 'click');
  assert.equal(note.value, 'Nota sin guardar');
  assert.equal(descriptions.length, 0);
  await fixture.fire('#close-consultation', 'click');
  assert.equal(descriptions.length, 1);
  assert.equal(fixture.node('#consultation-editor').hidden, false);
  assert.equal(note.value, 'Nota sin guardar');
  accept = true;
  await fixture.fire('#close-consultation', 'click');
  assert.equal(fixture.node('#consultation-editor').hidden, true);
  assert.equal(note.value, '');
});

test('un cambio externo con un registro abierto relee la historia sin bloquear su guardado', async () => {
  const fixture = await historyFixture();
  fixture.node('#history-markdown-form').hidden = true;
  fixture.fire('#new-disease', 'click');
  fixture.node('#disease-form:disease').value = 'Borrador sin guardar';
  const before = fixture.calls.length;
  await fixture.fire('document', 'clinical-history-changed', {patient_id: 99});
  assert.equal(fixture.calls.length, before + 1);
  assert.equal(fixture.node('#disease-form:disease').value, 'Borrador sin guardar');
  await fixture.fire('#disease-form', 'submit');
  assert.equal(fixture.writes().length, 1);
});

test('el cambio de paciente se avisa cuando el listado ya refleja el paciente guardado', async () => {
  const fixture = documentFixture();
  const list = deferred();
  const request = (url, options = {}) => options.method === 'POST'
    ? Promise.resolve({ok: true, status: 201, data: {id: 5, name: 'Paciente nuevo'}})
    : list.promise;
  const module = await loadModule('patients.js', fixture, request, {'./history.js': {initHistory: () => ({})}});
  module.initPatients('http://java.test');
  fixture.node('#patient-name').value = 'Paciente nuevo';
  const pending = fixture.fire('#patient-form', 'submit');
  await tick();
  assert.deepEqual(fixture.emitted, []);
  list.resolve(ok([{id: 5, name: 'Paciente nuevo', birth_date: '1990-01-01', email: 'nuevo@example.com'}]));
  await pending;
  assert.deepEqual(fixture.emitted, ['patients-changed']);
});

test('la búsqueda de pacientes ignora tildes y mayúsculas', async () => {
  const fixture = documentFixture();
  const module = await loadModule('patients.js', fixture, async () => ok([
    {id: 1, name: 'José Pérez', birth_date: '1990-01-01', email: 'jose@example.com'},
    {id: 2, name: 'Ana Demo', birth_date: '1991-02-02', email: 'ana@example.com'},
  ]), {'./history.js': {initHistory: () => ({})}});
  const patients = module.initPatients('http://java.test');
  await patients.loadPatients();
  fixture.node('#patient-search').value = 'PEREZ';
  fixture.fire('#patient-search', 'input');
  assert.equal(fixture.node('#patients-body').children.length, 1);
  assert.equal(fixture.node('#patient-empty').hidden, true);
  fixture.node('#patient-search').value = 'nadie';
  fixture.fire('#patient-search', 'input');
  assert.equal(fixture.node('#patient-empty').hidden, false);
});

test('una recarga de pacientes en cola se incluye en la finalización de la primera', async () => {
  const fixture = documentFixture();
  const first = deferred();
  const queued = deferred();
  let count = 0;
  const rows = ok([{id: 1, name: 'Paciente sintético'}]);
  const module = await loadModule('chat.js', fixture, () => {
    count += 1;
    return count === 1 ? Promise.resolve(rows) : count === 2 ? first.promise : queued.promise;
  });
  module.initChat('http://java.test');
  await tick();
  let finished = false;
  const pending = fixture.fire('document', 'patients-changed').then(() => { finished = true; });
  await fixture.fire('document', 'patients-changed');
  first.resolve(rows);
  await tick();
  assert.equal(count, 3);
  assert.equal(finished, false);
  assert.equal(fixture.node('#submit').disabled, true);
  queued.resolve(rows);
  await pending;
  assert.equal(fixture.node('#submit').disabled, false);
});

async function chatFixture() {
  const fixture = documentFixture();
  const calls = [];
  const state = {rows: [{id: 1, name: 'Ana Demo'}, {id: 2, name: 'Bruno Demo'}], respond: null};
  const request = async (url, options = {}) => {
    calls.push({url, options});
    return url.endsWith('/patients') ? ok(state.rows) : state.respond(options);
  };
  const module = await loadModule('chat.js', fixture, request);
  module.initChat('http://java.test');
  await tick();
  const ask = (patientId, question) => {
    fixture.node('#patient').value = String(patientId);
    fixture.node('#question').value = question;
    return fixture.fire('#chat-form', 'submit');
  };
  const executionIds = () => calls.filter(call => call.url === '/chat').map(call => call.options.headers['X-Execution-ID']);
  return {...fixture, state, ask, executionIds};
}
const saved = ok({direct_answer: 'Sin RAG', rag_answer: 'Con RAG', sources: [], model: 'modelo', index_synced: true,
  consultation: {id: 'guardada', saved: true}});

test('X-Execution-ID se reutiliza al reintentar y se renueva al cambiar la consulta, tras guardarla o tras un 409', async () => {
  const fixture = await chatFixture();
  const responses = [
    {ok: false, status: 503, data: {detail: 'Modelo no disponible'}},
    {ok: false, status: 503, data: {detail: 'Modelo no disponible'}},
    {ok: false, status: 503, data: {detail: 'Modelo no disponible'}},
    saved,
    {ok: false, status: 409, data: {detail: 'Este UUID ya corresponde a otra consulta'}},
    saved,
  ];
  fixture.state.respond = () => responses.shift();
  await fixture.ask(1, 'Primera consulta');
  await fixture.ask(1, 'Primera consulta');
  await fixture.ask(1, 'Consulta corregida');
  await fixture.ask(1, 'Consulta corregida');
  assert.equal(fixture.emitted.at(-1), 'clinical-history-changed');
  await fixture.ask(1, 'Consulta corregida');
  assert.equal(fixture.node('#error').textContent, 'Este UUID ya corresponde a otra consulta');
  await fixture.ask(1, 'Consulta corregida');
  assert.deepEqual(fixture.executionIds(), ['id-1', 'id-1', 'id-2', 'id-2', 'id-3', 'id-4']);
});

test('Cancelar corta la espera, libera el formulario y conserva el UUID para recuperar la consulta', async () => {
  const fixture = await chatFixture();
  fixture.state.respond = options => new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => { const error = new Error('Petición cancelada.'); error.name = 'AbortError'; reject(error); });
  });
  const pending = fixture.ask(2, 'Consulta larga');
  await tick();
  assert.equal(fixture.node('#cancel-chat').hidden, false);
  assert.equal(fixture.node('#submit').disabled, true);
  fixture.fire('#cancel-chat', 'click');
  await pending;
  assert.match(fixture.node('#error').textContent, /cancelada.*mismo ID/);
  assert.equal(fixture.node('#error').className, 'notice warning');
  assert.equal(fixture.node('#cancel-chat').hidden, true);
  assert.equal(fixture.node('#submit').disabled, false);
  fixture.state.respond = () => saved;
  await fixture.ask(2, 'Consulta larga');
  assert.deepEqual(fixture.executionIds(), ['id-1', 'id-1']);
});

test('si el paciente elegido se elimina, el selector queda sin paciente y lo avisa', async () => {
  const fixture = await chatFixture();
  const select = fixture.node('#patient');
  assert.equal(select.value, '', 'Al cargar no se elige un paciente por omisión');
  assert.equal(select.options[0].textContent, 'Selecciona un paciente');
  select.value = '2';
  fixture.state.rows = [{id: 1, name: 'Ana Demo'}];
  await fixture.fire('document', 'patients-changed');
  assert.equal(select.value, '');
  assert.match(fixture.node('#error').textContent, /ID 2.*Selecciona otro/);
  assert.equal(fixture.node('#error').className, 'notice warning');
  fixture.state.respond = () => saved;
  await fixture.fire('#chat-form', 'submit');
  assert.equal(fixture.executionIds().length, 0, 'Sin paciente elegido no se envía la consulta');
});

async function loadApi(fetch) {
  const fixture = documentFixture();
  const context = vm.createContext({document: fixture.document, CustomEvent, URL, AbortController, setTimeout, clearTimeout,
    performance, fetch, crypto: {getRandomValues: bytes => bytes.fill(7)}, location: {href: 'http://localhost:8000/', origin: 'http://localhost:8000'}});
  const module = new vm.SourceTextModule(fs.readFileSync(path.join(staticDir, 'api.js'), 'utf8'), {context, identifier: path.join(staticDir, 'api.js')});
  await module.link(() => { throw new Error('api.js no importa otros módulos'); });
  await module.evaluate();
  return {api: module.namespace, fixture};
}
const response = (status, body) => ({ok: status < 400, status, text: async () => body === undefined ? '' : JSON.stringify(body), headers: {get: () => null}});

test('api.js: un solo estado de índice para todas las vistas y errores que nombran la API', async () => {
  let fail = true;
  const {api, fixture} = await loadApi(async url => {
    if (url.startsWith('http://localhost:8080')) throw new TypeError('Failed to fetch');
    return fail ? response(503, {detail: 'Qdrant no disponible'}) : response(200, {status: 'synced'});
  });
  const failing = api.syncIndex(7);
  assert.equal(api.indexSyncing(7), true);
  await assert.rejects(failing, /Qdrant no disponible/);
  assert.equal(api.indexSyncing(7), false);
  assert.equal(api.indexError(7), 'Qdrant no disponible');
  fail = false;
  await api.syncIndex(7);
  assert.equal(api.indexError(7), undefined);
  assert.equal(api.errorMessage({status: 422, api: 'Java', data: {detail: 'birth_date: La fecha no puede ser futura'}}),
    'Fecha de nacimiento: La fecha no puede ser futura');
  assert.equal(api.errorMessage({status: 422, data: {detail: [{loc: ['body', 'disease'], msg: 'Sin encabezados'}]}}),
    'Enfermedad: Sin encabezados');
  assert.ok(fixture.emitted.filter(type => type === 'index-sync-changed').length >= 2);
  await assert.rejects(api.request('http://localhost:8080/patients'), /API Java.*CORS/);
  assert.match(api.errorMessage({status: 500, api: 'Java', data: null}), /API Java tuvo un error interno/);
  assert.equal(api.errorMessage({status: 409, api: 'Java', data: {detail: 'Hay dos informes para este paciente'}}), 'Hay dos informes para este paciente');
  assert.match(api.newId(), /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('api.js: cancelar desde la interfaz no se confunde con agotar el plazo', async () => {
  const {api} = await loadApi((url, {signal}) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => { const error = new Error('aborted'); error.name = 'AbortError'; reject(error); });
  }));
  const controller = new AbortController();
  const pending = api.request('/chat', {method: 'POST', signal: controller.signal}, 60000);
  controller.abort();
  await assert.rejects(pending, {name: 'AbortError', message: 'Petición cancelada.'});
  await assert.rejects(api.request('/chat', {}, 5), /API Python no respondió dentro del plazo/);
});

async function explorerFixture(respond, confirm = async () => true) {
  const fixture = documentFixture();
  const calls = [];
  const confirmations = [];
  const request = async (url, options = {}) => { calls.push({url, options}); return respond(url, options); };
  const module = await loadModule('explorer.js', fixture, request, {'./api.js': {
    confirmAction: async description => { confirmations.push(description); return confirm(description); }}});
  module.initExplorer('python', 'http://localhost:8000', true);
  const root = fixture.node('#explorer-python');
  const operation = (method, path) => {
    const details = root.children.find(child => child.dataset?.method === method && child.dataset?.path === path);
    const form = details.children[1].children[0].children[0];
    const field = name => form.children.find(child => child.name === name);
    return {form, field, run: form.children.find(child => child.type === 'submit'),
      submit: () => form.listeners.get('submit')({preventDefault() {}})};
  };
  return {...fixture, calls, confirmations, operation};
}
const answer = (status, data = {}) => ({ok: status < 400, status, data, text: '', duration: 1});

test('explorador: PUT de paciente pide confirmación y un fallo del índice no bloquea el botón', async () => {
  let accept = false;
  const fixture = await explorerFixture(url => answer(url.endsWith('/sync') ? 503 : 200, {id: 5}), async () => accept);
  const put = fixture.operation('PUT', '/patients/{id}');
  put.field('id').value = '5';
  await put.submit();
  assert.match(fixture.confirmations[0], /Actualizar el paciente 5/);
  assert.equal(fixture.calls.length, 0, 'Sin confirmar no se envía el PUT');
  accept = true;
  await put.submit();
  assert.deepEqual(fixture.calls.map(call => `${call.options.method} ${call.url}`),
    ['PUT http://localhost:8000/patients/5', 'POST /clinical/patients/5/sync']);
  assert.ok(fixture.emitted.includes('patients-changed'));
  assert.equal(put.run.disabled, false);
});

test('explorador: POST /chat confirma, reutiliza X-Execution-ID al reintentar y lo renueva al cambiar el cuerpo, tras un 409 o al guardar', async () => {
  const responses = [answer(503), answer(503), answer(409, {detail: 'UUID usado'}), answer(200, {index_synced: true}), answer(200, {index_synced: true})];
  const fixture = await explorerFixture(() => responses.shift());
  const chat = fixture.operation('POST', '/chat');
  await chat.submit();
  await chat.submit();
  chat.field('body').value = JSON.stringify({patient_id: 2, question: 'Otra consulta'});
  await chat.submit();
  await chat.submit();
  await chat.submit();
  assert.equal(fixture.confirmations.length, 5);
  assert.match(fixture.confirmations[2], /paciente 2/);
  assert.deepEqual(fixture.calls.map(call => call.options.headers['X-Execution-ID']), ['id-1', 'id-1', 'id-2', 'id-3', 'id-4']);
  assert.equal(fixture.dispatched.filter(event => event.type === 'clinical-history-changed').length, 2);
  assert.equal(fixture.dispatched.at(-1).detail.patient_id, 2);
});

test('el doble de api.js sólo ofrece lo que exporta el módulo real', async () => {
  const {api} = await loadApi(async () => response(200, {}));
  assert.deepEqual(Object.keys(apiDouble()).filter(name => !(name in api)), []);
});

test('cada import entre módulos estáticos existe en el módulo importado', () => {
  for (const file of fs.readdirSync(staticDir).filter(name => name.endsWith('.js'))) {
    const source = fs.readFileSync(path.join(staticDir, file), 'utf8');
    for (const [, names, target] of source.matchAll(/^import \{([^}]+)\} from '\.\/([\w-]+\.js)';/gm)) {
      const exported = fs.readFileSync(path.join(staticDir, target), 'utf8');
      for (const name of names.split(',').map(item => item.trim())) {
        assert.match(exported, new RegExp(`export (async )?(function|const) ${name}\\b`), `${file} importa ${name} de ${target}`);
      }
    }
  }
});
