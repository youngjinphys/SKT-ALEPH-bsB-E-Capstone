# Dashboard header alignment audit · 2026-11-04

## Source and evidence

- Exact repository: `youngjinphys/SKT-ALEPH-bsB-E-Capstone`.
- Started from `c6a72a1298ced9bf20baa7a026fadca7d8139090`; rebased cleanly onto verified remote main `751335234c9fd33c8c2d20e465bd41e3f4b790fe` after concurrent PIN/presentation/deployment/DNS-observability changes. Work remained in an isolated checkout.
- The supplied cropped screenshot shows introduction/presentation link labels near the top of outlined controls, with the neighboring logout label vertically centered.
- The live `/dashboard` reproduces the issue. At 1188 CSS px, both anchor labels were 10.5px above center while the logout label was 0.5px from center. After an authorized PIN session became available, read-only DOM geometry at 792 CSS px showed presentation text on three lines, lock text on two, and the refresh button squeezed to about 30px wide. No PIN was read or logged, and no live policy action was used for testing.
- Narrow live checks at 500 CSS px and 333 CSS px (150% zoom) showed no horizontal overflow; at 333px the introduction label still split over two lines. Shared browser dimensions and original 150% zoom were restored afterward.
- This patch is local. Observations from the live site describe **before-change** behavior, not proof of deployment or acceptance of the fix.

## Root causes

1. The cloud adapter inserts anchors with the `quiet-button` class. The theme gives them a 40px minimum height and zero vertical padding but no internal alignment. Flex alignment on the parent centers the outer boxes, while anchor text remains at the top. A native button centers its own content, causing the visible mismatch.
2. The fixed sidebar remains present above 700px. Header context, cloud navigation, account action, status, refresh, and authenticated lock control compete in one flex row. Shrinking controls causes fragmented Korean labels and undersized icon targets.
3. Connection dot and status text are independent flex children. Introducing responsive wrapping without grouping them could separate the dot from its meaning. Account status can also include a long email address.
4. The old workbench's 64px header height conflicts with the theme's 79px minimum; a fixed height is inappropriate once rows can wrap.

## Change

- Shared final workbench styles explicitly center text in both anchors and buttons, remove default link underlines for these outlined controls, and keep 44px targets.
- Controls keep whole labels and do not shrink. The header grows when rows wrap; tablet context occupies its own row at 701–1100px. Mobile actions also wrap as whole controls rather than splitting words.
- Status dot and text share one non-interactive status element. Long status text is bounded and can break safely; no session/auth behavior changes.
- The compact mobile status remains visually a dot, but its text is visually hidden instead of removed from the accessibility tree.
- Existing focus indicators and `[hidden]` behavior remain intact. No authentication files, application controller, API, access policy, or presentation animation are changed.

## Regression checks

`tests/browser/dashboard_header.py` renders actual assembled local/cloud HTML and CSS with application scripts removed. It makes no authentication or API calls. Connected/PIN/account labels and lock visibility are synthetic layout states.

- 84 cases: local locked/connected and cloud locked/connected/PIN/long account, each at 320/360/390/700/701/707/768/787/1024/1100/1101/1280/1440/1920 CSS px.
- Actual glyph centering/containment, control count, single-line labels, minimum height, overlap, document overflow, status grouping/text containment, tablet rows, hidden lock state, native tab order, focus outline presence and containment.
- Selected header screenshots and JSON geometry are written to the configured artifact directory. The existing unified dashboard workflow runs this independent check before the authenticated workflow smoke test.

## Verification status

- Console Python: **21 passed**.
- Cloud Python: **49 passed, 2 skipped** because disposable PostgreSQL configuration is not present. Skips are not passes.
- Cloud JavaScript: **26 passed**.
- Python compilation, assembled cloud JavaScript syntax, and diff whitespace checks: passed.
- Local browser acceptance: **blocked before rendering**. Chromium failed to create its process singleton Unix socket (`Operation not permitted`). No sandbox or access restriction was bypassed. Geometry, keyboard, screenshot, and post-change visual checks are authored but **not executed** locally.
- Before release, run the header browser test in the normal permitted browser-capable CI environment and inspect its screenshots. A syntax/unit pass does not establish visual correctness.
