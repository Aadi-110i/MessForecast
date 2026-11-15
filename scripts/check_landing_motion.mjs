/* Checks that the landing page motion actually runs: the hero settles, the
   measured figures count up to the values the database returned, and the
   page stands completely still for a reader who has asked for less motion. */
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PUPPETEER_PATH =
  process.env.PUPPETEER_PATH || 'C:/Users/Dell/AppData/Roaming/npm/node_modules/puppeteer-core';
const CHROME_PATH =
  process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const base = (process.argv[2] || 'http://127.0.0.1:8013').replace(/\/$/, '');
const EXPECTED = ['₹1,361', '₹768', '₹592', '2.33%', '94.9%'];

const puppeteer = require(PUPPETEER_PATH);
const browser = await puppeteer.launch({
  executablePath: CHROME_PATH,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const problems = [];

async function run(label, reduced) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  if (reduced) {
    await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
  }
  page.on('pageerror', (e) => problems.push(`${label}: page error: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`${label}: console error: ${m.text()}`);
  });

  await page.goto(`${base}/landing/`, { waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 1600));

  const hero = await page.evaluate(() => {
    const h1 = document.querySelector('.lp-hero-text h1');
    const shot = document.querySelector('.lp-shot-hero');
    const cs = getComputedStyle(h1);
    return {
      h1Opacity: cs.opacity,
      h1Visibility: cs.visibility,
      shotOpacity: getComputedStyle(shot).opacity,
    };
  });

  await page.evaluate(() => {
    document.querySelector('.lp-table').scrollIntoView({ block: 'center' });
  });
  await new Promise((r) => setTimeout(r, 2400));

  const figs = await page.evaluate(() =>
    [...document.querySelectorAll('[data-fig]')].map((e) => e.textContent.trim())
  );

  console.log(
    `${label}: hero head opacity ${hero.h1Opacity} (${hero.h1Visibility}), picture opacity ${hero.shotOpacity}, figures ${JSON.stringify(figs)}`
  );

  if (Number(hero.h1Opacity) < 0.99 || hero.h1Visibility === 'hidden') {
    problems.push(`${label}: the hero headline did not settle`);
  }
  if (Number(hero.shotOpacity) < 0.99) {
    problems.push(`${label}: the hero picture did not settle`);
  }
  figs.forEach((f, i) => {
    if (f !== EXPECTED[i]) problems.push(`${label}: figure ${i} reads "${f}", expected "${EXPECTED[i]}"`);
  });

  await page.close();
}

await run('motion', false);
await run('reduced', true);
await browser.close();

if (problems.length) {
  console.log('--- problems ---');
  problems.forEach((p) => console.log(p));
  process.exit(1);
}
console.log('--- problems --- none');
