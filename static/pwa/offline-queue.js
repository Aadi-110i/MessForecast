/* =========================================================================
   MessForecast — offline queue
   -------------------------------------------------------------------------
   Scans and actuals are written to IndexedDB on the tablet *before* they are
   sent. If the network is down they wait there. When it comes back the queue
   drains into the server.

   Idempotency is the whole point. Every queued record carries a
   client-generated UUID, and the server ignores a UUID it has already
   stored. That means:

     - a scan can be sent twice without doubling the attendance;
     - a tablet that loses power mid-sync can safely retry;
     - the queue can be drained in any order, as often as it likes.

   Nothing here depends on a library or a network connection.
   ========================================================================= */
(function () {
  'use strict';

  var DB_NAME = 'messforecast';
  var DB_VERSION = 1;
  var STORE = 'queue';

  var Queue = {};
  window.MFQueue = Queue;

  /* ---------------------------------------------------------------------
     Device identity — stable per tablet, used to audit sync batches
     --------------------------------------------------------------------- */
  Queue.deviceId = function () {
    var key = 'messforecast.deviceId';
    try {
      var existing = window.localStorage.getItem(key);
      if (existing) { return existing; }
      var generated = 'tablet-' + Math.random().toString(36).slice(2, 10);
      window.localStorage.setItem(key, generated);
      return generated;
    } catch (e) {
      return 'tablet-unknown';
    }
  };

  /* ---------------------------------------------------------------------
     UUID with a fallback for browsers without crypto.randomUUID
     --------------------------------------------------------------------- */
  Queue.uuid = function () {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    if (window.crypto && window.crypto.getRandomValues) {
      var bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      var hex = Array.prototype.map.call(bytes, function (b) {
        return ('0' + b.toString(16)).slice(-2);
      }).join('');
      return (
        hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16) + '-' +
        hex.slice(16, 20) + '-' + hex.slice(20)
      );
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === 'x' ? r : ((r & 0x3) | 0x8);
      return v.toString(16);
    });
  };

  /* ---------------------------------------------------------------------
     IndexedDB plumbing
     --------------------------------------------------------------------- */
  function openDB() {
    return new Promise(function (resolve, reject) {
      if (!window.indexedDB) { reject(new Error('IndexedDB is not available')); return; }
      var request = window.indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = function (event) {
        var db = event.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          var store = db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
          store.createIndex('kind', 'kind', { unique: false });
          store.createIndex('created_at', 'created_at', { unique: false });
        }
      };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }

  function tx(mode, fn) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var transaction = db.transaction(STORE, mode);
        var store = transaction.objectStore(STORE);
        var result;
        try { result = fn(store); } catch (e) { reject(e); return; }
        transaction.oncomplete = function () {
          db.close();
          resolve(result && 'result' in result ? result.result : result);
        };
        transaction.onerror = function () { db.close(); reject(transaction.error); };
        transaction.onabort = function () { db.close(); reject(transaction.error); };
      });
    });
  }

  /* ---------------------------------------------------------------------
     Public API
     --------------------------------------------------------------------- */
  Queue.add = function (kind, payload) {
    var item = {
      kind: kind,
      payload: payload,
      created_at: new Date().toISOString(),
      attempts: 0,
      last_error: ''
    };
    return tx('readwrite', function (store) { return store.add(item); })
      .then(function () { Queue.paint(); return Queue.drain(); });
  };

  Queue.count = function () {
    return tx('readonly', function (store) { return store.count(); });
  };

  Queue.items = function () {
    return tx('readonly', function (store) { return store.getAll(); });
  };

  Queue.clear = function () {
    return tx('readwrite', function (store) { return store.clear(); });
  };

  Queue.remove = function (id) {
    return tx('readwrite', function (store) { return store.delete(id); });
  };

  Queue.update = function (id, changes) {
    return tx('readwrite', function (store) {
      return store.get(id).then(function (item) {
        if (!item) { return null; }
        Object.keys(changes).forEach(function (key) { item[key] = changes[key]; });
        return store.put(item);
      });
    });
  };

  /* ---------------------------------------------------------------------
     Draining
     --------------------------------------------------------------------- */
  var draining = false;

  Queue.drain = function () {
    if (draining) { return Promise.resolve({ skipped: true }); }
    if (!navigator.onLine) { Queue.paint(); return Promise.resolve({ offline: true }); }
    draining = true;

    return Queue.items()
      .then(function (items) {
        if (!items.length) { return { sent: 0, failed: 0 }; }
        var attendance = items.filter(function (i) { return i.kind === 'attendance'; })
                             .map(function (i) { return i.payload; });
        var actuals = items.filter(function (i) { return i.kind === 'actuals'; });

        var work = [];

        if (attendance.length) {
          work.push(
            fetch('/api/attendance/sync', {
              method: 'POST',
              credentials: 'same-origin',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.MessForecast.csrfToken(),
                'X-Device-Id': Queue.deviceId()
              },
              body: JSON.stringify({ records: attendance, device_id: Queue.deviceId() })
            }).then(function (res) {
              if (!res.ok) { throw new Error('sync failed with status ' + res.status); }
              return res.json();
            }).then(function (result) {
              // Remove every attendance item we just sent. The server may have
              // ignored some as duplicates — that is still a success for us,
              // because the record is already there.
              return Promise.all(
                items
                  .filter(function (i) { return i.kind === 'attendance'; })
                  .map(function (i) { return Queue.remove(i.id); })
              ).then(function () { return result; });
            })
          );
        }

        actuals.forEach(function (item) {
          work.push(
            fetch('/api/actuals', {
              method: 'POST',
              credentials: 'same-origin',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.MessForecast.csrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
              },
              body: JSON.stringify(item.payload)
            }).then(function (res) {
              if (!res.ok) { throw new Error('actuals failed with status ' + res.status); }
              return Queue.remove(item.id);
            })
          );
        });

        return Promise.allSettled(work).then(function (results) {
          var sent = 0, failed = 0;
          results.forEach(function (r) {
            if (r.status === 'fulfilled') { sent++; } else { failed++; }
          });
          return { sent: sent, failed: failed };
        });
      })
      .catch(function () { return { sent: 0, failed: 1 }; })
      .then(function (outcome) {
        draining = false;
        Queue.paint();
        window.MessForecast.dispatch('queuechange', outcome);
        return outcome;
      });
  };

  /* ---------------------------------------------------------------------
     Badge
     --------------------------------------------------------------------- */
  Queue.paint = function () {
    Queue.count().then(function (count) {
      var pill = document.getElementById('queue-pill');
      var label = document.getElementById('queue-label');
      if (!pill || !label) { return; }
      if (count > 0) {
        pill.hidden = false;
        pill.className = 'k-pill queued';
        label.textContent = count + (count === 1 ? ' queued' : ' queued');
      } else {
        pill.hidden = true;
      }
      window.MessForecast.dispatch('queuecount', { count: count });
    });
  };

  /* ---------------------------------------------------------------------
     Auto-drain triggers
     --------------------------------------------------------------------- */
  window.addEventListener('online', function () { Queue.drain(); });
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) { Queue.drain(); }
  });
  window.setInterval(function () { Queue.drain(); }, 20000);
  window.addEventListener('load', function () { Queue.paint(); Queue.drain(); });
})();
