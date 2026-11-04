# Node connectivity and quality diagnostics implementation plan

> Execute in the isolated validation sandbox; commit only the verified result to main.

**Goal:** Complete the existing signed resource graphs and make missing local telemetry actionable without fake measurements or new trust grants.
**Architecture:** Keep v1-v4 signed reports and bounded state unchanged. Add read-only receiver capability checks, version-aware operator guidance, and sample-qualified quality summaries. The real device retains its private key and replay counter.
**Stack:** Python/FastAPI, current Linux collector, bundled SVG/JavaScript and Node/browser regression tests.

- [x] Test receiver health without authentication, DB reads, or writes; test TLS/redirect/clock failures and local-only interface inference.
- [x] Implement an explicit HTTP health contract at GET /v1/nodes/report. Check it before changing local services.
- [x] Preserve existing node identity, public/private keys, counters and upstream choice when reconnecting. Infer an interface only from a unique local IP assignment.
- [x] Expose verified report format in analytics; identify legacy format 2 as upgrade-required, independently from expired policy.
- [x] Add failure-rate and NIC-error charts plus per-transport p50/p95 and adjacent-observation variation, with sample counts and hourly downsampling caveats.
- [x] Reject mixed interface counters during hotplug, test missing/restarted observations, and retain null values.
- [x] Run Python/JS/browser checks (desktop/mobile), verify untrusted requests are rejected, commit main and deploy the existing project.

Review focus: no production fixture insertion; no inference of local host access; no reset of live device counters; no claims of packet loss from DNS probe failure; do not treat API reachability as database/agent health.

Verification: 72 cloud tests (2 external-DB cases skipped), 59 JavaScript tests, 31 browser flow checks. A private isolated fixture provides browser telemetry; production received no synthetic data. The final deployment and local-host upgrade are reported separately.
