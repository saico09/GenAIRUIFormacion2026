// Sólo lee pacientes/historia y abre un formulario sin enviarlo.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const base = (process.env.PYTHON_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const output = path.resolve(process.env.EVIDENCE_DIR || path.join(__dirname, '../evidencias/pacientes-unificados-2026-11-07/ui-visual'));

async function main() {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const writes = [];
  page.on('request', req => { if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method())) writes.push({method: req.method(), url: req.url()}); });
  try {
    await page.goto(base + '/#pacientes');
    await page.locator('#patients-body [data-patient-id="1"] [data-action="history"]').click();
    await page.waitForFunction(() => document.querySelector('#patient-detail').getAttribute('aria-busy') === 'false');
    const buttons = page.locator('#history-body .row-actions button');
    assert.ok(await buttons.count() >= 2);
    async function oneLineButtons() {
      return buttons.evaluateAll(elements => elements.every(button => {
        const range = document.createRange(); range.selectNodeContents(button);
        const rects = [...range.getClientRects()];
        return rects.length === 1 && rects[0].width <= button.clientWidth;
      }));
    }
    assert.equal(await oneLineButtons(), true, 'Las etiquetas de acciones deben caber en una línea');
    const panel = page.locator('#history-table').locator('xpath=ancestor::div[contains(@class,"history-panel")]');
    await panel.screenshot({path: path.join(output, 'tabla-desktop.png')});
    await page.setViewportSize({width: 390, height: 844});
    await page.locator('#history-table').locator('..').evaluate(element => { element.scrollLeft = element.scrollWidth; });
    assert.equal(await oneLineButtons(), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await panel.screenshot({path: path.join(output, 'acciones-mobile.png')});
    await page.locator('#new-disease').click();
    await page.locator('#disease-form').screenshot({path: path.join(output, 'formulario-mobile.png')});
    assert.deepEqual(writes, []);
    fs.writeFileSync(path.join(output, 'resultados.json'), JSON.stringify({passed: true, checked_at: new Date().toISOString(),
      actions_single_line: true, mobile_width: 390, mobile_table_scroll: true, writes, screenshots: ['tabla-desktop.png', 'acciones-mobile.png', 'formulario-mobile.png']}, null, 2) + '\n');
    console.log(`PASS Acciones legibles, tabla móvil desplazable y formulario sin escrituras: ${output}`);
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
