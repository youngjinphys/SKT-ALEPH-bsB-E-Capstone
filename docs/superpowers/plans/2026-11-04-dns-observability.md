# DNS observability and live dashboard

Goal: enrich signed node reports and make the existing /dashboard actionable, without collecting browsing history or disrupting DNS.

Design: retain v1/v2 reports and add validated v3 metrics. Measure existing active canary probes, host load/memory/disk/uptime, and opt-in dnsmasq aggregate CHAOS TXT counters. Preserve signatures, replay checks, policy identity and Naver DB isolation. Keep bounded per-node history atomically inside receipts. Authenticated read-only analytics endpoint; near-real-time polling with pause, visibility/offline backoff, stale markers, accessible SVG charts and reduced motion.

Alternatives considered: raw query logging/packet capture (privacy and low-memory hardware costs); external Prometheus/WebSocket platform (extra operational dependency). Selected: lightweight aggregate counters and the existing HTTPS push/poll pipeline. No WebSocket or zero-latency claim.

Limits: no client IP/domain history, no false block-count from NXDOMAIN, no percentile estimated from a handful of probes, no missing-to-zero conversion, no cross-boot counter rates, no unsigned health reports. At most 48 compact samples per node and 24h retention; old v1/v2 remain accepted. Existing keys and production state are never seeded or bypassed. main only; retain a single commit after 6966b0bcd6533543d4e04c32c9cf985b7ebe9a31.

Files: policy-sync/metrics.py (collection/schema), telemetry.py (signed envelope v3), policy-server/analytics.py (bounded history/aggregation), nodes.py + console.py + cloud/app.py (receipts/read endpoint), console_observability.py (HTML/CSS/JS), console_script.py (poll scheduling), install-dns-telemetry.sh (explicit metrics option), tests, docs.

Test sequence:
1. Failing tests for metrics shape, bounds, missing fields, protocol versions, reset/gap rates and retention.
2. Collector/schema and atomic history; run core/cloud regression tests.
3. Dashboard real API integration, query windows, table/CSV, stale and offline states, animation constraints; Node fake-timer tests + browser desktop/mobile flow.
4. Review diff and verify blob/tree equality; update main with expected HEAD lease; build existing Vercel project; verify public routes and unauthorized API access.

Research: dnsmasq official manual (CHAOS stats), RFC 9076 and RFC 8932 (data minimization), Prometheus instrumentation and histogram guidance (counter reset and distribution semantics). All operational samples in tests are synthetic and never published to production.
