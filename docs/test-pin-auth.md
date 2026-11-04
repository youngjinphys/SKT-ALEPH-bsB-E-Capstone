# Temporary dashboard PIN login

This is a shared **test operator** login, not individual identity or MFA. It grants the same operations permissions as an authorized dashboard operator, including writes. Use only with approved test users and test data. Existing Google login stays available when configured.

## Before enabling

1. Review and apply `cloud/migrations/002_test_pin_auth.sql` to the same dedicated operations database used by `ALEPH_STATE_URL`. Migration 001 must already exist. Do not change the database capability or authentication project as part of this migration.
2. Run the PostgreSQL integration test against a **disposable local database only** using `PIN_TEST_DATABASE_URL`; the test creates roles and applies both migrations. It is deliberately not a production health check.
3. Obtain approval to create/register a new test login credential and enable it in production. Never commit credentials or send the raw PIN through chat/logs. Generate a random 8–12 digit PIN using a secure setup channel. A short/common/reused PIN remains weak even with throttling; prefer a random 12-digit PIN.
4. Store only salted scrypt hashes in server-only environment variables. Format: `scrypt$<16-byte salt as 32 hex>$<32-byte digest as 64 hex>` with n=16384, r=8, p=1. Do not use NEXT_PUBLIC or VITE variables.
5. Configure `CAPSTONE_TEST_PIN_HASH`, `CAPSTONE_TEST_PIN_STARTS_AT` and `CAPSTONE_TEST_PIN_EXPIRES_AT` (integer Unix seconds, positive period no longer than 14 days), then `CAPSTONE_TEST_PIN_ENABLED=true`. No default credential exists. Missing/malformed/expired settings disable PIN login.
6. Optionally set `CAPSTONE_TEST_ACCESS_CODE_HASH` using the same format for an additional long random shared code. This is not an independent second factor. Leaving it unset does not weaken the mandatory session, origin and rate-limit protections.
7. Redeploy after approval and test login, protected operations, failed PIN, logout, reload and expiry. Keep the previous deployment/environment configuration available for rollback. Never enable while migration or database availability is uncertain.

## Protections and limitations

- All serverless instances reserve attempts through one PostgreSQL row lock before verifying credentials. Rolling limits allow at most 5 attempts per minute and 30 per hour globally, regardless of claimed IP. The array is bounded to 30 timestamps. A distributed attacker can consume this quota and deny new logins; this does not grant access. Public shared PIN login is not suitable for long-term production authentication.
- Sessions contain 256 random bits, last at most 15 minutes and never outlive the configured test period. Only SHA-256 session hashes are stored in the private RLS-protected database table. Cookies are Secure, HttpOnly, SameSite=Strict and `__Host-` scoped.
- POST requests require the configured site origin. PIN values are cleared from the form immediately and never stored in browser storage. Database/configuration failures deny access, not bypass it.
- PIN/extra-code/expiry rotation changes the session configuration fingerprint. Disabling blocks existing PIN sessions immediately on the newly deployed code. Re-enabling identical settings may revive an unexpired session: rotate the PIN hash or explicitly delete test sessions to revoke permanently. Those operations require the appropriate approval.
- The global limit and shared identity mean individual attribution and individual revocation are unavailable. Use individual identity authentication for real users or sensitive data.
- Preview deployments cannot use the production operations database through the adapter.
- Logout requires successful server revocation. If storage is unavailable, the UI stays locked and reports failure so the user can retry. Clearing a browser cookie alone is not described as successful server logout.

## Rollback / cleanup

Disable the PIN environment flag and redeploy; preserve existing Google and database settings. Remove only this feature's credentials after confirming they are no longer used and obtaining required approval. Do not revoke a shared operations capability merely because Google setup was abandoned. Retain the migration tables until session cleanup and recovery requirements are settled.

## Validation evidence (2026-11-03)

The script `tests/cloud/sql/pin_isolated_validation.sql` passed on PostgreSQL 17 through the Naver Supabase connection, using session-local temporary tables/functions and an explicit rollback. A follow-up catalog query confirmed zero test tables or test RPC functions remained. It verifies rolling attempt limits and window release, maximum session lifetime, creation/check/rotation/deletion, and rejection by a synthetic authorization stub. It does **not** prove real capability validation, deployed grants/RLS, multi-connection concurrency, or browser/end-to-end behavior. Those deployment gates remain open.

A separate Free-plan project (`aleph-pin-validation`) was provisioned with approval and a verified $0/month quote. Migrations 001/002 applied successfully. Twelve anon-role RPC requests were submitted concurrently; a follow-up database read found exactly five accepted reservations, spanning 20.4 seconds. The RPC tool returned only each batch's final SELECT, so per-request allow/deny values and distinct connection IDs were not captured. Treat this as a parallel-call rate-limit smoke check, not comprehensive contention verification. All four private tables report RLS enabled and no anon SELECT/INSERT privileges. A test-counter reset approval expired; it was not retried or bypassed. Production was not changed. Full session/capability rejection, contention and browser end-to-end validation remain pending.

On resumption, the dedicated test counter reset succeeded. A subsequent eight-request parallel run was interrupted by approval review; follow-up reads found two accepted reservations, so its outcome is partial and it was not repeated. Independent read-only negative checks passed: anon session RPC with an incorrect capability returned SQLSTATE 42501 (`Invalid operations capability`), and direct anon access to the private sessions table returned SQLSTATE 42501 (`permission denied for schema`). Both anon and authenticated lack private-schema USAGE while having execute permission on the capability-gated public RPCs. Session count is zero. These negative checks do not establish positive session lifecycle or full concurrency correctness.
