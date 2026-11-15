# 10 — Offline and sync

The specification's requirement:

> *a browser service worker with IndexedDB queues scans locally and syncs when connectivity
> returns. The sync endpoint must be idempotent – every offline record carries a client-generated
> UUID and the server ignores one it has already stored.*

This document explains how that works, end to end, and what was measured.

---

## 1. Why this is the hard part

The specification calls it out twice — in the technical deltas and again in the readiness
section:

> *Both tracks: service workers and offline sync appear in no syllabus and are the real learning
> here.*

The difficulty is not caching. It is that **the tablet will lose its connection in the middle of
a service**, exactly when 1,500 students are walking past the counter, and it will try again
later with the same data. A system that does not handle the retry loses or doubles attendance.

The design has one organising idea:

> **Every scan is written to local storage before it is sent, and every scan carries an identity
> the server can recognise a second time.**

Everything else follows from that.

---

## 2. The three parts

| Part | File | Job |
|---|---|---|
| The queue | `static/pwa/offline-queue.js` | holds records in IndexedDB until they are accepted |
| The worker | `static/pwa/sw.js` | serves the app shell offline; never touches data writes |
| The endpoint | `apps/attendance/services.py::sync_attendance_batch` | accepts a batch and ignores what it already has |

---

## 3. The client side

### Writing before sending

`Queue.add(kind, payload)` puts a record into IndexedDB and *then* tries to send it. The write
comes first:

```javascript
Queue.add = function (kind, payload) {
  var item = { kind: kind, payload: payload, created_at: new Date().toISOString(), ... };
  return tx('readwrite', function (store) { return store.add(item); })
    .then(function () { Queue.paint(); return Queue.drain(); });
};
```

If the network is down, `drain()` sees `navigator.onLine` is false and returns without sending.
The record is already safe in IndexedDB. Nothing is lost.

### The UUID

Every record gets a UUID **on the tablet**, before it leaves:

```javascript
Queue.uuid = function () {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  if (window.crypto && window.crypto.getRandomValues) {
    // RFC 4122 version 4, built from 16 random bytes.
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, ...);
};
```

The fallback matters. `crypto.randomUUID` needs a secure context; a kitchen tablet served over
plain HTTP on the local network does not have one. The `getRandomValues` path works in any
context, and the final `Math.random` path means the feature degrades rather than breaking.

The UUID is generated **once**, when the scan happens, and it travels with the record forever. It
is not regenerated on retry. That is the whole point: a retry must present the same identity.

### The device identity

```javascript
Queue.deviceId = function () {
  var key = 'messforecast.deviceId';
  var existing = window.localStorage.getItem(key);
  if (existing) { return existing; }
  var generated = 'tablet-' + Math.random().toString(36).slice(2, 10);
  window.localStorage.setItem(key, generated);
  return generated;
};
```

Stored in `localStorage`, so it survives a reload and a tablet restart. It goes to the server in
the `X-Device-Id` header and lands on the `AttendanceAudit` row, so it is always possible to
answer "which tablet sent this batch?".

### Draining

```javascript
Queue.drain = function () {
  if (draining) { return Promise.resolve({ skipped: true }); }   // no concurrent drains
  if (!navigator.onLine) { Queue.paint(); return Promise.resolve({ offline: true }); }
  ...
};
```

The `draining` guard matters: `drain()` is called from four places — on `online`, on
`visibilitychange`, on a 20-second timer, and after every `add()`. Without the guard, four
drains could run at once and send the same batch four times. The server would handle it (that is
what the UUID is for), but there is no reason to make the server do work the client can avoid.

Attendance records are batched into one `POST /api/attendance/sync`; actuals are posted one at a
time, because each one is a separate service.

**A deliberate detail.** When the sync returns, the client removes *every* attendance item it
sent — including the ones the server reported as duplicates:

```javascript
// Remove every attendance item we just sent. The server may have
// ignored some as duplicates — that is still a success for us,
// because the record is already there.
```

A duplicate means the record is already stored. Keeping it in the queue would mean sending it
again on the next drain, forever.

### When the drain runs

```javascript
window.addEventListener('online', function () { Queue.drain(); });
document.addEventListener('visibilitychange', function () { if (!document.hidden) { Queue.drain(); } });
window.setInterval(function () { Queue.drain(); }, 20000);
window.addEventListener('load', function () { Queue.paint(); Queue.drain(); });
```

Four triggers: the network coming back, the operator switching back to the app, a 20-second
timer, and page load. Between them, a queued record waits at most 20 seconds for a connection
and drains within a second of one appearing.

