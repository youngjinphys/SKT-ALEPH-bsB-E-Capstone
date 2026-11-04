"""Read-only, no-external-assets visual theme for the DNS console."""
THEME = r"""/* ALEPH Operations. Derived from the visual conventions of
   SKT-ALEPH-PR-Page (dark cyan glass) and Claire (Observatory geometry).
   Decorative styling only: no synthetic telemetry, no privileged controls. */
:root {
  --base: #071522;
  --panel: #0a1f32;
  --surface: #0c263a;
  --line: rgba(147, 211, 235, .22);
  --muted: #a0bcca;
  --cyan: #67dbeb;
  --cyan-dark: #12384b;
  --green: #6bd9ba;
  --amber: #f1c486;
  --red: #ffa0ab;
  color: #edf8fc;
  font-family: Pretendard, "Apple SD Gothic Neo", "Noto Sans KR",
               "Malgun Gothic", system-ui, sans-serif;
}
body {
  background: #071522;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
.skip-link {
  position: fixed;
  top: -80px;
  left: 20px;
  z-index: 100;
  background: #e7fcff;
  color: #092334;
  padding: 12px 18px;
  border-radius: 8px;
  font-weight: 750;
  font-size: 13px;
}
.skip-link:focus { top: 16px; }
.shell { background: var(--base); }
.sidebar {
  background: linear-gradient(172deg, #0b2436, #081a2a 63%, #071625);
  border-right-color: rgba(167, 219, 239, .15);
}
.brand strong { letter-spacing: .10em; }
.brand-asterisk { color: var(--amber); }
.side-caption, .overline, .eyebrow { color: #91b7c8; }
.nav-item { color: #b0cbd7; }
.nav-item.active {
  background: linear-gradient(90deg, rgba(48, 126, 151, .25),
              rgba(25, 67, 89, .16));
  border-color: rgba(116, 214, 235, .25);
  color: #e8fdff;
}
.nav-item:hover { background: rgba(108, 199, 228, .09); }
.nav-item.active:before { background: var(--cyan); }
.nav-item.active .nav-icon, .nav-item:hover .nav-icon { color: var(--cyan); }
.security-card {
  background: rgba(19, 56, 77, .62);
  border-color: rgba(135, 205, 229, .20);
}
.security-card small { color: #a1bccb; }
.main-column {
  background: radial-gradient(ellipse at 70% -12%, rgba(31, 116, 150, .28),
              transparent 50%),
              linear-gradient(160deg, #071522, #0a1d2d 53%, #071522);
}
.topbar {
  height: 76px;
  border-bottom-color: rgba(141, 209, 237, .16);
  background: rgba(8, 23, 39, .78);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.crumb { color: #bed6e2; }
.crumb span:first-child { color: var(--cyan); }
.content { padding-top: 35px; }
.hero {
  min-height: 254px;
  position: relative;
  isolation: isolate;
  overflow: hidden;
  padding: 36px 38px;
  margin: 0 0 15px;
  align-items: flex-start;
  border: 1px solid rgba(152, 218, 243, .25);
  border-radius: 23px;
  background: radial-gradient(ellipse at 88% 28%, rgba(64, 150, 194, .20),
              transparent 44%),
              linear-gradient(120deg, rgba(16, 48, 71, .96),
              rgba(7, 27, 46, .96) 64%, rgba(9, 36, 59, .95));
  box-shadow: 0 26px 70px rgba(1, 9, 22, .20),
              inset 0 1px 0 rgba(225, 250, 255, .07);
}
.hero > :not(.hero-art) { position: relative; z-index: 2; }
.hero-copy { max-width: 620px; }
.hero h1 {
  font-size: clamp(31px, 3.4vw, 51px);
  font-weight: 760;
  line-height: 1.13;
  color: #f3fcff;
  text-shadow: 0 7px 26px rgba(0, 10, 30, .22);
  letter-spacing: -.058em;
  margin-bottom: 14px;
}
.hero .eyebrow { color: #77e2e6; }
.hero .lead {
  color: #b1cbd7;
  font-size: clamp(12px, .95vw, 15px);
  max-width: 540px;
}
.hero-trust {
  margin-top: 27px;
  display: flex;
  flex-wrap: wrap;
  gap: 9px 23px;
  color: #9ac4d1;
  font-size: 11px;
}
.signal-mini {
  width: 6px; height: 6px; display: inline-block;
  border-radius: 50%; margin-right: 7px;
  vertical-align: 1px;
  background: #6be1bf;
  box-shadow: 0 0 10px rgba(107, 225, 191, .55);
}
.hero-tools {
  position: absolute !important;
  right: 29px;
  top: 22px;
  z-index: 4 !important;
  padding: 0;
}
.environment-label {
  background: rgba(15, 56, 76, .85);
  border-color: rgba(117, 227, 230, .35);
  color: #a8e5e5;
}
.hero-art {
  position: absolute;
  z-index: 1;
  width: min(33vw, 358px);
  height: min(33vw, 358px);
  right: 4%;
  top: 50%;
  transform: translateY(-47%);
  pointer-events: none;
}
.orbit {
  position: absolute;
  left: 50%;
  top: 50%;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}
.orbit-outer {
  width: 91%;
  height: 91%;
  border: 1px solid rgba(137, 226, 239, .30);
  box-shadow: 0 0 70px rgba(61, 171, 213, .08);
}
.orbit-outer::before, .orbit-outer::after {
  content: "";
  position: absolute;
  inset: 11% 32%;
  border: 1px solid rgba(138, 213, 239, .28);
  border-radius: 50%;
  transform: rotate(40deg);
}
.orbit-outer::after {
  inset: 32% 11%;
  transform: rotate(-30deg);
  border-style: dashed;
}
.orbit-inner {
  width: 65%;
  height: 65%;
  border: 1px solid rgba(133, 226, 242, .38);
  transform: translate(-50%, -50%) rotate(-28deg) scaleY(.77);
  box-shadow: 0 0 45px rgba(67, 184, 222, .10);
}
.orbital-core {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 36%;
  height: 36%;
  border: 1px solid rgba(178, 233, 255, .54);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: radial-gradient(circle at 27% 24%, rgba(164, 235, 255, .44),
              rgba(45, 127, 181, .25) 38%, rgba(4, 31, 64, .78) 80%);
  box-shadow: inset -15px -15px 40px rgba(0, 16, 42, .72),
              0 0 68px rgba(74, 184, 225, .17);
}
.orbit-north, .orbit-east, .orbit-west {
  position: absolute;
  font: 10px/1.2 ui-monospace, Consolas, monospace;
  letter-spacing: .15em;
  color: #94c9dc;
  white-space: nowrap;
}
.orbit-north { top: 47%; left: 45%; color: #e8fbff; font-size: 11px; }
.orbit-east { right: -3%; top: 29%; }
.orbit-west { left: -5%; bottom: 30%; }
.hero-art::after {
  content: "";
  position: absolute;
  top: 15%;
  left: 42%;
  width: 8px;
  height: 8px;
  background: #a9f6f1;
  border-radius: 50%;
  box-shadow: 0 0 13px 5px rgba(98, 216, 239, .28);
  animation: orbit-pulse 4s ease-in-out infinite;
}
@keyframes orbit-pulse {
  0%, 100% { opacity: .6; transform: scale(.9); }
  50% { opacity: 1; transform: scale(1.3); }
}
.verification-strip {
  min-height: 46px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 11px 16px;
  margin: 0 0 27px;
  padding: 10px 16px;
  border: 1px solid rgba(124, 201, 226, .19);
  border-radius: 10px;
  background: rgba(8, 31, 49, .80);
  color: #9dbac9;
  font-size: 11px;
}
.verification-strip strong { color: #e4f5fa; font-weight: 750; }
.verification-strip .strip-prefix {
  color: #80dfeb;
  letter-spacing: .08em;
  font-size: 10px;
  font-weight: 800;
}
.strip-break { width: 1px; height: 17px; background: #385970; }
.strip-tail { margin-left: auto; color: #88aab9; }
.verification-strip[data-state="warning"] {
  border-color: rgba(245, 190, 121, .35);
}
.verification-strip[data-state="warning"] #verification-status { color: #f8d6a5; }
.verification-strip[data-state="error"] #verification-status { color: #ffb0b9; }
.stat-card, .surface {
  background: linear-gradient(155deg, rgba(18, 51, 75, .92),
              rgba(9, 31, 51, .96));
  border-color: rgba(152, 213, 237, .22);
  border-radius: 18px;
  box-shadow: 0 17px 44px rgba(2, 13, 29, .16),
              inset 0 1px 0 rgba(239, 252, 255, .04);
}
.stat-card {
  position: relative;
  overflow: hidden;
  min-height: 166px;
  transition: border-color .18s ease, transform .18s ease;
}
.stat-card::before {
  content:"";
  position:absolute; inset:0 0 auto; height:2px;
  background: linear-gradient(90deg, transparent, rgba(131, 221, 239, .43), transparent);
}
.stat-card:hover {
  border-color: rgba(153, 225, 244, .45);
  transform: translateY(-2px);
}
.stat-caption { color: #b9d4df; }
.stat-value { color: #f1fbff; font-variant-numeric: tabular-nums; }
.stat-card p { color: #9db6c4; }
.surface .section-top h2 { color: #eef9fc; }
.overline { font-size: 10px; letter-spacing: .16em; color: #72dce5; }
.pill.muted { background: rgba(42, 90, 112, .25); border-color: rgba(114, 186, 217, .20); color: #b8d8e6; }
.pill.warning { background: rgba(86, 62, 35, .32); color: #f1c58c; }
.pipeline { gap: 11px; margin-bottom: 27px; }
.stage-number {
  border-radius: 12px;
  background: rgba(29, 89, 110, .39);
  border-color: rgba(114, 213, 234, .28);
}
.stage strong { color: #d8eff6; }
.stage small { color: #9ab5c2; }
.stage-arrow { color: #70acc0; }
.panel-footer { border-top-color: rgba(150, 210, 233, .19); }
.panel-footer span, .panel-footer strong { line-height: 1.6; }
.pipeline-bottom {
  border-top: 1px solid rgba(133, 197, 222, .12);
  margin-top: 19px;
  display: grid;
  grid-template-columns: 1fr 1.6fr;
  gap: 12px;
  padding-top: 17px;
}
.pipeline-bottom small { color: #86abbe; display: block; margin-bottom: 5px; }
.pipeline-bottom strong { font-size: 12px; color: #d8f4f7; }
.deployment-status-icon, .deployment-big-icon {
  background: rgba(28, 83, 109, .36);
  border-color: rgba(111, 205, 232, .30);
}
.deployment-summary p { color: #a4bdca; }
.info-banner {
  background: rgba(14, 42, 60, .65);
  border-color: rgba(129, 201, 232, .23);
  border-radius: 13px;
}
.info-banner p { color: #a9bfcd; }
.evidence-health {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 13px;
  padding: 16px 20px;
  margin-bottom: 18px;
  border: 1px solid rgba(240, 184, 116, .42);
  border-left: 3px solid #efbc77;
  background: rgba(67, 47, 34, .50);
  border-radius: 12px;
}
.evidence-health .health-mark {
  display: grid;
  place-items: center;
  flex: 0 0 29px;
  width: 29px; height: 29px; border-radius: 50%;
  border: 1px solid #eebf84;
  color: #f4cc97;
  font-weight: 800;
}
.evidence-health > div { flex: 1; }
.evidence-health strong { font-size: 12px; color: #ffe2b6; }
.evidence-health p { font-size: 11px; color: #d4bca8; margin: 4px 0 0; }
.evidence-health .text-button { color: #ffdfad; }
.review-eligibility {
  padding: 11px 13px;
  font-size: 11px;
  line-height: 1.6;
  background: rgba(21, 66, 76, .40);
  border: 1px solid rgba(112, 215, 223, .23);
  border-radius: 9px;
  color: #bde9e7;
}
.review-eligibility[data-state="warning"] {
  background: rgba(91, 58, 36, .43);
  border-color: rgba(245, 191, 115, .40);
  color: #f4d1a0;
}
.review-eligibility[data-state="error"] {
  background: rgba(95, 41, 51, .36);
  border-color: rgba(250, 146, 151, .34);
  color: #fbbabf;
}
.review-item.selected { background: rgba(39, 103, 128, .27); }
.review-item:hover { background: rgba(57, 120, 147, .20); }
.review-item:focus-visible { outline-offset: -3px; }
.button.primary {
  background: linear-gradient(140deg, #a2edf4, #6fdae9);
  border-color: #a8f0f5;
  color: #082537;
}
.button.primary:hover:not(:disabled) { background: #c6f7fa; }
.button.outline { background: rgba(18, 56, 75, .52); }
.button.outline:hover { background: rgba(26, 91, 115, .60); }
input:not([type="checkbox"]), select, textarea {
  border-color: rgba(150, 215, 236, .31);
  background: rgba(6, 24, 41, .89);
  color: #effbff;
}
input:disabled, textarea:disabled { opacity: .55; }
.check-row input { accent-color: var(--cyan); }
.login-card {
  background: linear-gradient(145deg, rgba(20, 59, 84, .94), rgba(8, 28, 47, .97));
  border-color: rgba(133, 214, 241, .30);
  box-shadow: 0 30px 100px rgba(1, 11, 27, .36);
}
.login-symbol { background: rgba(48, 125, 155, .35); color: #87f1ec; }
.result-card, .subtle-note { background: rgba(7, 28, 47, .68); }
.published-row { border-bottom-color: rgba(125, 192, 218, .17); }
.draft-item { background: rgba(8, 30, 49, .77); border-color: rgba(117, 192, 222, .24); }
.status-dot.verified { background: var(--green); box-shadow: 0 0 12px rgba(95, 223, 183, .5); }
.status-dot.error { background: var(--red); box-shadow: 0 0 12px rgba(255, 134, 156, .4); }
@supports ((backdrop-filter: blur(7px)) or (-webkit-backdrop-filter: blur(7px))) {
  .surface, .stat-card {
    backdrop-filter: blur(7px);
    -webkit-backdrop-filter: blur(7px);
  }
}
@media (max-width: 1300px) {
  .hero-art { opacity: .58; right: -1%; }
  .hero-copy { max-width: 530px; }
}
@media (max-width: 900px) {
  .hero-art { opacity: .30; right: -7%; }
  .hero-copy { max-width: 72%; }
  .hero { min-height: 215px; padding: 31px 28px; }
}
@media (max-width: 700px) {
  .sidebar { background: #0a2133; }
  .topbar { height: 57px; }
  .hero { padding: 28px 22px; min-height: 226px; border-radius: 19px; }
  .hero-copy { max-width: 100%; }
  .hero-art { opacity: .16; right: -34%; width: 300px; height: 300px; }
  .hero-tools { position: relative !important; top: auto; right: auto; margin-top: 17px; }
  .hero-trust { font-size: 10px; margin-top: 19px; }
  .environment-label { font-size: 9px; }
  .verification-strip { gap: 7px 12px; font-size: 10px; }
  .strip-tail { margin-left: 0; flex-basis: 100%; }
  .pipeline-bottom { grid-template-columns: 1fr; }
  .stat-card { min-height: 133px; }
}
@media (prefers-reduced-motion: reduce) {
  .hero-art::after { animation: none; }
  .stat-card, .stat-card:hover { transition: none; transform: none; }
}
@media (prefers-reduced-transparency: reduce) {
  .topbar, .surface, .stat-card { backdrop-filter: none; -webkit-backdrop-filter: none; }
  .surface, .stat-card { background: #102b3f; }
}
@media (forced-colors: active) {
  .hero, .surface, .stat-card, .evidence-health, .verification-strip, .info-banner {
    background: Canvas;
    color: CanvasText;
    border-color: CanvasText;
    box-shadow: none;
    backdrop-filter: none;
  }
  .hero-art { display: none; }
  .button.primary, .nav-item.active { background: Highlight; color: HighlightText; }
}
/* The proposed replacement is deliberately inspected before independent signing.
   These metrics compare verified files, not live resolver state. */
.draft-impact-panel {
  margin-top: 16px;
  border-color: rgba(122, 212, 235, .35);
  background: linear-gradient(125deg, rgba(20, 58, 81, .89), rgba(9, 31, 51, .97));
}
.draft-impact-panel h3 { font-size: 16px; overflow-wrap: anywhere; margin-bottom: 12px; }
.impact-metrics { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; margin: 20px 0 6px; }
.impact-metric { border: 1px solid rgba(136,210,229,.23); border-radius: 11px; padding: 16px; background: rgba(4,25,43,.44); }
.impact-metric span { display: block; color: #adc8d6; font-size: 11px; }
.impact-metric strong { display: block; font-size: 30px; color: #e9fbff; margin-top: 8px; font-variant-numeric: tabular-nums; }
.impact-metric[data-state="warning"] { border-color: rgba(244,190,120,.48); background: rgba(83,56,32,.27); }
.impact-metric[data-state="warning"] strong { color: #f9d49f; }
.impact-warning { border-left: 3px solid #e7b46b; padding: 14px 17px; margin: 17px 0; background: rgba(92,61,33,.26); color: #ffe1ad; font-size: 12px; line-height: 1.7; }
.impact-sample { font-size: 11px; line-height: 1.7; color: #a9c9d5; overflow-wrap: anywhere; margin: 13px 0; }
.draft-actions { flex-wrap: wrap; }
@media (max-width:700px) { .impact-metrics { grid-template-columns: 1fr; } }
@media (forced-colors: active) {
  .draft-impact-panel,.impact-metric,.impact-warning { background: Canvas; color: CanvasText; border-color: CanvasText; }
  .impact-metric strong,.impact-metric[data-state="warning"] strong { color: CanvasText; }
}
/* Aggregate node status retains the difference between local apply and
   independent DNS answer corroboration; never imply fleet-wide LAN coverage. */
.fleet-summary{margin:0 0 20px;padding:22px 27px}
.fleet-title{align-items:center}
.fleet-title p{margin:8px 0 0}
.fleet-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-top:22px}
.fleet-metrics>div{background:rgba(7,31,50,.55);border:1px solid rgba(131,214,232,.2);border-radius:11px;padding:16px 17px}
.fleet-metrics small{font-size:10px;color:#9ebecb;display:block;line-height:1.5}
.fleet-metrics strong{font-size:27px;color:#effbff;display:block;margin-top:8px;font-variant-numeric:tabular-nums}
.fleet-metrics [data-state="warning"] strong{color:#f5ce93}
@media(max-width:700px){.fleet-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.fleet-title{align-items:flex-start;flex-wrap:wrap}.fleet-metrics>div{padding:13px}.fleet-summary{padding:18px}}
@media(forced-colors:active){.fleet-metrics>div{background:Canvas;color:CanvasText;border-color:CanvasText}.fleet-metrics strong,.fleet-metrics [data-state="warning"] strong{color:CanvasText}}
/* DNS-node identities and independently signed status receipts.
   Derived from the established PR-Page / Claire design tokens. */
.nodes-panel { margin-top: 20px; }
.nodes-layout { display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.9fr);gap:20px;align-items:start; }
.node-list { display:grid;gap:12px;max-height:680px;overflow-y:auto; }
.node-card { padding:20px;background:rgba(7,28,48,.68);border:1px solid rgba(138,206,234,.23);border-radius:13px; }
.node-head { display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;align-items:start; }
.node-head strong { display:block;font-size:14px;color:#ebfaff; }
.node-head small { display:block;margin-top:8px;color:#91afc4; }
.node-facts { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding-top:18px;margin-top:16px;border-top:1px solid rgba(136,204,224,.17); }
.node-facts div { display:flex;flex-direction:column;gap:5px; }
.node-facts span { color:#849eaf;font-size:10px; }
.node-facts strong { font-size:11px;color:#d8edf3;overflow-wrap:anywhere; }
.node-hash { color:#8eb7c8;font-size:10px;margin-top:17px;overflow-wrap:anywhere; }
.node-footer { display:flex;justify-content:space-between;gap:12px;align-items:center;border-top:1px solid rgba(126,204,225,.15);padding-top:12px;margin-top:18px; }
.node-footer span { font-size:10px;color:#f0c383; }
.node-form { border:1px solid rgba(129,194,215,.29);border-radius:12px;padding:20px;background:rgba(8,35,57,.62); }
.node-form h3 { margin:11px 0; }
.node-form .button { margin-top:22px; }
.node-boundary-note { margin-top:20px; }
@media(max-width:1050px){.nodes-layout{grid-template-columns:1fr}}
@media(max-width:700px){.node-facts{grid-template-columns:1fr 1fr}.node-head{align-items:flex-start}}
@media(forced-colors:active){.node-card,.node-form{background:Canvas;color:CanvasText;border-color:CanvasText}}

/* Provenance preview and deliberate import; never imply auto-enforcement. */
.intel-refresh-panel{margin:0 0 20px;padding:22px 26px;border-color:rgba(121,207,228,.29)}
.intel-refresh-panel h3{font-size:19px;margin:7px 0 8px}
.intel-refresh-panel .section-top{align-items:flex-start}
.intel-refresh-panel .muted-copy{max-width:860px;font-size:12px;line-height:1.7}
.intel-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;margin:20px 0 14px}
.intel-summary>div{background:rgba(6,29,47,.58);border:1px solid rgba(132,198,217,.24);border-radius:10px;padding:14px}
.intel-summary small{display:block;font-size:10px;color:#9ebccb;line-height:1.6}
.intel-summary strong{display:block;margin-top:7px;font-size:13px;color:#eefbff;overflow-wrap:anywhere}
.intel-refresh-form{padding:14px 0 0;border-top:1px solid rgba(138,202,225,.22)}
.intel-refresh-form .check-row{font-size:12px;margin-bottom:10px}
.intel-refresh-form .action-row{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 12px}
.intel-refresh-form .button{min-height:41px}
.intel-refresh-form button:disabled{opacity:.52;cursor:not-allowed}
#intel-note{min-height:24px}
@media(max-width:900px){.intel-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.intel-refresh-panel{padding:17px}.intel-refresh-panel .section-top{display:block}.intel-refresh-form .action-row .button{width:100%}}
@media(forced-colors:active){.intel-refresh-panel,.intel-summary>div{background:Canvas;color:CanvasText;border-color:CanvasText}}

/* --------------------------------------------------------------------------
   Operations visual system v2 — observability-first hierarchy and interactions
   The colors communicate evidence boundaries, never simulated live telemetry.
   -------------------------------------------------------------------------- */
:root {
  --ops-text: #f0f8fc;
  --ops-text-secondary: #b9d0dc;
  --ops-text-tertiary: #94b0c2;
  --ops-border: rgba(150, 206, 225, .24);
  --ops-radius: 18px;
  --ops-shadow: 0 18px 55px rgba(0, 10, 25, .24);
  --ops-focus: #a1f0f2;
}
html { scroll-behavior: smooth; }
body { color: var(--ops-text); }
body::selection { background: rgba(98, 218, 229, .35); color: #f6ffff; }
button, input, select, textarea { -webkit-tap-highlight-color: transparent; }
button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
a:focus-visible {
  outline: 3px solid var(--ops-focus);
  outline-offset: 3px;
}
button:disabled { cursor: not-allowed; }
button:disabled, .button:disabled { opacity: .48; box-shadow: none; }
button:focus-visible { position: relative; z-index: 2; }
input:not([type="checkbox"]), select, textarea {
  border-radius: 10px;
  min-height: 43px;
  transition: border-color .18s ease, box-shadow .18s ease, background .18s ease;
}
input:not([type="checkbox"]):focus, select:focus, textarea:focus {
  border-color: rgba(117, 228, 237, .83);
  box-shadow: 0 0 0 3px rgba(94, 211, 231, .14);
  background: rgba(5, 29, 46, .96);
}
input::placeholder, textarea::placeholder { color: #91abb9; }
textarea { line-height: 1.65; resize: vertical; }
.check-row { color: #d3e6ec; line-height: 1.6; }
.check-row input { width: 16px; height: 16px; flex: 0 0 16px; margin-top: 3px; }
.fine-print, .muted-copy { color: #a9c1ce; }
.fine-print { font-size: 11px; line-height: 1.75; }
.shell { background: #07131f; }
.sidebar {
  z-index: 30;
  border-right: 1px solid rgba(125, 188, 210, .16);
  background: linear-gradient(174deg, #0a2535 0%, #071b2a 57%, #061521 100%);
  box-shadow: 9px 0 30px rgba(0, 11, 25, .12);
  overflow-y: auto;
  scrollbar-width: thin;
}
.sidebar::before {
  content: "";
  pointer-events: none;
  position: absolute;
  inset: 0 0 auto 0;
  height: 210px;
  background: radial-gradient(ellipse at 25% 7%, rgba(87, 212, 231, .10), transparent 70%);
}
.brand { position: relative; margin-bottom: 52px; }
.brand strong { font-weight: 850; letter-spacing: .12em; }
.brand small { color: #9bb8c6; }
.side-caption { color: #8aabba; letter-spacing: .17em; }
.side-nav { position: relative; gap: 7px; }
.nav-item {
  position: relative;
  min-height: 48px;
  border-radius: 12px;
  padding: 12px 13px;
  transition: background .18s ease, border-color .18s ease, color .18s ease, transform .18s ease;
}
.nav-item.active {
  border-color: rgba(129, 229, 235, .31);
  background: linear-gradient(98deg, rgba(50, 131, 153, .31), rgba(16, 54, 76, .48));
  box-shadow: inset 0 1px 0 rgba(195, 249, 252, .06), 0 9px 22px rgba(0, 16, 30, .16);
}
.nav-item.active::before { height: 23px; width: 3px; border-radius: 9px; background: #a4f5f2; }
.nav-item:hover:not(.active) { transform: translateX(2px); border-color: rgba(135, 209, 228, .12); }
.nav-icon { color: #94b6c8; }
.nav-count {
  min-width: 22px;
  padding: 2px 5px;
  text-align: center;
  border-radius: 6px;
  color: #c9e6ef;
  background: rgba(122, 195, 221, .12);
}
.security-card { border-radius: 15px; padding: 16px; }
.security-card strong { font-size: 12px; color: #e4f3f7; }
.main-column {
  background:
    radial-gradient(ellipse 800px 380px at 83% -6%, rgba(23, 115, 144, .15), transparent 70%),
    radial-gradient(ellipse 600px 550px at 2% 50%, rgba(10, 76, 96, .08), transparent 75%),
    #071522;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  flex-shrink: 0;
  min-height: 79px;
  height: auto;
  padding-block: 12px;
  background: rgba(6, 21, 35, .91);
  border-bottom: 1px solid rgba(141, 205, 227, .18);
  box-shadow: 0 9px 30px rgba(0, 12, 26, .1);
}
.topbar-context { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.topbar .crumb { font-size: 12px; letter-spacing: .02em; }
.topbar-subtitle { font: 700 9px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: .16em; color: #80a9bb; }
.topbar-actions { display: flex; gap: 12px; }
.connection-dot { width: 8px; height: 8px; }
.connection { color: #b9d6e0; font-weight: 600; }
.icon-button {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  background: rgba(30, 67, 87, .65);
  border: 1px solid rgba(120, 202, 229, .26);
  color: #d3f5fb;
  border-radius: 11px;
  transition: transform .2s ease, background .2s ease;
}
.icon-button:hover { background: rgba(44, 106, 132, .65); transform: rotate(40deg); }
.quiet-button {
  min-height: 40px;
  border: 1px solid rgba(150, 202, 222, .22);
  border-radius: 10px;
  padding: 0 13px;
  color: #c6dce4;
}
.quiet-button:hover { background: rgba(70, 106, 126, .18); color: #f1fcff; }
.content { max-width: 1530px; padding-top: 29px; }
.hero {
  min-height: 252px;
  padding: clamp(26px, 3vw, 40px);
  margin-bottom: 14px;
  border-radius: 23px;
  border-color: rgba(145, 221, 236, .28);
  background:
    radial-gradient(circle at 80% 52%, rgba(59, 189, 209, .15), transparent 35%),
    radial-gradient(circle at 7% 2%, rgba(111, 200, 227, .10), transparent 42%),
    linear-gradient(120deg, rgba(16, 53, 76, .97) 0%, rgba(7, 31, 50, .98) 60%, rgba(7, 37, 57, .97));
  box-shadow: 0 26px 75px rgba(0, 11, 28, .24), inset 0 1px 0 rgba(220, 249, 255, .09);
}
.hero::before {
  content: "";
  position: absolute;
  pointer-events: none;
  inset: 0;
  background: linear-gradient(125deg, rgba(240, 255, 255, .045), transparent 38%);
  border-radius: inherit;
}
.hero-copy { max-width: 700px; }
.hero h1 { font-size: clamp(33px, 3.1vw, 49px); letter-spacing: -.055em; margin-bottom: 14px; }
.hero .lead { font-size: clamp(13px, 1vw, 15px); max-width: 585px; line-height: 1.7; color: #c5dfeb; }
.hero .eyebrow { color: #8beaf0; letter-spacing: .14em; }
.hero-actions { margin-top: 24px; display: flex; flex-wrap: wrap; gap: 10px; }
.hero-actions .button { min-height: 44px; padding: 10px 18px; font-size: 12px; gap: 17px; }
.hero-primary { box-shadow: 0 10px 27px rgba(66, 205, 229, .12); }
.hero-secondary { border-color: rgba(146, 210, 230, .3); }
.hero-trust { margin-top: 22px; color: #a5c9d6; gap: 8px 18px; }
.hero-trust span { line-height: 1.5; }
.hero-art { right: 3%; width: min(30vw, 324px); height: min(30vw, 324px); opacity: .78; }
.orbit-outer { border-color: rgba(131, 229, 233, .38); }
.orbital-core { box-shadow: inset -15px -15px 40px rgba(0, 16, 42, .62), 0 0 70px rgba(85, 223, 223, .16); }
.environment-label { font-size: 10px; letter-spacing: .09em; }
.verification-strip {
  position: relative;
  gap: 10px 14px;
  padding: 15px 18px;
  margin-bottom: 31px;
  min-height: 56px;
  border-radius: 13px;
  background: rgba(11, 35, 53, .92);
  border-color: rgba(125, 207, 226, .28);
}
.strip-indicator { width: 8px; height: 8px; flex-shrink: 0; border-radius: 50%; background: #75bad0; box-shadow: 0 0 13px rgba(78, 185, 207, .3); }
.verification-strip[data-state="normal"] .strip-indicator { background: #7bcbdc; box-shadow: 0 0 13px rgba(87, 181, 205, .26); }
.verification-strip[data-state="warning"] .strip-indicator { background: #f5c88f; box-shadow: 0 0 14px rgba(248, 187, 101, .30); }
.verification-strip[data-state="error"] .strip-indicator { background: #ff9cac; box-shadow: 0 0 14px rgba(255, 130, 153, .30); }
.verification-strip .strip-prefix { color: #9bd1dd; }
.verification-strip #verification-status { font-size: 12px; letter-spacing: -.01em; }
.strip-checked { font-size: 11px; color: #b9d2de; }
.strip-checked strong { font-variant-numeric: tabular-nums; }
.strip-tail { font-size: 11px; color: #a3c0ce; line-height: 1.4; }
.section-heading--metrics {
  display: flex;
  justify-content: space-between;
  align-items: end;
  flex-wrap: wrap;
  gap: 10px 20px;
  margin: 0 0 16px;
}
.section-heading--metrics h2 { margin: 7px 0 0; font-size: 20px; letter-spacing: -.035em; }
.section-heading--metrics p { margin: 0; color: #9ab8c7; font-size: 11px; }
.section-top.outside { margin-bottom: 24px; }
.section-top.outside h2 { font-size: clamp(21px, 2vw, 27px); letter-spacing: -.04em; margin-top: 8px; }
.section-top.outside p { margin: 8px 0 0; font-size: 12px; color: #a5c4d1; }
.stats-grid { gap: 14px; margin-bottom: 21px; }
.stat-card {
  min-height: 155px;
  padding: 23px;
  border-radius: var(--ops-radius);
  border-color: var(--ops-border);
  box-shadow: var(--ops-shadow), inset 0 1px 0 rgba(245, 255, 255, .05);
}
.stat-card::before { height: 2px; opacity: .68; }
.stat-card:nth-child(2)::before { background: linear-gradient(90deg,transparent,rgba(105,222,190,.68),transparent); }
.stat-card:nth-child(3)::before { background: linear-gradient(90deg,transparent,rgba(247,206,147,.6),transparent); }
.stat-card:nth-child(4)::before { background: linear-gradient(90deg,transparent,rgba(156,183,241,.6),transparent); }
.stat-card:hover { transform: translateY(-3px); box-shadow: 0 24px 48px rgba(0, 13, 29, .32); }
.stat-caption { font-size: 12px; font-weight: 750; color: #cae0e8; }
.stat-value { font-size: clamp(33px, 3vw, 42px); line-height: 1.14; margin: 18px 0 6px; font-weight: 820; }
.stat-card p { font-size: 11px; line-height: 1.5; color: #9bbbc8; margin-bottom: 0; }
.surface { border-radius: var(--ops-radius); border-color: var(--ops-border); box-shadow: var(--ops-shadow), inset 0 1px 0 rgba(246, 255, 255, .045); }
.surface .section-top h2 { font-size: 19px; letter-spacing: -.035em; }
.overline { color: #85deeb; font-weight: 790; letter-spacing: .14em; }
.dashboard-grid { gap: 19px; }
.pipeline { gap: 5px; margin: 27px 0 17px; align-items: stretch; }
.pipeline .stage {
  appearance: none;
  font: inherit;
  text-align: left;
  color: #e2f5fa;
  padding: 14px 11px 16px;
  min-width: 0;
  border: 1px solid rgba(137, 205, 226, .22);
  border-radius: 12px;
  background: rgba(13, 47, 68, .44);
  cursor: pointer;
  transition: background .18s ease, border-color .18s ease, transform .18s ease;
}
.pipeline .stage:hover { transform: translateY(-2px); background: rgba(24, 80, 104, .53); border-color: rgba(117, 220, 226, .48); }
.pipeline .stage:active { transform: translateY(0); }
.pipeline .stage .stage-number { margin-bottom: 13px; border-radius: 9px; width: 32px; height: 32px; color: #a6eff3; }
.pipeline .stage strong { font-size: 12px; line-height: 1.4; margin-bottom: 5px; }
.pipeline .stage small { font-size: 10px; line-height: 1.55; color: #a6c8d6; }
.pipeline .stage-final { background: rgba(13, 62, 75, .45); }
.pipeline .stage-arrow { align-self: center; margin: 0 1px; color: #8ebdcb; font-size: 16px; line-height: 1; }
.pipeline-bottom { margin-top: 25px; padding-top: 20px; }
.panel-footer { gap: 10px; flex-wrap: wrap; }
.fleet-summary { padding: 24px 26px; }
.fleet-title p { font-size: 12px; color: #b1c9d5; line-height: 1.6; max-width: 760px; }
.fleet-metrics { gap: 12px; margin-top: 22px; }
.fleet-metrics > div {
  position: relative;
  overflow: hidden;
  padding: 18px 18px 17px;
  background: rgba(7, 30, 47, .66);
  border-color: rgba(145, 201, 222, .23);
}
.fleet-metrics > div::before { content:""; position:absolute; left:0; top:14px; bottom:14px; width:3px; border-radius:0 3px 3px 0; background: rgba(113,201,219,.55); }
.fleet-metrics > div[data-metric="attested"]::before { background: rgba(88,206,179,.69); }
.fleet-metrics > div[data-metric="correlated"]::before { background: rgba(115,227,216,.82); }
.fleet-metrics > div[data-metric="pending"]::before { background: rgba(248,190,118,.75); }
.fleet-metrics small { font-size: 11px; color: #abc8d6; }
.fleet-metrics strong { font-size: 30px; }
.intel-refresh-panel { padding: 26px; border-radius: var(--ops-radius); }
.intel-refresh-panel .section-top h3 { font-size: 22px; letter-spacing: -.038em; }
.intel-activity-line { height: 3px; border-radius: 10px; overflow: hidden; background: rgba(102, 188, 205, .14); margin: 21px 0 -7px; }
.intel-activity-line::after { content: ""; display: block; height: 100%; width: 0; background: linear-gradient(90deg, transparent, #7ae1e8, transparent); }
.intel-refresh-panel[data-status="RUNNING"] .intel-activity-line::after { width: 45%; animation: intel-activity 1.8s ease-in-out infinite; }
@keyframes intel-activity { from { transform: translateX(-110%); } to { transform: translateX(340%); } }
.intel-summary { margin: 22px 0 17px; }
.intel-summary > div { border-color: rgba(150, 204, 225, .22); padding: 16px; }
.intel-summary strong { font-size: 14px; }
#intel-state { color: #d3e9f3; }
.intel-refresh-panel[data-status="RUNNING"] #intel-state { color: #a1e7f4; }
.intel-refresh-panel[data-status="SUCCESS"] #intel-state { color: #a7efd7; }
.intel-refresh-panel[data-status="ERROR"] #intel-state,
.intel-refresh-panel[data-status="UNAVAILABLE"] #intel-state,
.intel-refresh-panel[data-status="INTERRUPTED"] #intel-state { color: #ffc2cb; }
.intel-refresh-panel .fine-print { padding-top: 12px; border-top: 1px solid rgba(133, 196, 219, .16); }
.intel-refresh-form { border-top-color: rgba(126, 199, 224, .25); }
.intel-refresh-form .check-row { margin: 13px 0; }
.intel-refresh-form .action-row { margin-top: 20px; }
.intel-refresh-form .button { min-height: 44px; }
.review-list-panel { border-color: rgba(143, 204, 222, .24); }
.review-item { transition: background .16s ease, border-color .16s ease; padding: 19px 20px; }
.review-item.selected { background: rgba(35, 103, 129, .32); box-shadow: inset 3px 0 0 #83e0ea; }
.review-item:hover { background: rgba(48, 117, 145, .21); }
.review-item strong { overflow-wrap: anywhere; font-size: 12px; }
.review-editor { top: 100px; }
.review-editor h2, #review-domain { overflow-wrap: anywhere; }
.review-eligibility { font-size: 12px; }
.list-toolbar { gap: 12px; }
.list-toolbar input { min-width: 0; }
.node-card { border-radius: 14px; transition: border-color .16s ease, background .16s ease; }
.node-card[data-tone="good"] { border-color: rgba(117, 222, 180, .32); }
.node-card[data-tone="bad"] { border-color: rgba(255, 145, 157, .38); }
.node-card[data-tone="warn"] { border-color: rgba(243, 191, 120, .34); }
.node-card .node-head small { font-variant-numeric: tabular-nums; }
.node-card .node-facts strong { font-size: 12px; line-height: 1.55; }
.node-form { border-radius: 14px; }
.draft-item { border-radius: 12px; transition: background .18s ease; }
.draft-item:hover { background: rgba(19, 60, 83, .68); }
.draft-actions { gap: 8px 13px; }
.published-row { padding-block: 14px; }
.toast { border: 1px solid rgba(125, 205, 229, .35); box-shadow: 0 24px 60px rgba(0, 12, 29, .46); }
.login-card { width: min(100%, 470px); padding: clamp(27px, 4vw, 47px); }
.login-card h1 { line-height: 1.25; }
.login-wrap { min-height: min(72vh, 720px); }
@media (max-width: 1250px) {
  .hero-art { right: -1%; opacity: .58; }
  .hero-copy { max-width: 575px; }
  .stat-card { padding: 19px; }
}
@media (max-width: 1000px) {
  .hero-copy { max-width: 100%; }
  .hero-art { opacity: .25; }
  .dashboard-grid { gap: 15px; }
  .review-editor { position: static; }
  .pipeline .stage { padding: 14px 13px; }
}
@media (max-width: 700px) {
  .sidebar {
    position: sticky;
    top: 0;
    z-index: 35;
    width: 100%;
    height: auto;
    min-height: 0;
    padding: 12px 13px 9px;
    overflow: visible;
    box-shadow: 0 10px 25px rgba(0, 9, 20, .35);
    backdrop-filter: blur(15px);
    -webkit-backdrop-filter: blur(15px);
  }
  .sidebar::before { height: 85px; }
  .brand { margin: 0 0 11px; padding: 0 2px; }
  .brand strong { font-size: 17px; }
  .brand small { font-size: 8px; }
  .side-nav { gap: 7px; overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; padding: 0 0 5px; scroll-snap-type: x proximity; }
  .nav-item { min-height: 40px; padding: 9px 12px; flex: 0 0 auto; white-space: nowrap; scroll-snap-align: start; font-size: 12px; }
  .nav-item:hover { transform: none; }
  .nav-count { display: none; }
  .topbar { position: relative; z-index: 10; min-height: 57px; padding: 8px 17px; }
  .topbar-subtitle { display: none; }
  .topbar-actions { gap: 9px; }
  .icon-button { width: 38px; height: 38px; }
  .quiet-button { min-height: 36px; }
  .content { padding: 21px 15px 46px; }
  .hero { padding: 26px 22px; border-radius: 18px; min-height: 260px; }
  .hero h1 { font-size: clamp(30px, 9vw, 37px); }
  .hero .lead { font-size: 13px; }
  .hero .eyebrow { font-size: 9px; line-height: 1.5; }
  .hero-actions { margin-top: 21px; }
  .hero-actions .button { min-height: 43px; font-size: 11px; }
  .hero-art { opacity: .15; right: -35%; width: 280px; height: 280px; }
  .hero-trust { margin-top: 20px; font-size: 10px; }
  .verification-strip { padding: 13px 14px; gap: 9px 11px; margin-bottom: 26px; }
  .strip-tail { flex-basis: 100%; margin-left: 19px; }
  .section-heading--metrics { align-items: start; }
  .section-heading--metrics h2 { font-size: 19px; }
  .section-heading--metrics p { font-size: 11px; }
  .stats-grid { gap: 10px; }
  .stat-card { min-height: 139px; padding: 17px 15px; border-radius: 14px; }
  .stat-caption { font-size: 11px; gap: 8px; }
  .stat-value { font-size: 33px; margin: 12px 0 7px; }
  .stat-symbol { font-size: 16px; }
  .stat-card p { font-size: 10px; }
  .surface { border-radius: 15px; }
  .pipeline { gap: 9px; }
  .pipeline .stage { flex: 1 1 calc(50% - 9px); min-width: 0; }
  .pipeline .stage strong { font-size: 12px; }
  .pipeline .stage small { font-size: 11px; }
  .pipeline .stage-arrow { display: none; }
  .fleet-summary { padding: 19px; }
  .fleet-metrics { gap: 9px; }
  .fleet-metrics > div { padding: 14px; }
  .fleet-metrics strong { font-size: 26px; }
  .fleet-metrics small { font-size: 10px; }
  .intel-refresh-panel { padding: 20px; }
  .intel-summary { gap: 9px; }
  .intel-summary > div { padding: 13px; }
  .intel-summary strong { font-size: 12px; }
  .node-card { padding: 17px; }
  .node-facts { gap: 12px; }
  .node-facts strong { font-size: 11px; }
  .review-item { padding: 16px; }
  .review-editor { top: auto; }
  .login-wrap { min-height: calc(100dvh - 210px); }
}
@media (max-width: 400px) {
  .hero-actions { display: grid; grid-template-columns: 1fr; }
  .hero-actions .button { width: 100%; }
  .stats-grid { gap: 8px; }
  .stat-card { padding: 14px 12px; }
  .stat-card p { font-size: 10px; }
  .fleet-metrics > div { padding: 12px; }
  .pipeline .stage { flex-basis: 100%; }
  .node-facts { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .intel-refresh-panel[data-status="RUNNING"] .intel-activity-line::after { animation: none; width: 100%; }
  html { scroll-behavior: auto; }
  .icon-button:hover { transform: none; }
  .nav-item:hover, .stat-card:hover, .pipeline .stage:hover { transform: none; }
}
@media (prefers-reduced-transparency: reduce) {
  .sidebar, .topbar, .surface, .stat-card, .hero { backdrop-filter: none; -webkit-backdrop-filter: none; }
  .sidebar { background: #0a2233; }
  .topbar { background: #091e2e; }
  .surface, .stat-card { background: #102c41; }
  .hero { background: #11344b; }
}
@media (prefers-contrast: more) {
  .surface, .stat-card, .node-card, .intel-summary > div { border-color: #9fbfce; }
  .nav-item, .muted-copy, .fine-print { color: #e4f0f5; }
  .verification-strip { border-color: #b9dce7; }
}
@media (forced-colors: active) {
  .hero, .intel-refresh-panel, .intel-summary > div, .node-card, .fleet-metrics > div, .verification-strip { background: Canvas; border-color: CanvasText; color: CanvasText; box-shadow: none; }
  .nav-item.active, .pipeline .stage:hover { background: Highlight; color: HighlightText; }
  .strip-indicator { background: CanvasText; box-shadow: none; border: 1px solid CanvasText; }
  .fleet-metrics > div::before { display: none; }
}
"""
