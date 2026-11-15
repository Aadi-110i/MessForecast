/**
 * MessForecast — landing page product captures
 *
 * The Hallmark capture harness (scripts/hallmark_capture.mjs) writes whole
 * viewport screenshots for the sweep. The landing page needs tighter frames:
 * a single screen rather than the whole console, so that the hero visual is
 * the product doing its job and not a page of navigation.
 *
 * This script signs in with the demo account and captures a set of named
 * frames at 2x, each cropped to a selector on the page:
 *
 *   static/img/landing/overview.png     the reconciliation, the tally and the
 *                                       ledger, cropped to the page column
 *   static/img/landing/reconciliation.png  today's services, reconciled
 *   static/img/landing/brief.png        the kitchen brief and why this number
 *   static/img/landing/plan.png         the preparation plan and the indent
 *   static/img/landing/accuracy.png     forecast error by week
 *   static/img/landing/scan.png         attendance capture, at phone width
 *
 * Usage: node scripts/capture_landing_shots.mjs [--base http://127.0.0.1:8013]
 */

import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
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

const OUT = join(ROOT, 'static', 'img', 'landing');
mkdirSync(OUT, { recursive: true });

/**
 * Each shot is a route, a selector to crop to and the size to crop at. The
 * selector is captured as an element screenshot, so the frame is exactly the
 * product surface and nothing of the browser chrome comes with it.
 *
 * These are the three frames the landing page uses. Everything the page
 * claims is visible in the running product, never drawn.
 */
const SHOTS = [
  {
    // The bone brief on the kitchen tablet: why this number.
    name: 'brief',
    path: '/kitchen/?service=5126',
    selector: '.k-brief-inner',
    width: 1440,
    height: 900,
    max: 520,
  },
  {
    // Attendance capture on the phone at the gate.
    name: 'scan',
    path: '/scan/',
    selector: '.k-main, main.page, body',
    width: 390,
    height: 844,
    max: 660,
  },
  {
    // The kitchen tablet, at the size the tablet is actually held at. The
    // landing hero needs a portrait-or-square frame it can sit beside a
    // column of text, and this is the surface the product is built around.
    // The viewport is taller than the frame so the sticky action bar falls
    // outside the crop: the brief is the story, not the buttons.
    name: 'kitchen',
    path: '/kitchen/?service=5126',
    selector: 'body.k-shell',
    width: 1024,
    height: 900,
    max: 690,
  },
];

const problems = [];
const puppeteer = require(PUPPETEER_PATH);

const browser = await puppeteer.launch({
  executablePath: CHROME_PATH,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

try {
  const page = await browser.newPage();
  page.on('pageerror', (err) => problems.push(`page error: ${err.message}`));

  await page.setViewport({ width: 1440, height: 900 });
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

  for (const shot of SHOTS) {
    await page.setViewport({ width: shot.width, height: shot.height, deviceScaleFactor: 2 });
    const response = await page.goto(`${BASE}${shot.path}`, {
      waitUntil: 'networkidle0',
      timeout: 30000,
    });
    const status = response ? response.status() : 0;
    if (status !== 200) {
      problems.push(`${shot.name}: HTTP ${status} at ${shot.path}`);
      continue;
    }

    // Let the charts draw before the frame is taken.
    await page.evaluate(() => {
      if (window.MessForecast && window.MessForecast.drawCharts) {
        window.MessForecast.drawCharts();
      }
    });
    await new Promise((r) => setTimeout(r, 400));

    const handle = await page.$(shot.selector);
    if (!handle) {
      problems.push(`${shot.name}: selector "${shot.selector}" not found on ${shot.path}`);
      continue;
    }

    // An element screenshot fails on a very tall element, so the frame is
    // measured and clipped to a bounded rectangle instead.
    const box = await handle.boundingBox();
    if (!box) {
      problems.push(`${shot.name}: selector "${shot.selector}" has no box on ${shot.path}`);
      continue;
    }
    const max = shot.max || 900;
    const height = Math.min(box.height, max);
    const clip = {
      x: Math.max(0, box.x),
      y: Math.max(0, box.y),
      width: Math.min(box.width, shot.width),
      height,
    };
    await page.screenshot({ path: join(OUT, `${shot.name}.png`), clip });
    console.log(
      `captured ${shot.name} (${shot.path}, ${shot.selector}, ${Math.round(clip.width)}x${Math.round(height)})`
    );
  }
} finally {
  await browser.close();
}

console.log('\n--- problems ---');
if (problems.length === 0) {
  console.log('none');
} else {
  [...new Set(problems)].forEach((p) => console.log('  ' + p));
}
