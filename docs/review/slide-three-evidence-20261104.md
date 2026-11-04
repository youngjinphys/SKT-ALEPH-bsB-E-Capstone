# Slide #3 evidence and alignment review · 2026-11-04

## Request and source scope

- [Year/count alignment request](https://discord.com/channels/1562649431948398662/1562649618536202324/1567362103302430860), 2026-11-04 02:17:25.607 UTC.
- [Request for a better basis than the small 40,000 increase](https://discord.com/channels/1562649431948398662/1562649618536202324/1567362370265677977), 02:18:29.256 UTC. This message did not explicitly identify a slide or reply target; association with adjacent #3 discussion is an inference.
- The active deck sequence identifies #3 as `friction`. The Pi experiment requests are separate and are not changed here.

## Findings and changes

1. The old chart had two bars, while its detached value list declared three desktop columns. Each numeric observation now keeps its period and count in the same column. Decorative bars are hidden from assistive technology; each period/value pair remains readable once.
2. APWG's rounded 3.76m to 3.80m change is only approximately 1.1%. It was a poor visual justification for choosing a DNS-layer project, even though the original notes did not call it explosive growth.
3. Slide #3 now shows **3,103,438 unique domains reported for phishing, May 1, 2025–April 30, 2026**, as a dated absolute-count card. The smaller two-year bars are removed. It is neither an estimate of all global phishing nor a count of victims/URLs.
4. The independent Okta AI-web-builder case stays separate. The headline does not claim AI caused the domain volume or that the ALEPH prototype blocked this many attacks.
5. Notes, presenter script, source registry, TypeScript model, content validator and JSON schema are updated together. No timing, slide ordering, DNS logic or production state is changed.

## Primary evidence and decision

- [Interisle/Cybercrime Information Center annual table](https://cybercrimeinfocenter.squarespace.com/phishing-activity-year-over-year-numbers-may-april-2026): 3,103,438 unique domain names in the specified observation year.
- [Interisle methodology](https://interisle.net/research-methodology): domains are deduplicated within/across feeds and across hostnames/URLs; these are observed registered-domain units, not a comprehensive census. Shared-hosting domain counts do not authorize blocking all children.
- The prior year's 1,542,922 appears in the same table, but consistency of the feed panel across both periods was not established. Therefore no +101% headline is used. A historical 2025 +38% series was considered but not substituted merely for a more dramatic comparison.
- [Okta July 2025 observation](https://www.okta.com/blog/threat-intelligence/okta-observes-v0-ai-tool-used-to-build-phishing-sites/) remains a distinct case, not a causal attribution.

## Validation

- `npm run check`: TypeScript, content validation (23 authored/14 active/9 archived, 1,200 seconds), production build passed.
- Modified slide #3 passed the declared JSON schema; negative, fractional and string statistic values were rejected. Full-schema comparison found existing unrelated schema/data mismatches, unchanged from the base commit; the repository content validator passed. These pre-existing mismatches were not broadened into this patch.
- `git diff --check` passed.
- Added `tests/browser/presentation_evidence.py` for five screen sizes × reduced/no-preference motion, exact value/period/source checks, no old bars, layout containment, reload and screenshots.
- Browser execution is **not verified here**: Chromium launch was blocked by the executor's local-socket restriction. Standard escalation then failed with a bwrap filesystem setup error. No alternate bypass or production browser run was attempted. Run the included test in the approved browser/CI environment after `npm run check`.
