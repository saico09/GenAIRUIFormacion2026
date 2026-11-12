// Edge + Playwright: CRUD real; errores y respuestas de chat simulados en el navegador.
// CHAT_URL, JAVA_URL y EVIDENCE_DIR permiten verificar también las copias semanales.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const chatUrl = process.env.CHAT_URL || 'http://127.0.0.1:8000/';
const pythonUrl = new URL(chatUrl).origin;
const javaUrl = (process.env.JAVA_URL || `${new URL(chatUrl).protocol}//${new URL(chatUrl).hostname}:8080`).replace(/\/$/, '');
const output = path.resolve(process.env.EVIDENCE_DIR || path.join(__dirname, '../evidencias/ui-2026-11-07'));
const marker = `Portal QA ${crypto.randomUUID()}`;
const original = { name: marker, birth_date: '1995-05-05', email: 'portal-qa@example.com' };
const edited = { name: `${marker} editado`, birth_date: '1996-06-06', email: 'portal-editado@example.com' };
const report = { started_at: new Date().toISOString(), chat_url: chatUrl, java_url: javaUrl, checks: [], mocks: [] };
const owned = new Map();
const pendingResponses = [];
let before;

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort((left, right) => {
    if (left === right) return 0;
    return left < right ? -1 : 1;
  }).map(key => [key, canonical(value[key])]));
  return value;
}
function hash(rows) {
  return crypto.createHash('sha256').update(JSON.stringify(canonical([...rows].sort((a, b) => a.id - b.id)))).digest('hex');
}
async function jsonRequest(base, endpoint, options = {}) {
  const response = await fetch(base + endpoint, { ...options, signal: AbortSignal.timeout(endpoint.endsWith('/sync') ? 180000 : 15000) });
  const text = await response.text();
  return { status: response.status, data: text ? JSON.parse(text) : null };
}
async function snapshots() {
  const result = {};
  for (const [name, base] of [['python', pythonUrl], ['java', javaUrl]]) {
    const response = await jsonRequest(base, '/patients');
    assert.equal(response.status, 200, `Snapshot ${name}`);
    result[name] = response.data;
  }
  return result;
}
function record(name, extra = {}) {
  report.checks.push({ name, passed: true, ...extra });
  console.log(`PASS ${name}`);
}
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}
async function waitSignal(signal, label) {
  let timer;
  try {
    await Promise.race([signal.promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`No se inicio la peticion: ${label}`)), 15000);
    })]);
  } finally { clearTimeout(timer); }
}
async function main() {
  fs.mkdirSync(output, { recursive: true });
  before = await snapshots();
  report.before = Object.fromEntries(Object.entries(before).map(([name, rows]) => [name, { count: rows.length, sha256: hash(rows) }]));
  const browser = await chromium.launch({ executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  let page;
  try {
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(15000);
    const requests = [];
    page.on('request', request => requests.push({ method: request.method(), url: request.url() }));
    page.on('response', response => {
      const request = response.request();
      if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/patients' || response.status() !== 201) return;
      const task = (async () => {
        const submitted = request.postDataJSON();
        if (submitted?.name !== original.name) return;
        const patient = await response.json();
        const base = new URL(request.url()).origin;
        if ([pythonUrl, javaUrl].includes(base) && Number.isInteger(patient.id)) owned.set(`${base}/${patient.id}`, { base, id: patient.id });
      })();
      pendingResponses.push(task);
    });
    const count = (method, base, endpoint) => requests.filter(item => item.method === method && item.url === base + endpoint).length;
    const navigate = async name => {
      await page.locator(`[data-nav="${name}"]`).click();
      await page.locator(`#view-${name}`).waitFor({ state: 'visible' });
      assert.equal(await page.locator('[data-view]:visible').count(), 1);
    };
    const endpoint = async (api, method, route) => {
      const element = page.locator(`#explorer-${api} details[data-method="${method}"][data-path="${route}"]`);
      if (!await element.evaluate(node => node.open)) await element.locator('summary').click();
      return element;
    };
    const waitIdle = async element => {
      await element.locator('.endpoint-response[aria-busy="false"]').waitFor();
      assert.equal(await element.locator('button[type="submit"]').isEnabled(), true);
    };
    const runEndpoint = async (element, expectedStatus) => {
      await element.locator('button[type="submit"]').click();
      await page.waitForFunction(({ method, route, api, status }) => {
        const node = document.querySelector(`#explorer-${api} details[data-method="${method}"][data-path="${route}"]`);
        return node.querySelector('.endpoint-response').getAttribute('aria-busy') === 'false'
          && node.querySelector('.http-status').textContent.startsWith(`${status} ·`);
      }, { method: await element.getAttribute('data-method'), route: await element.getAttribute('data-path'), api: (await element.evaluate(node => node.closest('[data-api]').dataset.api)), status: expectedStatus });
      await waitIdle(element);
    };

    await page.goto(chatUrl);
    await page.locator('#explorer-java details').first().waitFor({ state: 'attached' });
    await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    assert.deepEqual(await page.locator('#patient option').evaluateAll(nodes => nodes.map(node => ({id: Number(node.value), name: node.textContent}))),
      before.java.map(row => ({id: row.id, name: row.name})), 'Selector clínico leído de Java');
    assert.equal(await page.locator('#config-error').isVisible(), false);
    assert.deepEqual(await page.locator('[data-nav]').evaluateAll(nodes => nodes.map(node => node.dataset.nav)), ['consultas', 'pacientes', 'api-python', 'api-java']);
    for (const name of ['consultas', 'pacientes', 'api-python', 'api-java']) await navigate(name);
    assert.equal((await page.locator('#explorer-java .api-base code').textContent()).replace(/\/$/, ''), javaUrl);
    await navigate('pacientes');
    await page.locator('.skip-link').evaluate(link => link.click());
    assert.equal(new URL(page.url()).hash, '#pacientes', 'Saltar al contenido conserva la seccion actual');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'main');
    assert.equal(await page.locator('#view-pacientes').isVisible(), true);
    record('Cuatro secciones, orden de navegacion y salto al contenido sin cambiar seccion');

    await navigate('pacientes');
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled);
    await page.locator('#new-patient').click();
    await page.locator('#patient-name').fill(original.name);
    await page.locator('#patient-birth').fill(original.birth_date);
    await page.locator('#patient-email').fill(original.email);
    const releaseCreate = deferred();
    const createStarted = deferred();
    const createUrl = javaUrl + '/patients';
    const delayCreate = async route => {
      if (route.request().method() !== 'POST') return route.continue();
      createStarted.resolve();
      await releaseCreate.promise;
      await route.continue();
    };
    await page.route(createUrl, delayCreate);
    const createBefore = count('POST', javaUrl, '/patients');
    const createdResponse = page.waitForResponse(response => response.url() === createUrl && response.request().method() === 'POST');
    await page.locator('#save-patient').click();
    await waitSignal(createStarted, 'POST Java');
    try {
      assert.equal(await page.locator('#save-patient').isDisabled(), true);
      for (const id of ['patient-name', 'patient-birth', 'patient-email']) assert.equal(await page.locator(`#${id}`).isDisabled(), true);
      await page.locator('#patient-form').evaluate(form => { form.requestSubmit(); form.requestSubmit(); });
      await page.waitForTimeout(150);
      assert.equal(count('POST', javaUrl, '/patients') - createBefore, 1);
    } finally { releaseCreate.resolve(); }
    const created = await createdResponse;
    assert.equal(created.status(), 201);
    const patient = await created.json();
    owned.set(`${javaUrl}/${patient.id}`, { base: javaUrl, id: patient.id });
    await page.unroute(createUrl, delayCreate);
    await page.locator('#patient-dialog').waitFor({ state: 'hidden' });
    await page.locator('#patient-search').fill(marker);
    const row = page.locator(`#patients-body tr[data-patient-id="${patient.id}"]`);
    await row.waitFor();
    await row.locator('[data-action="edit"]').click();
    await page.locator('#patient-dialog').waitFor();
    assert.equal(await page.locator('#patient-name').inputValue(), original.name);
    await page.locator('#patient-name').fill(edited.name);
    await page.locator('#patient-birth').fill(edited.birth_date);
    await page.locator('#patient-email').fill(edited.email);
    const editResponse = page.waitForResponse(response => response.url() === `${javaUrl}/patients/${patient.id}` && response.request().method() === 'PUT');
    await page.locator('#save-patient').click();
    assert.equal((await editResponse).status(), 200);
    await page.locator('#patient-dialog').waitFor({ state: 'hidden' });
    await page.waitForFunction(({ id, name }) => document.querySelector(`#patients-body tr[data-patient-id="${id}"]`)?.textContent.includes(name), { id: patient.id, name: edited.name });
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled, null, {timeout: 200000});
    assert.equal(await page.locator('#patient-index-notices').isVisible(), false, 'Renombrado sincronizado');
    await page.screenshot({ path: path.join(output, 'portal-paciente-temporal.png'), fullPage: true });
    const deleteBefore = count('DELETE', javaUrl, `/patients/${patient.id}`);
    await row.locator('[data-action="delete"]').click();
    await page.locator('#confirm-dialog').waitFor();
    await page.locator('#confirm-cancel').click();
    await page.locator('#confirm-dialog').waitFor({ state: 'hidden' });
    await page.waitForTimeout(150);
    assert.equal(count('DELETE', javaUrl, `/patients/${patient.id}`), deleteBefore);
    assert.equal((await jsonRequest(javaUrl, `/patients/${patient.id}`)).status, 200);
    await row.locator('[data-action="delete"]').click();
    const deletedResponse = page.waitForResponse(response => response.url() === `${javaUrl}/patients/${patient.id}` && response.request().method() === 'DELETE');
    await page.locator('#confirm-accept').click();
    const deleted = await deletedResponse;
    assert.equal(deleted.status(), 204);
    assert.equal(await deleted.text(), '');
    await row.waitFor({ state: 'detached' });
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled, null, {timeout: 200000});
    assert.equal(await page.locator('#patient-index-notices').isVisible(), false, 'Índice eliminado junto al temporal');
    owned.delete(`${javaUrl}/${patient.id}`);
    record('CRUD Java real en modal, cancelar DELETE y submit duplicado bloqueado', { temporary_id: patient.id });

    for (const [api, base] of [['python', pythonUrl], ['java', javaUrl]]) {
      await navigate(`api-${api}`);
      const health = await endpoint(api, 'GET', '/health');
      await runEndpoint(health, 200);
      assert.equal(JSON.parse(await health.locator('.response-body').textContent()).status, 'ok');
      const missingId = Math.max(999999, ...before[api].map(item => item.id + 1));
      assert.equal(before[api].some(item => item.id === missingId), false);
      const get = await endpoint(api, 'GET', '/patients/{id}');
      await get.locator('input[name="id"]').fill(String(missingId));
      await runEndpoint(get, 404);
      const post = await endpoint(api, 'POST', '/patients');
      await post.locator('textarea').fill(JSON.stringify({ name: '', birth_date: '1990-01-01', email: 'invalid@example.com' }));
      await runEndpoint(post, 422);
      const postsBefore = count('POST', base, '/patients');
      await post.locator('textarea').fill('{ JSON invalido');
      await post.locator('button[type="submit"]').click();
      await post.locator('.notice[role="alert"]').waitFor();
      assert.match(await post.locator('.notice').textContent(), /JSON v[aá]lido/);
      assert.equal(await post.locator('.http-status').isVisible(), false, 'El JSON invalido no conserva el estado HTTP anterior');
      assert.equal(await post.locator('.response-meta').textContent(), '');
      assert.match(await post.locator('.response-body').textContent(), /Ejecuta esta petici[oó]n/);
      await page.waitForTimeout(150);
      assert.equal(count('POST', base, '/patients'), postsBefore);
      const remove = await endpoint(api, 'DELETE', '/patients/{id}');
      await remove.locator('input[name="id"]').fill(String(missingId));
      const deletesBefore = count('DELETE', base, `/patients/${missingId}`);
      await remove.locator('button[type="submit"]').click();
      await page.locator('#confirm-dialog').waitFor();
      await page.locator('#confirm-cancel').click();
      await page.locator('#confirm-dialog').waitFor({ state: 'hidden' });
      await page.waitForTimeout(150);
      assert.equal(count('DELETE', base, `/patients/${missingId}`), deletesBefore);
      record(`Explorador ${api}:200/404/422, JSON invalido y cancelacion sin peticion`);

      const healthUrl = base + '/health';
      const abort = route => route.abort('connectionfailed');
      await page.route(healthUrl, abort);
      await health.locator('button[type="submit"]').click();
      await health.locator('.http-status.network-error').waitFor();
      await waitIdle(health);
      assert.match(await health.locator('.response-body').textContent(), /No se pudo conectar/);
      await page.unroute(healthUrl, abort);
      const serverError = route => route.fulfill({ status: 500, contentType: 'application/json',
        headers: { 'access-control-allow-origin': pythonUrl }, body: JSON.stringify({ detail: 'Fallo simulado de prueba' }) });
      await page.route(healthUrl, serverError);
      await runEndpoint(health, 500);
      assert.match(await health.locator('.response-body').textContent(), /Fallo simulado/);
      await page.unroute(healthUrl, serverError);
      const releaseGet = deferred();
      const getStarted = deferred();
      const delayGet = async route => { getStarted.resolve(); await releaseGet.promise; await route.continue(); };
      await page.route(healthUrl, delayGet);
      const getsBefore = count('GET', base, '/health');
      await health.locator('button[type="submit"]').click();
      await waitSignal(getStarted, `GET ${api}`);
      try {
        assert.equal(await health.locator('button[type="submit"]').isDisabled(), true);
        assert.equal(await health.locator('.endpoint-response').getAttribute('aria-busy'), 'true');
        await health.locator('form').evaluate(form => { form.requestSubmit(); form.requestSubmit(); });
        await page.waitForTimeout(150);
        assert.equal(count('GET', base, '/health') - getsBefore, 1);
      } finally { releaseGet.resolve(); }
      await page.waitForFunction(api => document.querySelector(`#explorer-${api} details[data-path="/health"] .endpoint-response`).getAttribute('aria-busy') === 'false', api);
      assert.match(await health.locator('.http-status').textContent(), /^200/);
      await page.unroute(healthUrl, delayGet);
      report.mocks.push({ api, cases: ['network_failure', 'http_500'], real_services_stopped: false });
      record(`Explorador ${api}: errores simulados, carga, submit unico y recuperacion`);
      if (api === 'java' && await page.locator('#explorer-java details[data-path="/actuator/health"]').count()) {
        const actuatorHealth = await endpoint(api, 'GET', '/actuator/health');
        await runEndpoint(actuatorHealth, 200);
        assert.equal(JSON.parse(await actuatorHealth.locator('.response-body').textContent()).status, 'UP');
        const actuatorMetrics = await endpoint(api, 'GET', '/actuator/prometheus');
        await runEndpoint(actuatorMetrics, 200);
        assert.match(await actuatorMetrics.locator('.response-body').textContent(), /# (HELP|TYPE) /);
        record('Actuator Java: health y Prometheus legibles desde el navegador con CORS');
      }
    }

    await navigate('consultas');
    const releaseChat = deferred();
    const chatStarted = deferred();
    const clinicalPatient = before.java.find(row => row.name === 'Ana Demo');
    assert.ok(clinicalPatient, 'Ana Demo debe existir en Java');
    const history = await jsonRequest(javaUrl, `/patients/${clinicalPatient.id}/history`);
    assert.equal(history.status, 200);
    const mockSources = history.data.entries.flatMap(entry => Object.entries({Enfermedad: 'disease', Tratamiento: 'treatment', Medicamento: 'medication'})
      .map(([section, field]) => ({patient_id: clinicalPatient.id, record_id: entry.id, source: history.data.filename, section, text: entry[field] || 'No registrado.'}))).slice(0, 3);
    assert.equal(mockSources.length, 3, 'El fixture de Ana tiene al menos un registro');
    const question = `¿Qué enfermedad tiene ${clinicalPatient.name}?`;
    const mockChat = async route => {
      const data = route.request().postDataJSON();
      assert.deepEqual(data, { patient_id: clinicalPatient.id, question });
      chatStarted.resolve(); await releaseChat.promise;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        direct_answer: 'Respuesta simulada para comprobar la interfaz.',
        rag_answer: `${mockSources[0].text} [${mockSources[0].source}/${mockSources[0].record_id}/${mockSources[0].section}]`,
        sources: mockSources,
      }) });
    };
    await page.route(pythonUrl + '/chat', mockChat);
    await page.locator('#patient').selectOption(String(clinicalPatient.id));
    await page.locator('#question').fill(question);
    const chatBefore = count('POST', pythonUrl, '/chat');
    await page.locator('#submit').click();
    await waitSignal(chatStarted, 'POST chat simulado');
    try {
      for (const id of ['submit', 'patient', 'question', 'reload-patients']) assert.equal(await page.locator(`#${id}`).isDisabled(), true);
      assert.equal(await page.locator('#loading').isVisible(), true);
      await page.locator('#chat-form').evaluate(form => { form.requestSubmit(); form.requestSubmit(); });
      await page.waitForTimeout(150);
      assert.equal(count('POST', pythonUrl, '/chat') - chatBefore, 1);
    } finally { releaseChat.resolve(); }
    await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    assert.match(await page.locator('#direct').textContent(), /simulada/);
    assert.ok((await page.locator('#rag').textContent()).includes(mockSources[0].text));
    assert.deepEqual(await page.locator('#sources summary').allTextContents(), mockSources.map(source => `${source.source} / ${source.section} · Registro ${source.record_id}`));
    assert.deepEqual(await page.locator('#sources .source-fragment').allTextContents(), mockSources.map(source => source.text));
    assert.match(await page.locator('#used-question').textContent(), /¿Qué enfermedad tiene Ana Demo\?/);
    assert.equal(await page.locator('#question').inputValue(), question);
    await page.unroute(pythonUrl + '/chat', mockChat);
    report.mocks.push({ api: 'chat', cases: ['comparison_sources_and_loading'], real_inference: false });
    record('Comparativa y fuentes RAG con respuesta simulada; carga y submit unico');

    await page.setViewportSize({ width: 390, height: 844 });
    for (const name of ['consultas', 'pacientes', 'api-python', 'api-java']) {
      await navigate(name);
      const dimensions = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
      assert.ok(dimensions.document <= dimensions.viewport + 1 && dimensions.body <= dimensions.viewport + 1, `Overflow horizontal en ${name}: ${JSON.stringify(dimensions)}`);
      record(`Movil390 ${name} sin overflow del documento`, dimensions);
    }
    await page.screenshot({ path: path.join(output, 'portal-movil-explorador.png'), fullPage: true });
    report.result = 'passed';
  } catch (error) {
    report.result = 'failed';
    report.error = { type: error.name, message: String(error.message).slice(0, 1500) };
    throw error;
  } finally {
    if (page) await page.unrouteAll({ behavior: 'ignoreErrors' });
    await Promise.allSettled(pendingResponses);
    // Solo IDs creados por esta ejecución y aún reconocibles como sus datos ficticios.
    for (const { base, id } of owned.values()) {
      const current = await jsonRequest(base, `/patients/${id}`);
      if (current.status === 404) {
        if (base === javaUrl) {
          const sync = await jsonRequest(pythonUrl, `/clinical/patients/${id}/sync`, {method: 'POST'});
          assert.equal(sync.status, 200); assert.equal(sync.data.status, 'removed');
        }
        continue;
      }
      assert.ok(current.status === 200 && [original.name, edited.name].includes(current.data.name), 'No se elimina un registro ajeno a esta prueba');
      assert.equal((await jsonRequest(base, `/patients/${id}`, { method: 'DELETE' })).status, 204);
      if (base === javaUrl) {
        const sync = await jsonRequest(pythonUrl, `/clinical/patients/${id}/sync`, {method: 'POST'});
        assert.equal(sync.status, 200); assert.equal(sync.data.status, 'removed');
      }
    }
    const after = await snapshots();
    report.after = Object.fromEntries(Object.entries(after).map(([name, rows]) => [name, { count: rows.length, sha256: hash(rows) }]));
    report.data_preserved = Object.keys(before).every(name => hash(before[name]) === hash(after[name]));
    report.finished_at = new Date().toISOString();
    if (!report.data_preserved) report.result = 'failed';
    fs.writeFileSync(path.join(output, 'portal-resultados.json'), JSON.stringify(report, null, 2) + '\n', 'utf8');
    await browser.close();
    assert.equal(report.data_preserved, true, 'Los hashes de los pacientes cambiaron');
  }
}

main().catch(error => { console.error(`${error.name}: ${error.message}`); process.exitCode = 1; });
