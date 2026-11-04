# GUI Threat Intelligence Refresh — security and integration audit (2026-11-03)

## Actual implementation path

`policy_server refresh` already handles OpenPhish Community text feed → Google Safe Browsing v5 `urls:search` → bounded `collected.json`, `verified.json`, `review-template.json` and `latest.json`. The existing 12-hour collector timer remains unchanged.

The new `policy_server.refresh_bridge` is a dedicated **non-root** Unix-socket worker running as `aleph-policy-server`, activated by systemd. Only the `aleph-ops-console` UID may request `status`, `start`, or the collector's **latest run** snapshot. Kernel `SO_PEERCRED` is verified. There are no arbitrary URLs, shell commands, custom API requests, signing or DNS publication operations in the IPC grammar. The API key remains a 0600 collector-owned file; the console service has neither read rights on it nor an argument to provide another key.

The GUI exposes `GET /api/intel` (metadata only), `POST /api/intel/refresh` (requires explicit terms/data disclosure acknowledgements) and `POST /api/intel/import` (exact newest run/fingerprint, current review revision and typed confirmation). Raw suspicious URLs are transferred only over protected local IPC to a 0700 reviewer workspace, never returned in browser responses. Console review lists continue to show domain and URL hash, not source URL.

## Safety constraints

1. **Concurrency/quota:** 5-minute persistent manual request cooldown, one active bridge worker, and the existing `.refresh.lock` across timer and GUI refreshes. Status differentiates idle/running/success/error/interrupted/unavailable.
2. **Fail closed:** errors in fetching OpenPhish, GSB calls, parsing, writing, credentials or runner access cannot overwrite `latest.json` with partial evidence or change currently approved DNS policy.
3. **Evidence replacement:** no automatic import. Each latest-run transfer is fingerprint checked and bound to on-disk review revision; existing verified and review files are backed up in owner-only `evidence-archive` before explicit replacement. Newly imported review approvals always start `false`.
4. **Trust boundaries:** separate offline Ed25519 policy signing, root-only `promote`, DNS fetch/apply and device-signed telemetry are unchanged. A successful dataset refresh is **not** a blocklist update or proof of edge DNS enforcement.
5. **Privacy:** upstream GSB `urls:search` sends the OpenPhish URL candidates to Google. GUI does not receive API credentials. The private collector storage and archived verified artifacts may contain raw malicious URL strings; back them up securely and establish retention rules.
6. **External limitations:** OpenPhish Community typically refreshes on a roughly 12-hour cycle, while GSB response cache duration and project evidence freshness may be shorter. Clicking refresh every five minutes cannot produce new OpenPhish intelligence every time. This manual workflow alone cannot guarantee continuous blocking.

## Tested paths

- Fixed collector command and peer UID; rejects arbitrary actions, unsupported fields and path traversal.
- Persistent cooldown, overlapping requests, restart status, provider error preservation.
- Signed policy/review workflow remains isolated; new evidence does not inherit previous approvals.
- Browser API rejects missing bearer and cross-origin writes; metadata response contains no full URL.
- Unix socket client refuses world-permissive endpoints and non-sockets; non-root CI exercises a real `SO_PEERCRED`-checked socket.
- Installed units and scripts are validated through shell dry-runs, Python tests, JavaScript syntax, and GitHub Actions.

## What must still be verified in production

Actual OpenPhish/GSB requests require a valid account, API key, network egress and compliance with both providers' current terms. Deploying the bridge requires the existing dedicated users, identical reviewed runtime at `/opt/aleph-policy-code`, systemd Unix-socket activation and HTTPS/VPN access to the console. The repository's offline CI does not use real credentials or attest to a live server installation. A failure is visible in the GUI and detailed diagnosis remains in systemd's service logs.

Official references: [OpenPhish Community feed](https://github.com/openphish/public_feed), [OpenPhish feed cadence](https://openphish.com/phishing_feeds.html), [Google Safe Browsing v5 URLs search](https://developers.google.com/safe-browsing/reference/rest/v5/urls/search).
