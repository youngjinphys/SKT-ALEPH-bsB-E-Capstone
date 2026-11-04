# Operator integrity and interface review — 2026-11-03

## Scope and retained decisions

Reviewed the current unified Capstone main tree, including the standalone Python
console, Unix collector bridge, Vercel `/dashboard` adapter, cloud storage
transactions and the shared browser assets. The Next presentation and slides
were preserved. Credential separation, manual SUBTREE approval, independent
policy signing, monotonic policy sequences and device-signed status reporting
remain valid decisions and were retained.

The earlier claim that the GUI was fully connected needed qualification: the
Unix collector integration applies to the standalone policy host, not Vercel.
This review makes the difference explicit rather than simulating a connected
collector or placing API/signing credentials in the browser.

## Reproduced findings and corrections

| Finding | Consequence | Correction and evidence |
| --- | --- | --- |
| Persisted collector status validated field **names**, not values | A malformed `error_code` could enter status responses | Validate `data[field]`; regression fails against old implementation |
| IPC response write was outside the per-client exception boundary | A disconnected Unix client could stop the service loop | Catch response I/O failure per connection; next request is still serviced |
| Cloud API offered `nodes/remove` while UI called `nodes/unregister` | Registered device removal returned 404 | Canonical UI route plus compatibility alias |
| Cloud evidence import bypassed the local archive/reset workflow | Prior evidence/reviews had inconsistent recovery semantics | Shared preview-bound import, owner-only backups, no inherited approval |
| Preview not bound to both evidence and reviews | An operator could confirm a different state from the inspected state | Context revision covers both files; conflicting commits return 409 |
| New sequence accepted older policy issuance | Cloud behavior was weaker than root publisher chronology | Strictly later `issued_at` required as well as increasing sequence |
| Declared cloud JSON request limit was ignored by a smaller parser | Valid large input was rejected as malformed JSON | Strict bounded decoder uses the endpoint's explicit limit |
| Draft generation fetched fresh approvals at click time without binding displayed state | Concurrent approvals could change the decision being confirmed | GUI and HTTP build bind the displayed review-set revision |
| UI shared identical affordances across different execution modes | External-only cloud collection looked like broken local integration | Explicit capability response and mode-aware actions |
| Destructive browser prompts lacked inspectable context | Harder to compare identity, scope and effects before commit | Accessible typed dialogs, fingerprints, publication delta preview, cancellation |

## Implemented operator features

Compact context header and next-action panel, review queue counts, node search and
status filtering, clear empty/error states, duplicate-submit protection, focus
restoration, Escape cancellation, and lock-time invalidation of pending actions.
Cloud key registration displays the computed fingerprint before trust is saved.
Cloud publication displays changes and acknowledgement requirements before the
signed envelope is committed. Read-only previews do not update durable state.

## Validation performed

Local policy-server suite: 105 tests discovered in each privilege mode. Root run
passed with 7 expected non-root-only skips; non-root run passed with 19 expected
root-only skips. Cloud suite: 25 tests passed after preserving the concurrent session-authorization
update; all 5 existing JavaScript login race tests also passed. Browser acceptance: 12 named local
and cloud scenarios passed with zero page errors; desktop 1440 and widths 390/768
were rendered and checked for horizontal overflow. JavaScript syntax and markup
contracts are checked separately. GitHub CI repeats these tests with repository
pinned dependencies and retains synthetic screenshots/results.

Screenshots use isolated synthetic data, not production screenshots. Browser
fetch is connected to real loopback API handlers through a harness binding;
production network routing and CSP are not covered by that transport. No live
provider credentials, Supabase project mutation, Vercel project creation, remote
root command or real DNS policy deployment was performed in this review.

## Remaining boundaries

A signed node report is not TPM remote integrity attestation. Neither local DNS
probing nor UI status demonstrates every LAN client's DNS path. Public key
revocation/rotation and storage retention remain explicit administrator tasks.
The state snapshot is bounded; archives can consume its capacity and are not
automatically deleted. Multi-user RBAC, immutable audit storage and a durable
cloud collection scheduler are not added here. These are architectural choices
requiring separate authorization and acceptance, not reasons to silently widen
the web console's privileges.
