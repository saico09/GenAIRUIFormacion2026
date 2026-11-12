// Navegador y APIs reales. Sólo crea/modifica/elimina un paciente temporal propio.
// No llama al LLM ni administra contenedores. Requiere el proyecto ya iniciado.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const python = (process.env.PYTHON_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const java = (process.env.JAVA_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const marker = crypto.randomUUID().slice(0, 8);
const output = path.resolve(process.env.EVIDENCE_DIR || path.join(__dirname, '../evidencias/pacientes-unificados-2026-11-07', `ui-${marker}`));
const report = {started_at: new Date().toISOString(), mocks: [], llm_called: false, checks: []};
const values = {disease: 'Rinitis alérgica de prueba', treatment: 'Evitar el polen', medication: 'Cetirizina'};
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort((left, right) => {
    if (left === right) return 0;
    return left < right ? -1 : 1;
  }).map(key => [key, canonical(value[key])])) : value;
const hash = value => crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const check = name => { report.checks.push({name, passed: true}); console.log(`PASS ${name}`); };
async function request(base, endpoint, method = 'GET', body) {
  const response = await fetch(base + endpoint, {method, headers: body ? {'Content-Type': 'application/json'} : {},
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(endpoint.endsWith('/sync') ? 180000 : 30000)});
  const text = await response.text();
  let data; try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  return {status: response.status, data};
}
async function snapshot() {
  const result = {};
  for (const [name, base] of [['python', python], ['java', java]]) {
    const response = await request(base, '/patients'); assert.equal(response.status, 200);
    result[name] = response.data.sort((a, b) => a.id - b.id);
  }
  assert.deepEqual(result.python, result.java, 'Ambas APIs deben compartir pacientes');
  result.histories = [];
  for (const row of result.java) {
    const response = await request(java, `/patients/${row.id}/history`); assert.equal(response.status, 200);
    result.histories.push(response.data);
  }
  return result;
}

