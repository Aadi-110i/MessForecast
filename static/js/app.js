/* =========================================================================
   MessForecast — shared browser helpers
   -------------------------------------------------------------------------
   No framework, no CDN. Everything here has to work with the network down,
   because the tablet in the kitchen does not get one.
   ========================================================================= */
(function () {
  'use strict';

  var MF = window.MessForecast || {};
  window.MessForecast = MF;

  /* ---------------------------------------------------------------------
     Django plumbing
     --------------------------------------------------------------------- */
  MF.csrfToken = function () {
    var input = document.querySelector('[name="csrfmiddlewaretoken"]');
    if (input && input.value) { return input.value; }
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  };

  MF.postJSON = function (url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': MF.csrfToken(),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify(body || {})
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!res.ok) {
          var detail = (data && (data.detail || data.message)) || ('Request failed (' + res.status + ')');
          var error = new Error(detail);
          error.status = res.status;
          error.payload = data;
          throw error;
        }
        return data;
      });
    });
  };

  MF.getJSON = function (url) {
    return fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (res) { return res.json(); });
  };

  /* ---------------------------------------------------------------------
     Toast
     --------------------------------------------------------------------- */
  MF.toast = function (message, kind, ms) {
    var el = document.getElementById('k-toast');
    if (!el) { return; }
    el.textContent = message;
    el.className = 'k-toast show' + (kind ? ' ' + kind : '');
    window.clearTimeout(el._timer);
    el._timer = window.setTimeout(function () {
      el.className = 'k-toast' + (kind ? ' ' + kind : '');
    }, ms || 3200);
  };

  /* ---------------------------------------------------------------------
     Connectivity indicator
     --------------------------------------------------------------------- */
  function paintNetwork() {
    var online = navigator.onLine;
    var bar = document.getElementById('netbar');
    if (bar) { bar.classList.toggle('show', !online); }

    var pill = document.getElementById('net-pill');
    var label = document.getElementById('net-label');
    if (pill && label) {
      pill.className = 'k-pill ' + (online ? 'online' : 'offline');
      label.textContent = online ? 'Online' : 'Offline';
    }
    document.body.setAttribute('data-online', online ? '1' : '0');
    MF.dispatch('networkchange', { online: online });
  }

  MF.dispatch = function (name, detail) {
    document.dispatchEvent(new CustomEvent('mf:' + name, { detail: detail }));
  };

  window.addEventListener('online', paintNetwork);
  window.addEventListener('offline', paintNetwork);

  /* ---------------------------------------------------------------------
     Charts — inline SVG, drawn here so nothing is fetched from a CDN
     --------------------------------------------------------------------- */
  function parseLabel(value) {
    if (value === null || value === undefined) { return ''; }
    var str = String(value);
    if (/^\d{4}-\d{2}-\d{2}/.test(str)) {
      var d = new Date(str + 'T00:00:00');
      if (!isNaN(d.getTime())) {
        return d.getDate() + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()];
      }
    }
    return str;
  }

  function niceMax(value) {
    if (!value || value <= 0) { return 1; }
    var exp = Math.pow(10, Math.floor(Math.log10(value)));
    var frac = value / exp;
    var nice = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 2.5 ? 2.5 : frac <= 5 ? 5 : 10;
    return nice * exp;
  }

  function drawChart(root) {
    var type = root.getAttribute('data-chart') || 'bar';
    var src = root.getAttribute('data-src');
    var valueKey = root.getAttribute('data-value');
    var labelKey = root.getAttribute('data-label');
    var prefix = root.getAttribute('data-prefix') || '';
    var suffix = root.getAttribute('data-suffix') || '';
    var height = parseInt(root.getAttribute('data-height') || '200', 10);
    var title = root.getAttribute('data-title') || 'chart';

    var holder = src ? document.getElementById(src) : null;
    if (!holder) { return; }

    var rows;
    try { rows = JSON.parse(holder.textContent); } catch (e) { return; }
    if (!rows || !rows.length) { return; }

    var values = rows.map(function (row) {
      var raw = row[valueKey];
      var num = parseFloat(raw);
      return isNaN(num) ? 0 : num;
    });
    var labels = rows.map(function (row) { return parseLabel(row[labelKey]); });

    var W = 760, H = height;
    var padL = 56, padR = 12, padT = 14, padB = 30;
    var innerW = W - padL - padR;
    var innerH = H - padT - padB;
    var max = niceMax(Math.max.apply(null, values.concat([0])));
    // The band is needed for the axis labels of both chart types, so it is
    // worked out before the branch rather than inside the bar case.
    var band = innerW / values.length;

    var svg = ['<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" ' +
               'preserveAspectRatio="xMidYMid meet" aria-label="' + escapeHtml(title) + '">'];

    // horizontal grid + y labels
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var y = padT + innerH - (innerH * t / ticks);
      var v = max * t / ticks;
      svg.push('<line class="grid-line" x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y + '"></line>');
      svg.push('<text class="axis-text" x="' + (padL - 8) + '" y="' + (y + 3) + '" text-anchor="end">' +
               prefix + (Math.round(v * 100) / 100) + suffix + '</text>');
    }

    if (type === 'line') {
      var pts = values.map(function (v, i) {
        var x = padL + (values.length === 1 ? innerW / 2 : innerW * i / (values.length - 1));
        var y = padT + innerH - (v / max) * innerH;
        return [x, y];
      });
      var line = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
      var area = line + ' L' + pts[pts.length - 1][0].toFixed(1) + ' ' + (padT + innerH) +
                 ' L' + pts[0][0].toFixed(1) + ' ' + (padT + innerH) + ' Z';
      svg.push('<path class="area" d="' + area + '"></path>');
      svg.push('<path class="line" d="' + line + '"></path>');
      pts.forEach(function (p) {
        svg.push('<circle class="dot" cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="3"></circle>');
      });
    } else {
      var barW = Math.max(6, Math.min(band * 0.62, 54));
      values.forEach(function (v, i) {
        var h = max ? (v / max) * innerH : 0;
        var x = padL + band * i + (band - barW) / 2;
        var y = padT + innerH - h;
        svg.push('<rect class="bar" x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' +
                 barW.toFixed(1) + '" height="' + Math.max(1, h).toFixed(1) + '" rx="3"></rect>');
      });
    }

    // x labels — thinned out so they never collide
    var every = Math.max(1, Math.ceil(labels.length / 12));
    labels.forEach(function (label, i) {
      if (i % every !== 0 && i !== labels.length - 1) { return; }
      var x = padL + band * i + band / 2;
      svg.push('<text class="bar-label" x="' + x.toFixed(1) + '" y="' + (H - 10) + '" text-anchor="middle">' +
               escapeHtml(label) + '</text>');
    });

    svg.push('</svg>');
    root.innerHTML = svg.join('');
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ---------------------------------------------------------------------
     The forecast band
     ---------------------------------------------------------------------
     A forecast is a number with a range around it. This draws the range as
     an area and the prediction as a line, so the reader sees how much room
     the kitchen has rather than a single false-precision figure.

     The data is a list of {label, predicted, lower, upper}.
     ------------------------------------------------------------------- */
  function drawBand(root) {
    var src = root.getAttribute('data-src');
    var title = root.getAttribute('data-title') || 'forecast band';
    var height = parseInt(root.getAttribute('data-height') || '220', 10);

    var holder = src ? document.getElementById(src) : null;
    if (!holder) { return; }

    var rows;
    try { rows = JSON.parse(holder.textContent); } catch (e) { return; }
    if (!rows || !rows.length) { return; }

    var W = 760, H = height;
    var padL = 52, padR = 14, padT = 16, padB = 34;
    var innerW = W - padL - padR;
    var innerH = H - padT - padB;

    // The scale is fitted to the range, not to zero. A forecast band drawn
    // against a zero baseline squashes the range into a hairline, and the
    // range is the whole point of the chart.
    var lo = Infinity;
    var hi = -Infinity;
    rows.forEach(function (row) {
      var lower = parseFloat(row.lower);
      var upper = parseFloat(row.upper);
      var predicted = parseFloat(row.predicted);
      if (!isNaN(lower)) { lo = Math.min(lo, lower); hi = Math.max(hi, lower); }
      if (!isNaN(upper)) { lo = Math.min(lo, upper); hi = Math.max(hi, upper); }
      if (!isNaN(predicted)) { lo = Math.min(lo, predicted); hi = Math.max(hi, predicted); }
    });
    if (!isFinite(lo) || !isFinite(hi)) { return; }
    if (hi - lo < 1) { hi = lo + 1; }
    var headroom = (hi - lo) * 0.15;
    var yMin = Math.max(0, lo - headroom);
    var yMax = hi + headroom;

    var step = rows.length > 1 ? innerW / (rows.length - 1) : 0;
    var xAt = function (i) { return padL + (rows.length === 1 ? innerW / 2 : step * i); };
    var yAt = function (v) {
      var value = isNaN(v) ? yMin : v;
      return padT + innerH - ((value - yMin) / (yMax - yMin)) * innerH;
    };

    var svg = ['<svg class="chart band" viewBox="0 0 ' + W + ' ' + H + '" role="img" ' +
               'preserveAspectRatio="xMidYMid meet" aria-label="' + escapeHtml(title) + '">'];

    for (var t = 0; t <= 4; t++) {
      var y = padT + innerH - (innerH * t / 4);
      svg.push('<line class="grid-line" x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y + '"></line>');
      svg.push('<text class="axis-text" x="' + (padL - 8) + '" y="' + (y + 3) + '" text-anchor="end">' +
               Math.round(yMin + (yMax - yMin) * t / 4) + '</text>');
    }

    // The band: an upper edge and a lower edge, joined into one area.
    // It reuses the chart vocabulary the other charts use, so the colour
    // rules in app.css apply without a second set of selectors.
    var upper = rows.map(function (row, i) {
      return (i ? 'L' : 'M') + xAt(i).toFixed(1) + ' ' + yAt(parseFloat(row.upper)).toFixed(1);
    }).join(' ');
    var lower = rows.slice().reverse().map(function (row, i) {
      var index = rows.length - 1 - i;
      return 'L' + xAt(index).toFixed(1) + ' ' + yAt(parseFloat(row.lower)).toFixed(1);
    }).join(' ');
    svg.push('<path class="area" d="' + upper + ' ' + lower + ' Z"></path>');

    var line = rows.map(function (row, i) {
      return (i ? 'L' : 'M') + xAt(i).toFixed(1) + ' ' + yAt(parseFloat(row.predicted)).toFixed(1);
    }).join(' ');
    svg.push('<path class="line" d="' + line + '"></path>');

    // Dots mark the individual services. On a dense band they would crowd
    // the line, so they shrink as the series grows.
    var dotR = rows.length > 24 ? 2 : 3;
    rows.forEach(function (row, i) {
      svg.push('<circle class="dot" cx="' + xAt(i).toFixed(1) + '" cy="' +
               yAt(parseFloat(row.predicted)).toFixed(1) + '" r="' + dotR + '"></circle>');
    });

    // The x axis is per service, so several services share a date. A label is
    // drawn when the date changes and there is room for it, which keeps the
    // axis readable without repeating a day.
    var lastLabel = null;
    var lastX = -Infinity;
    rows.forEach(function (row, i) {
      var label = parseLabel(row.label);
      var x = xAt(i);
      if (label === lastLabel) { return; }
      if (x - lastX < 54) { return; }
      lastLabel = label;
      lastX = x;
      svg.push('<text class="bar-label" x="' + x.toFixed(1) + '" y="' + (H - 12) +
               '" text-anchor="middle">' + escapeHtml(label) + '</text>');
    });

    svg.push('</svg>');
    root.innerHTML = svg.join('');
  }

  MF.drawCharts = function () {
    var nodes = document.querySelectorAll('[data-chart]');
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].getAttribute('data-chart') === 'band') {
        drawBand(nodes[i]);
      } else {
        drawChart(nodes[i]);
      }
    }
  };

  /* ---------------------------------------------------------------------
     Boot
     --------------------------------------------------------------------- */
  function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) { return; }

    // When a new worker takes over, the page it is looking at is the old one.
    // The reader gets the new screen without being asked to refresh. Two
    // things can announce the change — this and the worker's own message —
    // so the flag in the session makes sure the page reloads once, not twice.
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      if (sessionStorage.getItem('mf-sw-reloaded')) { return; }
      sessionStorage.setItem('mf-sw-reloaded', '1');
      window.location.reload();
    });
    if (sessionStorage.getItem('mf-sw-reloaded')) {
      sessionStorage.removeItem('mf-sw-reloaded');
    }

    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {
      // A failed registration must never break the page; the app still works,
      // it just will not be available offline.
    });
  }

  /* ---------------------------------------------------------------------
     The rail, on a narrow screen
     ---------------------------------------------------------------------
     Under 60rem the rail folds away behind a menu button in the top bar.
     Without scripting the rail simply stays open, so the navigation is
     never lost.
     --------------------------------------------------------------------- */
  function setupRail() {
    var toggle = document.getElementById('navtoggle');
    var rail = document.getElementById('rail');
    if (!toggle || !rail) { return; }

    var narrow = window.matchMedia('(max-width: 60rem)');

    var sync = function () {
      if (narrow.matches) {
        toggle.hidden = false;
        var open = toggle.getAttribute('aria-expanded') === 'true';
        rail.hidden = !open;
        toggle.textContent = open ? 'Close' : 'Menu';
      } else {
        toggle.hidden = true;
        rail.hidden = false;
        toggle.setAttribute('aria-expanded', 'false');
      }
    };

    toggle.addEventListener('click', function () {
      var open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', open ? 'false' : 'true');
      sync();
    });

    if (narrow.addEventListener) { narrow.addEventListener('change', sync); }
    else if (narrow.addListener) { narrow.addListener(sync); }
    sync();
  }

  /* ---------------------------------------------------------------------
     Filter forms
     ---------------------------------------------------------------------
     The dashboard filters round-trip to the server. While that is in flight
     the button says so, so the screen is never waiting without an answer.
     --------------------------------------------------------------------- */
  function setupFilterForms() {
    var forms = document.querySelectorAll('form.toolbar');
    for (var i = 0; i < forms.length; i++) {
      forms[i].addEventListener('submit', function (event) {
        var button = event.currentTarget.querySelector('.btn[type="submit"]');
        if (!button) { return; }
        button.setAttribute('aria-busy', 'true');
        button.textContent = 'Applying';
      });
    }
  }

  function boot() {
    paintNetwork();
    MF.drawCharts();
    registerServiceWorker();
    setupRail();
    setupFilterForms();

    // Redraw on resize so the charts stay crisp without a library.
    var timer = null;
    window.addEventListener('resize', function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(MF.drawCharts, 180);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
