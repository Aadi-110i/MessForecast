/**
 * Capture every Phase 2 screen at the widths that matter.
 *
 * The console is read at 1440, which is the width a manager works at. The
 * kitchen tablet is captured at 1024, the size of the wall-mounted screen
 * in the kitchen, because that is the width its layout is designed for.
 */

import { mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(HERE, 'noop.js'));
const puppeteer = require(join(HERE, 'rendertools', 'node_modules', 'puppeteer-core'));

const BASE = 'http://127.0.0.1:8414';
const OUT = join(HERE, 'phase2');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

/* The auth screens are read signed out. They are captured before the sign in
 * below, otherwise the register view redirects to the dashboard. */
const AUTH_SCREENS = [
  ['login', '/accounts/login/', 1440, 900],
  ['register', '/accounts/register/', 1440, 900],
];

const CONSOLE_SCREENS = [
  ['admin-dashboard', '/dashboard/', 1440, 900],
  ['forecast-dashboard', '/console/forecast/', 1440, 900],
  ['attendance', '/console/attendance/', 1440, 900],
  ['menu-management', '/console/menus/', 1440, 900],
  ['menu-cycle-detail', '/console/menus/46/', 1440, 900],
  ['recipe-management', '/console/recipes/', 1440, 900],
  ['recipe-detail', '/console/recipes/311/', 1440, 900],
  ['dish-management', '/console/dishes/', 1440, 900],
  ['preparation-planning', '/dashboard/planning/', 1440, 900],
  ['waste-analytics', '/dashboard/waste/', 1440, 900],
  ['reports', '/console/reports/', 1440, 900],
  ['settings', '/console/settings/', 1440, 900],
  ['registration-codes', '/accounts/codes/', 1440, 900],
  ['component-library', '/console/design-system/', 1440, 900],
  ['data-quality', '/dashboard/data-quality/', 1440, 900],
];

const FULL_PAGES = [
  ['admin-dashboard-full', '/dashboard/'],
  ['forecast-dashboard-full', '/console/forecast/'],
  ['menu-management-full', '/console/menus/'],
  ['recipe-detail-full', '/console/recipes/311/'],
  ['attendance-full', '/console/attendance/'],
  ['component-library-full', '/console/design-system/'],
];

const TABLET_SCREENS = [
  ['kitchen-dashboard', '/kitchen/', 1024, 768],
  ['kitchen-actuals', '/kitchen/actuals/5132/', 1024, 768],
  ['capture', '/scan/', 1024, 768],
];

const NARROW_SCREENS = [
  ['admin-dashboard-narrow', '/dashboard/', 390, 844],
  ['forecast-narrow', '/console/forecast/', 390, 844],
  ['kitchen-dashboard-narrow', '/kitchen/', 768, 1024],
];

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function signIn(page) {
  await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle0' });
  await page.type('#id_username', 'sysadmin');
  await page.type('#id_password', 'messdemo');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle0' }),
    page.click('button[type=submit]'),
  ]);
}

async function capture(page, name, path, width, height, full) {
  await page.setViewport({ width, height });
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle0' });
  await wait(500);
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: full });
  console.log(`  ${name.padEnd(30)} ${width}x${height} ${full ? 'full' : 'fold'}`);
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-color-profile=srgb'],
  });
  const page = await browser.newPage();

  console.log('capturing the auth screens, signed out:');
  for (const [name, path, width, height] of AUTH_SCREENS) {
    await capture(page, name, path, width, height, false);
  }

  console.log('capturing the console:');
  await signIn(page);
  for (const [name, path, width, height] of CONSOLE_SCREENS) {
    await capture(page, name, path, width, height, false);
  }
  for (const [name, path] of FULL_PAGES) {
    await capture(page, name, path, 1440, 900, true);
  }

  console.log('capturing the tablet:');
  for (const [name, path, width, height] of TABLET_SCREENS) {
    await capture(page, name, path, width, height, false);
  }

  console.log('capturing narrow:');
  for (const [name, path, width, height] of NARROW_SCREENS) {
    await capture(page, name, path, width, height, false);
  }

  await browser.close();
  console.log('done');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
