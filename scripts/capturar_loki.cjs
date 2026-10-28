// Abre en Explore las consultas verificadas de un JSON de evidencia y guarda sus URLs/capturas.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const input = process.argv[2] || 'evidencias/s07/031-loki.json';
  const evidence = JSON.parse(fs.readFileSync(input, 'utf8'));
  const directory = process.env.EVIDENCE_DIR || path.dirname(input);
  const prefix = process.env.EVIDENCE_PREFIX || path.basename(input).split('-')[0];
  fs.mkdirSync(directory, { recursive: true });
  const setting = fs.readFileSync('.env', 'utf8').split(/\r?\n/)
    .find(line => line.startsWith('GRAFANA_ADMIN_PASSWORD='));
  if (!setting) throw new Error('Falta la contraseña de Grafana');
  const browser = await chromium.launch({ executablePath: process.env.EDGE_PATH ||
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1600, height: Number(process.env.SCREENSHOT_HEIGHT || 1500) },
    });
    await page.goto('http://localhost:3000/login');
    await page.locator('input[name="user"]').fill('admin');
    await page.locator('input[name="password"]').fill(setting.slice('GRAFANA_ADMIN_PASSWORD='.length));
    await page.getByRole('button', { name: 'Log in', exact: true }).click();
    await page.waitForURL(url => !url.pathname.includes('login'));
    const views = [];
    for (const check of evidence.checks) {
      const pane = { a: { datasource: 'loki', queries: [{ refId: 'A', expr: check.query,
        queryType: 'range', datasource: { uid: 'loki', type: 'loki' } }],
        range: { from: String(Date.parse(check.start_utc)), to: String(Date.parse(check.end_utc)) } } };
      const url = 'http://localhost:3000/explore?' + new URLSearchParams({
        panes: JSON.stringify(pane), schemaVersion: '1', orgId: '1',
      });
      await page.goto(url);
      await page.getByText(`${check.logs.length} lines displayed`, { exact: false }).waitFor();
      const text = await page.locator('body').innerText();
      for (const event of check.logs) {
        if (!text.includes(event.request_id)) throw new Error(`No se ve ${event.request_id} en Explore`);
      }
      const file = `${prefix}-${check.name || check.service}.png`;
      await page.screenshot({ path: path.join(directory, file), fullPage: true });
      views.push({ query: check.query, url, screenshot: file, lines: check.logs.length });
    }
    fs.writeFileSync(path.join(directory, `${prefix}-explore.json`), JSON.stringify(views, null, 2) + '\n');
    console.log(`OK ${views.length} consultas visibles en Explore con sus request_id`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
