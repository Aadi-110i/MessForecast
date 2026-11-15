/**
 * Check the two fixes that a screenshot alone cannot prove:
 *   1. the two figures on the capture screen never run into each other
 *   2. the top bar on a phone never runs past the edge of the screen
 */
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(HERE, 'noop.js'));
const puppeteer = require(join(HERE, 'rendertools', 'node_modules', 'puppeteer-core'));

const BASE = process.env.BASE || 'http://127.0.0.1:8010';
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

let bad = 0;

console.log('--- capture screen: the two figures beside each other ---');
for (const width of [390, 768, 1024, 1440]) {
  await page.setViewport({ width, height: width < 500 ? 844 : 1024 });
  await page.goto(`${BASE}/scan/`, { waitUntil: 'networkidle0' });
  const r = await page.evaluate(() => {
    const stamps = document.querySelector('.k-stamps');
    const counts = [...stamps.querySelectorAll('.k-count')];
    // The widest value a real service reaches.
    counts[0].textContent = '1403';
    counts[1].textContent = '1800';
    const boxes = counts.map((c) => {
      const b = c.getBoundingClientRect();
      const cell = c.closest('.k-stamp').getBoundingClientRect();
      const pad = parseFloat(getComputedStyle(c.closest('.k-stamp')).paddingRight);
      return {
        text: c.textContent,
        fontSize: getComputedStyle(c).fontSize,
        textW: Math.round(c.scrollWidth),
        cellW: Math.round(cell.width - pad),
        spillsCell: c.scrollWidth > c.clientWidth + 0.5,
      };
    });
    const b0 = counts[0].getBoundingClientRect();
    const b1 = counts[1].getBoundingClientRect();
    const overlap = b0.right > b1.left + 0.5;
    const sameRow = Math.abs(b0.top - b1.top) < 2;
    return {
      cols: getComputedStyle(stamps).gridTemplateColumns,
      boxes,
      overlap,
      sameRow,
    };
  });
  const ok = !r.boxes.some((b) => b.spillsCell) && !(r.overlap && r.sameRow);
  if (!ok) bad++;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${width}px  cols=${r.cols}  overlap=${r.overlap} sameRow=${r.sameRow}`);
  for (const b of r.boxes) {
    console.log(`        "${b.text}" font=${b.fontSize} text=${b.textW}px cell=${b.cellW}px spills=${b.spillsCell}`);
  }
}

console.log('--- top bar on a phone ---');
for (const width of [360, 390, 480]) {
  await page.setViewport({ width, height: 844 });
  await page.goto(`${BASE}/dashboard/`, { waitUntil: 'networkidle0' });
  const r = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const ub = document.querySelector('.userbox');
    const buttons = [...document.querySelectorAll('.userbox .btn')];
    return {
      vw,
      userboxRight: Math.round(ub.getBoundingClientRect().right),
      buttons: buttons.map((b) => ({
        label: b.textContent.trim(),
        right: Math.round(b.getBoundingClientRect().right),
        width: Math.round(b.getBoundingClientRect().width),
        reachable: b.getBoundingClientRect().right <= vw + 1,
      })),
    };
  });
  const ok = r.buttons.every((b) => b.reachable) && r.userboxRight <= r.vw + 1;
  if (!ok) bad++;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${width}px  vw=${r.vw} userboxRight=${r.userboxRight}`);
  for (const b of r.buttons) {
    console.log(`        "${b.label}" right=${b.right} width=${b.width} reachable=${b.reachable}`);
  }
}

console.log(bad === 0 ? 'clean' : `${bad} problems`);
await browser.close();
