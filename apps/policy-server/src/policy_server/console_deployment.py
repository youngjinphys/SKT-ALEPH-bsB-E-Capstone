"""Presentation of scoped observations, not a second policy engine.

These styles apply last to the shared local/cloud shell. All actions remain in
its existing controller and every state is rendered from authenticated reads.
"""
CSS = r'''
/* A calm, high-density control surface with visibly separate proof stages. */
:root{--ops-surface:#0c2234;--ops-muted:#aec4d4;--ops-label:#a9d3df}
body{background:#07131e}
.content{max-width:1590px}
.hero{background:linear-gradient(110deg,rgba(24,64,83,.82),rgba(10,30,46,.94))!important;border-color:rgba(134,205,222,.27)!important}
.hero h1{font-weight:720!important}.hero-art{opacity:.16!important}
.hero .lead{color:#b6d0df!important}.overline{color:var(--ops-label);line-height:1.5}
.runtime-context{padding-bottom:12px}.runtime-context .runtime-boundary{color:#96b1c3}
.surface{background:linear-gradient(125deg,rgba(16,44,62,.96),rgba(9,28,45,.98));border-color:rgba(130,190,212,.23);border-radius:14px}
.button{min-height:44px}.text-button{min-height:38px;line-height:1.5}
.read-error{padding:13px 16px;border:1px solid #ac6472;border-left:3px solid #f49eaa;border-radius:10px;background:#32212c;color:#ffd9df;font-size:13px;line-height:1.65;margin:0 0 16px}
.read-error[hidden]{display:none}
.inline-count{display:inline-block;margin-left:8px;font:600 12px ui-monospace,SFMono-Regular,monospace;color:#9ed4df;letter-spacing:0}
.deployment-toolbar{display:flex;align-items:center;justify-content:space-between;gap:22px;margin-bottom:18px;padding:18px 21px;border:1px solid rgba(135,208,223,.26);border-radius:13px;background:#0c2335}
.deployment-target{display:grid;grid-template-columns:minmax(0,340px);gap:6px;flex:1;min-width:0}
.deployment-target label{margin:0;font-size:12px;color:#b9deea;font-weight:700}
.deployment-target select{width:100%;min-width:0;min-height:44px;font-size:14px;border-color:#527b90;background:#081c2c}
.deployment-target .fine-print{font-size:11px;line-height:1.5;color:#a4bed0}
.deployment-observation{display:grid;gap:7px;min-width:0;text-align:right}
.deployment-observation strong{font-size:12px;color:#e2f5fa;font-variant-numeric:tabular-nums;line-height:1.6}
.deployment-observation .overline{font-size:9px;letter-spacing:.12em}
.deployment-observation .fine-print{font-size:11px}
.deployment-toolbar>.button{flex-shrink:0}
[data-panel="deployment"]>.dashboard-grid{gap:16px;margin-bottom:16px}
[data-panel="deployment"]>.dashboard-grid>.surface{padding:22px 24px;min-width:0;position:relative}
[data-panel="deployment"]>.dashboard-grid>.surface::before{content:"";position:absolute;top:0;left:23px;right:23px;height:2px;background:linear-gradient(90deg,#74cbd7,transparent);opacity:.65}
[data-panel="deployment"]>.dashboard-grid>.surface:nth-child(2)::before{background:linear-gradient(90deg,#c7b689,transparent)}
[data-panel="deployment"] .deployment-big-icon{display:none}
[data-panel="deployment"] .surface>h3{margin:14px 0 8px;font-size:20px;line-height:1.45;letter-spacing:-.025em}
[data-panel="deployment"] .muted-copy{font-size:12px;line-height:1.7}
[data-panel="deployment"] .fact-list{margin-top:20px}
[data-panel="deployment"] .fact-list>div{gap:16px;align-items:flex-start;padding:10px 0;font-size:12px}
[data-panel="deployment"] .fact-list>div>span{flex:0 0 105px;color:#a7bfd1}
[data-panel="deployment"] .fact-list>div>strong{min-width:0;text-align:right;line-height:1.55;overflow-wrap:anywhere}
[data-panel="deployment"] .fact-list .mono{font-size:11px;font-weight:500;letter-spacing:.02em}
[data-panel="deployment"] .selected-node-facts{margin-bottom:14px}
[data-panel="deployment"][aria-busy="true"] .deployment-toolbar{border-color:#7bd6de}
[data-panel="deployment"]>.published-list-surface{margin:16px 0;padding:24px}
.published-header{align-items:flex-start}.published-header input{max-width:260px;min-height:44px}
.published-head{font-size:11px;letter-spacing:.03em}.published-row{padding:14px 12px;min-height:48px}
.published-row .mini-badge{justify-self:start;min-width:57px;text-align:center;letter-spacing:.05em}
.published-row strong{font-weight:600}.published-row:hover{background:rgba(126,205,221,.055)}
.nodes-panel{padding:24px;margin-top:16px}
.nodes-panel>.section-top.outside{margin-bottom:18px}
.nodes-layout{grid-template-columns:minmax(0,1fr)!important;gap:18px}
.node-list{grid-template-columns:repeat(2,minmax(0,1fr));max-height:none;overflow:visible;gap:14px}
.node-list>.empty-list{grid-column:1/-1}
.node-card{padding:20px;border-radius:12px;background:#0a2031}
.node-head .mini-badge{white-space:normal;max-width:190px;line-height:1.5;font-size:10px}
.node-head>div{min-width:0}.node-head strong{font-size:15px}.node-head small{font-size:11px;overflow-wrap:anywhere}
.node-facts{gap:14px 18px;padding-top:16px;margin-top:16px}
.node-facts span{font-size:11px;color:#a7c1d2}.node-facts strong{font-size:12px;line-height:1.6}
.node-hash{color:#a3c8d7;line-height:1.5}.node-footer{align-items:center}
.node-enrollment{border:1px dashed rgba(145,196,212,.4);border-radius:12px;background:#0a2030;padding:0 18px}
.node-enrollment>summary{cursor:pointer;min-height:54px;display:flex;gap:15px;align-items:center;list-style:none;font-size:13px;font-weight:700;color:#d6edf5}
.node-enrollment>summary::-webkit-details-marker{display:none}
.node-enrollment>summary>span{font-size:11px;color:#a4c1d1;font-weight:400;margin-left:auto}
.node-enrollment>summary::after{content:"＋";color:#9adce3}.node-enrollment[open]>summary::after{content:"−"}
.node-enrollment>summary:focus-visible{outline:2px solid var(--ops-focus);outline-offset:2px}
.node-enrollment .node-form{border:0;background:transparent;padding:8px 0 20px;max-width:680px}
.node-boundary-note{background:rgba(10,35,50,.55);margin-top:18px;padding:14px 17px}
.node-boundary-note p{font-size:11px;line-height:1.7}.node-boundary-note strong{font-size:12px}
[data-panel="deployment"]>.cloud-tools{padding:15px 22px;margin-top:16px;margin-bottom:16px}
[data-panel="deployment"]>.cloud-tools>summary{font-size:14px;min-height:33px}
/* Overview: put the next decision and current evidence before decorative process. */
.attention-panel{background:#122c3e;padding:20px 23px}.attention-copy h2{font-size:20px}.attention-copy p{max-width:680px}
.stats-grid{gap:14px}.stat-card{background:#10283b!important;border-color:rgba(129,196,217,.24)}
.stat-value{font-variant-numeric:tabular-nums;letter-spacing:-.035em;font-size:38px!important}
.fleet-metrics>div{border:0;border-radius:0;background:none;border-left:1px solid rgba(141,198,221,.24);padding:8px 18px}
.fleet-metrics>div:first-child{border-left:0;padding-left:0}.fleet-metrics strong{font-size:28px}
.fleet-summary{padding:22px 24px}.fleet-title .muted-copy{font-size:12px}
@media(min-width:1101px){.content{padding-left:38px;padding-right:38px}.topbar{padding-left:38px;padding-right:38px}.sidebar{width:236px;flex-basis:236px}.brand{padding-left:10px}.stats-grid{margin-bottom:17px}}
@media(max-width:1100px){.deployment-toolbar{flex-wrap:wrap}.deployment-target{flex:1 1 240px}.deployment-observation{flex:1 1 170px}.deployment-toolbar>.button{margin-left:auto}.node-list{grid-template-columns:1fr}}
@media(max-width:700px){
  body[data-active-view="deployment"] .hero .lead{display:none}
  body[data-active-view="deployment"] .runtime-context{display:none}
  body[data-active-view="deployment"] .verification-strip .strip-tail{display:none}
  body[data-active-view="deployment"] .verification-strip{margin-bottom:13px!important}
  .deployment-toolbar{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding:13px;margin-bottom:14px}
  .deployment-target{grid-column:1/-1;display:grid;grid-template-columns:1fr;gap:5px}
  .deployment-target select{font-size:13px;min-height:44px}.deployment-target .fine-print{font-size:10px}
  .deployment-observation{display:block;text-align:left;align-self:center;min-width:0}
  .deployment-observation .overline{display:none}.deployment-observation strong{display:block;font-size:10px}
  .deployment-observation .fine-print{display:block;font-size:10px;line-height:1.5}
  .deployment-toolbar>.button{min-height:44px;font-size:11px;padding:8px 11px}
  [data-panel="deployment"]>.dashboard-grid{gap:13px;margin-bottom:13px}
  [data-panel="deployment"]>.dashboard-grid>.surface{padding:18px}
  [data-panel="deployment"] .surface>h3{font-size:19px;margin:11px 0 8px}
  [data-panel="deployment"] .fact-list>div{font-size:11px;gap:10px}
  [data-panel="deployment"] .fact-list>div>span{flex-basis:83px}
  [data-panel="deployment"]>.published-list-surface,.nodes-panel{padding:17px}
  .node-list{grid-template-columns:minmax(0,1fr)}.node-card{padding:16px}
  .node-head .mini-badge{max-width:none}.node-facts{gap:12px}.node-facts strong{font-size:11px}
  .node-enrollment{padding:0 13px}.node-enrollment>summary{font-size:12px;gap:7px}.node-enrollment>summary>span{display:none}
  .node-toolbar .field-inline{min-width:120px}.node-toolbar input,.node-toolbar select{min-height:44px}
  .node-boundary-note{padding:13px}.read-error{padding:12px;font-size:12px}
  .fleet-metrics{gap:9px}.fleet-metrics>div{padding:9px 11px;border-left:0;border-top:1px solid rgba(141,198,221,.23)}.fleet-metrics>div:first-child{padding-left:11px;border-left:0}
  .attention-copy h2{font-size:18px}.published-header input{max-width:none}
}
@media(forced-colors:active){
  .deployment-toolbar,.node-enrollment,.node-card,.surface,.read-error,.stat-card,.attention-panel{background:Canvas!important;color:CanvasText;border-color:CanvasText}
  .read-error,.deployment-target select,.node-head .mini-badge{color:CanvasText;background:Canvas}
  .deployment-target label,.deployment-observation strong,.node-enrollment>summary,.node-facts span,.node-facts strong{color:CanvasText}
}
'''
