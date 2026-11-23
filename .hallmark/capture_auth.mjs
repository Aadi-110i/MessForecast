/**
 * Capture the sign-in and register screens, and the states they can be in.
 */
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(HERE, 'noop.js'));
const puppeteer = require(join(HERE, 'rendertools', 'node_modules', 'puppeteer-core'));

const BASE = process.env.BASE || 'http://127.0.0.1:8010';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const OUT = join(HERE, 'shots', 'auth');
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage();

// The service worker keeps the stylesheet it cached, so a capture taken
// straight after a change would show the old one. Clear it first.
await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle0' });
await page.evaluate(async () => {
  const regs = await navigator.serviceWorker.getRegistrations();
  for (const r of regs) await r.unregister();
  for (const k of await caches.keys()) await caches.delete(k);
});

async function shot(name, path, width, height, full = true) {
  await page.setViewport({ width, height });
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle0' });
  // The page arrives in stages: the last piece of the ticket is drawn at
  // 0.6s and takes 0.95s to settle, so the capture waits for the page to
  // stop moving rather than for the network to go quiet.
  await new Promise((r) => setTimeout(r, 1800));
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: full });
  console.log('shot', name);
}

// The sign-in screen, at the sizes it is read at.
await shot('1-signin-desktop', '/accounts/login/', 1440, 900);
await shot('2-signin-narrow', '/accounts/login/', 390, 844);
await shot('3-signin-tablet', '/accounts/login/', 820, 1180);

// The register screen.
await shot('4-register-desktop', '/accounts/register/', 1440, 900);
await shot('5-register-narrow', '/accounts/register/', 390, 844);

// The sign-in screen with a refusal on it.
await page.setViewport({ width: 1440, height: 900 });
await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle0' });
await page.type('#id_username', 'manager');
await page.type('#id_password', 'wrong-password');
await Promise.all([
  page.waitForNavigation({ waitUntil: 'networkidle0' }),
  page.click('button[type=submit]'),
]);
await new Promise((r) => setTimeout(r, 700));
await page.screenshot({ path: join(OUT, '6-signin-refused.png'), fullPage: true });
console.log('shot 6-signin-refused');

// The register screen with a refusal on the code field.
await page.setViewport({ width: 1440, height: 900 });
await page.goto(`${BASE}/accounts/register/`, { waitUntil: 'networkidle0' });
await page.type('#id_code', 'ZZZZ-9999');
await page.type('#id_username', 'newcomer');
await page.type('#id_password', 'longenoughpassword');
await page.type('#id_password_confirm', 'longenoughpassword');
await page.click('#register-submit');
await new Promise((r) => setTimeout(r, 1200));
await page.screenshot({ path: join(OUT, '7-register-refused.png'), fullPage: true });
console.log('shot 7-register-refused');

await browser.close();
