// Recorrido real sobre las APIs levantadas; sólo crea y elimina su paciente temporal.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {randomUUID, createHash} = require('node:crypto');
const {chromium} = require('playwright');
const base = process.env.PYTHON_URL || 'http://localhost:8000';
const java = process.env.JAVA_URL || 'http://localhost:8080';
const output = path.resolve(process.env.EVIDENCE_DIR || path.join(__dirname, '../evidencias/consultas-automaticas-2026-11-07/ui-real'));
const report = {mode: 'real_browser_real_apis_real_llm', mocks: false, started_at: new Date().toISOString(), checks: []};
const check = name => {report.checks.push({name, passed: true}); console.log(`PASS ${name}`);};
async function api(url, options = {}) {
  const response = await fetch(url, {...options, signal: AbortSignal.timeout(420000)});
  const text = await response.text();
  let data; try {data = text ? JSON.parse(text) : null;} catch {data = text;}
  return {status: response.status, data, text};
}
const json = (method, body) => ({method, headers: {'content-type': 'application/json'}, body: JSON.stringify(body)});
async function main() {
  fs.mkdirSync(output, {recursive: true});
  const before = await api(`${java}/patients`); assert.equal(before.status, 200);
  const temp = {name: 'Prueba UI consulta automática', birth_date: '1990-05-15', email: `ui-auto-${randomUUID()}@example.com`};
  let patient = null, browser = null, page = null;
  try {
    const created = await api(`${java}/patients`, json('POST', temp)); assert.equal(created.status, 201);
    patient = created.data; report.patient = patient;
    browser = await chromium.launch({executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
    page = await browser.newPage({viewport: {width: 1440, height: 1050}});
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    page.setDefaultTimeout(15000);
    await page.goto(base);
    await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    await page.locator('#patient').selectOption(String(patient.id));
    const question = 'Refiere dolor de estómago después de comer desde ayer. No presenta vómitos ni diarrea.';
    await page.locator('#question').fill(question);
    const reply = page.waitForResponse(response => response.url() === `${base}/chat` && response.request().method() === 'POST', {timeout: 420000});
    await page.locator('#submit').click();
    const response = await reply; assert.equal(response.status(), 200); const data = await response.json();
    report.chat = data; report.execution_id = response.headers()['x-execution-id'];
    await page.waitForFunction(() => document.querySelector('#loading').hidden, {timeout: 420000});
    assert.equal(data.consultation.saved, true); assert.equal(data.consultation.patient_id, patient.id);
    assert.match(data.consultation.id, /^[0-9a-f-]{36}$/);
    assert.ok(data.direct_answer.length > 30); assert.ok(data.rag_answer.length > 30);
    assert.match(data.rag_answer, /Diagnóstico orientativo \(sin confirmar\)/);
    assert.doesNotMatch(data.rag_answer, /[¿?]/);
    assert.match(await page.locator('#chat-save-status').textContent(), /guardada.*PostgreSQL/);
    const saved = await api(`${java}/patients/${patient.id}/history`); assert.equal(saved.status, 200);
    assert.equal(saved.data.entries.length, 0); assert.equal(saved.data.consultations.length, 1);
    const consultation = saved.data.consultations[0];
    assert.equal(consultation.id, data.consultation.id); assert.equal(consultation.question, question);
    assert.equal(consultation.direct_answer, data.direct_answer); assert.equal(consultation.rag_answer, data.rag_answer);
    assert.ok(saved.data.markdown.includes(question)); assert.ok(saved.data.markdown.includes(data.rag_answer.split('\n')[0]));
    check('Chat real guarda motivo y ambas respuestas en el Markdown sin añadir diagnósticos confirmados');

    await page.locator('#open-chat-history').click();
    await page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false');
    assert.equal(await page.locator('#history-patient-name').textContent(), patient.name);
    assert.equal(await page.locator('#consultations-body tr').count(), 1); assert.equal(await page.locator('#history-body tr').count(), 0);
    await page.locator('.saved-consultation summary').click();
    assert.equal((await page.locator('.saved-answer').allTextContents())[1], data.rag_answer);
    await page.screenshot({path: path.join(output, 'consulta-guardada.png'), fullPage: true});
    await page.reload();
    await page.getByRole('button', {name: `Abrir historia de ${patient.name}`}).click();
    await page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false');
    assert.equal(await page.locator('#consultations-body tr').count(), 1);
    await page.locator('#history-markdown summary').click();
    const download = page.waitForEvent('download'); await page.locator('#download-history').click();
    const file = await download; await file.saveAs(path.join(output, 'informe-temporal.md'));
    assert.equal(file.suggestedFilename(), saved.data.filename);
    const markdown = fs.readFileSync(path.join(output, 'informe-temporal.md'), 'utf8');
    assert.equal(markdown, saved.data.markdown);
    report.markdown_sha256 = createHash('sha256').update(markdown).digest('hex');
    check('Informe accesible desde el chat, respuestas consultables y persistencia tras recargar; descarga exacta');

    await page.locator('#new-consultation').click();
    await page.locator('#manual-entry').click();
    await page.locator('.entry-draft [name="disease"]').fill('Enfermedad ficticia UI confirmada');
    await page.locator('.entry-draft [data-save-entry]').click();
    await page.locator('#confirm-dialog').waitFor(); await page.locator('#confirm-cancel').click();
    assert.equal((await api(`${java}/patients/${patient.id}/history`)).data.entries.length, 0);
    await page.locator('.entry-draft [data-save-entry]').click();
    await page.locator('#confirm-dialog').waitFor(); await page.locator('#confirm-accept').click();
    await page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false');
    const confirmed = await api(`${java}/patients/${patient.id}/history`);
    assert.equal(confirmed.data.entries.length, 1); assert.equal(confirmed.data.consultations.length, 1);
    assert.equal(confirmed.data.consultations[0].rag_answer, data.rag_answer);
    await page.locator('#edit-history').click();
    const edited = confirmed.data.markdown.replace('Enfermedad ficticia UI confirmada', 'Enfermedad ficticia UI revisada');
    await page.locator('#history-markdown-input').fill(edited); await page.locator('#save-markdown').click();
    await page.locator('#confirm-dialog').waitFor(); await page.locator('#confirm-cancel').click();
    assert.equal((await api(`${java}/patients/${patient.id}/history`)).data.revision, confirmed.data.revision);
    await page.locator('#save-markdown').click(); await page.locator('#confirm-dialog').waitFor(); await page.locator('#confirm-accept').click();
    await page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false');
    const final = await api(`${java}/patients/${patient.id}/history`);
    assert.equal(final.data.entries[0].disease, 'Enfermedad ficticia UI revisada');
    assert.equal(final.data.consultations.length, 1); assert.equal(final.data.consultations[0].rag_answer, data.rag_answer);
    report.final_history = final.data;
    check('Registro confirmado y edición MD requieren confirmar; cancelar no escribe y la consulta original se conserva');
    await page.setViewportSize({width: 390, height: 844});
    await page.screenshot({path: path.join(output, 'historia-movil.png'), fullPage: true});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []); check('Vista móvil real sin desbordamiento y sin errores JavaScript');
    report.result = 'passed';
  } catch (error) {
    report.result = 'failed'; report.error = error.message;
    if (page) await page.screenshot({path: path.join(output, 'fallo.png'), fullPage: true});
    throw error;
  } finally {
    if (browser) await browser.close();
    if (patient) {
      const actual = await api(`${java}/patients/${patient.id}`);
      assert.equal(actual.data.email, temp.email, 'Sólo borrar el temporal propio');
      const deleted = await api(`${java}/patients/${patient.id}`, {method: 'DELETE'}); assert.equal(deleted.status, 204);
      const sync = await api(`${base}/clinical/patients/${patient.id}/sync`, {method: 'POST'}); assert.equal(sync.status, 200);
      const missing = await api(`${java}/patients/${patient.id}`); assert.equal(missing.status, 404);
      report.cleanup = {patient_deleted: true, index_removed: sync.data, retained_sql_backups_and_audit_expected: true};
    }
    const after = await api(`${java}/patients`);
    for (const original of before.data) assert.deepEqual(after.data.find(row => row.id === original.id), original);
    report.original_patient_rows_preserved = true;
    report.finished_at = new Date().toISOString();
    fs.writeFileSync(path.join(output, 'resultados.json'), JSON.stringify(report, null, 2) + '\n');
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
