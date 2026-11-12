// Java, Markdown, sincronización y navegador reales. Solo usa un paciente temporal propio.
// Por defecto simula propuesta/chat; --real-llm habilita esas llamadas reales explícitamente.
// No inicia, detiene ni reconstruye servicios.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const python = (process.env.PYTHON_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const java = (process.env.JAVA_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const realLlm = process.argv.includes('--real-llm');
const marker = crypto.randomUUID().slice(0, 8);
const output = path.resolve(process.env.EVIDENCE_DIR || path.join(__dirname, '../evidencias/clinica-2026-11-07', `ui-real-${marker}`));
const original = {name: `Historia UI ${marker}`, birth_date: '1990-05-15', email: `historia-ui-${marker}@example.com`};
const values = {disease: 'Síndrome ficticio Nube', treatment: 'Terapia ficticia Clara', medication: 'Compuesto ficticio Azul'};
const note = `Datos sintéticos. Enfermedad: ${values.disease}. Tratamiento: ${values.treatment}. Medicamento: ${values.medication}.`;
const report = {started_at: new Date().toISOString(), real_services_used: true, real_llm: realLlm,
  mocks: realLlm ? [] : ['POST /clinical/proposals', 'POST /chat'], checks: []};
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort((left, right) => {
    if (left === right) return 0;
    return left < right ? -1 : 1;
  }).map(key => [key, canonical(value[key])])) : value;
const hash = value => crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const check = (name, detail = {}) => { report.checks.push({name, passed: true, ...detail}); console.log(`PASS ${name}`); };
async function request(base, endpoint, method = 'GET', body) {
  const response = await fetch(base + endpoint, {method, headers: body ? {'Content-Type': 'application/json'} : {},
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(endpoint.endsWith('/sync') ? 180000 : 20000)});
  const text = await response.text();
  let data; try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  return {status: response.status, data};
}
async function snapshot() {
  const state = {};
  for (const [name, base] of [['python', python], ['java', java]]) {
    const response = await request(base, '/patients'); assert.equal(response.status, 200);
    state[name] = [...response.data].sort((a, b) => a.id - b.id);
  }
  state.histories = [];
  for (const row of state.java) {
    const history = await request(java, `/patients/${row.id}/history`); assert.equal(history.status, 200);
    state.histories.push(history.data);
  }
  return state;
}
const digest = state => Object.fromEntries(Object.entries(state).map(([key, rows]) => [key, {count: rows.length, sha256: hash(rows)}]));

