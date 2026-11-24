/* =========================================================================
   Attendance capture — QR, RFID and manual entry
   -------------------------------------------------------------------------
   Every scan is written to the local queue first, with a client-generated
   UUID. The queue drains itself when the connection is up, so the operator
   never has to think about the network mid-service.
   ========================================================================= */
(function () {
  'use strict';

  var MF = window.MessForecast;
  var Queue = window.MFQueue;

  var select = document.getElementById('svc');
  var countEl = document.getElementById('live-count');
  var registeredEl = document.getElementById('live-registered');
  var barEl = document.getElementById('live-bar');
  var logEl = document.getElementById('scan-log');
  var manualInput = document.getElementById('manual-id');
  var qrButton = document.getElementById('btn-qr');
  var rfidButton = document.getElementById('btn-rfid');
  var manualButton = document.getElementById('btn-manual');
  var video = document.getElementById('qr-video');

  if (!select) { return; }

  var currentServiceId = null;
  var scanning = false;
  var stream = null;

  /* ---------------------------------------------------------------------
     Service state
     --------------------------------------------------------------------- */
  function service() {
    var option = select.options[select.selectedIndex];
    if (!option) { return null; }
    return {
      id: parseInt(option.value, 10),
      hall_id: parseInt(option.getAttribute('data-hall'), 10),
      date: option.getAttribute('data-date'),
      meal: option.getAttribute('data-meal'),
      registered: parseInt(option.getAttribute('data-registered'), 10) || 0,
      count: parseInt(option.getAttribute('data-count'), 10) || 0
    };
  }

  function paintCounts(count, registered) {
    if (countEl) { countEl.textContent = count; }
    if (registeredEl) { registeredEl.textContent = registered; }
    if (barEl) {
      var pct = registered ? Math.min(100, (count / registered) * 100) : 0;
      // The bar grows from its foot with a transform, so it never animates
      // its own width.
      barEl.style.transform = 'scaleX(' + (pct / 100).toFixed(4) + ')';
      var track = barEl.parentElement;
      if (track && track.hasAttribute('role')) {
        track.setAttribute('aria-valuenow', String(Math.round(pct)));
      }
      var pctEl = document.getElementById('live-progress-pct');
      if (pctEl) {
        pctEl.textContent = Math.round(pct) + '% (' + count + '/' + registered + ')';
      }
    }
  }

  function refreshCounts() {
    var svc = service();
    if (!svc) { return; }
    fetch('/api/attendance/count?service=' + svc.id, { credentials: 'same-origin' })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data || typeof data.attendance_count !== 'number') { return; }
        svc.count = data.attendance_count;
        svc.registered = data.registered_strength;
        paintCounts(svc.count, svc.registered);
      })
      .catch(function () { /* offline: the queued count on screen stays */ });
  }

  select.addEventListener('change', function () {
    var svc = service();
    if (!svc) { return; }
    currentServiceId = svc.id;
    paintCounts(svc.count, svc.registered);
    refreshCounts();
  });

  /* ---------------------------------------------------------------------
     The log
     --------------------------------------------------------------------- */
  function log(message, kind) {
    if (!logEl) { return; }
    if (logEl.querySelector('div') && logEl.textContent.indexOf('Waiting for the first scan') !== -1) {
      logEl.innerHTML = '';
    }
    var line = document.createElement('div');
    if (kind) { line.className = kind; }
    var time = new Date();
    line.textContent = time.toTimeString().slice(0, 8) + '  ' + message;
    logEl.insertBefore(line, logEl.firstChild);
    while (logEl.children.length > 60) {
      logEl.removeChild(logEl.lastChild);
    }
  }

  /* ---------------------------------------------------------------------
     Recording a scan
     --------------------------------------------------------------------- */
  function recordScan(identifier, method) {
    var svc = service();
    if (!svc) { return; }
    identifier = (identifier || '').trim();
    if (!identifier) {
      MF.toast('Enter the credential number first.', 'bad');
      return;
    }

    var payload = {
      client_uuid: Queue.uuid(),
      service_id: svc.id,
      hall_id: svc.hall_id,
      date: svc.date,
      meal: svc.meal,
      student_identifier: identifier,
      method: method,
      captured_at: new Date().toISOString(),
      device_id: Queue.deviceId(),
      captured_offline: !navigator.onLine
    };

    // Always queue first. The queue drains straight away when online, so this
    // costs nothing and guarantees the same path online and offline.
    Queue.add('attendance', payload).then(function () {
      svc.count += 1;
      paintCounts(svc.count, svc.registered);
      log(identifier + '  · ' + method + (navigator.onLine ? '' : '  · held offline'), 'new');
    }).catch(function () {
      MF.toast('Could not store that scan on this tablet.', 'bad');
    });
  }

  /* ---------------------------------------------------------------------
     Manual entry
     --------------------------------------------------------------------- */
  if (manualButton) {
    manualButton.addEventListener('click', function () {
      recordScan(manualInput ? manualInput.value : '', 'MANUAL');
      if (manualInput) { manualInput.value = ''; manualInput.focus(); }
    });
  }
  if (manualInput) {
    manualInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        recordScan(manualInput.value, 'MANUAL');
        manualInput.value = '';
      }
    });
  }

  if (rfidButton) {
    rfidButton.addEventListener('click', function () {
      MF.toast('RFID reader not attached — type the credential number instead.', 'bad', 4000);
      if (manualInput) { manualInput.focus(); }
    });
  }

  /* ---------------------------------------------------------------------
     QR scanning
     ---------------------------------------------------------------------
     Uses the BarcodeDetector API where the tablet supports it. Where it does
     not, the operator types the credential — the same code path, the same
     idempotency guarantee.
     --------------------------------------------------------------------- */
  function stopScanner() {
    scanning = false;
    if (stream) {
      stream.getTracks().forEach(function (track) { track.stop(); });
      stream = null;
    }
    if (video) { video.hidden = true; video.srcObject = null; }
    if (qrButton) { qrButton.textContent = 'Scan QR code'; }
  }

  if (qrButton) {
    qrButton.addEventListener('click', function () {
      if (scanning) { stopScanner(); return; }

      if (!('BarcodeDetector' in window)) {
        MF.toast('This tablet has no barcode scanner. Type the credential number instead.', 'bad', 5000);
        if (manualInput) { manualInput.focus(); }
        return;
      }
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        MF.toast('No camera available. Type the credential number instead.', 'bad', 5000);
        return;
      }

      navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
        .then(function (mediaStream) {
          stream = mediaStream;
          scanning = true;
          if (video) {
            video.srcObject = mediaStream;
            video.hidden = false;
          }
          if (qrButton) { qrButton.textContent = 'Stop scanning'; }
          // Starting the camera is a promise of its own. Returning it keeps
          // the detection loop from running before the picture is live.
          return video ? video.play() : Promise.resolve();
        })
        .then(function () {
          var detector = new window.BarcodeDetector({ formats: ['qr_code'] });
          var tick = function () {
            if (!scanning) { return; }
            detector.detect(video).then(function (codes) {
              if (codes && codes.length) {
                var value = codes[0].rawValue;
                recordScan(value, 'QR');
                stopScanner();
                return;
              }
              window.requestAnimationFrame(tick);
            }).catch(function () {
              window.requestAnimationFrame(tick);
            });
          };
          tick();
        })
        .catch(function () {
          MF.toast('Camera permission refused. Type the credential number instead.', 'bad', 5000);
        });
    });
  }

  /* ---------------------------------------------------------------------
     Wiring
     --------------------------------------------------------------------- */
  var svc = service();
  if (svc) {
    currentServiceId = svc.id;
    paintCounts(svc.count, svc.registered);
    refreshCounts();
  }
  window.setInterval(refreshCounts, 5000);

  document.addEventListener('mf:queuechange', function () {
    refreshCounts();
  });
  document.addEventListener('mf:queuecount', function (event) {
    var pill = document.getElementById('queue-pill');
    var label = document.getElementById('queue-label');
    if (pill && label) {
      pill.hidden = !event.detail.count;
      label.textContent = event.detail.count + ' queued';
    }
  });
})();
