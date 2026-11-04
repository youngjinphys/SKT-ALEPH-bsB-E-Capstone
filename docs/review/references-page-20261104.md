# References presentation correction · 2026-11-04

The user clarified that references belong in a slide, not a separate page or header button. The separate route and links are removed. The sources slide is restored as slide 15 after the unchanged 14-slide, 20-minute presentation. All 37 repository/manuscript sources are grouped in the slide and remain available in its notes. The exact Discord attachment remains unverified.

The following records describe the earlier, superseded page implementation, not the current requested layout.

# References page · 2026-11-04

## Scope and provenance

The current user request was to read the markdown and add the missing references page. The exact earlier Discord request/attachment was not available when this patch was prepared; this is not represented as a verified restoration of yesterday's precise specification.

Read and used the current `apps/web/docs/presentation/final-20min-scenario.md`, active deck sequence and source registry. The existing `sources` authored slide is archived. Its renderer would also show only eight sources, so unarchiving it alone would not provide a complete reference page.

## Implementation

- Added the public, server-rendered `/capstone/references` route with a visible presentation-header link and notes-panel link.
- The page maps all 14 active slides to their citations, lists every unique source, and renders all 17 Q&A sections directly from the manuscript. On the reconciled a43013b base, the #3 evidence update and two newer DNS experiment links produce 37 deduplicated sources.
- The source registry and markdown remain authoritative. Sources shared by slides or paragraph links are deduplicated by document URL; per-slide back-links remain intact. Archived slide content is not silently added to the 14-slide sequence.
- Inline markdown links/code are converted to React nodes. Raw HTML is never interpreted, external links require HTTPS, and source links use `noopener noreferrer`.
- Added explicit build-file tracing for the markdown and JSON data so the route can read them in a packaged deployment.
- The current runtime uses Google Safe Browsing `v5/urls:search`. Its primary reference was corrected from the old v5alpha1 URL to the verified v5 reference. The old team-test snapshot remains distinguished from current API implementation.
- No DNS, authentication, security settings, production state, presentation timing or sequence is changed.

## Verification

- `npm run check` passed: TypeScript, content validation and production build, including the new route.
- `node --test tests/cloud/presentation-references.test.mjs`: 3 passed. Covers complete active-slide and Q&A inclusion, same-document deduplication, missing/invalid-source rejection, and no archived-slide leakage.
- `python tests/browser/presentation_references_http.py`: passed on the local built server. HTTP 200; 37 source entries, 14 slide mappings, 17 Q&A; unique IDs; existing internal-anchor targets; HTTPS external links; CSP; build trace includes manuscript/source registry.
- Before reconciliation, all 35 generated source destinations were retrieved: 16 pinned project GitHub documents/code files through the GitHub connector, and 19 primary external sources through web retrieval. The replacement Safe Browsing v5 page was separately retrieved after correction. This is link/source-identity validation, not a new execution of every historical experiment.
- `git diff --check` passed.
- Browser/visual QA is still unverified because the execution environment blocks Chromium's local socket at launch. The prior standard escalation failed during environment setup. Local HTTP/rendered-markup checks do not substitute for mobile/desktop visual QA. No deployment was attempted.

## Integration

Apply the references-only patch with three-way/hunk review of `SlideDeck.tsx`, `README.md`, `sources.json` and `next.config.ts` so concurrent presentation changes survive. Re-run the listed checks and approved browser/keyboard CI against the final combined tree. Deployment requires the user's authorization.

## Reconciliation on current main

- Reconciled against a43013b; preserved the newer DNS source entries, #9 experiments, flow controls, timestamp and mobile changes. Only the source-registry append needed conflict resolution.
- The exact Discord attachment was identified as `SKT-ALEPH-reference-index.md` (2026-11-03 07:53 UTC, message 1567084166531522690), but its 32-reference contents remain unavailable. The page is based on the separately verified current repository manuscript and source registry, not claimed to reproduce that attachment.
- Inspected the user image and changed only the architecture pipeline step 02 owner label from 관리자 to 정책기반 위험도 판정. Manual approval/signing and scope caveats remain intact.
- The final combined tree passes build, TypeScript, content validation, three reference-index unit tests and the local HTTP contract. Added these page checks and the evidence browser check to existing CI so launch-capable runners verify them before deployment.

## CI and visual follow-up

- Commit a7ae516 passed all CI, including 10 slide-3 layout states, three references/navigation/pipeline-label states and the full existing keyboard suite. The first ead6f54 run exposed a return-link client-navigation issue; native fragment links fixed it without weakening the test.
- Reviewed desktop and mobile CI screenshots. The global fixed build timestamp could overlay scrolling citations, so the reference route alone now places that metadata in normal footer flow. The presentation retains its existing reserved fixed footer.
