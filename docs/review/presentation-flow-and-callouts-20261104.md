# Presentation flow and callout review · 2026-11-04

## Scope and causes

The shared term callout attached most leaders to the right of a word, without checking the rest of the line. It also mixed viewport rectangles with unscaled layout offsets. This caused the supplied CNAME and dnsmasq examples to draw across text or drift at zoom.

The DNS animation contained an explicit `initialTour` transition from the normal lookup to the blocked lookup. Shared explanatory flows advanced every 1.4–1.6 seconds and stopped once. These behaviors were separate from user selection and did not match the requested manual scenario model.

## Changes

- Route each decorative leader from any of the four sides of actual rendered word fragments. Complete text fragments, controls and the note are hard exclusions. Use consistent rendered coordinates and update on resizing, scrolling, font loading, content changes and finite layout/transform animations. If no safe route exists, preserve the explanation and omit only its decorative connector.
- Advance causal flow stages at 2.2 seconds and packets at 1.8 seconds. Hold the finished flow quietly for one second, then repeat that selected flow. The one-time DNS construction introduction is slower, and is not repeated on every loop.
- Scenario selection stays manual. Normal/blocked DNS, implementation/proposal, CNAME/SUBTREE, protocol choice and DNS route choice do not change due to timers. The policy-response comparison also keeps its selected state instead of selecting another button automatically.
- After a completed flow and its rest, unselected alternatives receive a subtle 3.6-second border/glow cue. It does not move focus, change text opacity, alter layout or select an option.
- Remove the DNS diagram's HTTP notice branch and its obsolete rendering branches. The separate HTTP-versus-HTTPS explanation and actual backend HTTP notice functionality are outside this removal's scope.
- Rename the DNS choice to `차단 대상 조회`, paired with `정상 조회`.
- Respect reduced motion, the deck's global motion pause, offscreen visibility and background tabs. Repeated visual steps do not generate endless screen-reader live announcements. Explicit selections remain accessible native buttons.

## Verification

- TypeScript, content validation and production build passed locally.
- 12 Node tests passed: three flow-state tests and nine callout geometry tests, covering both supplied screenshots, all five terms, multiline targets, fractional zoom, crowded layouts, 120 randomized arrangements and dense moving layouts.
- Geometry routing measured approximately 0.09–0.14 ms for representative 100/200-fragment scenes after safe lower-bound pruning.
- Added browser acceptance checks for real-time looping, the one-second rest, manual choices, cues, replay, pause, reduced motion, the active terms at five viewport sizes, 125% zoom, scroll and remounts. Updated existing keyboard/motion expectations for the removed DNS choice and label.
- Browser acceptance has not been executed locally: the existing environment cannot launch Chromium because its socket operation is restricted. The restriction was not retried or bypassed. Exact CI and deployed browser verification are still required.
- The user explicitly approved including the previously denied `presentation_controls.py` locator correction. Anonymous buttons use their stable DOM ordinal within a remounted slide state, instead of treating innerText containing aria-hidden text as an accessible name. All behavioral assertions remain in place.

Independent review also caught and resolved same-phase packet replay, initial motion-preference flashing, a timing-sensitive browser rest assertion, and detached callout-target retention.

No backend policy, authentication, dashboard, DNS deployment or experiment data was changed. This review does not claim that source changes have been published or deployed.

## Exact main CI follow-up

The first run on `61ab9ac` passed the build, dashboard browser checks, keyboard navigation and text transitions, then the new all-term audit exposed an orphan SNI definition on the precedents table. Its authored data explicitly removed the SNI example because TLS is a different layer, but EvidenceTable still selected the annotation by slide ID. Remove that stale binding, the special text rewrite and unused SNI layout styles rather than restoring unrelated content. The browser suite now checks the four active annotations and explicitly rejects the orphan definition on precedents.

Responsive stress tests permit safe omission of a decorative leader only while retaining the visible target and accessible explanation. All four desktop baselines must show a collision-free leader; text inside both the diagram and its explanation is checked. The dnsmasq baseline also verifies that its marker can choose the top of the word.

## CNAME connector placement

The CNAME connector was nested inside each card. A compact mobile grid placed it beside the domain in the lower-right cell. Render connectors as sibling rows between cards instead. The arrow stays on the shared card centerline, with the relationship label beside it and the existing packet/replay behavior preserved. Remove the obsolete child-grid rule. Browser checks assert the between-card bounds, centered arrow and unclipped label at all five viewports and zoom.

The second exact run (`58e27ca`) passed all four active callouts at five viewports and zoom and the DNS loop/manual selection checks. It then exposed a timing/focus-sensitive replay assertion. The test now sends R from the current scrolled view, waits for the replayed cycle/old decorative element removal, and still requires the old element to detach. It waits for route visibility before testing replay rather than racing IntersectionObserver.
