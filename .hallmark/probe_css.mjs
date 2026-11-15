import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(HERE, 'noop.js'));
const puppeteer = require(join(HERE, 'rendertools', 'node_modules', 'puppeteer-core'));

const BASE = 'http://127.0.0.1:8414';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });

// What does the server actually hand over for the stylesheet?
const css = await page.goto(`${BASE}/static/css/components.css`, { waitUntil: 'domcontentloaded' });
const body = await css.text();
const idx = body.indexOf('.c-spec-value {');
console.log('--- served components.css ---');
console.log(body.slice(idx, idx + 260));

await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle0' });
await page.type('#id_username', 'sysadmin');
await page.type('#id_password', 'messdemo');
await Promise.all([
  page.waitForNavigation({ waitUntil: 'networkidle0' }),
  page.click('button[type=submit]'),
]);
await page.goto(`${BASE}/console/settings/`, { waitUntil: 'networkidle0' });

const out = await page.evaluate(() => {
  const v = document.querySelector('.c-spec-value');
  const cs = getComputedStyle(v);
  const spec = getComputedStyle(v.parentElement);
  return {
    valueTextAlign: cs.textAlign,
    valueDisplay: cs.display,
    valueWidth: cs.width,
    specDisplay: spec.display,
    specCols: spec.gridTemplateColumns,
    specJustify: spec.justifyItems,
    childCount: v.parentElement.children.length,
    outerHTML: v.parentElement.outerHTML.slice(0, 300),
  };
});
console.log(JSON.stringify(out, null, 2));
await browser.close();
