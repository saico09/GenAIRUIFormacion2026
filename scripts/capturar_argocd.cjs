// Captura el repositorio o la revisión ya comprobada por verificar_gitops.py.
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const input = process.argv[2];
  const repository = input === '--repo';
  if (!input) throw new Error('Indica --repo o el JSON guardado por verificar_gitops.py');
  const evidence = repository ? null : JSON.parse(fs.readFileSync(input, 'utf8'));
  const directory = process.env.EVIDENCE_DIR || (repository ? 'evidencias/s09' : path.dirname(input));
  const prefix = process.env.EVIDENCE_PREFIX || (repository ? '041' : path.basename(input).split('-')[0]);
  fs.mkdirSync(directory, { recursive: true });
  const secret = JSON.parse(execFileSync(path.resolve('.local/bin/kubectl.exe'), [
    '--context=genai', '-n', 'argocd', 'get', 'secret', 'argocd-initial-admin-secret', '-o', 'json',
  ], { encoding: 'utf8' }));
  const browser = await chromium.launch({ executablePath: process.env.EDGE_PATH ||
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    const page = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 1800, height: 1200 } });
    await page.goto('https://localhost:8443');
    await page.locator('input[name=username]').fill('admin');
    await page.locator('input[name=password]').fill(Buffer.from(secret.data.password, 'base64').toString());
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL(url => !url.pathname.includes('login'));
    await page.waitForFunction(() => !document.body.innerText.includes('Loading...'));
    if (repository) {
      await page.getByText('Settings', { exact: true }).click();
      await page.getByText('Repositories', { exact: true }).click();
      await page.locator('#app').getByText('Successful', { exact: false }).waitFor();
    } else {
      await page.goto('https://localhost:8443/applications/argocd/fastapi');
      await page.waitForFunction(commit => {
        const body = document.body.innerText;
        return body.includes(commit.slice(0, 7)) && body.includes('Synced') && body.includes('Healthy');
      }, evidence.commit);
    }
    const screenshot = `${prefix}-argocd.png`;
    await page.screenshot({ path: path.join(directory, screenshot), fullPage: true });
    fs.writeFileSync(path.join(directory, `${prefix}-ui.json`), JSON.stringify({
      checked_at: new Date().toISOString(), url: page.url(), login: true, screenshot,
      ...(repository ? { repository_connection: 'Successful' } : {
        commit: evidence.commit, health: 'Healthy', sync: 'Synced',
        expected_replicas: evidence.replicas, pods: evidence.pods.map(pod => pod.name),
      }),
    }, null, 2) + '\n');
    console.log(`OK interfaz Argo CD: ${page.url()}`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
