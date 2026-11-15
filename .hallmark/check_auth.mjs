/**
 * Check the sign-in and register screens against the rules that matter:
 * the refusals land in the right place, the focus is visible, the labels
 * are attached, and nothing moves when the reader has asked for less.
 */
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(HERE, 'noop.js'));
const puppeteer = require(join(HERE, 'rendertools', 'node_modules', 'puppeteer-core'));

const BASE = process.env.BASE || 'http://127.0.0.1:8010';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

let bad = 0;
function check(name, ok, detail) {
  if (!ok) bad++;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`);
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('  [pageerror]', e.message));

async function fresh(path, width = 1440) {
  await page.setViewport({ width, height: 900 });
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle0' });
  await page.evaluate(async () => {
    const regs = await navigator.serviceWorker.getRegistrations();
    for (const r of regs) await r.unregister();
    for (const k of await caches.keys()) await caches.delete(k);
  });
  await page.reload({ waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 500));
}

console.log('--- the sign-in screen ---');
await fresh('/accounts/login/');
let r = await page.evaluate(() => {
  const inputs = [...document.querySelectorAll('.auth-field input')];
  return {
    labels: inputs.map((i) => {
      const l = document.querySelector(`label[for="${i.id}"]`);
      return l ? l.textContent.trim() : null;
    }),
    autocomplete: inputs.map((i) => i.getAttribute('autocomplete')),
    types: inputs.map((i) => i.getAttribute('type')),
    names: inputs.map((i) => i.getAttribute('name')),
    h1: document.querySelectorAll('h1').length,
    landmarks: {
      header: !!document.querySelector('header'),
      main: !!document.querySelector('main'),
      footer: !!document.querySelector('footer'),
    },
    skip: !!document.querySelector('a.skip[href="#main"]'),
    mainId: (document.querySelector('main') || {}).id,
    errorRole: (document.querySelector('.auth-error') || {}).getAttribute ? document.querySelector('.auth-error') && document.querySelector('.auth-error').getAttribute('role') : null,
    spinnerExists: false,
  };
});
check('one h1', r.h1 === 1, `h1 count ${r.h1}`);
check('every input has a label', r.labels.every(Boolean), JSON.stringify(r.labels));
check('autocomplete set on every input', r.autocomplete.every(Boolean), JSON.stringify(r.autocomplete));
check('skip link points at the main', r.skip && r.mainId === 'main');
check('header and main landmarks present', r.landmarks.header && r.landmarks.main);

// The focus has to be visible: the bar and the rule under the field.
const focus = await page.evaluate(() => {
  const input = document.getElementById('id_username');
  input.focus();
  const field = input.closest('.auth-field');
  const cs = getComputedStyle(field, '::before');
  const after = getComputedStyle(field, '::after');
  return {
    barVisible: cs.transform !== 'none' && cs.backgroundColor !== 'rgba(0, 0, 0, 0)',
    barTransform: cs.transform,
    ruleTransform: after.transform,
    inputOutline: getComputedStyle(input).outlineStyle,
  };
});
check('focus shows the bar', focus.barVisible, focus.barTransform);
check('focus draws the rule', focus.ruleTransform !== 'none', focus.ruleTransform);
check('the input ring is replaced, not lost', focus.inputOutline === 'none');

// A refusal has to say what to do next, next to the fields.
await page.type('#id_username', 'manager');
await page.type('#id_password', 'wrong-password');
await Promise.all([
  page.waitForNavigation({ waitUntil: 'networkidle0' }),
  page.click('button[type=submit]'),
]);
await new Promise((res) => setTimeout(res, 400));
r = await page.evaluate(() => {
  const err = document.getElementById('auth-error');
  return {
    shown: !!err && !err.hidden,
    role: err && err.getAttribute('role'),
    text: err && err.textContent.trim(),
    describedby: document.getElementById('id_username').getAttribute('aria-describedby'),
    invalid: document.getElementById('id_username').getAttribute('aria-invalid'),
    focused: document.activeElement && document.activeElement.id,
  };
});
check('the refusal is shown', r.shown);
check('the refusal is announced', r.role === 'alert');
check('the refusal says what to do', /check them and try again/i.test(r.text || ''), r.text);
check('the field points at the refusal', r.describedby === 'auth-error');
check('the field is marked invalid', r.invalid === 'true');
check('the refused field takes the cursor', r.focused === 'id_username', String(r.focused));

console.log('--- the register screen ---');
await fresh('/accounts/register/');
r = await page.evaluate(() => {
  const inputs = [...document.querySelectorAll('.auth-field input')];
  return {
    labels: inputs.map((i) => !!document.querySelector(`label[for="${i.id}"]`)),
    autocomplete: inputs.map((i) => i.getAttribute('autocomplete')),
    spellcheck: inputs.map((i) => i.getAttribute('spellcheck')),
    errorLive: [...document.querySelectorAll('[data-error]')].map((n) => n.getAttribute('aria-live')),
    h1: document.querySelectorAll('h1').length,
  };
});
check('one h1', r.h1 === 1);
check('every input has a label', r.labels.every(Boolean));
check('spellcheck off for the code and the username', r.spellcheck[0] === 'false' && r.spellcheck[1] === 'false', JSON.stringify(r.spellcheck));
check('the field refusals are announced', r.errorLive.every((v) => v === 'polite'), JSON.stringify(r.errorLive));

// A refusal on the code must land on the code.
await page.type('#id_code', 'ZZZZ-9999');
await page.type('#id_username', 'newcomer');
await page.type('#id_password', 'longenoughpassword');
await page.type('#id_password_confirm', 'longenoughpassword');
await page.click('#register-submit');
await new Promise((res) => setTimeout(res, 2000));
r = await page.evaluate(() => {
  const code = document.querySelector('[data-field="code"]');
  const slot = code.querySelector('[data-error]');
  return {
    slotText: slot.textContent,
    slotShown: !slot.hidden,
    invalid: code.classList.contains('is-invalid'),
    aria: document.getElementById('id_code').getAttribute('aria-invalid'),
    buttonLabel: document.getElementById('register-submit').textContent.trim(),
    busy: document.getElementById('register-submit').getAttribute('aria-busy'),
  };
});
check('the refusal lands on the code', r.slotShown && /not recognised/i.test(r.slotText), r.slotText);
check('the code is marked invalid', r.invalid && r.aria === 'true');
check('the button is released again', r.busy === null && r.buttonLabel === 'Create account', `${r.buttonLabel} busy=${r.busy}`);

console.log('--- reduced motion ---');
await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
await fresh('/accounts/register/');
r = await page.evaluate(() => {
  const side = document.querySelector('.auth-side');
  const form = document.querySelector('.auth-form');
  return {
    sideAnimation: getComputedStyle(side).animationName,
    formAnimation: getComputedStyle(form).animationName,
    sideOpacity: getComputedStyle(side).opacity,
    visible: getComputedStyle(document.querySelector('.auth-form h1')).opacity,
  };
});
check('nothing animates under reduced motion', r.sideAnimation === 'none' && r.formAnimation === 'none', `${r.sideAnimation} / ${r.formAnimation}`);
check('the content is still there', r.visible === '1');

console.log('--- layout at three widths ---');
for (const width of [390, 820, 1440]) {
  await fresh('/accounts/login/', width);
  const m = await page.evaluate(() => {
    const de = document.documentElement;
    const side = document.querySelector('.auth-side').getBoundingClientRect();
    const main = document.querySelector('.auth-main').getBoundingClientRect();
    return {
      scrolls: de.scrollWidth > de.clientWidth + 1,
      sideBottom: Math.round(side.bottom),
      mainTop: Math.round(main.top),
      stacked: main.top >= side.bottom - 1,
    };
  });
  check(`${width}px does not scroll sideways`, !m.scrolls);
}

console.log(bad === 0 ? 'clean' : `${bad} problems`);
await browser.close();
