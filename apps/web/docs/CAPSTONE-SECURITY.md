# Capstone authentication and deployment — security boundary

## Decision: Google-only authorization code + PKCE

At the capstone root `/` there is one Google sign-in action, no email/password form, and no client-side Supabase key or token. The retired `POST /api/auth {action:login}` responds with HTTP **400 INVALID_ACTION**, without forwarding credentials to Supabase. This does not change the shared Supabase tenant's own password policy or other applications.

- `GET /api/oauth?action=status` checks the public Supabase provider settings and exposes only enabled/disabled/unknown.
- `GET /api/oauth?action=start` validates the exact canonical production origin, creates an unpredictable PKCE verifier/challenge, and sets a 5-minute host-only `Secure; HttpOnly; SameSite=Lax` verifier cookie.
- `GET /api/oauth-callback?code=...` requires the matching browser verifier, exchanges the code server-side, rechecks the Supabase identity and optional allowlist, then sets `__Host-capstone_at` / `__Host-capstone_rt` with `Secure; HttpOnly; SameSite=Strict`. Session tokens never appear in browser JavaScript, HTML or application URLs.
- `GET /api/auth` verifies Supabase identity online. Expired access tokens can refresh the session. Transient upstream failures respond with 503 rather than clearing legitimate cookies.
- `POST /api/auth {action:logout}` validates same-origin request metadata, clears app cookies and calls `/auth/v1/logout?scope=local`. This is important: Supabase defaults to **global** logout, which could disrupt the user's other sessions in the shared Claire identity tenant.
- `GET /app` revalidates the current identity in a Vercel server function. The protected page is currently a non-sensitive welcome screen, not a confidential dataset.
- `/fishing/` and `/capstone/` remain read-only public training/presentation pages, intentionally isolated from the account APIs.

## Google provider: verified incomplete configuration

On 2026-10-28 the production `/api/oauth?action=status` response was `{"provider":"google","state":"disabled","mode":"pkce","passwordRequired":false}`. **No real Google login can succeed until the provider is enabled**. The Supabase connector in this environment can inspect the project but does not have a supported method to set Google OAuth Client ID/Secret. Do not substitute an insecure bypass, test credentials, Claire admin keys, or a fake authenticated session.

1. Create a Google Auth Platform OAuth client of type Web application. Register JavaScript origin `https://skt-aleph-capstone.vercel.app`.
2. At Google Cloud, add the Google-to-Supabase redirect URI `https://ytvwpdjfrpwxwtucclpe.supabase.co/auth/v1/callback`.
3. In Supabase Authentication > Providers > Google, turn on Google and enter the authorized Google Client ID and Secret. Keep the secret in the Supabase dashboard; never put it in Git or a client env variable.
4. In Supabase Authentication > URL Configuration, set Site URL to `https://skt-aleph-capstone.vercel.app` and allow exactly `https://skt-aleph-capstone.vercel.app/api/oauth-callback` as a redirect URL.
5. Vercel already stores the encrypted server variables `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `CAPSTONE_SITE_ORIGIN`. Do not add a Supabase service-role/secret key to this app.
6. For team-only access, configure server-side `CAPSTONE_ALLOWED_EMAILS` before attaching confidential data. Without this optional list, any email-confirmed user of the shared Supabase tenant could enter only the non-sensitive landing. Long-term access control must be per resource, server-side, with audited RLS/RBAC.

## Validation contract and known boundaries

- Check `GET /api/health` for application env configuration and `GET /api/oauth?action=status` for provider readiness; these checks are not proof of a completed sign-in.
- After provider activation, validate a real approved Google account: provider redirect > Google selection > Supabase callback > verified `/app` > session refresh > current-session-only logout. Never claim this end-to-end test passed before credentials exist.
- The capstone page never requires a password. Google may still display its own email/password or MFA/account-selection UI **on Google's origin**, which is not a capstone-controlled form.
- Existing Claire API/data tables are not exposed from `/app`. Prior checks found RLS on the six public tables, but new data must be audited independently. Changes to shared Auth providers can affect Claire, so scope changes carefully.
- The PKCE cookie uses `SameSite=Lax` solely for Google's top-level redirect; session cookies use `SameSite=Strict`. Browser local/session storage does not persist auth secrets.
- Vercel production is publicly accessible while preview deployments still require Vercel Authentication. Preview URLs must not be registered as OAuth redirect origins.
- The public presentation and fictional law-firm demo retain `noindex` and disclosure policies. `noindex` is not access control.
- The PiraNyang mascot is a project-owned WebP asset with a motion pause control; browser reduced-motion preferences are respected.
- The former frontend `tests/` suite and Playwright E2E configuration were removed on 2026-11-02. Current CI checks TypeScript, slide-content consistency and the production build. Since 2026-11-04, the unified repository's existing Python Playwright runner also checks presentation keyboard navigation, input/modal focus guards, mobile pane keys and hydration in `tests/browser/presentation_keyboard.py`. This targeted coverage does not restore the former PKCE/session, full responsive-layout or disclosure-dialog suite. Live Google OAuth remains unverified.

References: [Google sign-in](https://supabase.com/docs/guides/auth/social-login/auth-google), [Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls), [Sign-out scopes](https://supabase.com/docs/guides/auth/signout).
