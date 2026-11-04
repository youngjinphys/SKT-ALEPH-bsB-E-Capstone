# Unified presentation and DNS operations implementation plan

## Goal and approved scope
Preserve PR-Page main 313164e65314032468d47e5c43273e35e77fba84 in apps/web, host the existing policy console at /dashboard, and use only the existing skt-aleph-capstone Vercel project and domain. No new Git branches. The Capstone main repository is the source of truth.

## Architecture
Vercel Services routes /dashboard and /api/ops to a Python control service, and all public presentation/auth routes to the unchanged Next.js application. DNS stays on local nodes. Python validators, signatures, review bindings and expiry rules remain authoritative. A dedicated Supabase JSONB snapshot with compare-and-swap revision persists only the control workspace. No local filesystem is durable, no online policy private keys are introduced, and no broad service-role key is used. Existing Supabase authentication is reused; operations require an explicit administrator allowlist separate from general Google login. Only reviewed public keys are accepted.

## Tasks and verification
1. Preserve all tracked source presentation assets and routes; alter only navigation and approved callbacks. Verify copied hashes and build/typecheck.
2. Add tested request authentication, immutable key pinning, bounded path validation, storage CAS and Python service adapter. Test absent config, unauthorized users, stale writes, corrupted payloads, node report verification and existing engine output.
3. Add isolated durable storage schema and constrained RPC credential. Deny direct table access, verify invalid capability and CAS conflicts; no changes to other application data.
4. Adapt existing console HTML/JS to cookie authentication and /api/ops paths; preserve local-server UI behavior. Add trusted-key upload, evidence import and independently signed publication actions, with explicit validation and failure states.
5. Configure same-project routing, run existing Python tests, frontend checks and browser smoke tests. Push only main and verify remote HEAD. Stage and validate the existing project's release before assigning the existing domain; record any provider limitations.

## Review focus
- Empty operator allowlist denies all operations, despite a verified general login.
- Public machine ingress verifies signatures and replay counters before durable writes.
- Concurrent snapshots fail with 409, never last-writer-wins silently.
- Publication requires independent signature, monotonic sequence and withdrawals acknowledgement.
- Preview credentials and operational production state must not be shared accidentally.
- Site import preserves assets and existing Google callback; unavailable services never become zero/healthy data.
