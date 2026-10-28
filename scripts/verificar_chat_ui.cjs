// Prueba real de navegador; requiere Playwright y Edge instalados.
// --error-y-reintento espera que el operador detenga Ollama y lo vuelva a iniciar.
// --demo prueba enfermedad y cirugía de Ana; EVIDENCE_DIR/PREFIX conservan cada ensayo.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const outputDir = process.env.EVIDENCE_DIR
    ? path.resolve(process.env.EVIDENCE_DIR) : path.resolve(__dirname, '../evidencias/S04');
  const prefix = process.env.EVIDENCE_PREFIX ? `${process.env.EVIDENCE_PREFIX}-` : '';
  const evidencePath = name => path.join(outputDir, `${prefix}${name}`);
  fs.mkdirSync(outputDir, {recursive: true});
  const errorMode = process.argv.includes('--error-y-reintento');
  const datasetMode = process.argv.includes('--dataset');
  const demoMode = process.argv.includes('--demo');
  const dataset = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../datos/preguntas.json'), 'utf8'));
  const browser = await chromium.launch({
    executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });
  try {
    const page = await browser.newPage({viewport: {width: 1366, height: 900}});
    await page.goto(process.env.CHAT_URL || 'http://127.0.0.1:8000/');
    await page.locator('#patient option[value="1"]').waitFor({state: 'attached'});
    let posts = 0;
    page.on('request', request => { if (request.url().endsWith('/chat') && request.method() === 'POST') posts++; });
    await page.fill('#question', '   ');
    await page.click('#submit');
    assert.equal(await page.locator('#error').textContent(), 'Escribe una pregunta');
    assert.equal(posts, 0, 'No debe enviar POST cuando la pregunta está vacía');
    console.log('OK pregunta vacía: aviso y cero POST');

    async function send(question, expectedStatus, checkLoading = false) {
      const responsePromise = page.waitForResponse(r => r.url().endsWith('/chat'), {timeout: 250000});
      await page.click('#submit');
      if (checkLoading) {
        assert.equal(await page.locator('#submit').isDisabled(), true);
        assert.equal(await page.locator('#patient').isDisabled(), true);
        assert.equal(await page.locator('#question').isDisabled(), true);
        assert.equal(await page.locator('#loading').isVisible(), true);
      }
      const response = await responsePromise;
      assert.equal(response.status(), expectedStatus);
      assert.deepEqual(response.request().postDataJSON(), {patient_id: question.patient_id, question: question.question});
      await page.waitForFunction(() => !document.querySelector('#submit').disabled);
      assert.equal(await page.locator('#patient').isDisabled(), false);
      assert.equal(await page.locator('#question').isDisabled(), false);
      assert.equal(await page.locator('#loading').isVisible(), false);
      assert.equal(await page.locator('#question').inputValue(), question.question);
      return response.json();
    }

    if (errorMode) {
      await page.selectOption('#patient', String(dataset[0].patient_id));
      await page.fill('#question', dataset[0].question);
      const failure = await send(dataset[0], 503);
      assert.equal(failure.detail, 'LLM no disponible');
      assert.equal(await page.locator('#error').textContent(), 'LLM no disponible');
      await page.screenshot({path: evidencePath('error-ollama.png'), fullPage: true});
      console.log('ERROR_VERIFICADO: 503 visible y pregunta conservada; esperando reinicio de Ollama');
      const deadline = Date.now() + 90000;
      let available = false;
      while (Date.now() < deadline) {
        try {
          const response = await fetch('http://127.0.0.1:11434/api/version', {signal: AbortSignal.timeout(2000)});
          if (response.ok) { available = true; break; }
        } catch { }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      assert.equal(available, true, 'Ollama no se reinició durante la prueba');
      const result = await send(dataset[0], 200, true);
      assert.match(result.rag_answer, /Alfa/);
      assert.equal(await page.locator('#error').isVisible(), false);
      await page.screenshot({path: evidencePath('reintento.png'), fullPage: true});
      fs.writeFileSync(process.env.EVIDENCE_DIR ? evidencePath('resultados.json') : path.join(outputDir, '../S04-ui-018.json'), JSON.stringify({error: failure, retry: result, question_preserved: true, empty_posts: 0, loading_verified: true}, null, 2));
      console.log('018 OK: error, misma pregunta, reintento, carga y ambas respuestas');
    } else {
      const results = [];
      for (const question of datasetMode ? dataset : demoMode ? [dataset[0], dataset[3]] : [dataset[0]]) {
        await page.selectOption('#patient', String(question.patient_id));
        await page.fill('#question', question.question);
        const result = await send(question, 200, true);
        assert.ok(result.direct_answer.trim());
        assert.ok(result.rag_answer.toLowerCase().includes(question.expected.toLowerCase()));
        assert.equal(result.sources.length, 2);
        assert.ok(result.sources.every(source => source.patient_id === question.patient_id));
        assert.equal(await page.locator('#direct').textContent(), result.direct_answer);
        assert.equal(await page.locator('#rag').textContent(), result.rag_answer);
        assert.deepEqual(await page.locator('#sources li').allTextContents(),
          result.sources.map(source => `${source.source} / ${source.section}`));
        const patientName = await page.locator('#patient option:checked').textContent();
        assert.equal(await page.locator('#used-question').textContent(),
          `Paciente consultado: ${patientName}. Pregunta enviada: ${question.question}`);
        assert.ok(await page.getByRole('heading', {name: 'Sin RAG', exact: true}).isVisible());
        assert.ok(await page.getByRole('heading', {name: 'Con RAG', exact: true}).isVisible());
        await page.screenshot({path: evidencePath(`caso-${results.length + 1}.png`), fullPage: true});
        results.push({...question, ...result});
        console.log(`OK ID ${question.patient_id}: ${question.expected}, fuentes correctas`);
      }
      fs.writeFileSync(process.env.EVIDENCE_DIR ? evidencePath('resultados.json') : path.join(outputDir, '../S04-ui-019.json'), JSON.stringify(results, null, 2));
    }
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
