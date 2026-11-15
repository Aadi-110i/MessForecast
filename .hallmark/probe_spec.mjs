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
await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle0' });
await page.type('#id_username', 'sysadmin');
await page.type('#id_password', 'messdemo');
await Promise.all([
  page.waitForNavigation({ waitUntil: 'networkidle0' }),
  page.click('button[type=submit]'),
]);
await page.goto(`${BASE}/console/settings/`, { waitUntil: 'networkidle0' });

const out = await page.evaluate(() => {
  const rows = [...document.querySelectorAll('.c-spec')].slice(0, 4);
  const styles = getComputedStyle(document.querySelector('.c-spec'));
  const valueStyle = getComputedStyle(document.querySelector('.c-spec-value'));
  const listRow = document.querySelector('.c-list > li > div');
  return {
    specDisplay: styles.display,
    specCols: styles.gridTemplateColumns,
    specWidth: styles.width,
    valueFont: valueStyle.fontSize,
    valueFamily: valueStyle.fontFamily,
    valueDisplay: valueStyle.display,
    listDisplay: listRow ? getComputedStyle(listRow).display : null,
    listCols: listRow ? getComputedStyle(listRow).gridTemplateColumns : null,
    rows: rows.map((r) => {
      const name = r.querySelector('.c-spec-name');
      const val = r.querySelector('.c-spec-value');
      return {
        name: name ? name.textContent.trim() : null,
        value: val ? val.textContent.trim() : null,
        nameBox: name ? name.getBoundingClientRect().toJSON() : null,
        valBox: val ? val.getBoundingClientRect().toJSON() : null,
        rowBox: r.getBoundingClientRect().toJSON(),
      };
    }),
  };
});
console.log(JSON.stringify(out, null, 2));
await browser.close();
