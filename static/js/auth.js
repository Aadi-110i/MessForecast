/* =========================================================================
   MessForecast - the sign-in and register screens
   -------------------------------------------------------------------------
   Four small jobs, all of them about the ticket:

   1. The pass is measured against the frame and scaled down when the window
      is too short for it, so the door never needs a scrollbar to be usable.
   2. The eye opens the password.
   3. The barcode in the foot is drawn from the pass number, so it changes
      with the page rather than being a picture of one.
   4. The demonstration account can be filled in without typing it.
   ========================================================================= */
(function () {
  'use strict';

  var stage = document.querySelector('.auth-stage');
  var topbar = document.querySelector('.auth-topbar');
  var ticketWrap = document.querySelector('.auth-ticket-wrap');
  var ticket = document.querySelector('.auth-ticket');

  /* ---------------------------------------------------------------------
     The fit: the ticket never outgrows the frame it sits in
     --------------------------------------------------------------------- */
  function fitTicket() {
    if (!ticketWrap || !ticket) { return; }

    var stacked = window.matchMedia('(max-width: 1040px)').matches;
    if (stacked) {
      ticketWrap.style.zoom = '';
      return;
    }

    var topH = topbar ? topbar.getBoundingClientRect().height : 60;
    document.documentElement.style.setProperty('--auth-topbar-h', Math.round(topH) + 'px');

    var layout = document.querySelector('.auth-layout');
    var layoutPad = 0;
    if (layout) {
      var cs = window.getComputedStyle(layout);
      layoutPad = parseFloat(cs.paddingTop || 0) + parseFloat(cs.paddingBottom || 0);
    }

    var available = window.innerHeight - topH - layoutPad - 10;

    ticketWrap.style.zoom = '';
    var natural = ticketWrap.offsetHeight;

    if (natural > 0 && available > 0) {
      // Scale up to 1.25x if height permits (matching the 125% zoom look),
      // and scale down smoothly so the bottom is never cut off.
      var targetScale = Math.min(1.25, Math.max(0.5, (available - 16) / natural));
      ticketWrap.style.zoom = targetScale.toFixed(3);
    }
  }

  var fitFrame = 0;
  function scheduleFit() {
    if (fitFrame) { window.cancelAnimationFrame(fitFrame); }
    fitFrame = window.requestAnimationFrame(fitTicket);
  }

  window.addEventListener('resize', scheduleFit);
  window.addEventListener('orientationchange', scheduleFit);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(scheduleFit);
  }
  scheduleFit();

  /* ---------------------------------------------------------------------
     The eye
     --------------------------------------------------------------------- */
  Array.prototype.forEach.call(document.querySelectorAll('[data-auth-eye]'), function (button) {
    var input = document.getElementById(button.getAttribute('data-auth-eye'));
    if (!input) { return; }
    button.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-label', show ? 'Hide the password' : 'Show the password');
      button.setAttribute('aria-pressed', show ? 'true' : 'false');
      var use = button.querySelector('use');
      if (use) {
        use.setAttribute('href', show ? '#i-eye-off' : '#i-eye');
      }
      input.focus();
    });
  });

  /* ---------------------------------------------------------------------
     The demonstration account
     --------------------------------------------------------------------- */
  Array.prototype.forEach.call(document.querySelectorAll('[data-auth-demo]'), function (button) {
    button.addEventListener('click', function () {
      var user = document.getElementById('id_username');
      var pass = document.getElementById('id_password');
      if (!user || !pass) { return; }
      user.value = button.getAttribute('data-auth-demo') || '';
      pass.value = button.getAttribute('data-auth-demo-password') || '';
      user.dispatchEvent(new Event('input', { bubbles: true }));
      pass.dispatchEvent(new Event('input', { bubbles: true }));
      pass.focus();
    });
  });

  /* ---------------------------------------------------------------------
     The barcode
     --------------------------------------------------------------------- */
  function barcode(el, seed) {
    if (!el) { return; }
    var s = 7;
    var i;
    for (i = 0; i < seed.length; i++) { s = (s * 31 + seed.charCodeAt(i)) % 2147483647; }
    function rand() {
      s = (s * 1103515245 + 12345) % 2147483648;
      return s / 2147483648;
    }
    var x = 0;
    var bars = '';
    while (x < 190) {
      var w = 1 + Math.floor(rand() * 3);
      if (rand() > 0.42) {
        bars += '<rect x="' + x + '" y="0" width="' + w + '" height="40"></rect>';
      }
      x += w + 1;
    }
    el.innerHTML = bars;
  }

  var passMeta = document.querySelector('[data-auth-pass]');
  var seed = passMeta ? passMeta.getAttribute('data-auth-pass') : 'MESSFORECAST';
  barcode(document.getElementById('auth-barcode'), seed);
})();
