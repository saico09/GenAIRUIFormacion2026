// Contratos UI aislados. HTTP simulado; no toca pacientes, modelos ni bases reales.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {chromium} = require('playwright');

const staticRoot = path.resolve(__dirname, '../python-api/app/static');
const output = path.resolve(process.env.EVIDENCE_DIR || path.join(__dirname, '../evidencias/consultas-persistentes-2026-11-07/ui-aislada'));
const report = {mode: 'isolated_browser_mock', real_services_used: false, checks: [], started_at: new Date().toISOString()};
const check = name => { report.checks.push({name, passed: true}); console.log(`PASS ${name}`); };
const json = (route, status, body) => route.fulfill({status, contentType: 'application/json', headers: {'access-control-allow-origin': '*'}, body: JSON.stringify(body)});
const rows = [
  {id: 42, name: 'Ana UI ficticia', birth_date: '1990-05-15', email: 'ana-ui@example.com'},
  {id: 43, name: 'Bruno UI ficticio', birth_date: '1991-06-16', email: 'bruno-ui@example.com'},
];
const recordId = '1d1783d9-8800-4972-ad7f-a3c6042575b0';
const records = new Map();
let chatMode = 'normal';
let syncFails = false;
const requests = [];
function history(patientId) {
  const consultations = [...records.values()].filter(row => row.patient_id === patientId);
  return {patient_id: patientId, filename: `paciente-${patientId}-demo.md`, revision: 'a'.repeat(64),
    entries: [{id: recordId, disease: 'Enfermedad ficticia Alfa', treatment: '', medication: ''}], consultations,
    markdown: `# Informe ficticio\n\n## Consultas registradas\n${consultations.map(row => row.question).join('\n')}`};
}
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
  const browser = await chromium.launch({executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.setDefaultTimeout(12000);
  await page.route('**/*', async route => {
    const req = route.request(); const url = new URL(req.url()); const method = req.method();
    if (url.origin === base && (url.pathname === '/' || url.pathname.startsWith('/static/'))) return route.continue();
    const body = req.postData() ? req.postDataJSON() : null;
    requests.push({method, path: url.pathname, body, execution_id: req.headers()['x-execution-id']});
    if (url.pathname === '/ui-config') return json(route, 200, {java_api_port: 29980, metrics_enabled: true});
    if (url.pathname === '/patients') return json(route, 200, rows);
    const patientMatch = url.pathname.match(/^\/patients\/(42|43)$/);
    if (patientMatch) return json(route, 200, rows.find(row => row.id === Number(patientMatch[1])));
    const historyMatch = url.pathname.match(/^\/patients\/(42|43)\/history$/);
    if (historyMatch && method === 'GET') return json(route, 200, history(Number(historyMatch[1])));
    const consultationMatch = url.pathname.match(/^\/patients\/42\/consultations\/([0-9a-f-]+)$/);
    if (consultationMatch && method === 'GET') return json(route, 200, records.get(consultationMatch[1]));
    if (url.pathname === '/patients/42/consultations' && method === 'POST') {
      const saved = {...body, patient_id: 42, created_at: new Date().toISOString()}; records.set(body.id, saved);
      return json(route, 201, saved);
    }
    if (url.pathname.endsWith('/history.md')) return route.fulfill({status: 200, contentType: 'text/markdown', body: history(Number(url.pathname.split('/')[2])).markdown});
    if (url.pathname === '/clinical/patients/42/sync') return json(route, syncFails ? 503 : 200,
      syncFails ? {detail: 'Índice no disponible (simulado)'} : {patient_id: 42, status: 'synced'});
    if (url.pathname === '/chat') {
      const id = req.headers()['x-execution-id'];
      assert.match(id, /^[0-9a-f-]{36}$/i);
      if (chatMode === 'network-error') return route.abort('connectionreset');
      if (chatMode === 'save-error') return json(route, 503, {detail: 'No se guardó la consulta (simulado)'});
      const consultation = records.get(id) || {id, patient_id: body.patient_id, question: body.question,
        direct_answer: 'Respuesta directa ficticia.', rag_answer: 'Antecedente: Alfa. Orientación: completar los datos de la consulta.',
        model: 'modelo-ui-simulado', created_at: new Date().toISOString()};
      records.set(id, consultation);
      const sources = [
        {kind: 'confirmed_record', source: 'paciente-42-demo.md', section: 'Enfermedad', record_id: recordId, text: 'Enfermedad ficticia Alfa'},
        {source: 'paciente-42-demo.md', section: 'Consulta', record_id: id, text: body.question},
      ];
      return json(route, 200, {...consultation, sources, consultation: {...consultation, saved: true}, index_synced: chatMode !== 'pending-sync'});
    }
    throw new Error(`Petición no prevista: ${method} ${req.url()}`);
  });
  const chatRequests = () => requests.filter(row => row.path === '/chat');
  const waitChat = () => page.waitForFunction(() => !document.querySelector('#submit').disabled && document.querySelector('#loading').hidden);
  const waitHistory = () => page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false');
  try {
    await page.goto(base);
    await waitChat();
    assert.match(await page.locator('.query-form .helper').textContent(), /se guardan/);
    const question = 'Ana refiere dolor de cabeza. <img src=x onerror=alert(1)>';
    await page.locator('#question').fill(question);
    chatMode = 'network-error';
    await page.locator('#submit').click(); await waitChat();
    assert.match(await page.locator('#error').textContent(), /conectar/);
    assert.equal(records.size, 0);
    chatMode = 'normal';
    await page.locator('#submit').click(); await waitChat();
    assert.equal(chatRequests()[0].execution_id, chatRequests()[1].execution_id);
    assert.equal(records.size, 1);
    assert.match(await page.locator('#chat-save-status').textContent(), /guardada.*Ana UI ficticia.*PostgreSQL/);
    assert.match(await page.locator('#chat-execution-id').textContent(), /modelo-ui-simulado/);
    assert.match(await page.locator('#sources summary').nth(0).textContent(), /Registro confirmado/);
    assert.match(await page.locator('#sources summary').nth(1).textContent(), /Consulta reportada/);
    check('Reintento de red conserva UUID; éxito muestra guardado, paciente y modelo');

    await page.locator('#open-chat-history').click(); await waitHistory();
    assert.equal(await page.locator('#history-patient-name').textContent(), rows[0].name);
    assert.equal(await page.locator('#history-body tr').count(), 1);
    assert.equal(await page.locator('#consultations-body tr').count(), 1);
    assert.equal(await page.locator('.consultation-question').textContent(), question);
    assert.equal(await page.locator('#consultations-body img').count(), 0);
    await page.locator('.saved-consultation summary').click();
    assert.equal(await page.locator('.saved-answer').count(), 2);
    await page.locator('#history-markdown summary').click();
    assert.match(await page.locator('#history-markdown-text').textContent(), /dolor de cabeza/);
    check('Enlace abre paciente correcto; consultas y registros separados, respuestas y Markdown visibles sin HTML ejecutable');

    await page.locator('#edit-history').click();
    await page.locator('#history-markdown-input').fill('Borrador que debe conservarse');
    await page.locator('[data-nav="consultas"]').click();
    chatMode = 'pending-sync';
    await page.locator('#submit').click(); await waitChat();
    assert.notEqual(chatRequests()[1].execution_id, chatRequests()[2].execution_id);
    assert.equal(records.size, 2);
    assert.match(await page.locator('#chat-save-status').textContent(), /guardada.*Falta actualizar/);
    const countBeforeSync = chatRequests().length;
    syncFails = true;
    await page.locator('#retry-chat-sync').click(); await waitChat();
    assert.match(await page.locator('#chat-save-status').textContent(), /sigue guardada/);
    syncFails = false;
    await page.locator('#retry-chat-sync').click(); await waitChat();
    assert.equal(await page.locator('#retry-chat-sync').isVisible(), false);
    assert.equal(chatRequests().length, countBeforeSync);
    assert.equal(records.size, 2);
    check('Nueva consulta obtiene otro UUID; reintentar índice no repite chat ni duplica registros');

    await page.locator('[data-nav="pacientes"]').click();
    assert.equal(await page.locator('#history-markdown-input').inputValue(), 'Borrador que debe conservarse');
    assert.equal(await page.locator('#save-markdown').isDisabled(), true);
    assert.match(await page.locator('#history-notice').textContent(), /consulta nueva/);
    await page.locator('#refresh-history').click(); await waitHistory();
    assert.equal(await page.locator('#history-markdown-input').inputValue(), 'Borrador que debe conservarse');
    assert.equal(await page.locator('#consultations-body tr').count(), 2);
    check('Una consulta nueva invalida la revisión del editor sin perder el borrador');

    await page.locator('#history-back').click();
    await page.getByRole('button', {name: 'Abrir historia de Bruno UI ficticio'}).click(); await waitHistory();
    assert.equal(await page.locator('#consultations-body tr').count(), 0);
    assert.equal(await page.locator('#consultations-empty').isVisible(), true);
    await page.locator('#consult-patient').click();
    assert.equal(await page.locator('#patient').inputValue(), '43');
    await page.locator('#question').fill('Consulta de Bruno');
    chatMode = 'save-error';
    await page.locator('#submit').click(); await waitChat();
    assert.equal(await page.locator('#chat-record-actions').isVisible(), false);
    assert.match(await page.locator('#error').textContent(), /No se guardó/);
    assert.equal(records.size, 2);
    check('Cambiar de paciente limpia consultas previas; error de guardado no muestra éxito');

    await page.locator('[data-nav="api-java"]').click();
    const reading = page.locator('#explorer-java details[data-method="GET"][data-path="/patients/{id}/consultations/{uuid}"]');
    await reading.locator('summary').click();
    await reading.locator('[name="id"]').fill('42');
    await reading.locator('[name="uuid"]').fill('no-es-uuid');
    await reading.locator('button[type="submit"]').click();
    assert.match(await reading.locator('.notice').textContent(), /formato UUID/);
    const firstId = [...records.keys()][0];
    await reading.locator('[name="uuid"]').fill(firstId);
    await reading.locator('button[type="submit"]').click();
    await page.waitForFunction(() => document.querySelector('#explorer-java details[data-path="/patients/{id}/consultations/{uuid}"] .http-status').textContent.startsWith('200'));
    assert.match(await reading.locator('.response-body').textContent(), /dolor de cabeza/);
    const writing = page.locator('#explorer-java details[data-method="POST"][data-path="/patients/{id}/consultations"]');
    await writing.locator('summary').click(); await writing.locator('[name="id"]').fill('42');
    await writing.locator('button[type="submit"]').click();
    await page.locator('#confirm-dialog').waitFor(); await page.locator('#confirm-cancel').click();
    assert.equal(records.size, 2);
    await writing.locator('button[type="submit"]').click();
    await page.locator('#confirm-dialog').waitFor(); await page.locator('#confirm-accept').click();
    await page.waitForFunction(() => document.querySelector('#explorer-java details[data-path="/patients/{id}/consultations"] .endpoint-response').getAttribute('aria-busy') === 'false');
    assert.equal(records.size, 3);
    assert.match(await writing.locator('.notice').textContent(), /sincronizado/);
    check('Explorador valida UUID, lee consulta y confirma o cancela el registro manual antes de escribir');

    await page.setViewportSize({width: 390, height: 844});
    await page.locator('[data-nav="consultas"]').click();
    await page.screenshot({path: path.join(output, 'consulta-movil.png'), fullPage: true});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('[data-nav="pacientes"]').click();
    await page.locator('#history-back').click();
    await page.getByRole('button', {name: 'Abrir historia de Ana UI ficticia'}).click(); await waitHistory();
    await page.screenshot({path: path.join(output, 'historia-movil.png'), fullPage: true});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    check('Vista móvil sin desbordamiento de página y sin errores JavaScript');
    report.result = 'passed';
  } catch (error) {
    report.result = 'failed'; report.error = error.message;
    await page.screenshot({path: path.join(output, 'fallo.png'), fullPage: true}); throw error;
  } finally {
    report.finished_at = new Date().toISOString(); report.requests = requests;
    fs.writeFileSync(path.join(output, 'resultados.json'), JSON.stringify(report, null, 2) + '\n');
    await browser.close(); await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
