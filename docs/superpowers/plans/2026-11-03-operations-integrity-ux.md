# Operations integrity and guided dashboard implementation plan

**Goal:** Make the shared local/cloud control interface accurately describe its capabilities and support safe, inspectable operator decisions.

**Architecture:** Retain the existing Python compiler, credential separation, Next presentation, and same-project `/dashboard` routes. Correct concrete local IPC failures and cloud API parity; stage evidence changes and signed publication previews before explicit commit. Use the existing navy/cyan UI, with a compact workbench header, actionable status, searchable node fleet, and accessible confirmation dialogs.

**Constraints:** Main only. No new Vercel project. No automatic policy signing or approval. No live provider calls or private credentials in tests. Preserve concurrent commits and original slides.

## Task 1 — Local collector resilience
- Regression-test corrupt persisted status values and disconnected Unix clients.
- Validate actual field values; isolate each connection, and do not let a broken client stop the collector.
- Retain fixed commands, peer UID, bounded input, and persistent cooldown.

## Task 2 — Cloud operation parity and verified handoff
- Regression-test `nodes/unregister`, explicit capabilities, stale review imports, and chronological publication.
- Add evidence preview bound to current review/evidence state; archive old records, reset all new approvals, and prevent stale preview commits.
- Add signed publication preview; reuse exact signature/withdrawal/rotation checks and bind to current sequence.
- Keep the cloud collector honestly external-only; do not expose an unusable local socket action.

## Task 3 — Shared operator workbench
- Capture the current cloud and local UI before changing layout.
- Improve task hierarchy, next action, runtime badges, and mobile readability rather than duplicating the presentation page.
- Replace browser prompts with keyboard-accessible typed confirmation dialogs; lock conflicting writes and invalidate stale fetch results.
- Provide node search/status filters and accurate empty/error/stale states; never label missing observations as success.

## Task 4 — Verification and delivery
- Run Python suites (privileged and nonprivileged boundaries), JS syntax, cloud API contracts, and Playwright desktop/mobile workflows.
- Inspect before/after screenshots and console/page errors.
- Preserve main HEAD with a lease and atomically publish related runtime/UI/tests. Remove the temporary source-snapshot workflow after inspection.
- State live deployment, provider, Supabase, and LAN verification limitations explicitly.

## Execution evidence

Collector regression, cloud preview/commit parity and the shared workbench were
implemented and tested locally. Root/non-root policy suites and cloud suite passed;
browser harness captured desktop/mobile and confirmation screenshots. Production
network/auth/provider/LAN acceptance is explicitly outside these offline checks.
GitHub publication and final CI are checked against the current main lease.
