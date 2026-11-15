/**
 * Measure what overflows a page at a given width.
 * Usage: node scripts/measure_overflow.mjs <path> [width]
 */
import { createRequire } from 'node:module';
import { join } from 'node:path';

const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER_PATH || 'C:/Users/Dell/AppData/Roaming/npm/node_modules/puppeteer-core');
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const BASE = (process.env.MF_BASE || 'http://127.0.0.1:8013').replace(/\/$/, '');
const path = process.argv[2] || '/accounts/login/';
const width = parseInt(process.argv[3] || '375', 10);

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width, height: 800 });
await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle0' });
if (path !== '/accounts/login/') {
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle0' });
}

const report = await page.evaluate((vw) => {
  const out = [];
  const chain = [];
  let node = document.querySelector('main.page');
  while (node) {
    const r = node.getBoundingClientRect();
    const cs = getComputedStyle(node);
    chain.push({
      sel: `${node.tagName.toLowerCase()}${node.id ? '#' + node.id : ''}${typeof node.className === 'string' && node.className ? '.' + node.className.trim().split(/\s+/).join('.') : ''}`,
      left: Math.round(r.left),
      width: Math.round(r.width),
      cssWidth: cs.width,
      display: cs.display,
      minWidth: cs.minWidth,
      paddingInline: cs.paddingLeft + '/' + cs.paddingRight,
      marginInline: cs.marginLeft + '/' + cs.marginRight,
      flex: cs.flex,
      overflowX: cs.overflowX,
    });
    node = node.parentElement;
  }
  const walk = (el, depth) => {
    const r = el.getBoundingClientRect();
    if (r.right > vw + 0.5 || r.width > vw + 0.5) {
      out.push({
        depth,
        sel: `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : ''}`,
        left: Math.round(r.left),
        right: Math.round(r.right),
        width: Math.round(r.width),
        scrollWidth: el.scrollWidth,
      });
    }
    if (depth < 6) {
      for (const c of el.children) walk(c, depth + 1);
    }
  };
  walk(document.documentElement, 0);
  return {
    docScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    innerWidth: window.innerWidth,
    chain,
    offenders: out.slice(0, 25),
  };
}, width);

console.log(JSON.stringify(report, null, 2));
await browser.close();
