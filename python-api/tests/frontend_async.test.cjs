// Contratos de coordinación con DOM y transporte mínimos; no abre un navegador ni usa APIs reales.
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

function documentFixture() {
  const nodes = new Map();
  const emitted = [];
  function node(key) {
    if (!nodes.has(key)) nodes.set(key, {
      value: '', textContent: '', hidden: false, disabled: false, children: [], dataset: {},
      attributes: new Map(), listeners: new Map(), classList: {add() {}, remove() {}},
      elements: {namedItem: name => node(`${key}:${name}`)},
      addEventListener(type, callback) { this.listeners.set(type, callback); },
      setAttribute(name, value) { this.attributes.set(name, value); },
      getAttribute(name) { return this.attributes.get(name); },
      querySelector: selector => node(`${key} ${selector}`), querySelectorAll: () => [],
      replaceChildren(...children) { this.children = children; this.options = children; },
      append(...children) { this.children.push(...children); },
      focus() {}, scrollIntoView() {}, reset() {}, setCustomValidity() {},
    });
    return nodes.get(key);
  }
  const events = node('document');
  const document = {
    querySelector: node, getElementById: id => node(`#${id}`), querySelectorAll: () => [],
    createElement: tag => node(`created:${tag}:${nodes.size}`),
    addEventListener: (type, callback) => events.addEventListener(type, callback),
    dispatchEvent: event => { emitted.push(event.type); },
  };
  const fire = (selector, type, detail) => node(selector).listeners.get(type)({preventDefault() {}, detail});
  return {document, node, fire, emitted};
}

async function loadModule(name, fixture, request, extra = {}) {
  const context = vm.createContext({document: fixture.document, TextEncoder, CustomEvent, Event, URL, Blob, console});
  const api = {
    request, errorMessage: result => `HTTP ${result.status}`,
    notice(element, message, tone = 'error') { element.textContent = message; element.hidden = !message; element.className = `notice ${tone}`; },
    confirmAction: async () => true, confirmDelete: async () => true,
  };
  const module = new vm.SourceTextModule(fs.readFileSync(path.join(staticDir, name), 'utf8'), {context});
  await module.link(specifier => {
    const exports = specifier === './api.js' ? api : extra[specifier];
    assert.ok(exports, `Dependencia inesperada: ${specifier}`);
    return new vm.SyntheticModule(Object.keys(exports), function () {
      for (const [key, value] of Object.entries(exports)) this.setExport(key, value);
    }, {context});
  });
  await module.evaluate();
  return module.namespace;
}

async function historyFixture(onChanged, failWrite = false) {
  const fixture = documentFixture();
  const calls = [];
  const report = {entries: [], consultations: [], markdown: '# Paciente', revision: 'r1', filename: 'paciente.md'};
  const request = async (url, options = {}) => {
    calls.push({url, method: options.method || 'GET'});
    if (options.method && !url.endsWith('/sync') && failWrite) throw new Error('Escritura rechazada');
    return {ok: true, data: url.endsWith('/diseases') ? [] : report};
  };
  const module = await loadModule('history.js', fixture, request);
  const history = module.initHistory('http://java.test', onChanged);
  await history.open({id: 99, name: 'Paciente sintético', email: 'test@example.com'});
  fixture.node('#disease-form:disease').value = 'Registro sintético';
  return {...fixture, calls};
}

for (const operation of ['registro', 'markdown']) {
  test(`${operation}: espera el refresco antes de sincronizar y de habilitar otra escritura`, async () => {
    const refresh = deferred();
    let refreshStarted = false;
    const fixture = await historyFixture(() => { refreshStarted = true; return refresh.promise; });
    const form = operation === 'registro' ? '#disease-form' : '#history-markdown-form';
    const pending = fixture.fire(form, 'submit');
    await tick();
    assert.equal(refreshStarted, true);
    assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'true');
    assert.equal(fixture.calls.filter(call => call.url.endsWith('/sync')).length, 0);
    await fixture.fire(form, 'submit');
    assert.equal(fixture.calls.filter(call => ['POST', 'PUT'].includes(call.method)).length, 1);
    refresh.resolve();
    await pending;
    assert.equal(fixture.calls.filter(call => call.url.endsWith('/sync')).length, 1);
    assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'false');
  });
}

