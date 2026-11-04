"""Restrained semantic accents for the shared local and cloud console.

Neutral surfaces dominate. Category color identifies a metric, never proves
health; labels, line styles and explicit stale/error states remain authoritative.
Loaded last so component-specific chart colors share the same legend tokens.
"""
CSS = r'''
:root {
  --tone-sky: #9bbfd8;
  --tone-sage: #9fc9b4;
  --tone-lilac: #bca9dc;
  --tone-amber: #ddbc88;
  --tone-rose: #e0a0a5;
  --tone-muted: #a9b5c4;
  --base: #101722;
  --panel: #171f2b;
  --surface: #1b2431;
  --cyan: var(--tone-sky);
  --green: var(--tone-sage);
  --amber: var(--tone-amber);
  --red: var(--tone-rose);
  --ops-focus: #bad6eb;
}
body,.shell {background:#101722;color:#edf1f6}
.sidebar {background:linear-gradient(180deg,#1a2332,#111923);border-color:#344252}
.topbar {background:rgba(20,27,39,.96);border-color:#344252}
.hero {background:radial-gradient(ellipse at 92% 5%,rgba(164,141,199,.12),transparent 60%),linear-gradient(120deg,#1d2837,#151e2b);border-color:#394757}
.hero .eyebrow,.hero-trust {color:var(--tone-muted)}
.eyebrow-line {background:var(--tone-lilac)}
.nav-item.active {background:#293342;border-color:#4c6072;color:#eff3f7}
.nav-item.active::before {background:var(--tone-sage)}
.nav-item.active .nav-icon {color:var(--tone-sage)}
.button.primary {background:var(--tone-sage);border-color:var(--tone-sage);color:#10211c;box-shadow:none}
.button.primary:hover:not(:disabled) {background:#bbdbca;border-color:#bbdbca}
.button.primary.hero-primary {background:var(--tone-lilac);border-color:var(--tone-lilac);color:#20192c}
.button.primary.hero-primary:hover:not(:disabled) {background:#d0c2e6;border-color:#d0c2e6}
.button.outline,.button.secondary {background:#202a38;border-color:#506174;color:#dbe5ef}
.button.outline:hover:not(:disabled),.button.secondary:hover:not(:disabled) {background:#2a3646;border-color:var(--tone-sky)}
.surface,.stat-card {background:#1b2431;border-color:#354353}
.runtime-context {background:#161e2a;border-color:#354353}
.runtime-dot,.connection-dot.online,.signal-mini {background:var(--tone-sage);box-shadow:none}
.stat-card {--card-accent:var(--tone-sky);box-shadow:0 12px 30px rgba(0,0,0,.13),inset 0 1px 0 rgba(255,255,255,.03)}
.stat-card:has(#stat-approved) {--card-accent:var(--tone-sage)}
.stat-card:has(#stat-drafts) {--card-accent:var(--tone-lilac)}
.stat-card::before {background:var(--card-accent);width:36px;left:22px;right:auto;opacity:.85;height:2px}
.stat-card .stat-symbol,.stat-card .stat-value {color:var(--card-accent)}
.stat-card .stat-symbol {background:rgba(161,180,204,.07);border:1px solid rgba(161,180,204,.19);border-radius:8px}
.stat-card p {color:var(--tone-muted)}
.fleet-metrics>div {--card-accent:var(--tone-sky);background:#17212e;border-color:#354353}
.fleet-metrics>div[data-metric="attested"],.fleet-metrics>div[data-metric="correlated"] {--card-accent:var(--tone-sage)}
.fleet-metrics>div[data-metric="pending"] {--card-accent:var(--tone-amber);background:#28251f;border-color:#66543e}
.fleet-metrics>div strong {color:var(--card-accent)}
.fleet-metrics small {color:#b2bdcb}
.pipeline .stage {background:#17212e;border-color:#394858}
.pipeline .stage-number {color:var(--tone-sky)}
.pipeline .stage[data-go="drafts"] .stage-number {color:var(--tone-lilac)}
.pipeline .stage[data-go="deployment"] .stage-number {color:var(--tone-sage)}
.attention-panel {background:#27251f;border-color:#5f523f;border-left-color:var(--tone-amber)}
.attention-panel .overline,.attention-panel .attention-mark {color:var(--tone-amber)}
.attention-panel[data-tone="normal"] {background:#1b2924;border-color:#3e5c4e;border-left-color:var(--tone-sage)}
.attention-panel[data-tone="normal"] .overline,.attention-panel[data-tone="normal"] .attention-mark {color:var(--tone-sage)}
.verification-strip {background:#17212e;border-color:#3d4d60}
.verification-strip[data-state="warning"] {background:#28251f;border-color:#66543e}
.verification-strip[data-state="warning"] #verification-status,.warning-text,.impact-warning {color:var(--tone-amber)}
.verification-strip[data-state="error"] {background:#2b2027;border-color:#73505a}
.verification-strip[data-state="error"] #verification-status,.read-error {color:var(--tone-rose)}
.mini-badge.good,.pill.good {background:#20332a;border-color:#476a58;color:var(--tone-sage)}
.mini-badge.warn,.pill.warn {background:#30291f;border-color:#715d42;color:var(--tone-amber)}
.mini-badge.bad,.pill.bad {background:#34242c;border-color:#79525e;color:var(--tone-rose)}
.observatory {--obs-cyan:var(--tone-sky);--obs-violet:var(--tone-lilac);background:#141b27;border-color:#3b475b}
.obs-heading .overline,.obs-resource-heading .overline {color:var(--tone-sage)}
.obs-heading p,.obs-resource-heading p,.obs-time small,.obs-footer {color:var(--tone-muted)}
.obs-live {background:#1c2925;border-color:#456253;color:var(--tone-sage)}
.obs-live[data-state="fetching"] {background:#1d2b38;border-color:#4c6275;color:var(--tone-sky)}
.obs-live[data-state="error"] {background:#2b2027;border-color:#73505a;color:var(--tone-rose)}
.obs-live[data-state="offline"] {background:#28251f;border-color:#66543e;color:var(--tone-amber)}
.obs-live[data-state="paused"],.obs-live[data-state="hidden"],.obs-live[data-state="locked"] {background:#212834;border-color:#495564;color:var(--tone-muted)}
.obs-alert {background:#1b2633;border-left-color:var(--tone-sky);color:#c3d1df}
.obs-alert[data-state="warning"] {background:#28251f;border-left-color:var(--tone-amber);color:#e3cba5}
.obs-kpis>div {--metric-accent:var(--tone-sky);padding:14px 16px;background:#1a2533;border:1px solid #354353;border-radius:10px;box-shadow:inset 0 2px 0 var(--metric-accent)}
.obs-kpis>div:last-child {border:1px solid #354353}
.obs-kpis>div:has(:where(#obs-tcp)),.obs-kpis>div:has(:where(#obs-cpu)) {--metric-accent:var(--tone-lilac);background:#21202c}
.obs-kpis>div:has(:where(#obs-hit)) {--metric-accent:var(--tone-sage);background:#172822}
.obs-resource-kpis>div:has(:where(#obs-quality-fail)),.obs-resource-kpis>div:has(:where(#obs-link-errors)) {--metric-accent:var(--tone-muted);background:#1b2431}
.obs-kpis strong,#obs-hit {color:var(--metric-accent)}
.obs-kpis span {color:#c0cbd9}
.obs-kpis small {color:var(--tone-muted)}
.obs-chart-card {--chart-accent:var(--tone-sky);background:#111925;border-color:#354353}
.obs-chart-card h3 {color:#edf1f6}
.obs-chart-card h3::before {content:'';display:inline-block;width:6px;height:6px;margin-right:8px;border-radius:2px;background:var(--chart-accent);vertical-align:middle}
.obs-chart-card figcaption span,.obs-empty,.obs-table-wrap,.obs-details span {color:var(--tone-muted)}
.obs-chart-card:has(#obs-cpu-chart) {--chart-accent:var(--tone-lilac);--obs-cyan:var(--tone-lilac)}
.obs-chart-card:has(#obs-host-chart) {--chart-accent:var(--tone-sage);--obs-cyan:var(--tone-sage);--obs-violet:var(--tone-sky)}
.obs-chart-card:has(#obs-traffic-chart) {--obs-cyan:var(--tone-sky);--obs-violet:var(--tone-sage)}
.obs-chart-card:has(#obs-quality-chart) {--obs-cyan:var(--tone-sky);--obs-violet:var(--tone-lilac)}
.obs-chart-card:has(#obs-metric option[value="cache_hit_pct"]:checked),.obs-chart-card:has(#obs-metric option[value="memory_used_pct"]:checked) {--chart-accent:var(--tone-sage);--obs-cyan:var(--tone-sage)}
.obs-chart-card:has(#obs-metric option[value="cpu_used_pct"]:checked),.obs-chart-card:has(#obs-metric option[value="load_1m"]:checked) {--chart-accent:var(--tone-lilac);--obs-cyan:var(--tone-lilac)}
.obs-chart-card:has(#obs-metric option[value="dns_failure_pct"]:checked),.obs-chart-card:has(#obs-metric option[value="nic_drops_per_s"]:checked) {--chart-accent:var(--tone-amber);--obs-cyan:var(--tone-amber)}
.obs-line.udp {stroke:var(--obs-cyan)}
.obs-line.tcp {stroke:var(--obs-violet);stroke-dasharray: 5 3}
.obs-point.udp {fill:var(--obs-cyan)}
.obs-point.tcp {fill:var(--obs-violet)}
.obs-chart-card .obs-key.udp {color:var(--obs-cyan)}
.obs-chart-card .obs-key.tcp {color:var(--obs-violet)}
.obs-key.udp::before {background:var(--obs-cyan)}
.obs-key.tcp::before {background:var(--obs-violet)}
.obs-svg-text {fill:#a6b5c7}
.obs-gridline {stroke:#2b3545}
.obs-details #obs-memory {color:var(--tone-sage)}
.obs-details #obs-disk {color:var(--tone-sky)}
.obs-details meter {accent-color:var(--tone-sage)}
.obs-details #obs-disk-meter {accent-color:var(--tone-sky)}
.obs-table-wrap summary {color:var(--tone-sky)}
.obs-table-wrap th {color:#d1dbe6}
.obs-table-wrap tbody tr:hover {background:rgba(155,191,216,.05)}
.observatory[data-status="stale"] .obs-kpis>div {--metric-accent:var(--tone-muted);background:#1b2431;box-shadow:inset 0 2px 0 #627083}
.observatory[data-status="stale"] .obs-kpis strong {color:var(--tone-muted)}
/* Preserve the existing recency animation without flashing an unrelated cyan. */
@keyframes obs-change {
  0% {text-shadow:0 0 10px currentColor;transform:translateY(2px)}
  100% {text-shadow:none;transform:none}
}
@media (max-width:700px) {
  .obs-kpis>div {padding:12px 13px}
  .obs-kpis>div:nth-child(2) {border:1px solid #354353}
}
@media (prefers-contrast:more) {
  .surface,.stat-card,.obs-chart-card,.obs-kpis>div {border-color:#9caec1}
}
@media (forced-colors: active) {
  .sidebar,.topbar,.hero,.surface,.stat-card,.runtime-context,.obs-chart-card,
  .obs-kpis>div,.observatory[data-status="stale"] .obs-kpis>div,.fleet-metrics>div,
  .attention-panel,.attention-panel[data-tone="normal"],.verification-strip,
  .obs-alert,.obs-live,.mini-badge,.pill {background:Canvas!important;border-color:CanvasText!important;color:CanvasText!important;box-shadow:none!important}
  .stat-card .stat-value,.stat-card .stat-symbol,.fleet-metrics>div strong,
  .obs-kpis strong,.obs-chart-card .obs-key,.obs-details strong,
  .obs-table-wrap summary {color:CanvasText!important}
  .obs-line.udp,.obs-line.tcp {stroke:CanvasText!important}
  .obs-point,.obs-svg-text {fill:CanvasText!important}
  .button.primary,.nav-item.active {background:Highlight!important;border-color:Highlight!important;color:HighlightText!important}
}
'''
