// Ejecutar con NODE_PATH apuntando a Playwright; nunca imprime la clave de Grafana.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const directory = process.env.EVIDENCE_DIR || 'evidencias/s06';
  const prefix = process.env.EVIDENCE_PREFIX || '028';
  fs.mkdirSync(directory, { recursive: true });
  const setting = fs.readFileSync('.env', 'utf8').split(/\r?\n/)
    .find(line => line.startsWith('GRAFANA_ADMIN_PASSWORD='));
  if (!setting) throw new Error('Falta GRAFANA_ADMIN_PASSWORD en .env');
  const password = setting.slice('GRAFANA_ADMIN_PASSWORD='.length);
  const browser = await chromium.launch({
    executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    await page.goto('http://localhost:3000/login');
    await page.locator('input[name="user"]').fill('admin');
    await page.locator('input[name="password"]').fill(password);
    await page.getByRole('button', { name: 'Log in', exact: true }).click();
    await page.waitForURL(url => !url.pathname.includes('login'));
    await page.goto('http://localhost:3000/d/genai-apis/apis-genai?from=now-15m&to=now');
    await page.getByText('Latencia p95', { exact: true }).first().waitFor();
    const response = await page.request.get('http://localhost:3000/api/dashboards/uid/genai-apis');
    if (!response.ok()) throw new Error(`Dashboard HTTP ${response.status()}`);
    const { dashboard } = await response.json();
    const panels = dashboard.panels.filter(panel => panel.type === 'timeseries');
    if (panels.length !== 6) throw new Error('Se esperaban seis paneles');
    const values = [];
    for (const panel of panels) {
      const query = await page.request.post('http://localhost:3000/api/ds/query', {
        data: {
          from: String(Date.now() - 900000), to: String(Date.now()),
          queries: panel.targets.map(target => ({ ...target, intervalMs: 15000, maxDataPoints: 1000 })),
        },
      });
      if (!query.ok()) throw new Error(`Panel ${panel.id}: HTTP ${query.status()}`);
      const result = await query.json();
      const frames = result.results[panel.targets.at(-1).refId]?.frames || [];
      const numbers = frames.flatMap(frame => frame.data.values.slice(1).flat())
        .filter(value => typeof value === 'number' && Number.isFinite(value));
      if (!numbers.length) throw new Error(`Panel ${panel.id} sin valores finitos`);
      values.push({ panel: panel.id, title: panel.title, unit: panel.fieldConfig.defaults.unit, last: numbers.at(-1) });
    }
    await page.locator('canvas').first().waitFor();
    for (const [title, service] of [['FastAPI', 'fastapi'], ['Spring Boot', 'springboot']]) {
      const row = page.getByText(title, { exact: true }).first();
      await row.scrollIntoViewIfNeeded();
      const box = await row.boundingBox();
      const x = Math.max(0, box.x - 16);
      await page.screenshot({ path: path.join(directory, `${prefix}-${service}.png`),
        clip: { x, y: Math.max(0, box.y - 12), width: 1440 - x - 16, height: 350 } });
    }
    fs.writeFileSync(path.join(directory, `${prefix}-dashboard.json`), JSON.stringify(dashboard, null, 2) + '\n');
    fs.writeFileSync(path.join(directory, `${prefix}-paneles.json`), JSON.stringify({
      date: new Date().toISOString(), url: page.url(), values,
    }, null, 2) + '\n');
    console.log(JSON.stringify(values));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