### What the operator sees

A pill on the scan screen shows how many records are still queued. It is the only feedback the
operator needs: if the number is not falling, the network is down, and the scans are safe.

---

## 4. The server side

### The constraint

`apps/attendance/models.py::AttendanceRecord`:

```python
client_uuid = models.UUIDField(unique=True, ...)
```

One column, one constraint. The specification says this gives idempotency "for free", and it
does — but the *accounting* does not come free, and that is the part worth doing properly.

### The service

`apps/attendance/services.py::sync_attendance_batch` does five things in order:

**1. Collapse duplicates inside the batch.** A tablet that lost its connection may have queued
the same scan twice before it ever reached the server. Those are collapsed to one:

```python
by_uuid: dict[uuid_lib.UUID, dict] = {}
for payload in payloads:
    try:
        key = uuid_lib.UUID(str(payload.get("client_uuid")))
    except (ValueError, TypeError, AttributeError):
        rejected.append({"client_uuid": ..., "reason": "malformed client_uuid"})
        continue
    by_uuid.setdefault(key, payload)
```

A malformed UUID is **rejected individually**, with a reason, and the rest of the batch still
lands. One bad record must not cost the kitchen 1,499 good ones.

**2. Find what is already stored.**

```python
already_stored = set(
    AttendanceRecord.objects.filter(client_uuid__in=uuids).values_list("client_uuid", flat=True)
)
```

**3. Insert the rest, ignoring conflicts.**

```python
AttendanceRecord.objects.bulk_create(records, ignore_conflicts=True, batch_size=500)
```

`ignore_conflicts=True` maps to PostgreSQL's `ON CONFLICT DO NOTHING`. A UUID that arrived in
the microseconds between step 2 and step 3 is silently skipped instead of raising.

**4. Count exactly.** This is the part that is easy to get wrong:

```python
present_now = set(AttendanceRecord.objects.filter(client_uuid__in=uuids).values_list("client_uuid", flat=True))
created = len(present_now - already_stored)
duplicates = len(present_now & already_stored)
```

The counts are derived from the database, not from the input. A record that was new to this
request but arrived from another tablet one millisecond earlier is counted as a duplicate, which
is what it is.

**5. Refresh the denormalised counter.** `MealService.attendance_count` is a cached count for
the live display; it is recomputed from the records after the insert, so it cannot drift.

### The response

```json
{
  "received": 1,
  "created": 1,
  "duplicates": 0,
  "failed": 0,
  "rejected": [],
  "audit_id": 5
}
```

### The audit

Every batch writes an `AttendanceAudit` row: device id, received, created, duplicates, failed,
a JSON detail of the rejections, and the start and finish times. When a mess manager asks
"why is the count 480 when I counted 500 people?", the audit table is where the answer is.

---

## 5. The service worker

`static/pwa/sw.js` is plain JavaScript with no build step — as the specification asks, *"the
service worker is plain JavaScript and is not a Django concern"*.

### What it caches

```javascript
var SHELL_ASSETS = [
  '/static/css/app.css',
  '/static/css/kitchen.css',
  '/static/js/app.js',
  '/static/js/kitchen.js',
  '/static/js/scan.js',
  '/static/pwa/offline-queue.js',
  '/static/pwa/manifest.webmanifest',
  '/static/pwa/icon.svg',
  '/static/pwa/offline.html'
];
```

**Only static assets are precached — no HTML pages.** This is deliberate. If the login page were
precached, the precache would contain the login page, and a tablet that opened the app offline
would land on the login screen instead of the kitchen screen. HTML is cached dynamically on
navigation instead, once a signed-in page has actually been fetched.

### The three strategies

| Request | Strategy | Reason |
|---|---|---|
| Static assets | **cache-first** against a versioned cache | assets are versioned by name; a new version is a new URL, so there is nothing stale to worry about |
| Navigations | **network-first** → cached page → offline notice | fresh data wins when there is a connection; the kitchen still works when there is not |
| API reads | **network only** | caching an attendance count would be actively misleading |
| API writes | **never intercepted** | the IndexedDB queue owns writes |

The API-read rule is the important one. An offline kitchen screen that showed yesterday's
attendance count as if it were today's would be worse than one that showed an error. So the
worker lets API reads fail and the UI shows what it knows, with the timestamp.

### The offline notice

`static/pwa/offline.html` is the last resort: a plain page saying the tablet is offline and that
the scans are safe. The inline fallback in the worker covers the case where even that file was
never cached.

