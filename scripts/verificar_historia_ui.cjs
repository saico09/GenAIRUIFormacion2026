// Prueba aislada del frontend: HTTP simulado, sin acceder a pacientes ni servicios reales.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {chromium} = require('playwright');

const staticRoot = path.resolve(__dirname, '../python-api/app/static');
const output = path.resolve(process.env.EVIDENCE_DIR || path.join(__dirname, '../evidencias/clinica-2026-11-07/ui-aislada'));
const report = {mode: 'isolated_browser_mock', real_services_used: false, checks: [], started_at: new Date().toISOString()};
const check = name => { report.checks.push({name, passed: true}); console.log(`PASS ${name}`); };
const json = (route, status, body) => route.fulfill({status, contentType: 'application/json', headers: {'access-control-allow-origin': '*'}, body: JSON.stringify(body)});
const patient = {id: 42, name: 'Paciente UI ficticio', birth_date: '1990-05-15', email: 'ui@example.com'};
const recordId = '1d1783d9-8800-4972-ad7f-a3c6042575b0';
let history = {patient_id: 42, filename: 'paciente-42-paciente-ui-ficticio.md', revision: 'a'.repeat(64),
  markdown: '# Paciente UI ficticio\n\n<!-- Texto literal <img src=x onerror=alert(1)> -->\n',
  entries: [{id: recordId, disease: 'Enfermedad ficticia Alfa', treatment: '', medication: ''}]};
