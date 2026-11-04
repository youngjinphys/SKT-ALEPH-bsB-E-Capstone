# Dashboard background refresh

## Confirmed cause

The serialized 10-second poller calls the same `loadDeployment()` used for an
initial view load. That loader cleared published rules, node cards, counters,
and selected-node evidence before awaiting both HTTP requests. Every normal
poll therefore visibly reverted to an empty/loading display. Analytics already
kept its last observations during requests, so the destructive deployment read
was the primary cause rather than a full-page browser reload.

## Changes

- Keep the rendered data during same-session, same-target revalidation. Show
  “갱신 중 · 마지막 조회” and an explicit last-result verification notice.
- Disable node mutations while evidence is being rechecked; revalidate current
  node/key identity after any confirmation. Do not alter policy or DNS state.
- Keep identical rule rows, node cards, and target options in place. Track the
  actual rendered filter and invalidate the cache when changing target.
- Preserve the existing fail-closed contract after a failed read: clear the
  failed source, retain the independently successful source, and report partial
  failure. This is not an indefinite stale-success cache.
- Treat partial polls as failures for retry backoff. Wait for both overview
  reads to settle. Invalidate old polling epochs on view navigation.
- Process 401/403 before parsing response bodies. Purge snapshot, list, and
  read-only scalar state on lock; stale old-session responses cannot lock or
  repopulate a new session. No credentials or data are persisted.

## Verification

The real-controller Node regression tests use synthetic DOM/network transport,
not copied loader implementations. They cover pending reads, unchanged DOM,
filter reversals, A→B→A and out-of-order requests, independent failures and
identical recovery, logout, idle expiry, JSON/non-JSON 401/403, obsolete auth
responses, partial polling backoff, old-view errors, and overlapping overview
reads. Existing browser smoke assertions for failures and selected-target
identity remain in place. The browser suite additionally holds a real automatic
poll and checks row identity, displayed values, disabled mutations and recovery.

Local: 46 JavaScript tests passed; 21 console Python tests passed; 63 cloud Python
tests ran (61 passed, 2 skipped because disposable PostgreSQL is unavailable).
Assembled cloud JavaScript syntax, Python compilation and whitespace checks pass.
Browser rendering is not claimed from the local sandbox: Chromium's process
singleton socket is restricted. Exact-commit GitHub CI is the browser verification
path. A read-only live check reached the expired-session login screen; no PIN or
protected production data was accessed and no production state was changed.