test('un error al refrescar después de guardar no deja lista otra alta ni borra el error', async () => {
  const fixture = await historyFixture(async () => { throw new Error('Refresco fallido'); });
  await fixture.fire('#disease-form', 'submit');
  assert.match(fixture.node('#history-notice').textContent, /quedó guardado.*Refresco fallido/);
  assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'false');
  await fixture.fire('#disease-form', 'submit');
  assert.equal(fixture.calls.filter(call => call.method === 'POST').length, 1);
});

test('un fallo HTTP de guardado se muestra y libera el formulario', async () => {
  const fixture = await historyFixture(async () => {}, true);
  await fixture.fire('#disease-form', 'submit');
  assert.equal(fixture.node('#history-notice').textContent, 'Escritura rechazada');
  assert.equal(fixture.node('#patient-detail').getAttribute('aria-busy'), 'false');
  assert.equal(fixture.calls.filter(call => call.url.endsWith('/sync')).length, 0);
});

test('el cambio clínico espera al listado de pacientes antes de notificar al selector', async () => {
  const fixture = documentFixture();
  const response = deferred();
  let changed;
  const module = await loadModule('patients.js', fixture, () => response.promise, {
    './history.js': {initHistory(base, callback) { changed = callback; return {}; }},
  });
  module.initPatients('http://java.test');
  const pending = changed();
  assert.deepEqual(fixture.emitted, []);
  response.resolve({ok: true, data: []});
  await pending;
  assert.deepEqual(fixture.emitted, ['clinical-patients-changed']);
});

test('una recarga de pacientes en cola se incluye en la finalización de la primera', async () => {
  const fixture = documentFixture();
  const first = deferred();
  const queued = deferred();
  let count = 0;
  const rows = {ok: true, data: [{id: 1, name: 'Paciente sintético'}]};
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

for (const failCleanup of [false, true]) {
  test(`el verificador conserva el error original${failCleanup ? ' y el de limpieza' : ''}`, async () => {
    const file = path.resolve(__dirname, '../../scripts/verificar_consultas_ui_real.cjs');
    let patient;
    let saved;
    let failure;
    const processStub = {env: {}, exitCode: 0};
    const fetchStub = async (url, options) => {
      if (options.method === 'POST' && url.endsWith('/patients')) patient = {id: 99, ...JSON.parse(options.body)};
      if (options.method === 'DELETE') {
        if (failCleanup) throw new Error('Fallo de limpieza');
        patient = null;
      }
      const status = options.method === 'DELETE' ? 204 : options.method === 'POST' && url.endsWith('/patients') ? 201 : url.endsWith('/patients/99') && !patient ? 404 : 200;
      return {status, text: async () => JSON.stringify(url.endsWith('/patients') && options.method !== 'POST' ? [] : patient)};
    };
    const context = {__dirname: path.dirname(file), process: processStub, fetch: fetchStub, AbortSignal,
      console: {log() {}, error(error) { failure = error; }},
      require(name) {
        if (name === 'playwright') return {chromium: {async launch() { throw new Error('Fallo original'); }}};
        if (name === 'node:fs') return {existsSync: () => false, mkdirSync() {}, writeFileSync(destination, body) { saved = JSON.parse(body); }};
        return require(name);
      },
    };
    await vm.runInNewContext(fs.readFileSync(file, 'utf8'), context);
    assert.equal(processStub.exitCode, 1);
    assert.equal(saved.error, 'Fallo original');
    assert.equal(saved.result, 'failed');
    assert.equal(failure.name, 'AggregateError');
    assert.equal(failure.errors[0].message, 'Fallo original');
    assert.equal(failure.errors.length, failCleanup ? 2 : 1);
    if (failCleanup) assert.equal(saved.cleanup_error, 'Fallo de limpieza');
    else assert.equal(saved.cleanup.patient_deleted, true);
  });
}