async function main() {
  if (fs.existsSync(path.join(output, 'resultados.json'))) throw new Error('La carpeta ya contiene resultados; elige otro EVIDENCE_DIR.');
  fs.mkdirSync(output, {recursive: true});
  const before = await snapshot(); report.before = digest(before);
  let owned = null;
  let browser;
  let page;
  const traffic = [];
  let failure;
  try {
    const created = await request(java, '/patients', 'POST', original);
    assert.equal(created.status, 201); owned = created.data;
    report.temporary_patient_id = owned.id;
    assert.equal(before.python.some(row => row.id === owned.id), false, 'El ID de prueba debe estar ausente de Python');
    assert.equal((await request(python, `/patients/${owned.id}`)).status, 404);
    browser = await chromium.launch({executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
    page = await browser.newPage({viewport: {width: 1440, height: 1050}});
    page.setDefaultTimeout(20000);
    page.on('request', req => traffic.push({method: req.method(), url: req.url()}));
    const count = (method, suffix) => traffic.filter(item => item.method === method && item.url.endsWith(suffix)).length;
    if (!realLlm) {
      await page.route(python + '/clinical/proposals', async route => {
        assert.deepEqual(route.request().postDataJSON(), {patient_id: owned.id, note});
        await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({patient_id: owned.id,
          entries: [{...values, evidence: {...values}}], message: 'Propuesta simulada para comprobar el flujo de revisión.'})});
      });
      await page.route(python + '/chat', async route => {
        assert.equal(route.request().postDataJSON().patient_id, owned.id);
        const current = await request(java, `/patients/${owned.id}/history`);
        const entry = current.data.entries[0];
        await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({
          direct_answer: 'Respuesta simulada sin contexto.', rag_answer: entry.disease,
          sources: [{patient_id: owned.id, record_id: entry.id, source: current.data.filename, section: 'Enfermedad', text: entry.disease}],
        })});
      });
    }
    const idle = () => page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false', null, {timeout: 440000});
    const confirm = async accept => { await page.locator('#confirm-dialog').waitFor(); await page.locator(accept ? '#confirm-accept' : '#confirm-cancel').click(); await page.locator('#confirm-dialog').waitFor({state: 'hidden'}); };
    await page.goto(python + '/');
    await page.locator(`#patient option[value="${owned.id}"]`).waitFor({state: 'attached'});
    await page.locator('[data-nav="pacientes"]').click();
    await page.locator('#patient-search').fill(marker);
    const row = page.locator(`#patients-body tr[data-patient-id="${owned.id}"]`);
    await row.locator('[data-action="history"]').click(); await idle();
    assert.equal(await page.locator('#history-body tr').count(), 0);
    await page.locator('#new-consultation').click();
    await page.locator('#consultation-note').fill(note);
    const proposalResponse = page.waitForResponse(response => response.url() === python + '/clinical/proposals' && response.request().method() === 'POST', {timeout: 440000});
    await page.locator('#prepare-proposal').click();
    const proposalHttp = await proposalResponse;
    report.proposal = {note, status: proposalHttp.status(), request_id: proposalHttp.headers()['x-request-id'] || null,
      body: await proposalHttp.json()};
    await idle();
    assert.equal(report.proposal.status, 200);
    assert.ok(await page.locator('.entry-draft').count() > 0, await page.locator('#proposal-notice').textContent());
    const draft = page.locator('.entry-draft').first();
    report.proposed_fields = {};
    for (const [key, expected] of Object.entries(values)) {
      const input = draft.locator(`[name="${key}"]`);
      const proposed = await input.inputValue();
      assert.match(proposed, new RegExp(expected));
      assert.ok(note.includes(proposed), 'El campo propuesto debe estar escrito en la nota');
      report.proposed_fields[key] = proposed;
      // La persona revisa y puede ajustar puntuación antes de confirmar el borrador.
      await input.fill(expected);
    }
    assert.equal((await request(java, `/patients/${owned.id}/history`)).data.entries.length, 0);
    await draft.locator('[data-save-entry]').click(); await confirm(false); await idle();
    assert.equal(count('POST', `/patients/${owned.id}/history/entries`), 0);
    await draft.locator('[data-save-entry]').click(); await confirm(true); await idle();
    assert.equal(await page.locator('#history-sync').isVisible(), false, await page.locator('#history-sync-message').textContent());
    const saved = (await request(java, `/patients/${owned.id}/history`)).data;
    assert.equal(saved.entries.length, 1);
    const entry = saved.entries[0];
    assert.match(entry.id, /^[a-f0-9-]{36}$/i);
    assert.match(saved.markdown, new RegExp(entry.id));
    for (const key of Object.keys(values)) assert.equal(entry[key], values[key]);
    assert.deepEqual(await page.locator('#history-body td').allTextContents(), [entry.id, ...Object.values(values)]);
    report.confirmed_entry = entry;
    check('Identidad Java ausente de Python; propuesta revisada, cancelar no guarda y confirmar persiste UUID/Markdown', {record_id: entry.id});

    await page.locator('#history-markdown summary').click();
    const downloadEvent = page.waitForEvent('download'); await page.locator('#download-history').click();
    const download = await downloadEvent; assert.equal(download.suggestedFilename(), saved.filename);
    const file = path.join(output, 'historia-temporal.md'); await download.saveAs(file);
    assert.equal(fs.readFileSync(file, 'utf8'), saved.markdown); await idle();
    await page.locator('#edit-history').click();
    const newMarkdown = saved.markdown.replaceAll('Síndrome ficticio Nube', 'Síndrome ficticio Cedro');
    await page.locator('#history-markdown-input').fill(newMarkdown);
    await page.locator('#save-markdown').click(); await confirm(false); await idle();
    assert.equal(count('PUT', `/patients/${owned.id}/history`), 0);
    await page.locator('#save-markdown').click(); await confirm(true); await idle();
    const updated = (await request(java, `/patients/${owned.id}/history`)).data;
    assert.equal(updated.entries[0].id, entry.id);
    assert.equal(updated.entries[0].disease, 'Síndrome ficticio Cedro');
    assert.notEqual(updated.revision, saved.revision);
    assert.equal(await page.locator('#history-sync').isVisible(), false);
    report.edited_history = {filename: updated.filename, revision: updated.revision, entries: updated.entries};
    fs.writeFileSync(path.join(output, 'historia-editada.md'), updated.markdown);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: path.join(output, 'historia-editada.png'), fullPage: true});
    check('Descarga idéntica; edición Markdown confirmada conserva UUID y sincroniza nueva revisión');

    await page.locator('[data-nav="consultas"]').click();
    await page.locator('#patient').selectOption(String(owned.id));
    const question = `¿Qué enfermedad tiene ${original.name}?`;
    await page.locator('#question').fill(question);
    const chatResponse = page.waitForResponse(response => response.url() === python + '/chat' && response.request().method() === 'POST', {timeout: 440000});
    await page.locator('#submit').click();
    const chat = await chatResponse; assert.equal(chat.status(), 200, await chat.text());
    const answer = await chat.json();
    await page.waitForFunction(() => !document.querySelector('#submit').disabled, null, {timeout: 440000});
    assert.match(answer.rag_answer, /Cedro/i);
    assert.ok(answer.sources.some(source => source.patient_id === owned.id && source.record_id === entry.id));
    assert.equal((await request(java, `/patients/${owned.id}/history`)).data.revision, updated.revision, 'Preguntar no modifica el informe');
    await page.locator('#sources summary').first().click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: path.join(output, 'consulta.png'), fullPage: true});
    await page.locator('#prepare-chat-record').click(); await page.locator('#consultation-editor').waitFor(); await idle();
    assert.equal(await page.locator('#consultation-note').inputValue(), question);
    assert.equal((await request(java, `/patients/${owned.id}/history`)).data.revision, updated.revision);
    report.chat = {request_id: chat.headers()['x-request-id'] || null, ...answer};
    check(realLlm ? 'RAG real consulta la edición del paciente Java y devuelve su UUID; preguntar no escribe' : 'Chat simulado prueba fuentes y traslado de pregunta sin autoarchivo');

    await page.locator('#history-back').click();
    await row.locator('[data-action="edit"]').click();
    await page.locator('#patient-name').fill(original.name + ' Renombrado');
    await page.locator('#save-patient').click();
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled, null, {timeout: 200000});
    assert.equal(await page.locator('#patient-index-notices').isVisible(), false);
    const renamed = (await request(java, `/patients/${owned.id}/history`)).data;
    assert.notEqual(renamed.filename, updated.filename);
    assert.equal(renamed.entries[0].id, entry.id);
    const syncResponse = page.waitForResponse(response => response.url() === `${python}/clinical/patients/${owned.id}/sync` && response.request().method() === 'POST', {timeout: 200000});
    await row.locator('[data-action="delete"]').click(); await confirm(true);
    const cleanupResponse = await syncResponse; assert.equal(cleanupResponse.status(), 200);
    const removed = await cleanupResponse.json(); assert.equal(removed.status, 'removed'); assert.equal(removed.fragments, 0);
    await page.waitForFunction(() => !document.querySelector('#new-patient').disabled, null, {timeout: 200000});
    assert.equal((await request(java, `/patients/${owned.id}`)).status, 404);
    report.index_cleanup = removed;
    check('Renombrar actualiza filename; eliminar por UI limpia también el índice del paciente propio');
    report.result = 'passed';
  } catch (error) {
    failure = error; report.result = 'failed'; report.error = error.message;
    if (page) {
      await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
      await page.screenshot({path: path.join(output, 'fallo.png'), fullPage: true}).catch(() => {});
    }
  } finally {
    if (page) await page.unrouteAll({behavior: 'ignoreErrors'});
    try {
      // Si la respuesta del alta se perdió, se reconoce solo el marcador único de esta ejecución.
      const rows = await request(java, '/patients'); assert.equal(rows.status, 200);
      const candidates = rows.data.filter(row => row.email === original.email && [original.name, original.name + ' Renombrado'].includes(row.name));
      for (const row of candidates) {
        assert.ok(!before.java.some(old => old.id === row.id), 'Nunca se limpia un ID preexistente');
        if (owned) assert.equal(row.id, owned.id);
        assert.equal((await request(java, `/patients/${row.id}`, 'DELETE')).status, 204);
        owned = row;
      }
      if (owned) {
        const sync = await request(python, `/clinical/patients/${owned.id}/sync`, 'POST');
        assert.equal(sync.status, 200); assert.equal(sync.data.status, 'removed');
        report.cleanup_verified = true;
      }
      const after = await snapshot(); report.after = digest(after);
      report.data_preserved = hash(before) === hash(after);
      assert.equal(report.data_preserved, true, 'Datos o historias preexistentes cambiaron');
    } catch (error) { report.result = 'failed'; report.cleanup_error = error.message; failure ||= error; }
    report.finished_at = new Date().toISOString();
    fs.writeFileSync(path.join(output, 'resultados.json'), JSON.stringify(report, null, 2) + '\n');
    if (browser) await browser.close();
  }
  if (failure) throw failure;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