async function main() {
  fs.mkdirSync(output, {recursive: true});
  if (fs.existsSync(path.join(output, 'resultados.json'))) throw new Error('Usa una carpeta de evidencia nueva.');
  const before = await snapshot(); report.before_sha256 = hash(before);
  let owned = null;
  let browser;
  let failure;
  try {
    const created = await request(python, '/patients', 'POST', {name: `Registros UI ${marker}`, birth_date: '1990-05-15', email: `registros-${marker}@example.com`});
    assert.equal(created.status, 201); owned = created.data; report.temporary_patient_id = owned.id;
    assert.deepEqual((await request(java, `/patients/${owned.id}`)).data, owned);
    const initial = await request(java, `/patients/${owned.id}/history`);
    assert.equal(initial.status, 200); assert.match(initial.data.markdown, new RegExp(`patient_id: ${owned.id}`));
    assert.equal(initial.data.entries.length, 0);
    const consultationId = crypto.randomUUID();
    assert.equal((await request(java, `/patients/${owned.id}/consultations`, 'POST', {id: consultationId,
      question: 'Nota de prueba de conservación del diario.', direct_answer: 'Respuesta de prueba sin modelo.',
      rag_answer: 'Respuesta de prueba sin modelo.', model: 'fixture-ui', sources: []})).status, 201);
    browser = await chromium.launch({executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
    const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
    page.setDefaultTimeout(30000);
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    const traffic = []; page.on('request', req => traffic.push({method: req.method(), url: req.url()}));
    const count = (method, suffix) => traffic.filter(item => item.method === method && item.url.endsWith(suffix)).length;
    const idle = () => page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false', null, {timeout: 200000});
    const confirm = async accepted => {
      await page.locator('#confirm-dialog').waitFor();
      await page.locator(accepted ? '#confirm-accept' : '#confirm-cancel').click();
      await page.locator('#confirm-dialog').waitFor({state: 'hidden'});
    };
    const recordPath = `/patients/${owned.id}/diseases`;
    await page.goto(python + '/');
    await page.locator(`#patient option[value="${owned.id}"]`).waitFor({state: 'attached'});
    await page.locator('[data-nav="pacientes"]').click();
    for (const row of [...before.java, owned]) await page.locator(`#patients-body [data-patient-id="${row.id}"]`).waitFor();
    await page.locator(`#patients-body [data-patient-id="${owned.id}"] [data-action="history"]`).click(); await idle();
    assert.equal(await page.locator('#history-body tr').count(), 0);
    assert.equal(await page.locator('#consultations-body tr').count(), 1);
    assert.ok(count('GET', recordPath) > 0);
    check('Alta Python crea Markdown; Java, el listado completo y el selector de consultas comparten la identidad');

    await page.locator('#new-disease').click();
    await page.locator('#save-disease').click();
    assert.match(await page.locator('#disease-form-notice').textContent(), /al menos un campo/);
    for (const [key, value] of Object.entries(values)) await page.locator(`#disease-form [name="${key}"]`).fill(value);
    await page.locator('#save-disease').click(); await confirm(false); await idle();
    assert.equal(count('POST', recordPath), 0);
    await page.locator('#save-disease').click(); await confirm(true); await idle();
    const records = (await request(python, recordPath)).data;
    assert.equal(records.length, 1); const entry = records[0];
    assert.equal(entry.patient_id, owned.id);
    for (const key of Object.keys(values)) assert.equal(entry[key], values[key]);
    assert.deepEqual((await request(java, recordPath)).data, records);
    const row = page.locator(`#history-body [data-disease-id="${entry.id}"]`);
    assert.deepEqual((await row.locator('td').allTextContents()).slice(0, 4), [entry.id, ...Object.values(values)]);
    assert.equal(await page.locator('#history-sync').isVisible(), false, await page.locator('#history-sync-message').textContent());
    check('Formulario valida vacío; cancelar no escribe y confirmar crea una fila visible en ambas APIs');

    await row.locator('[data-disease-action="edit"]').click();
    await page.locator('#disease-treatment').fill('Evitar el polen y usar solución salina');
    await page.locator('#save-disease').click(); await confirm(true); await idle();
    const updated = (await request(python, `${recordPath}/${entry.id}`)).data;
    assert.equal(updated.id, entry.id); assert.equal(updated.treatment, 'Evitar el polen y usar solución salina');
    const history = (await request(java, `/patients/${owned.id}/history`)).data;
    assert.ok(history.markdown.includes(updated.treatment));
    assert.equal(history.consultations[0].id, consultationId);
    await page.locator('#history-markdown summary').click();
    const downloadEvent = page.waitForEvent('download'); await page.locator('#download-history').click();
    const download = await downloadEvent; await download.saveAs(path.join(output, 'informe-temporal.md')); await idle();
    assert.equal(fs.readFileSync(path.join(output, 'informe-temporal.md'), 'utf8'), history.markdown);
    await page.locator('#edit-history').click();
    const concurrent = {...values, treatment: 'Plan actualizado desde Python'};
    assert.equal((await request(python, `${recordPath}/${entry.id}`, 'PUT', concurrent)).status, 200);
    await page.locator('#save-markdown').click(); await confirm(true); await idle();
    assert.match(await page.locator('#history-notice').textContent(), /Otra operación/);
    assert.equal((await request(java, `${recordPath}/${entry.id}`)).data.treatment, concurrent.treatment);
    await page.locator('#refresh-history').click(); await idle();
    await page.locator('#cancel-markdown').click();
    await page.locator('#edit-history').click();
    const freshMarkdown = await page.locator('#history-markdown-input').inputValue();
    await page.locator('#history-markdown-input').fill(freshMarkdown.replace(values.medication, 'Cetirizina de prueba actualizada'));
    await page.locator('#save-markdown').click(); await confirm(true); await idle();
    assert.equal((await request(python, `${recordPath}/${entry.id}`)).data.medication, 'Cetirizina de prueba actualizada');
    assert.equal((await request(java, `/patients/${owned.id}/history`)).data.consultations[0].id, consultationId);
    check('Editar conserva UUID; Markdown coincide, rechaza una revisión antigua y actualiza la fila sin alterar el diario');

    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: path.join(output, 'registros-desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({path: path.join(output, 'registros-mobile.png'), fullPage: true});
    await page.setViewportSize({width: 1440, height: 1050});
    check('Tabla, acciones y formulario accesibles a 390 px sin desbordar la página');

    for (const api of ['python', 'java']) {
      await page.locator(`[data-nav="api-${api}"]`).click();
      const explorer = page.locator(`#explorer-${api}`);
      assert.equal(await explorer.locator('.endpoint[data-path*="/diseases"]').count(), 5);
      const endpoint = explorer.locator('.endpoint[data-method="GET"][data-path="/patients/{id}/diseases"]');
      await endpoint.locator('summary').click();
      await endpoint.locator('[name="id"]').fill(String(owned.id));
      await endpoint.locator('button[type="submit"]').click();
      await endpoint.locator('.http-status.ok').waitFor();
      assert.match(await endpoint.locator('.response-body').textContent(), new RegExp(entry.id));
    }
    check('Los dos exploradores ofrecen cinco operaciones diseases y ejecutan GET contra la misma tabla');

    await page.locator('[data-nav="pacientes"]').click(); await idle();
    await row.locator('[data-disease-action="delete"]').click(); await confirm(false); await idle();
    assert.equal(count('DELETE', `${recordPath}/${entry.id}`), 0);
    await row.locator('[data-disease-action="delete"]').click(); await confirm(true); await idle();
    assert.equal((await request(python, recordPath)).data.length, 0);
    const finalHistory = (await request(java, `/patients/${owned.id}/history`)).data;
    assert.equal(finalHistory.entries.length, 0); assert.equal(finalHistory.consultations[0].id, consultationId);
    assert.equal(await page.locator('#history-empty').isVisible(), true);
    assert.equal(await page.locator('#consultations-body tr').count(), 1);
    assert.deepEqual(errors, []);
    check('Cancelar DELETE no escribe; confirmar elimina sólo la fila y conserva la consulta guardada');
    report.traffic = traffic;
  } catch (error) {
    failure = error; report.error = error.stack;
  } finally {
    if (browser) await browser.close();
    if (owned) {
      const deleted = await request(python, `/patients/${owned.id}`, 'DELETE');
      report.cleanup = {patient_id: owned.id, status: deleted.status};
      if (![204, 404].includes(deleted.status)) failure ||= new Error('No se pudo retirar el paciente temporal');
      const sync = await request(python, `/clinical/patients/${owned.id}/sync`, 'POST');
      report.cleanup.sync_status = sync.status;
      if (sync.status !== 200) failure ||= new Error('No se pudo retirar el índice temporal');
    }
    const after = await snapshot(); report.after_sha256 = hash(after);
    if (report.after_sha256 !== report.before_sha256) failure ||= new Error('Cambió un paciente o una historia preexistente');
    report.finished_at = new Date().toISOString(); report.passed = !failure;
    fs.writeFileSync(path.join(output, 'resultados.json'), JSON.stringify(report, null, 2) + '\n');
  }
  if (failure) throw failure;
  console.log(`Evidencia: ${output}`);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
