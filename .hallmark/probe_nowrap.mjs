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
  const cell = document.querySelector('.ledger .nowrap');
  const hallCell = [...document.querySelectorAll('.ledger td')].find((td) =>
    td.textContent.includes('North Block Mess'),
  );
  const wrap = (hallCell || {}).closest ? hallCell.closest('.table-wrap') : null;
  const table = wrap ? wrap.querySelector('table') : null;
  const cs = hallCell ? getComputedStyle(hallCell) : null;
  return {
    url: location.pathname,
    foundBySelector: !!cell,
    hallCellHTML: hallCell ? hallCell.outerHTML : null,
    hallCellClass: hallCell ? hallCell.className : null,
    whiteSpace: cs ? cs.whiteSpace : null,
    wordBreak: cs ? cs.wordBreak : null,
    overflowWrap: cs ? cs.overflowWrap : null,
    cellWidth: hallCell ? Math.round(hallCell.getBoundingClientRect().width) : null,
    cellHeight: hallCell ? Math.round(hallCell.getBoundingClientRect().height) : null,
    tableWidth: table ? table.scrollWidth : null,
    wrapWidth: wrap ? wrap.clientWidth : null,
    matched: [...document.styleSheets].flatMap((s) => {
      try { return [...s.cssRules]; } catch (e) { return []; }
    }).filter((r) => r.selectorText && r.selectorText.includes('nowrap'))
      .map((r) => r.cssText.slice(0, 140)),
  };
});
console.log(JSON.stringify(out, null, 2));
await browser.close();
