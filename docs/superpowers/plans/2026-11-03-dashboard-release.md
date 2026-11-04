# Existing-project dashboard release plan

**Goal:** Release the unified main branch at the existing skt-aleph-capstone.vercel.app/dashboard, preserving the presentation and authorization.

**Architecture:** Retain apps/web Next.js and cloud FastAPI with the existing project, Supabase identity and revision-protected state. No new Git branches, project, secrets or DNS daemon.

**Review focus:** stale PR-Page Git link; disabled Google provider; OAuth error return paths; stale provider-availability links; preservation of all 131 source files.

1. Verify reference source coverage and current production routes; run cloud, login race and frontend checks.
2. Reproduce unavailable-provider stale-link behavior; test strict OAuth return-path handling before editing it.
3. Preserve /dashboard on OAuth failures, keep all error codes allowlisted, add user-facing login guidance.
4. Commit tested source on main with an expected-HEAD lease. Gate production builds to the unified source, without modifying credentials or weakening auth.
5. Build the exact commit in the existing Vercel project, verify routes, promote to the existing domain, check runtime errors.
6. Report external setup honestly: Google OAuth client setup and a Git-link change require authorized account configuration when tools cannot perform them.
