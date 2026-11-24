/**
 * The overview's sparklines.
 *
 * The console's chart component draws a full chart with axes and a grid,
 * which is the right thing on a report page and the wrong thing on a
 * briefing: a trend read at a glance does not need a scale to be legible.
 *
 * This draws the same numbers as a smooth line with a soft area beneath it,
 * the last point marked, and the first and last values written out. The
 * curve is a Catmull-Rom spline turned into cubic beziers, so the line
 * bends through the points rather than breaking at them.
 *
 * Usage:
 *   <div class="ov-spark" data-spark="wasteByWeek" data-value="waste_cost"
 *        data-label="week" data-prefix="₹" data-tone="loss" data-height="150"></div>
 *   with {{ rows|json_script:"wasteByWeek" }} alongside it.
 */
(function () {
  'use strict';

  function parseLabel(raw) {
    if (raw === null || raw === undefined) { return ''; }
    if (typeof raw === 'number') { return String(raw); }
    var text = String(raw);
    // A date arrives as an ISO string, and is written out the way a person
    // would write it.
    var match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (match) {
      var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return parseInt(match[3], 10) + ' ' + months[parseInt(match[2], 10) - 1];
    }
    return text;
  }

  /* Money is written with its separators, the way the rest of the product
     writes it. */
  function withSeparators(value) {
    var parts = String(value).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.join('.');
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /**
   * The curve through the points.
   */
  function splinePath(points) {
    if (points.length === 0) { return ''; }
    if (points.length === 1) { return 'M' + points[0][0].toFixed(1) + ' ' + points[0][1].toFixed(1); }
    if (points.length === 2) {
      return 'M' + points[0][0].toFixed(1) + ' ' + points[0][1].toFixed(1) +
        ' L' + points[1][0].toFixed(1) + ' ' + points[1][1].toFixed(1);
    }
    var d = 'M' + points[0][0].toFixed(1) + ' ' + points[0][1].toFixed(1);
    for (var i = 0; i < points.length - 1; i++) {
      var p0 = points[i - 1] || points[i];
      var p1 = points[i];
      var p2 = points[i + 1];
      var p3 = points[i + 2] || p2;
      var c1x = p1[0] + (p2[0] - p0[0]) / 6;
      var c1y = p1[1] + (p2[1] - p0[1]) / 6;
      var c2x = p2[0] - (p3[0] - p1[0]) / 6;
      var c2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += ' C' + c1x.toFixed(1) + ' ' + c1y.toFixed(1) +
        ', ' + c2x.toFixed(1) + ' ' + c2y.toFixed(1) +
        ', ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
    }
    return d;
  }

  function drawSpark(root) {
    var src = root.getAttribute('data-spark');
    var valueKey = root.getAttribute('data-value');
    var labelKey = root.getAttribute('data-label');
    var prefix = root.getAttribute('data-prefix') || '';
    var suffix = root.getAttribute('data-suffix') || '';
    var tone = root.getAttribute('data-tone') || 'model';
    var bars = root.getAttribute('data-bars') === '1';
    var height = parseInt(root.getAttribute('data-height') || '150', 10);

    var holder = src ? document.getElementById(src) : null;
    if (!holder) { return; }

    var rows;
    try { rows = JSON.parse(holder.textContent); } catch (e) { return; }
    if (!rows || !rows.length) { return; }

    var values = rows.map(function (row) {
      var num = parseFloat(row[valueKey]);
      return isNaN(num) ? 0 : num;
    });
    var labels = rows.map(function (row) { return parseLabel(row[labelKey]); });

    var W = 760;
    var H = height;
    var padT = 22;
    var padB = 26;
    var padR = 10;
    var innerH = H - padT - padB;
    var innerW = W - padR;

    var max = Math.max.apply(null, values);
    var min = Math.min.apply(null, values);
    // The scale is fitted to the values rather than to zero, so a trend that
    // moves inside a narrow band is still a trend and not a flat line.
    var span = max - min;
    var lo = span === 0 ? 0 : min - span * 0.25;
    var hi = span === 0 ? (max || 1) : max + span * 0.25;

    var svg = ['<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" ' +
      'aria-label="Trend of ' + escapeHtml(valueKey) + '">'];

    if (bars) {
      var band = innerW / values.length;
      var barW = Math.max(8, Math.min(band * 0.5, 44));
      values.forEach(function (v, i) {
        var h = hi === lo ? 0 : ((v - lo) / (hi - lo)) * innerH;
        var x = band * i + (band - barW) / 2;
        var y = padT + innerH - h;
        svg.push('<rect class="spark-bar" x="' + x.toFixed(1) + '" y="' + y.toFixed(1) +
          '" width="' + barW.toFixed(1) + '" height="' + Math.max(1, h).toFixed(1) +
          '" rx="3"></rect>');
      });
    } else {
      var points = values.map(function (v, i) {
        var x = values.length === 1 ? innerW / 2 : (innerW * i / (values.length - 1));
        var y = padT + innerH - ((v - lo) / (hi - lo)) * innerH;
        return [x, y];
      });
      var line = splinePath(points);
      var area = line + ' L' + points[points.length - 1][0].toFixed(1) + ' ' + (padT + innerH) +
        ' L' + points[0][0].toFixed(1) + ' ' + (padT + innerH) + ' Z';
      svg.push('<path class="spark-area" d="' + area + '"></path>');
      svg.push('<path class="spark-line" d="' + line + '"></path>');

      var last = points[points.length - 1];
      svg.push('<circle class="spark-dot" cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) +
        '" r="5"></circle>');

      // The last value, written out: a trend is only useful if the number it
      // ended on is readable without measuring the axis.
      var lastValue = values[values.length - 1];
      var label = prefix + withSeparators(Math.round(lastValue * 10) / 10) + suffix;
      svg.push('<text class="spark-value" x="' + Math.max(30, last[0] - 8).toFixed(1) + '" y="' +
        Math.max(14, last[1] - 13).toFixed(1) + '" text-anchor="end">' +
        escapeHtml(label) + '</text>');
    }

    // The ends of the period, so the reader knows what window they are in.
    var every = Math.max(1, Math.ceil(labels.length / 6));
    labels.forEach(function (label, i) {
      if (i % every !== 0 && i !== labels.length - 1) { return; }
      var x = bars ? (innerW / labels.length) * (i + 0.5) : (innerW * i / (labels.length - 1));
      var anchor = i === 0 ? 'start' : (i === labels.length - 1 ? 'end' : 'middle');
      svg.push('<text class="spark-label" x="' + x.toFixed(1) + '" y="' + (H - 8) +
        '" text-anchor="' + anchor + '">' + escapeHtml(label) + '</text>');
    });

    svg.push('</svg>');
    root.className = 'ov-spark is-' + tone + (bars ? ' is-bars' : '');
    root.innerHTML = svg.join('');
  }

  function drawAll() {
    var nodes = document.querySelectorAll('[data-spark]');
    for (var i = 0; i < nodes.length; i++) {
      drawSpark(nodes[i]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', drawAll);
  } else {
    drawAll();
  }

  window.MessForecast = window.MessForecast || {};
  window.MessForecast.drawSparks = drawAll;
})();