let mode = 'normal';
let failSync = false;
let mutationDelay = 0;
let patientDeleted = false;
let explorerPatientDeleted = false;
const requests = [];
const server = http.createServer((req, res) => {
  const file = req.url === '/' ? 'index.html' : req.url.replace(/^\/static\//, '');
  if (!/^[a-z.-]+$/.test(file)) { res.writeHead(404); res.end(); return; }
  const target = path.join(staticRoot, file);
  if (!fs.existsSync(target)) { res.writeHead(404); res.end(); return; }
  res.setHeader('content-type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
  res.end(fs.readFileSync(target));
});

async function main() {
  fs.mkdirSync(output, {recursive: true});
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const javaBase = 'http://127.0.0.1:29980';
  const browser = await chromium.launch({executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const count = (method, suffix) => requests.filter(item => item.method === method && item.path === suffix).length;
  await page.route('**/*', async route => {
    const req = route.request(); const url = new URL(req.url()); const method = req.method();
    if (url.origin === base && (url.pathname === '/' || url.pathname.startsWith('/static/'))) return route.continue();
    const body = req.postData() ? req.postDataJSON() : null;
    requests.push({origin: url.origin, method, path: url.pathname, body});
    if (url.pathname === '/ui-config') return json(route, 200, {java_api_port: 29980, metrics_enabled: false});
    if (url.pathname === '/patients/43' && method === 'PUT') return json(route, 200, {id: 43, ...body});
    if (url.pathname === '/patients/43' && method === 'DELETE') { explorerPatientDeleted = true; return route.fulfill({status: 204}); }
    if (url.pathname === '/clinical/patients/43/sync') return json(route, failSync ? 503 : 200,
      failSync ? {detail: 'Índice no disponible (simulado)'} : {patient_id: 43, status: explorerPatientDeleted ? 'removed' : 'synced'});
    if (url.origin === javaBase && url.pathname === '/patients' && method === 'GET') return json(route, 200, patientDeleted ? [] : [patient]);
    if (url.origin === javaBase && url.pathname === '/patients/42' && method === 'GET') return json(route, 200, patient);
    if (url.origin === javaBase && url.pathname === '/patients/42' && method === 'PUT') {
      Object.assign(patient, body); return json(route, 200, patient);
    }
    if (url.origin === javaBase && url.pathname === '/patients/42' && method === 'DELETE') {
      patientDeleted = true; return route.fulfill({status: 204});
    }
    if (url.pathname === '/patients/42/history.md') return route.fulfill({status: 200, contentType: 'text/markdown', body: history.markdown});
    if (url.pathname === '/patients/42/history' && method === 'GET') return json(route, 200, history);
    if (url.pathname === '/patients/42/history' && method === 'PUT') {
      assert.equal(body.confirmed, true);
      if (mode === 'conflict') return json(route, 409, {detail: 'Revisión desactualizada'});
      if (mode === 'invalid') return json(route, 422, {detail: 'Formato Markdown inválido'});
      assert.equal(body.revision, history.revision);
      history = {...history, markdown: body.markdown, revision: 'c'.repeat(64)};
      return json(route, 200, history);
    }
    if (url.pathname === '/patients/42/history/entries') {
      assert.equal(method, 'POST'); assert.equal(body.confirmed, true);
      if (mode === 'invalid') return json(route, 422, {detail: 'Revisión inválida (simulado)'});
      assert.equal(body.revision, history.revision);
      assert.equal(Object.hasOwn(body, 'id'), false, 'Java asigna el UUID');
      if (mutationDelay) await new Promise(resolve => setTimeout(resolve, mutationDelay));
      const entry = {id: `2d1783d9-8800-4972-ad7f-a3c6042575b${history.entries.length}`, disease: body.disease, treatment: body.treatment, medication: body.medication};
      history = {...history, revision: 'd'.repeat(64), entries: [...history.entries, entry], markdown: history.markdown + '\n' + entry.disease};
      return json(route, 200, history);
    }
    if (url.pathname === '/clinical/patients/42/sync') return json(route, failSync ? 503 : 200, failSync ? {detail: 'Qdrant no disponible (simulado)'} : {patient_id: 42, status: patientDeleted ? 'removed' : 'synced'});
    if (url.pathname === '/clinical/proposals') {
      assert.equal(body.patient_id, 42);
      if (mode === 'proposal-error') return json(route, 503, {detail: 'LLM no disponible (simulado)'});
      if (mode === 'empty') return json(route, 200, {patient_id: 42, entries: [], message: 'No hay hechos explícitos para registrar.'});
      return json(route, 200, {patient_id: 42, message: 'Revisa la propuesta.', entries: [
        {disease: 'Enfermedad ficticia Beta', treatment: '', medication: '', evidence: {disease: 'Consta enfermedad ficticia Beta.', treatment: '', medication: ''}},
        {disease: '', treatment: 'Tratamiento ficticio Delta', medication: '', evidence: {disease: '', treatment: 'Se indica tratamiento ficticio Delta.', medication: ''}},
      ]});
    }
    if (url.pathname === '/chat') {
      assert.equal(body.patient_id, 42);
      return json(route, 200, {direct_answer: 'No tengo contexto.', rag_answer: 'Consta Enfermedad ficticia Alfa.', sources: [{patient_id: 42, record_id: recordId, source: history.filename, section: 'Enfermedad', text: 'Enfermedad ficticia Alfa <script>literal</script>'}]});
    }
    throw new Error(`Petición no prevista: ${method} ${req.url()}`);
  });
  const idle = () => page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false');
  const confirm = async accept => { await page.locator('#confirm-dialog').waitFor(); await page.locator(accept ? '#confirm-accept' : '#confirm-cancel').click(); await page.locator('#confirm-dialog').waitFor({state: 'hidden'}); };
  try {
    await page.goto(base);
    await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    assert.equal(await page.locator('#patient').inputValue(), '42');
    assert.equal(count('GET', '/patients'), 1);
    assert.equal(requests.find(item => item.path === '/patients').origin, javaBase);
    await page.locator('[data-nav="pacientes"]').click();
    await page.getByRole('button', {name: 'Abrir historia de Paciente UI ficticio'}).click();
    await idle();
    assert.equal(await page.locator('#history-table tbody tr').count(), 1);
    assert.match(await page.locator('#history-table').textContent(), new RegExp(recordId));
    assert.deepEqual(await page.locator('#history-body td').allTextContents(), [recordId, 'Enfermedad ficticia Alfa', '—', '—']);
    check('Selector y detalle comparten identidad Java; tabla con UUID y vacíos sin inventar');

    await page.locator('#history-markdown summary').click();
    assert.match(await page.locator('#history-markdown-text').textContent(), /<img/);
    assert.equal(await page.locator('#history-markdown-text img').count(), 0);
    const downloaded = page.waitForEvent('download'); await page.locator('#download-history').click();
    assert.equal((await downloaded).suggestedFilename(), history.filename); await idle();
    await page.locator('#edit-history').click();
    const editedMarkdown = history.markdown + '\nEdición manual sintética.';
    await page.locator('#history-markdown-input').fill(editedMarkdown);
    await page.locator('#save-markdown').click(); await confirm(false); await idle();
    assert.equal(count('PUT', '/patients/42/history'), 0);
    mode = 'invalid'; await page.locator('#save-markdown').click(); await confirm(true); await idle();
    assert.equal(await page.locator('#history-markdown-input').inputValue(), editedMarkdown);
    assert.match(await page.locator('#history-notice').textContent(), /inválido/);
    mode = 'conflict'; await page.locator('#save-markdown').click(); await confirm(true); await idle();
    assert.equal(await page.locator('#save-markdown').isDisabled(), true);
    assert.match(await page.locator('#history-notice').textContent(), /Otra operación/);
    history.revision = 'b'.repeat(64); mode = 'normal';
    await page.locator('#refresh-history').click(); await idle();
    assert.equal(await page.locator('#history-markdown-input').inputValue(), editedMarkdown);
    assert.equal(await page.locator('#save-markdown').isEnabled(), true);
    failSync = true; await page.locator('#save-markdown').click(); await confirm(true); await idle();
    assert.equal(await page.locator('#history-markdown-form').isVisible(), false);
    assert.match(await page.locator('#history-sync-message').textContent(), /guardada en Java/);
    assert.equal(await page.locator('#history-notice').getAttribute('class'), 'notice warning');
    assert.equal(count('PUT', '/patients/42/history'), 3);
    failSync = false; await page.locator('#retry-history-sync').click(); await idle();
    assert.equal(await page.locator('#history-sync').isVisible(), false);
    assert.equal(count('PUT', '/patients/42/history'), 3, 'Reintentar sync no vuelve a guardar');
    check('Markdown literal/descarga; cancelación,422,409 con borrador conservado y sincronización reintentable');

    await page.locator('#new-consultation').click();
    await page.locator('#consultation-note').fill('Consta enfermedad ficticia Beta. Se indica tratamiento ficticio Delta.');
    await page.locator('#prepare-proposal').click(); await idle();
    assert.equal(await page.locator('.entry-draft').count(), 2);
    assert.match(await page.locator('.field-evidence').first().textContent(), /Consta enfermedad ficticia Beta/);
    assert.equal(count('POST', '/patients/42/history/entries'), 0);
    const first = page.locator('.entry-draft').first();
    await first.locator('textarea[name="disease"]').fill('Enfermedad ficticia Beta revisada');
    await first.locator('[data-save-entry]').click(); await confirm(false); await idle();
    assert.equal(count('POST', '/patients/42/history/entries'), 0);
    mutationDelay = 250;
    await first.locator('[data-save-entry]').click(); await confirm(true);
    await first.evaluate(form => { form.requestSubmit(); form.requestSubmit(); });
    await idle(); mutationDelay = 0;
    assert.equal(count('POST', '/patients/42/history/entries'), 1);
    assert.equal(await page.locator('.entry-draft').count(), 1);
    assert.equal(history.entries.at(-1).disease, 'Enfermedad ficticia Beta revisada');
    assert.equal(history.entries.at(-1).medication, '');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: path.join(output, 'detalle-propuesta.png'), fullPage: true});
    check('IA prepara varias propuestas editables con evidencia; guardar requiere confirmación y no se duplica');

    await page.locator('.entry-draft button[type="button"]').click();
    mode = 'empty'; await page.locator('#prepare-proposal').click(); await idle();
    assert.equal(await page.locator('.entry-draft').count(), 0);
    assert.match(await page.locator('#proposal-notice').textContent(), /No hay hechos/);
    await page.locator('#manual-entry').click();
    await page.locator('.entry-draft [data-save-entry]').click();
    assert.match(await page.locator('.entry-draft [role="alert"]').textContent(), /al menos/);
    assert.equal(count('POST', '/patients/42/history/entries'), 1);
    await page.locator('.entry-draft button[type="button"]').click();
    mode = 'proposal-error'; await page.locator('#prepare-proposal').click(); await idle();
    assert.match(await page.locator('#proposal-notice').textContent(), /registro manual/);
    assert.equal(await page.locator('#manual-entry').isEnabled(), true);
    await page.locator('#manual-entry').click();
    await page.locator('.entry-draft textarea[name="medication"]').fill('Medicamento ficticio Epsilon');
    await page.locator('.entry-draft [data-save-entry]').click(); await confirm(true); await idle();
    assert.equal(count('POST', '/patients/42/history/entries'), 2);
    assert.equal(history.entries.at(-1).medication, 'Medicamento ficticio Epsilon');
    assert.equal(history.entries.at(-1).disease, '');
    check('Sin propuesta o con error IA, registro manual confirmado funciona; no guarda campos vacíos');

    mode = 'normal'; await page.locator('[data-nav="consultas"]').click();
    const question = '¿Qué enfermedad tiene este paciente?'; await page.locator('#question').fill(question);
    await page.locator('#submit').click(); await page.locator('#prepare-chat-record').waitFor();
    assert.equal(count('POST', '/patients/42/history/entries'), 2, 'Preguntar no archiva respuestas');
    await page.locator('#sources summary').click();
    assert.match(await page.locator('#sources').textContent(), new RegExp(recordId));
    assert.match(await page.locator('.source-fragment').textContent(), /<script>literal/);
    assert.equal(await page.locator('.source-fragment script').count(), 0);
    const proposalsBefore = count('POST', '/clinical/proposals');
    await page.locator('#prepare-chat-record').click(); await page.locator('#consultation-editor').waitFor(); await idle();
    assert.equal(await page.locator('#consultation-note').inputValue(), question);
    assert.equal(count('POST', '/clinical/proposals'), proposalsBefore);
    assert.equal(count('POST', '/patients/42/history/entries'), 2);
    check('Fuentes muestran texto y record_id; Preparar registro solo lleva la pregunta como borrador');

    await page.setViewportSize({width: 390, height: 844});
    const width = await page.evaluate(() => ({viewport: innerWidth, document: document.documentElement.scrollWidth}));
    assert.ok(width.document <= width.viewport + 1, JSON.stringify(width));
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: path.join(output, 'detalle-movil.png'), fullPage: true});
    await page.locator('#history-back').click();
    await page.locator('[data-action="delete"]').click();
    assert.match(await page.locator('#confirm-description').textContent(), /historia clínica asociada/); await confirm(false);
    assert.equal(count('DELETE', '/patients/42'), 0);
    assert.deepEqual(errors, []);
    check('Detalle móvil sin desborde; eliminación advierte historia asociada y cancelar no elimina');
    failSync = true;
    await page.locator('[data-action="edit"]').click();
    await page.locator('#patient-name').fill('Paciente UI renombrado');
    await page.locator('#save-patient').click();
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled);
    assert.match(await page.locator('#patient-index-notices').textContent(), /actualizado en Java/);
    const updates = count('PUT', '/patients/42');
    failSync = false;
    await page.locator('[data-sync-patient="42"]').click();
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled);
    assert.equal(await page.locator('#patient-index-notices').isVisible(), false);
    assert.equal(count('PUT', '/patients/42'), updates);
    failSync = true;
    await page.locator('[data-action="delete"]').click(); await confirm(true);
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled);
    assert.equal(count('DELETE', '/patients/42'), 1);
    assert.match(await page.locator('#patient-index-notices').textContent(), /eliminado en Java/);
    failSync = false;
    await page.locator('[data-sync-patient="42"]').click();
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled);
    assert.equal(await page.locator('#patient-index-notices').isVisible(), false);
    assert.equal(count('DELETE', '/patients/42'), 1);
    check('Renombrar y eliminar sincronizan; reintento tras fallo solo repite sync, sin PUT ni DELETE');
    await page.locator('[data-nav="api-java"]').click();
    for (const method of ['PUT', 'DELETE']) {
      const endpoint = page.locator(`#explorer-java details[data-method="${method}"][data-path="/patients/{id}"]`);
      await endpoint.locator('summary').click();
      await endpoint.locator('input[name="id"]').fill('43');
      failSync = true;
      await endpoint.locator('button[type="submit"]').click();
      if (method === 'DELETE') await confirm(true);
      await endpoint.getByRole('button', {name: 'Reintentar sincronización'}).waitFor();
      assert.equal(count(method, '/patients/43'), 1);
      assert.match(await endpoint.locator('.notice').textContent(), /cambio en Java está guardado/);
      failSync = false;
      await endpoint.getByRole('button', {name: 'Reintentar sincronización'}).click();
      await page.waitForFunction(method => !document.querySelector(`#explorer-java details[data-method="${method}"][data-path="/patients/{id}"] button[type="submit"]`).disabled, method);
      assert.equal(count(method, '/patients/43'), 1);
      assert.match(await endpoint.locator('.notice').textContent(), /Índice RAG sincronizado/);
    }
    check('Explorador Java también sincroniza PUT/DELETE y reintenta sin repetir la operación');
    const openEndpoint = async (api, method, route) => {
      await page.locator(`[data-nav="api-${api}"]`).click();
      const element = page.locator(`#explorer-${api} details[data-method="${method}"][data-path="${route}"]`);
      if (!await element.evaluate(node => node.open)) await element.locator('summary').click();
      return element;
    };
    const waitEndpoint = async (element, expected) => {
      await page.waitForFunction(({api, method, route, status}) => {
        const el = document.querySelector(`#explorer-${api} details[data-method="${method}"][data-path="${route}"]`);
        return el.querySelector('.endpoint-response').getAttribute('aria-busy') === 'false' && el.querySelector('.http-status').textContent.startsWith(String(status));
      }, {api: await element.evaluate(node => node.closest('[data-api]').dataset.api), method: await element.getAttribute('data-method'), route: await element.getAttribute('data-path'), status: expected});
    };
    mode = 'normal';
    for (const suffix of ['/history', '/history.md']) {
      const endpoint = await openEndpoint('java', 'GET', '/patients/{id}' + suffix);
      await endpoint.locator('input[name="id"]').fill('42');
      const syncBefore = count('POST', '/clinical/patients/42/sync');
      await endpoint.locator('button[type="submit"]').click(); await waitEndpoint(endpoint, 200);
      assert.equal(count('POST', '/clinical/patients/42/sync'), syncBefore, 'Leer historia no sincroniza ni escribe');
      assert.ok((await endpoint.locator('.response-body').textContent()).includes(suffix.endsWith('.md') ? '# Paciente UI' : 'revision'));
    }
    mode = 'invalid';
    for (const [method, route] of [['PUT', '/patients/{id}/history'], ['POST', '/patients/{id}/history/entries']]) {
      const endpoint = await openEndpoint('java', method, route);
      await endpoint.locator('input[name="id"]').fill('42');
      const actualPath = route.replace('{id}', '42');
      const before = count(method, actualPath);
      await endpoint.locator('button[type="submit"]').click(); await confirm(false);
      assert.equal(count(method, actualPath), before);
      await endpoint.locator('button[type="submit"]').click(); await confirm(true); await waitEndpoint(endpoint, 422);
      assert.equal(count(method, actualPath), before + 1);
      assert.match(await endpoint.locator('.response-body').textContent(), /inválid/);
    }
    mode = 'normal';
    const proposalEndpoint = await openEndpoint('python', 'POST', '/clinical/proposals');
    await proposalEndpoint.locator('textarea').fill(JSON.stringify({patient_id: 42, note: 'Enfermedad ficticia Beta.'}));
    await proposalEndpoint.locator('button[type="submit"]').click(); await waitEndpoint(proposalEndpoint, 200);
    assert.match(await proposalEndpoint.locator('.response-body').textContent(), /evidence/);
    const syncEndpoint = await openEndpoint('python', 'POST', '/clinical/patients/{id}/sync');
    await syncEndpoint.locator('input[name="id"]').fill('42');
    await syncEndpoint.locator('button[type="submit"]').click(); await waitEndpoint(syncEndpoint, 200);
    assert.match(await syncEndpoint.locator('.response-body').textContent(), /removed/);
    check('Seis rutas clínicas en exploradores; GET sin mutación, escrituras confirmadas/cancelables y422visible');
    report.result = 'passed';
  } catch (error) {
    report.result = 'failed'; report.error = error.message;
    await page.screenshot({path: path.join(output, 'fallo.png'), fullPage: true});
    throw error;
  } finally {
    report.finished_at = new Date().toISOString(); report.requests = requests;
    fs.writeFileSync(path.join(output, 'resultados.json'), JSON.stringify(report, null, 2) + '\n');
    await browser.close(); await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
