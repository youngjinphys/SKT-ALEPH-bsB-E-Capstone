# Combined latency comparison and prototype summary

## Verified requests

- [Show p50 and p95 together and make their changes legible](https://discord.com/channels/1562649431948398662/1562649618536202324/1567365841689903144), 2026-11-04 02:32:16 UTC.
- [Remove “반례” from the prototype's confirmed-content summary](https://discord.com/channels/1562649431948398662/1562649618536202324/1567367504014352514), 02:38:53 UTC. The current `precedents` table contains the exact E조 프로토타입 row described in the request.

## Changes and boundaries

- Each latency condition now places p50 and p95 on the same zero-based axis. Circle and diamond markers identify the two percentiles; exact values remain printed together beneath each row.
- Every nonbaseline row shows both percentile differences from the stated comparison baseline, including whether that observation is faster or slower. No result is forced into an increase: one condition's median is lower while its p95 is higher.
- The joining segment is explicitly a p50–p95 span, not an error bar or confidence interval. No uncertainty estimate was invented from two summary values.
- All source observations, sample sizes, quantile method, CSV links and limitations remain unchanged. Differences of percentile summaries are not paired-difference estimates or causal policy cost.
- Removed the counterexample claim only from the precedents prototype summary and its matching presenter sentence. The separately demonstrated CNAME and SUBTREE limitations in slide #9 remain visible.
- Updated actual-control browser assertions to inspect both percentiles across all four conditions and to retain left/right slide navigation after condition selection.

## Verification

- Independent standard-library test checks the pinned CSV SHA-256, all 440 included observations, per-arm sample/success counts and every displayed p50/p95 using linear interpolation.
- The same test verifies the requested summary wording and preservation of the #9 limitations.
- Production build, TypeScript/content validation, local references HTTP and existing unit tests are rerun before integration.
- Browser layout and keyboard checks require the approved CI runner. No deployment is performed by this change.
