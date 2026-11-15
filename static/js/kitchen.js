/* =========================================================================
   Kitchen screen — portion entry and saving actuals
   ========================================================================= */
(function () {
  'use strict';

  var MF = window.MessForecast;
  var rows = document.getElementById('portion-rows');
  if (!rows) { return; }

  var saveBtn = document.getElementById('k-save');
  var servedInput = document.getElementById('k-served');
  var attendanceInput = document.getElementById('k-attendance');
  var modeSelect = document.getElementById('k-mode');
  var leftoverEl = document.getElementById('k-leftover');
  var leftoverFlag = document.getElementById('k-leftover-flag');
  var summaryEl = document.getElementById('prep-summary');

  /* ---------------------------------------------------------------------
     Steppers
     --------------------------------------------------------------------- */
  function inputs() {
    return Array.prototype.slice.call(rows.querySelectorAll('.k-stepper input'));
  }

  function preparedTotal() {
    return inputs().reduce(function (total, input) {
      var value = parseInt(input.value, 10);
      return total + (isNaN(value) ? 0 : Math.max(0, value));
    }, 0);
  }

  function clampInput(input) {
    var value = parseInt(input.value, 10);
    if (isNaN(value) || value < 0) { value = 0; }
    input.value = value;
    return value;
  }

  rows.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-step]');
    if (!button) { return; }
    event.preventDefault();
    var input = button.parentElement.querySelector('input');
    if (!input) { return; }
    var step = parseInt(button.getAttribute('data-step'), 10);
    var current = clampInput(input);
    input.value = Math.max(0, current + step);
    refresh();
  });

  rows.addEventListener('input', function (event) {
    if (event.target.matches('.k-stepper input')) { refresh(); }
  });

  /* ---------------------------------------------------------------------
     Live totals
     --------------------------------------------------------------------- */
  function refresh() {
    var prepared = preparedTotal();
    var served = servedInput ? parseInt(servedInput.value, 10) : 0;
    if (isNaN(served)) { served = 0; }
    var leftover = prepared - served;

    if (summaryEl) {
      summaryEl.textContent = 'prepared ' + prepared + ' · served ' + served;
    }
    if (leftoverEl) {
      leftoverEl.textContent = leftover > 0 ? leftover : 0;
    }
    if (leftoverFlag) {
      leftoverFlag.innerHTML = '';
      if (leftover < 0) {
        leftoverFlag.innerHTML = '<span class="k-flag short">ran short</span>';
      } else if (leftover > 0 && served > 0 && leftover / prepared > 0.12) {
        leftoverFlag.innerHTML = '<span class="k-flag over">high waste</span>';
      }
    }

    // Flag the dish rows that look wrong against the plan.
    var planTotal = 0;
    inputs().forEach(function (input) { planTotal += parseInt(input.value, 10) || 0; });
    Array.prototype.forEach.call(rows.querySelectorAll('.k-row'), function (row) {
      row.classList.remove('over', 'short');
    });
  }

  if (servedInput) { servedInput.addEventListener('input', refresh); }

  /* ---------------------------------------------------------------------
     Splitting the served total across the dishes
     ---------------------------------------------------------------------
     The kitchen records one served total. Each dish gives up portions in
     proportion to what was prepared from it, which is how the serving pot
     actually works. The split is shown so it is never a black box.
     --------------------------------------------------------------------- */
  function dishActuals(prepared, served) {
    var boxes = inputs();
    var weights = boxes.map(function (input) { return Math.max(0, parseInt(input.value, 10) || 0); });
    var weightTotal = weights.reduce(function (a, b) { return a + b; }, 0);

    var allocated = 0;
    var lines = boxes.map(function (input, index) {
      var dishId = parseInt(input.closest('.k-row').getAttribute('data-dish'), 10);
      var weight = weightTotal ? weights[index] / weightTotal : (1 / boxes.length);
      var share = Math.round(served * weight);
      allocated += share;
      return { dish: dishId, prepared_portions: weights[index], served_portions: share };
    });

    // Give any rounding remainder to the dish with the most prepared portions.
    if (lines.length) {
      var drift = served - allocated;
      if (drift !== 0) {
        var largest = 0;
        for (var i = 1; i < lines.length; i++) {
          if (lines[i].prepared_portions > lines[largest].prepared_portions) { largest = i; }
        }
        lines[largest].served_portions = Math.max(0, lines[largest].served_portions + drift);
      }
    }
    return lines;
  }

  /* ---------------------------------------------------------------------
     Saving
     --------------------------------------------------------------------- */
  function save() {
    if (!saveBtn) { return; }
    var serviceId = parseInt(saveBtn.getAttribute('data-service'), 10);
    var prepared = preparedTotal();
    var served = servedInput ? parseInt(servedInput.value, 10) : 0;
    if (isNaN(served)) { served = 0; }
    var attendance = attendanceInput ? parseInt(attendanceInput.value, 10) : 0;
    if (isNaN(attendance)) { attendance = 0; }

    var payload = {
      service: serviceId,
      prepared_portions_total: prepared,
      served_portions_total: served,
      leftover_portions_total: Math.max(0, prepared - served),
      prep_mode: modeSelect ? modeSelect.value : 'FORECAST_GUIDED',
      attendance_actual: attendance,
      dish_actuals: dishActuals(prepared, served)
    };

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving…';

    MF.postJSON('/api/actuals', payload)
      .then(function () {
        MF.toast('Actuals saved. Waste has been costed.', 'good');
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save actuals';
        window.setTimeout(function () { window.location.reload(); }, 1200);
      })
      .catch(function (error) {
        // Offline: keep it on the tablet and let the queue deliver it later.
        if (!navigator.onLine || error.status === undefined) {
          window.MFQueue.add('actuals', payload).then(function () {
            MF.toast('No connection. Saved on this tablet — it will sync automatically.', 'good', 5000);
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save actuals';
          });
          return;
        }
        MF.toast(error.message || 'Could not save the actuals.', 'bad', 5000);
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save actuals';
      });
  }

  if (saveBtn) { saveBtn.addEventListener('click', save); }

  refresh();
})();
