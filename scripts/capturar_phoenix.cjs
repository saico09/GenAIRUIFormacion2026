// Abre una traza real por su id y comprueba la correlación visible antes de capturar.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const input = process.argv[2];
  if (!input) throw new Error('Indica el JSON de evidencia con url, trace_id y request_id');
  const evidence = JSON.parse(fs.readFileSync(input, 'utf8'));
  const directory = process.env.EVIDENCE_DIR || path.dirname(input);
  const prefix = process.env.EVIDENCE_PREFIX || path.basename(input).split('-')[0];
  fs.mkdirSync(directory, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.EDGE_PATH ||
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1700, height: 1100 } });
    await page.goto(evidence.url, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: 'Attributes', exact: true }).click();
    await page.getByText(evidence.request_id, { exact: false }).waitFor();
    if (!(await page.locator('body').innerText()).includes(evidence.trace_id)) {
      throw new Error('No aparece el trace_id esperado');
    }
    const screenshot = `${prefix}-phoenix.png`;
    const children = evidence.spans.filter(span => span.parent_id);
    for (const name of children.map(span => span.name)) {
      await page.getByText(name, { exact: true }).waitFor();
    }
    await page.screenshot({ path: path.join(directory, screenshot), fullPage: true });
    const views = { url: evidence.url, resolved_url: page.url(), screenshot };
    const prompt = children.find(span => span.name === 'prompt');
    if (prompt) {
      await page.setViewportSize({ width: 1700, height: 1600 });
      await page.getByRole('button').filter({ has: page.getByText('prompt', { exact: true }) }).click();
      await page.getByText(prompt.context.span_id, { exact: false }).waitFor();
      await page.getByRole('tab', { name: 'Info', exact: true }).click();
      const text = await page.locator('body').innerText();
      for (const source of evidence.response.sources) {
        if (!text.includes(source.text)) throw new Error('No aparece un fragmento en la entrada del prompt');
      }
      views.prompt_screenshot = `${prefix}-prompt.png`;
      views.prompt_url = page.url();
      await page.screenshot({ path: path.join(directory, views.prompt_screenshot), fullPage: true });
    }
    fs.writeFileSync(path.join(directory, `${prefix}-phoenix-ui.json`), JSON.stringify({
      request_id: evidence.request_id, trace_id: evidence.trace_id,
      ...views,
    }, null, 2) + '\n');
    console.log(`OK traza ${evidence.trace_id} con request_id visible en Phoenix`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
