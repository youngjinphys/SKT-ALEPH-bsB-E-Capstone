# DNS observability: aggregate metrics and near-real-time dashboard

## What is measured

The existing `/dashboard` overview now includes a signed-node telemetry workspace.
Measurements use the node's dedicated Ed25519 reporting key, the existing replay
counter, registered node identity and HTTPS report path. They do not grant remote
DNS administration and do not change policy approval, expiry or signing rules.

| Metric | Source and meaning |
| --- | --- |
| Local UDP/TCP A and AAAA duration, RCODE, timeout/error | The **existing approved BLOCK canary** checks, timed with a monotonic clock. Charts show per-report mean of valid local responses, not whole-network latency, p95 or client experience. |
| Upstream A response duration/status | Existing independently configured positive-answer reference. A DNS name already absent/blocked upstream never becomes proof of successful local blocking. |
| Cache hits/misses/insertions/evictions and configured size | Opt-in decimal CHAOS TXT `hits.bind`, `misses.bind`, `insertions.bind`, `evictions.bind`, `cachesize.bind`. Five bounded UDP requests; no query logging or arbitrary targets. |
| Cache lookup rate and hit ratio | Adjacent counter deltas only, same boot, rising uptime, non-decreasing counters and <=150s gaps. No rate over restarts, resets, missing values or hour-sampled gaps. This is **not total client QPS or blocked-request count**. Diagnostic requests can affect cache counters. |
| Host uptime, one-minute load, memory/disk usage | Fixed `/proc` files and `/var/lib` filesystem statistics. Load is runnable/waiting task count, not CPU utilization. No hostnames, process inventory or client identities. |
| Active BLOCK rules and policy expiry | Matched, signature-verified policy in the local inbox. Rule count is not intercepted request count. |
| Observation delay | Server receipt time minus node report time. Includes clock skew and collection work; not pure network RTT. |

Raw visited domains, client IP addresses, full DNS query logs, HTTP headers and
packet captures are not added. A short hash of Linux's per-boot ID detects a host
restart; it is not a stable hardware identity. The registered DNS node's address
and the already-approved canary remain part of the existing attestation contract.

## Collection and storage limits

Report format 3 adds `metrics`; receivers remain compatible with exact v1/v2
schemas. Malformed, duplicate or non-finite measurements and additional fields
are rejected. A signed envelope remains limited to 8192 bytes. Query logging is
not enabled; unsupported CHAOS counters remain null, not zero.

Each node receipt atomically stores the latest signed envelope and a bounded
receiver-maintained history: latest **48** observations plus the last observation
in each of at most **24** hourly buckets, no older than 24 hours when read.
Hourly points are **last samples, not hourly averages**. Idle histories are pruned
on the next valid report; expired samples are hidden immediately on read. An
idempotent report retry neither appends a sample nor refreshes its receipt time.
Key retirement prevents the old node key from reviving its history.

History is derived metadata authenticated at ingestion, not separately signed
compliance storage. The current signed receipt and pinned enrollment are checked
before history is exposed. The same PostgreSQL compare-and-swap transaction
commits receipt and history in the cloud. No new tables, service-role key, public
analytics API or unsynchronized in-memory production history is introduced.
The existing 8 MiB/512-file control-plane capacity still applies. This is bounded
capstone monitoring, not an indefinite Prometheus/time-series warehouse.

## Live UI behavior

- The dashboard refreshes its read-only overview/deployment views **10 seconds
  after completion** of the previous automatic request. Node collect/send timers
  retain their **60-second defaults** with jitter. This is near-real-time polling,
  not WebSockets, per-query streaming or a zero-latency guarantee.
- At most one automatic refresh is active. Network failures back off to 20, 40
  then 60 seconds. Requests have a 20-second browser deadline. Hidden tabs,
  offline connections, locked sessions and operator pause stop scheduling.
- Missing data is `—`; gaps are not interpolated. Expired reports retain their
  last known values with a stale warning. Server connection and actual DNS-node
  freshness are separate signals.
- Node selector and 15-minute/1-hour/24-hour windows survive updates. SVG line
  styles, point titles, keyboard focus, a data table and aggregate CSV expose
  the values without relying on color or hover alone. CSV excludes label/formula
  text and any browsing data. Mobile layouts avoid horizontal page overflow.
- A short value-change highlight and a request-progress pulse provide recency
  feedback. `prefers-reduced-motion` disables them. There is no ambient motion
  pretending that packets are flowing.

## Rollout on an existing DNS node

Deploy the receiver/dashboard **before** upgrading the node reporter. The new
receiver accepts old reports; an old receiver cannot accept v3. The website
cannot upgrade a private DNS host by itself.

1. On the DNS host, check out the tested commit. Follow
   `production-install-and-validation.md` and use the code-only
   `scripts/deploy/upgrade-policy-runtime.sh --role dns` procedure: stop the
   policy/telemetry writers first, review the preview, apply, then resume the
   prior services. Do not replace or reset node keys, replay counters or policy
   state. Runtime source-equivalence verification includes the new modules.
2. Existing collection units immediately emit host/probe v3 metrics after the
   runtime upgrade. To enable cache aggregates, repeat the existing telemetry
   install preview with the **same** device/address/key/URL and add
   `--cache-metrics`; only after review add `--apply`. Example placeholders:

```bash
sudo bash scripts/deploy/install-dns-telemetry.sh \
  --device-id edge-69 --listen-ip <existing-private-dns-ip> \
  --probe-upstream <existing-independent-upstream-ip> \
  --report-url https://skt-aleph-capstone.vercel.app/v1/nodes/report \
  --private-key /root/aleph-ops-secrets/status.pem \
  --public-key /root/aleph-ops-secrets/status.pub \
  --cache-metrics
```

Do not use the policy-signing private key for status reporting. The placeholder
IPs must be replaced with the enrolled configuration. Do not enable public UDP
53 or weaken firewall/management ACLs. If `--no-ident` or dnsmasq build features
suppress counters, leave the values unavailable rather than changing those
security controls merely to obtain graphs.

```bash
sudo systemctl start aleph-ops-collect.service
sudo systemctl start aleph-ops-send.service
sudo journalctl -u aleph-ops-collect -u aleph-ops-send -n 50 --no-pager
```

In the dashboard, select the enrolled node. A counter rate needs two valid
samples; no signed report means no invented chart. Verify an allowed LAN client
separately: node-local diagnostics do not prove that every client uses this DNS
or rule out DoH/VPN/IPv6 bypass.

## Research and verification references

- dnsmasq manual: https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html
- RFC 9076 (DNS Privacy Considerations): https://www.rfc-editor.org/rfc/rfc9076.html
- RFC 8932 (DNS privacy service operational guidance): https://www.rfc-editor.org/rfc/rfc8932.html
- Prometheus histogram cautions: https://prometheus.io/docs/practices/histograms/

Automated acceptance uses synthetic, signed reports in isolated MemoryStore and
loopback servers. No synthetic telemetry is inserted into production. Unit tests
cover format compatibility, strict bounds, retries, rollover, history gaps,
capacity, authentication and polling cancellation. Browser tests exercise real
API handlers, plots, selectors, pause, missing samples, reduced motion and mobile
widths. The browser fixture does not certify live Google OAuth or the user's LAN.
