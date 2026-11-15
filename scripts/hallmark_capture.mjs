/**
 * MessForecast — Hallmark visual capture
 *
 * The dashboard, kitchen and capture screens all sit behind a sign-in, so a
 * browser that just opens a URL lands on the login page. This script signs in
 * with the demo account, walks every route, and for each one writes:
 *
 *   .hallmark/render/<name>.html   the rendered DOM with asset links rewritten
 *                                  to absolute file:// paths, so the Hallmark
 *                                  render tier can analyse a page that is
 *                                  normally behind authentication
 *   .hallmark/shots/<name>.png     a screenshot at each viewport
 *
 * Console errors and failed requests are collected and printed at the end.
 *
 * Usage:  node scripts/hallmark_capture.mjs [--base http://127.0.0.1:8013]
 */

import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const PUPPETEER_PATH =
  process.env.PUPPETEER_PATH || 'C:/Users/Dell/AppData/Roaming/npm/node_modules/puppeteer-core';
const CHROME_PATH =
  process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const args = process.argv.slice(2);
const baseArg = args.indexOf('--base');
const BASE = (baseArg !== -1 ? args[baseArg + 1] : 'http://127.0.0.1:8013').replace(/\/$/, '');

const USERNAME = process.env.MF_USER || 'manager';
const PASSWORD = process.env.MF_PASS || 'messdemo';

const ROUTES = [
  { name: 'login', path: '/accounts/login/', auth: false },
  { name: 'overview', path: '/', auth: true },
  { name: 'waste', path: '/dashboard/waste/', auth: true },
  { name: 'accuracy', path: '/dashboard/accuracy/', auth: true },
  { name: 'planning', path: '/dashboard/planning/', auth: true },
  { name: 'data-quality', path: '/dashboard/data-quality/', auth: true },
  { name: 'kitchen', path: '/kitchen/', auth: true },
  { name: 'capture', path: '/scan/', auth: true },
];

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'mobile', width: 375, height: 812 },
];

const OUT_HTML = join(ROOT, '.hallmark', 'render');
const OUT_SHOTS = join(ROOT, '.hallmark', 'shots');
mkdirSync(OUT_HTML, { recursive: true });
mkdirSync(OUT_SHOTS, { recursive: true });

const problems = [];

const puppeteer = require(PUPPETEER_PATH);

const browser = await puppeteer.launch({
  executablePath: CHROME_PATH,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

try {
  const page = await browser.newPage();

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      problems.push(`console error: ${msg.text()}`);
    }
  });
  page.on('pageerror', (err) => problems.push(`page error: ${err.message}`));
  page.on('requestfailed', (req) => {
    const url = req.url();
    if (url.startsWith('data:')) return;
    problems.push(`request failed: ${url} (${req.failure()?.errorText})`);
  });

  // --- sign in ---------------------------------------------------------
  await page.setViewport(VIEWPORTS[0]);
  await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle0', timeout: 30000 });
  await page.type('#id_username', USERNAME);
  await page.type('#id_password', PASSWORD);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 30000 }),
    page.click('button[type="submit"]'),
  ]);
  if (page.url().includes('/accounts/login/')) {
    throw new Error('Sign-in failed: the login form returned to the login page.');
  }
  console.log(`signed in as ${USERNAME}`);

  // --- walk the routes --------------------------------------------------
  for (const route of ROUTES) {
    await page.setViewport(VIEWPORTS[0]);
    const response = await page.goto(`${BASE}${route.path}`, {
      waitUntil: 'networkidle0',
      timeout: 30000,
    });
    const status = response ? response.status() : 0;
    if (status !== 200) {
      problems.push(`${route.name}: HTTP ${status} at ${route.path}`);
    }

    // Wait for the charts to be drawn.
    await page.evaluate(() => {
      if (window.MessForecast && window.MessForecast.drawCharts) {
        window.MessForecast.drawCharts();
      }
    });
    await new Promise((r) => setTimeout(r, 350));

    // The rendered DOM, with asset links rewritten to relative paths so the
    // render tier can load the stylesheet, the fonts and the scripts from
    // disk and judge the page as it is actually served.
    const html = await page.evaluate(() => document.documentElement.outerHTML);
    const rewritten = html.replace(
      /((?:href|src)=")\/static\//g,
      `$1${relative(OUT_HTML, join(ROOT, 'static')).replace(/\\/g, '/')}/`
    );
    writeFileSync(join(OUT_HTML, `${route.name}.html`), rewritten, 'utf8');

    for (const vp of VIEWPORTS) {
      await page.setViewport({ width: vp.width, height: vp.height });
      await new Promise((r) => setTimeout(r, 250));
      await page.evaluate(() => {
        if (window.MessForecast && window.MessForecast.drawCharts) {
          window.MessForecast.drawCharts();
        }
      });
      await new Promise((r) => setTimeout(r, 150));
      await page.screenshot({
        path: join(OUT_SHOTS, `${route.name}-${vp.name}.png`),
        fullPage: false,
      });
    }

    // Horizontal overflow check at the narrowest width.
    await page.setViewport({ width: 320, height: 800 });
    await new Promise((r) => setTimeout(r, 250));
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      offenders: Array.from(document.querySelectorAll('body *'))
        .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1)
        .slice(0, 5)
        .map((el) => `${el.tagName.toLowerCase()}.${el.className || '(no class)'}`),
    }));
    if (overflow.scrollWidth > overflow.innerWidth + 1) {
      problems.push(
        `${route.name}: horizontal scroll at 320px (${overflow.scrollWidth} > ${overflow.innerWidth}) ` +
          `offenders: ${overflow.offenders.join(', ')}`
      );
    }

    console.log(`captured ${route.name} (HTTP ${status})`);

    // The kitchen picker links to one service; follow the first one so the
    // portion-entry screen, which is the screen the cook actually uses, is
    // captured too.
    if (route.name === 'kitchen') {
      const href = await page.evaluate(() => {
        const link = document.querySelector('a[href*="service="]');
        return link ? link.getAttribute('href') : null;
      });
      if (href) {
        await page.setViewport(VIEWPORTS[0]);
        await page.goto(`${BASE}${href}`, { waitUntil: 'networkidle0', timeout: 30000 });
        await new Promise((r) => setTimeout(r, 350));
        const serviceHtml = await page.evaluate(() => document.documentElement.outerHTML);
        const serviceRewritten = serviceHtml.replace(
          /((?:href|src)=")\/static\//g,
          `$1${relative(OUT_HTML, join(ROOT, 'static')).replace(/\\/g, '/')}/`
        );
        writeFileSync(join(OUT_HTML, 'kitchen-service.html'), serviceRewritten, 'utf8');
        for (const vp of VIEWPORTS) {
          await page.setViewport({ width: vp.width, height: vp.height });
          await new Promise((r) => setTimeout(r, 250));
          await page.screenshot({
            path: join(OUT_SHOTS, `kitchen-service-${vp.name}.png`),
            fullPage: false,
          });
        }
        console.log('captured kitchen-service');
      }
    }
  }
} finally {
  await browser.close();
}

console.log('\n--- console and network problems ---');
if (problems.length === 0) {
  console.log('none');
} else {
  const unique = [...new Set(problems)];
  unique.forEach((p) => console.log('  ' + p));
  console.log(`${unique.length} distinct problem(s)`);
}
