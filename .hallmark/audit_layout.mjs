/**
 * A layout audit across every screen.
 *
 * It reports three things that a screenshot hides:
 *   1. a table that is wider than its scroll box (a column the reader cannot reach)
 *   2. any element whose content is wider than the viewport (a sideways scrollbar)
 *   3. any element that overflows its own box horizontally
 */

import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(HERE, 'noop.js'));
const puppeteer = require(join(HERE, 'rendertools', 'node_modules', 'puppeteer-core'));

const BASE = process.env.BASE || 'http://127.0.0.1:8414';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const PAGES = [
  ['admin-dashboard', '/dashboard/', 1440],
  ['forecast', '/console/forecast/', 1440],
  ['attendance', '/console/attendance/', 1440],
  ['menus', '/console/menus/', 1440],
  ['menu-detail', '/console/menus/46/', 1440],
  ['recipes', '/console/recipes/', 1440],
  ['recipe-detail', '/console/recipes/311/', 1440],
  ['dishes', '/console/dishes/', 1440],
  ['planning', '/dashboard/planning/', 1440],
  ['waste', '/dashboard/waste/', 1440],
  ['reports', '/console/reports/', 1440],
  ['settings', '/console/settings/', 1440],
  ['codes', '/accounts/codes/', 1440],
  ['design-system', '/console/design-system/', 1440],
  ['data-quality', '/dashboard/data-quality/', 1440],
  ['kitchen', '/kitchen/', 1024],
  ['kitchen-actuals', '/kitchen/actuals/5132/', 1024],
  ['capture', '/scan/', 1024],
  ['admin-narrow', '/dashboard/', 390],
  ['forecast-narrow', '/console/forecast/', 390],
  ['kitchen-narrow', '/kitchen/', 768],
  ['landing', '/landing/', 1440],
  ['landing-narrow', '/landing/', 390],
  ['capture-narrow', '/scan/', 390],
];

const AUDIT = () => {
  const out = { wideTables: [], pageOverflow: [], clipped: [], pageScroll: null, misaligned: [], labelOverflow: [] };
  const vw = document.documentElement.clientWidth;

  // A page that scrolls sideways is a defect. A table inside a scroll box is not.
  out.pageScroll =
    document.documentElement.scrollWidth > vw + 1
      ? { scrollWidth: document.documentElement.scrollWidth, vw }
      : null;

  for (const wrap of document.querySelectorAll('.table-wrap')) {
    const table = wrap.querySelector('table');
    if (!table) continue;
    if (table.scrollWidth > wrap.clientWidth + 1) {
      out.wideTables.push({
        table: table.className,
        tableWidth: table.scrollWidth,
        boxWidth: wrap.clientWidth,
        over: table.scrollWidth - wrap.clientWidth,
        head: [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim()),
      });
    }
  }

  // An element that spills past the viewport and is not inside a scroll box.
  const inScroller = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      const ov = getComputedStyle(p).overflowX;
      if (ov === 'auto' || ov === 'scroll' || ov === 'hidden') return true;
    }
    return false;
  };
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right > vw + 1 && !inScroller(el)) {
      out.pageOverflow.push({
        tag: el.tagName.toLowerCase(),
        cls: el.className && el.className.toString().slice(0, 60),
        right: Math.round(r.right),
        vw,
      });
    }
  }

  // Text that is cut off inside its own box.
  for (const el of document.querySelectorAll('.ledger td, .ledger th, .c-spec-name, .c-spec-value, .k-brief-line, .sv-goal, .btn, .chip')) {
    if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== 'visible') {
      out.clipped.push({
        tag: el.tagName.toLowerCase(),
        cls: el.className && el.className.toString().slice(0, 40),
        text: el.textContent.trim().slice(0, 40),
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      });
    }
  }

  // A column whose header and its cells disagree about which way they face.
  out.misaligned = [];
  for (const table of document.querySelectorAll('table.ledger')) {
    const heads = [...table.querySelectorAll('thead th')];
    const row = table.querySelector('tbody tr');
    if (!row) continue;
    const cells = [...row.children];
    heads.forEach((th, i) => {
      const td = cells[i];
      if (!td) return;
      const a = getComputedStyle(th).textAlign;
      const b = getComputedStyle(td).textAlign;
      if (a !== b) {
        out.misaligned.push({
          table: table.className,
          column: th.textContent.trim(),
          headAlign: a,
          cellAlign: b,
          cell: td.textContent.trim().slice(0, 24),
        });
      }
    });
  }
  out.misaligned = out.misaligned.slice(0, 12);

  // A label that overflows its own grid track and collides with the value.
  out.labelOverflow = [];
  for (const el of document.querySelectorAll('.c-spec-name, .c-list dt')) {
    const cell = el.parentElement;
    if (!cell) continue;
    const cellBox = cell.getBoundingClientRect();
    const labelBox = el.getBoundingClientRect();
    if (labelBox.width > cellBox.width + 1) {
      out.labelOverflow.push({
        cls: el.className || el.tagName.toLowerCase(),
        text: el.textContent.trim().slice(0, 40),
        labelWidth: Math.round(labelBox.width),
        cellWidth: Math.round(cellBox.width),
      });
    }
  }
  out.labelOverflow = out.labelOverflow.slice(0, 12);

  out.pageOverflow = out.pageOverflow.slice(0, 12);
  out.clipped = out.clipped.slice(0, 12);
  return out;
};

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

let problems = 0;
for (const [name, path, width] of PAGES) {
  await page.setViewport({ width, height: width < 500 ? 844 : 900 });
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle0' });
  const result = await page.evaluate(AUDIT);
  const count =
    result.wideTables.length +
    result.pageOverflow.length +
    result.clipped.length +
    result.misaligned.length +
    result.labelOverflow.length +
    (result.pageScroll ? 1 : 0);
  problems += count;
  if (count === 0) {
    console.log(`  ok    ${name} (${width})`);
    continue;
  }
  console.log(`  ISSUE ${name} (${width})`);
  if (result.pageScroll) {
    console.log(`      page scrolls sideways: ${result.pageScroll.scrollWidth} > ${result.pageScroll.vw}`);
  }
  for (const t of result.wideTables) {
    console.log(
      `      wide table: ${t.table} ${t.tableWidth} > ${t.boxWidth} (over ${t.over}) cols=${t.head.join(' | ')}`,
    );
  }
  for (const o of result.pageOverflow) {
    console.log(`      overflow: <${o.tag} class="${o.cls}"> right=${o.right} vw=${o.vw}`);
  }
  for (const c of result.clipped) {
    console.log(`      clipped: <${c.tag} class="${c.cls}"> "${c.text}" ${c.scrollWidth}>${c.clientWidth}`);
  }
  for (const l of result.labelOverflow) {
    console.log(
      `      label overflow: <${l.cls}> "${l.text}" ${l.labelWidth}>${l.cellWidth}`,
    );
  }
  for (const m of result.misaligned) {
    console.log(
      `      misaligned: column "${m.column}" head=${m.headAlign} cell=${m.cellAlign} ("${m.cell}")`,
    );
  }
}

console.log(problems === 0 ? 'clean' : `${problems} problems`);
await browser.close();
