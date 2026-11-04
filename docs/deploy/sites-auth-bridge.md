# Sites operations bridge

This is an optional server-to-server authentication adapter. The existing Vercel
Google/PIN login, operator allowlist, policy signatures and publication workflows
are unchanged. No DB credential moves to Sites, and no cross-origin browser API
access is granted. The backend frame policy is unchanged.

## Provisioning (separate approval required)

1. Review and apply `cloud/migrations/003_sites_bridge_nonce.sql` on the existing
   **operations** DB, after migration 001. It uses the existing private capability
   authorization, RLS, and one atomic nonce insertion shared by all workers.
2. Generate one random 32-byte key and encode as unpadded base64url. Install as
   `CAPSTONE_SITES_BRIDGE_SECRET` only in the two server environments. Never put it
   in browser code, source, command arguments, logs or public build variables.
3. Configure Vercel `CAPSTONE_SITES_BRIDGE_ORIGIN` to the exact published Sites
   origin, without a trailing slash. Do not change `CAPSTONE_OPS_ALLOWED_EMAILS`.
4. Deploy reviewed source only after approval. A missing migration/key/config
   fails closed. Do not fall back to a process-local nonce cache.

## Wire protocol v1

Only `GET` and `POST` to the allowlisted `/api/ops/` paths in
`cloud/sites_bridge.py` are supported; no query strings, redirects, arbitrary
upstream hosts, test-auth, auth or OAuth endpoints are forwarded. Maximum signed
body is 3 MiB; individual ordinary routes retain their tighter parsing limits.

Sites derives the email only from its server-native authenticated ChatGPT user.
Before signing a POST, require the exact browser Sites Origin and same-origin
Fetch Metadata. Construct fresh upstream headers, never forwarding browser
Cookie, Authorization, platform identity headers or supplied assertion headers.
Forward the exact validated Sites Origin for POST, not the Vercel origin.

`X-Aleph-Sites-Assertion` is unpadded base64url of UTF-8 JSON with exactly:

- `v`: integer 1
- `iss`: exact configured Sites origin
- `aud`: `aleph-ops`
- `email`: verified native identity email, checked against existing allowlist
- `iat`, `exp`: integer Unix seconds, maximum 30-second lifetime, 5-second future skew
- `jti`: fresh lowercase UUID v4 for each upstream request
- `method`: uppercase HTTP method
- `path`: exact canonical request path without a query
- `body_sha256`: lowercase hex SHA-256 of the exact outgoing bytes (empty for GET)

`X-Aleph-Sites-Signature` is unpadded base64url HMAC-SHA256 over the ASCII assertion
header, keyed by the decoded 32-byte secret. No JSON canonicalization is needed;
the encoded bytes themselves are signed. Duplicate JSON keys/headers are rejected.
Any assertion header opts into bridge verification, never existing cookie auth.
All POST assertions, including preview requests, are durably consumed before
dispatch. A failed request needs a fresh assertion; automatic mutation retries
could duplicate a committed operation and must not be used blindly.

Replay RPC: `aleph_sites_consume_nonce(capability text, nonce_hash text,
expires_epoch bigint) -> boolean`. `nonce_hash` is SHA-256 hex of issuer, newline,
and UUID. Storage outage returns 503. GET session checks require no DB access.

## Dashboard assets

Public non-secret source endpoints:

- `/dashboard?surface=sites`
- `/dashboard/assets/console.css?surface=sites`
- `/dashboard/assets/console.js?surface=sites`

Sites serves these bytes at its own origin, with an appropriate own-origin CSP.
Sign-in/out use normal `target="_top"` anchors to the platform routes
`/signin-with-chatgpt?return_to=%2Fdashboard` and
`/signout-with-chatgpt?return_to=%2F`. Platform callback handling is untouched.
Session verification goes exclusively through `/api/ops/session` and the
existing epoch-guarded controller. The normal Vercel assets retain Google/PIN UI.

## Verification

`PYTHONPATH=apps/policy-server/src:packages/policy-sync/src:. python -m unittest discover -s tests/cloud -p 'test_*.py'`

`node --test tests/cloud/*.test.mjs`

Unit tests mock the nonce RPC; they are not evidence that the production migration
has been applied. Verify actual PostgreSQL concurrent replay rejection separately
before enabling mutating bridge traffic, then verify native login, rejected
nonoperator, all dashboard views, interrupted login/logout, and a safe preview.