---

## 6. What was measured

### 3,000 scans, in one batch

From `python scripts/bench_sync.py`, against the live PostgreSQL database, through the same
`sync_attendance_batch` the queue drains into:

```
3,000 scans sent in a single batch
  created      : 3000
  duplicates   : 0
  stored       : 3000
  elapsed      : 5.544 s
  throughput   : 541 scans/second
  per scan     : 1.848 ms

  a 45-minute window at one scan per second needs 2,700 scans
  headroom     : 5x

replay of the same 3,000 scans
  created      : 0
  duplicates   : 3000
  stored       : 3000
  elapsed      : 0.088 s
```

The specification's acceptance criterion is *"3,000 attendance records captured in a 45-minute
window across halls without loss"*. The write path handles it in 5.5 seconds — **five times the
headroom** — and stores every one.

The replay is the more important half. A tablet that loses power mid-sync and retries the whole
batch is the *normal* failure case, not the exceptional one. The replay creates **zero** rows
and takes 88 milliseconds.

The replay is also much faster than the first send, and that is expected: the first send pays
for creating the student records and for the inserts; the replay short-circuits because every
UUID is already known.

### The duplicate cases, individually

`tests/test_attendance_sync.py` covers each way a duplicate can arise:

| Case | Test | Result |
|---|---|---|
| The same batch sent twice | `test_resending_the_same_batch_stores_nothing_new` | 0 created |
| The same UUID twice in one batch | `test_a_single_duplicated_uuid_inside_one_batch_is_stored_once` | stored once |
| The same student from two tablets | `test_a_record_already_stored_by_another_device_is_ignored` | ignored |
| A malformed UUID | `test_malformed_uuid_is_rejected_without_losing_the_batch` | rejected with a reason; the batch survives |
| Over HTTP | `scripts/verify_e2e.py` | `created=1`, then `created=0, duplicates=1` |

---

## 7. Failure modes, and what happens

| Failure | What happens | Is it survivable? |
|---|---|---|
| The network drops mid-service | Scans queue in IndexedDB; the pill shows the count; they drain when the network returns | Yes — this is the designed path |
| The tablet loses power | The queue is in IndexedDB, which survives a restart. The unsent records are still there | Yes |
| The server rejects the batch (500) | `drain()` catches it, the records stay in the queue, the next drain retries | Yes — nothing is removed until the server accepts |
| The server accepts but the response is lost | The next drain re-sends; the server sees the UUIDs as duplicates and drops them | Yes — this is the exact case the UUID exists for |
| The tablet is stolen or wiped | The records that were not yet sent are gone. Records already sent are on the server | **No** — this is a device-security matter, not a sync matter |
| Two tablets scan the same student | The second is ignored as a duplicate | Yes — one student, one attendance |
| The student scans twice | The second is ignored | Yes |

The rule that makes the whole thing work: **a record is removed from the queue only after the
server has accepted the batch.** Failure keeps the data.

---

## 8. Known gaps

| Gap | Why it is not closed | What would close it |
|---|---|---|
| No automated browser test of the IndexedDB queue | the queue is tested at the API boundary and by reading the code; driving IndexedDB needs a real browser | a Playwright run: load `/scan/` with the network disabled, scan, restore the network, assert one record lands |
| The offline queue is not encrypted at rest | the tablet is on the campus network and the data is a student identifier and a count | a device-level policy, or encrypting the IndexedDB payload |
| No conflict resolution between two tablets | not needed — a duplicate is a duplicate, and the UUID decides | nothing, unless two kiosks serve the same hall, which does not happen |
| The queue has no size limit | a tablet offline for a week would accumulate records | a cap with a warning; not needed at the current scale |

---

## 9. Files

| File | Lines | What it does |
|---|---:|---|
| `static/pwa/offline-queue.js` | 258 | the IndexedDB queue, the UUID generator, the drain logic |
| `static/pwa/sw.js` | 132 | the three caching strategies |
| `static/pwa/offline.html` | — | the offline notice |
| `static/pwa/manifest.webmanifest` | — | the PWA manifest |
| `static/js/scan.js` | — | the capture screen: QR via `BarcodeDetector`, RFID, manual entry |
| `apps/attendance/services.py` | — | `sync_attendance_batch` — the server side |
| `apps/attendance/models.py` | — | the `client_uuid` unique constraint |
| `apps/core/views.py` | — | serves `/sw.js` and the manifest with the right headers |
