"""Shared, dependency-free workbench: capability-aware UX and confirmation surface."""
CONTEXT_HTML = r'''<section class="runtime-context" aria-label="실행 환경과 권한">
  <div><span class="runtime-dot" aria-hidden="true"></span><strong id="runtime-label">실행 환경 확인 중</strong><span id="runtime-note">권한과 기능을 확인합니다.</span></div>
  <span class="runtime-boundary">독립 서명 · 명시적 게시 · 노드별 확인</span>
</section>'''
ATTENTION_HTML = r'''<section class="attention-panel" aria-labelledby="attention-title">
  <div class="attention-mark" aria-hidden="true">!</div><div class="attention-copy"><span class="overline">NEXT OPERATOR ACTION</span><h2 id="attention-title">현재 상태를 확인합니다</h2><p id="attention-note">검토 근거와 노드 보고를 별도로 확인합니다.</p></div><button id="attention-action" class="button outline" type="button" data-go="reviews">위협 검토 열기 →</button>
</section>'''
DIALOG_HTML = r'''<dialog id="ops-confirm" class="ops-confirm" aria-labelledby="ops-confirm-title" aria-describedby="ops-confirm-description">
  <form id="ops-confirm-form" novalidate>
    <div class="overline">REVIEW BEFORE COMMIT</div><h2 id="ops-confirm-title">변경 확인</h2><p id="ops-confirm-description"></p>
    <dl id="ops-confirm-facts" class="confirmation-facts"></dl>
    <div id="ops-confirm-typing"><label for="ops-confirm-input">확인 문구 <code id="ops-confirm-expected"></code>를 입력하세요.</label><input id="ops-confirm-input" autocomplete="off" spellcheck="false" autocapitalize="off"></div>
    <div class="confirmation-actions"><button type="button" class="button outline" id="ops-confirm-cancel">취소</button><button type="submit" class="button primary" id="ops-confirm-submit" disabled>확인 후 실행</button></div>
  </form>
</dialog>'''
NODE_FILTER_HTML = r'''<div class="node-toolbar"><label class="field-inline" for="node-search"><span>노드 검색</span><input id="node-search" type="search" placeholder="이름 · 장치 ID · 사설 IP"></label><label class="field-inline" for="node-state-filter"><span>상태 필터</span><select id="node-state-filter"><option value="all">모든 노드</option><option value="attention">확인 필요</option><option value="verified">DNS 응답 비교 확인</option></select></label><output id="node-visible-count" aria-live="polite">0개</output></div>'''
REVIEW_SUMMARY_HTML = r'''<div class="review-queue-summary" aria-label="검토 대기열 요약"><span>표시 <strong id="review-visible">–</strong></span><span>미승인 <strong id="review-pending">–</strong></span><span>유효 승인 <strong id="review-active-approved">–</strong></span><span>범위·만료 제한 <strong id="review-limited">–</strong></span></div>'''

CSS = r'''
/* Operations workbench — compact, legible, with deliberate action hierarchy. */
:root{--ops-text:#e6f0f8;--ops-muted:#a5b9cc;--ops-line:rgba(144,191,214,.23);--ops-focus:#8de9ec}
.hero{min-height:148px!important;padding:22px 28px!important;margin-bottom:12px!important;border-radius:14px!important}
.hero h1{font-size:30px!important;letter-spacing:-.045em;line-height:1.3;margin-bottom:8px}
.hero .eyebrow{margin-bottom:10px}.hero-art{width:180px!important;height:180px!important;right:2%!important;opacity:.3!important}
.hero-trust{margin-top:12px!important}.hero-actions{margin-top:16px!important}
body[data-active-view]:not([data-active-view="overview"]) .hero-actions{display:none}
body[data-active-view]:not([data-active-view="overview"]) .hero{min-height:114px!important}
body[data-active-view]:not([data-active-view="overview"]) .hero-trust{display:none}
.runtime-context{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 2px 16px;font-size:11px;color:var(--ops-muted)}
.runtime-context>div{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0}.runtime-context strong{color:var(--ops-text);font-weight:700}
.runtime-dot{width:6px;height:6px;border-radius:50%;background:#8ddee4;flex:0 0 auto}.runtime-boundary{font-size:10px;text-align:right}
.muted-copy,.lead,.fine-print{color:var(--ops-muted)}.lead{font-size:14px!important}.surface p{line-height:1.7}
.verification-strip{margin-bottom:20px!important;font-size:11px!important}
.attention-panel{display:flex;align-items:center;gap:18px;background:linear-gradient(115deg,rgba(26,62,82,.86),rgba(12,35,54,.8));border:1px solid var(--ops-line);border-left:3px solid #efc27d;border-radius:14px;padding:20px 22px;margin:0 0 22px}
.attention-mark{display:grid;place-items:center;flex:0 0 32px;height:32px;border-radius:50%;color:#ffd796;background:rgba(215,166,91,.13);font-size:17px;font-weight:750}
.attention-copy{min-width:0;flex:1}.attention-copy h2{font-size:19px;line-height:1.4;margin:5px 0}.attention-copy p{margin:0;font-size:12px;color:#b4c9d9;line-height:1.6}
.attention-panel .overline{font-size:9px;color:#e3be8b}.attention-panel[data-tone="normal"]{border-left-color:#8dd9ce}.attention-panel[data-tone="normal"] .attention-mark{color:#a9e3d5;background:rgba(81,184,164,.12)}
.stats-grid{gap:13px}.stat-card{min-height:137px!important;padding:20px!important}.stat-value{font-size:35px!important}
.stat-card p,.stat-caption,.pipeline .stage small{font-size:12px}.fleet-summary{margin-bottom:20px}
.review-queue-summary{display:flex;flex-wrap:wrap;gap:10px 20px;padding:13px 17px;border-bottom:1px solid var(--ops-line);font-size:11px;color:var(--ops-muted)}
.review-queue-summary strong{font-size:13px;color:var(--ops-text);margin-left:4px;font-variant-numeric:tabular-nums}
.review-editor{position:sticky;top:90px}.review-item strong{font-size:14px!important}.review-item small{font-size:12px}
.intel-refresh-panel{padding:21px 24px!important}.intel-refresh-panel h3{font-size:18px!important}
.intel-summary{gap:10px;margin:16px 0}.intel-summary>div{padding:12px!important}.intel-summary strong{font-size:12px!important}
.node-toolbar{display:flex;align-items:end;gap:12px;margin:0 0 17px;flex-wrap:wrap}.field-inline{margin:0;display:flex;flex-direction:column;gap:7px;flex:1;min-width:140px}.field-inline>span{font-size:11px;color:var(--ops-muted)}
.node-toolbar .field-inline:first-child{flex:2}.node-toolbar input,.node-toolbar select{min-height:42px}.node-toolbar output{padding-bottom:13px;color:var(--ops-muted);font-size:11px;white-space:nowrap}
.node-card{border-left:3px solid var(--ops-line)}.node-card[data-tone="good"]{border-left-color:#73d6b0}.node-card[data-tone="warn"]{border-left-color:#e9bd7b}.node-card[data-tone="bad"]{border-left-color:#f09baa}
.cloud-tools{border-color:var(--ops-line)}.cloud-tools>summary{cursor:pointer;list-style:none;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:16px;font-weight:700;min-height:36px}.cloud-tools>summary::-webkit-details-marker{display:none}.cloud-tools>summary::after{content:'＋';color:#8edce5;font-size:20px}.cloud-tools[open]>summary::after{content:'−'}.cloud-tools>summary:focus-visible{outline:2px solid var(--ops-focus);outline-offset:5px}
.cloud-tools[open]>.dashboard-grid{margin-top:22px}.cloud-preview{margin-top:17px;border:1px solid rgba(131,209,222,.32);border-radius:11px;background:rgba(6,24,38,.58);padding:18px}.cloud-preview h4{font-size:14px;margin:0 0 10px}.cloud-preview p{font-size:12px;color:#b5c8d8}.preview-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.preview-grid>div{border-left:2px solid #75b8c8;padding-left:11px}.preview-grid small{font-size:10px;color:#a6bdcf;display:block}.preview-grid strong{font-size:23px;display:block;margin-top:5px}.preview-grid .warning{color:#f6cf93}.preview-fingerprint{font-size:11px;overflow-wrap:anywhere;line-height:1.7;margin:15px 0;color:#bdd5df}
.ops-confirm{color:#e6f3fb;background:#10273b;border:1px solid #52768d;border-radius:18px;width:min(530px,calc(100vw - 30px));max-height:calc(100dvh - 40px);padding:29px;overflow:auto;box-shadow:0 30px 100px #0008}
.ops-confirm::backdrop{background:rgba(3,12,24,.78);backdrop-filter:blur(5px)}.ops-confirm h2{font-size:24px;margin:11px 0 13px}.ops-confirm p{font-size:13px;line-height:1.75;white-space:pre-line;color:#b5c9da}
.confirmation-facts{display:grid;grid-template-columns:minmax(90px,.7fr) minmax(0,1.5fr);gap:10px 15px;padding:16px 0;border-block:1px solid var(--ops-line);margin:20px 0;font-size:12px}
.confirmation-facts dt{color:#96b1c6}.confirmation-facts dd{margin:0;overflow-wrap:anywhere;line-height:1.6}.confirmation-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:23px}
.ops-confirm label{font-size:12px;line-height:1.8}.ops-confirm code{color:#91e6e5;font-size:12px}.ops-confirm input{font-size:14px!important;min-height:45px}
button[aria-busy="true"]{cursor:progress;opacity:.68}button[aria-busy="true"]::after{content:" · 처리 중";font-size:.85em}.button:disabled{transform:none!important}.form-status{font-size:12px;color:#b3cbd9;line-height:1.7}
@media(max-width:1000px){.review-editor{position:static}.runtime-boundary{display:none}}
/* Keep controls and observed data above decoration, especially on narrow displays. */
.surface{box-shadow:0 7px 24px rgba(0,8,19,.12)}
/* Cloud navigation uses anchors, while local actions use buttons. Center the
   content of both, not only their outer flex boxes. Preserve [hidden]. */
.topbar{height:auto;flex-wrap:wrap}
.topbar-actions{min-width:0;max-width:100%;flex-wrap:wrap;justify-content:flex-end}
.topbar-actions>.quiet-button{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;min-height:44px;line-height:1.4;white-space:nowrap;text-decoration:none}
.topbar-actions>.icon-button{flex:0 0 44px;width:44px;height:44px}
.connection-status{position:relative;display:inline-flex;align-items:center;gap:8px;min-width:0;max-width:min(100%,20rem)}
.connection-status>.connection-dot{flex:0 0 8px}
.connection-status>.connection{min-width:0;line-height:1.5;overflow-wrap:anywhere}
.surface>h3,.form-heading h3{line-height:1.5}
input:not([type="checkbox"]),select,textarea{font-size:14px;line-height:1.5}
label{font-size:12px}.button{min-height:42px;font-size:12px}
.fact-list>div{font-size:12px}.node-facts strong{font-size:12px}
.published-row strong{font-size:13px}.audit-entry{line-height:1.6}
@media(min-width:701px){.content{padding-top:26px}.sidebar{padding-top:27px}.brand{margin-bottom:39px}.side-nav{gap:7px}.nav-item{min-height:46px}}
/* The sidebar consumes 180–215px here. Give context its own row before
   squeezing action labels, and allow complete controls to wrap when needed. */
@media(min-width:701px) and (max-width:1100px){
  .topbar{gap:12px;padding-block:14px}
  .topbar-context{flex:1 0 100%}
  .topbar-actions{width:100%;gap:8px}
}
@media(max-width:700px){
  .sidebar{padding:12px 14px 10px;background:#0b2032}
  .brand{margin:0 0 10px}.brand strong{font-size:17px}.brand small{font-size:8px}
  .side-nav{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;overflow:visible}
  .nav-item{min-width:0;min-height:44px;font-size:11px;padding:8px 6px;gap:6px;justify-content:center}
  .nav-icon{font-size:16px;flex-shrink:0}.nav-count{font-size:10px;margin-left:0}
  .topbar{min-height:52px;height:auto;padding:7px 14px;gap:0}
  .topbar-context{display:none}.topbar-actions{width:100%;gap:6px}
  .topbar-actions>.connection-status{margin-left:auto;flex-shrink:0}
  /* Keep the compact dot visually, but retain its state for assistive tech. */
  .connection-status>.connection{display:block;position:absolute;left:0;top:0;width:1px;height:1px;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
  .topbar-actions>.quiet-button{font-size:11px;padding:8px 10px}
  .content{padding:18px 15px 38px}
  .hero,body[data-active-view]:not([data-active-view="overview"]) .hero{display:block;min-height:0!important;padding:0 0 16px!important;margin-bottom:0!important;background:none!important;border:0!important;box-shadow:none!important;overflow:visible}
  .hero .eyebrow,.hero-art,.hero-tools,.hero-trust{display:none!important}
  .hero-copy{max-width:100%!important}.hero h1{font-size:27px!important;margin:0 0 7px}
  .hero .lead{font-size:12px!important;line-height:1.65;margin:0;max-width:none}
  .hero-actions{margin-top:12px!important;gap:8px}.hero-actions .button{font-size:11px;min-height:38px;padding:9px 12px}
  .runtime-context{font-size:10px;padding:0 0 13px}.runtime-context>div{gap:5px 8px}
  #runtime-note{flex-basis:100%;padding-left:14px}
  .verification-strip{padding:11px 13px!important;gap:6px 10px!important;margin-bottom:20px!important;line-height:1.5}
  .verification-strip .strip-tail{font-size:10px;flex-basis:100%;margin:0}
  .attention-panel{padding:16px;gap:11px;flex-wrap:wrap}.attention-copy{flex-basis:calc(100% - 45px)}.attention-copy h2{font-size:17px}.attention-panel>.button{margin-left:43px;min-height:42px}
  .stat-card{padding:16px!important;min-height:124px!important}.stat-value{font-size:31px!important}.stat-card p{font-size:11px}
  .section-top.outside .overline{font-size:9px;letter-spacing:.12em}.section-top.outside p{font-size:12px;line-height:1.7}
  .confirmation-actions .button{flex:1;min-height:44px}.ops-confirm{padding:22px}
  .node-toolbar{gap:10px}.node-toolbar output{flex:0 0 auto}
  .intel-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.review-queue-summary{gap:9px 13px}
  .cloud-tools{padding:20px}.preview-grid{gap:7px}.preview-grid strong{font-size:21px}
  .published-head,.published-row{grid-template-columns:minmax(0,1.5fr) 53px minmax(70px,1fr);gap:7px;padding:11px 0}
  .published-row strong{font-size:11px;min-width:0}.published-row span:last-child{font-size:10px;overflow-wrap:anywhere}
  .audit-head,.audit-entry{grid-template-columns:minmax(0,.9fr) minmax(0,1fr) minmax(0,1.1fr);gap:8px;padding:12px 0;font-size:11px}
  .audit-entry strong{overflow-wrap:anywhere;min-width:0}
  .view[data-panel="deployment"]>.section-top.outside>div{display:none}
  .view[data-panel="deployment"]>.section-top.outside{justify-content:flex-end;margin-bottom:13px}
  .deployment-big-icon{display:none}.view[data-panel="deployment"] .surface>h3{margin-top:13px;font-size:19px;line-height:1.5}
  .fact-list>div{padding:11px 0}
  .toast{bottom:16px;right:15px;max-width:calc(100vw - 30px);font-size:12px}
}
@media(prefers-reduced-motion:reduce){.ops-confirm::backdrop{backdrop-filter:none}*{scroll-behavior:auto!important}}
@media(forced-colors:active){.ops-confirm,.attention-panel,.runtime-context,.cloud-preview{background:Canvas;color:CanvasText;border-color:CanvasText}.runtime-dot{background:CanvasText}.attention-copy p,.ops-confirm p,.confirmation-facts dt,.confirmation-facts dd{color:CanvasText}}
'''

JS = r'''
// Shared utilities are installed before the existing local/cloud controller.
let opsConfirmation = null;
let opsCapabilities = null;
let lastNodeItems = [];
function cancelConfirmation() {
  if(opsConfirmation)opsConfirmation.cancel();
}
function confirmOperation({title,description,phrase='',facts=[],action='확인 후 실행'}) {
  if(opsConfirmation)return Promise.resolve(false);
  const dialog=document.getElementById('ops-confirm');
  const previous=document.activeElement;
  document.getElementById('ops-confirm-title').textContent=title;
  document.getElementById('ops-confirm-description').textContent=description;
  document.getElementById('ops-confirm-expected').textContent=phrase;
  const input=document.getElementById('ops-confirm-input');input.value='';
  document.getElementById('ops-confirm-typing').hidden=!phrase;
  const list=document.getElementById('ops-confirm-facts');list.replaceChildren();
  for(const [label,value] of facts){const term=document.createElement('dt'),detail=document.createElement('dd');term.textContent=label;detail.textContent=String(value);list.append(term,detail);}
  list.hidden=!facts.length;
  const submit=document.getElementById('ops-confirm-submit');submit.textContent=action;submit.disabled=!!phrase;
  return new Promise(resolve=>{
    const epoch=sessionEpoch;
    const done=accepted=>{
      if(!opsConfirmation)return;
      opsConfirmation=null;dialog.close();
      dialog.removeEventListener('cancel',onCancel);
      document.getElementById('ops-confirm-form').onsubmit=null;
      document.getElementById('ops-confirm-cancel').onclick=null;input.oninput=null;
      if(previous?.isConnected)previous.focus({preventScroll:true});
      resolve(!!accepted && epoch===sessionEpoch && !!token);
    };
    const onCancel=event=>{event.preventDefault();done(false);};
    opsConfirmation={cancel:()=>done(false)};
    dialog.addEventListener('cancel',onCancel);
    input.oninput=()=>{submit.disabled=input.value!==phrase;};
    document.getElementById('ops-confirm-form').onsubmit=event=>{event.preventDefault();if(!phrase||input.value===phrase)done(true);};
    document.getElementById('ops-confirm-cancel').onclick=()=>done(false);
    dialog.showModal();(phrase?input:document.getElementById('ops-confirm-cancel')).focus();
  });
}
function bindAsyncForm(id,handler) {
  const form=document.getElementById(id);
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(form.dataset.busy==='true')return;
    const buttons=[...form.querySelectorAll('button[type="submit"]')];
    // Guard duplicate submissions without taking ownership of disabled: the
    // handler may refresh validation and change that state while it is busy.
    const ariaDisabled=buttons.map(x=>x.getAttribute('aria-disabled'));
    form.dataset.busy='true';buttons.forEach(x=>{x.setAttribute('aria-busy','true');x.setAttribute('aria-disabled','true');});
    try{await handler(event);}finally{delete form.dataset.busy;buttons.forEach((x,i)=>{
      x.removeAttribute('aria-busy');
      if(ariaDisabled[i]===null)x.removeAttribute('aria-disabled');else x.setAttribute('aria-disabled',ariaDisabled[i]);
    });}
  });
}
async function loadCapabilities() {
  const epoch=sessionEpoch;
  try {
    const caps=await api('/api/capabilities');
    if(epoch!==sessionEpoch||!token)return;
    opsCapabilities=caps;
    document.body.dataset.mode=caps.mode;
    document.getElementById('runtime-label').textContent=caps.mode==='cloud'?'클라우드 관제 · /dashboard':'로컬 정책 서버';
    document.getElementById('runtime-note').textContent=caps.direct_refresh?'OpenPhish·GSB 직접 검증 연결':caps.evidence_upload?'OpenPhish·GSB 설정 필요 · 수동 FQDN 가능':'수집 브리지 연결 필요';
    document.querySelector('.intel-refresh-panel').hidden=false;
    const env=document.querySelector('.environment-label');if(env)env.textContent=caps.mode==='cloud'?'CLOUD REVIEW & PUBLICATION':'LOCAL REVIEW & COLLECTION';
  } catch(error) {
    if(epoch!==sessionEpoch||!token||error.stale)return;
    document.body.dataset.mode='unknown';
    document.getElementById('runtime-label').textContent='기능 확인 실패';
    document.getElementById('runtime-note').textContent='연결 상태를 확인하고 다시 로그인하세요.';
  }
}
function renderAttention(result) {
  let title,note,label,target='reviews',normal=false;
  if(result.evidence_error){title='검토 근거를 확인할 수 없습니다';note='파일 권한이나 근거 불일치를 확인하세요. 정책 게시와 노드 상태는 별도로 유지됩니다.';label='근거 상태 확인';}
  else if(result.evidence_missing||!result.fresh){title='최신 검증 자료가 필요합니다';note='수집 결과를 확인한 뒤 새 근거를 가져오세요. 기존 승인과 게시 정책을 자동으로 덮어쓰지 않습니다.';label='자료 수집·가져오기';}
  else if(!result.approved_eligible){title='유효한 후보의 검토 승인이 필요합니다';note='도메인 전체와 하위 도메인 차단 영향을 확인하세요. 공유 호스팅·만료 근거는 승인 대상에서 제외됩니다.';label='검토 대기열 열기';}
  else if(result.drafts_error){title='정책 초안 저장소를 확인할 수 없습니다';note='새 초안을 만들기 전에 파일 무결성과 저장 공간을 확인하세요. 기존 게시 정책을 성공으로 추정하지 않습니다.';label='초안 상태 확인';target='drafts';}
  else if(!result.drafts){title='승인된 근거로 정책 초안을 만들 수 있습니다';note='생성 결과는 미서명 파일입니다. 독립 서명과 별도 게시 단계가 이어집니다.';label='DNS 초안 생성';target='drafts';}
  else if(result.deployment.state!=='SIGNED_FILE_VERIFIED'){title='서명 게시 기준선을 확인하세요';note='초안 생성과 게시 완료는 다릅니다. 서명 검증과 유효기간을 확인한 뒤 배포합니다.';label='게시 상태 확인';target='deployment';}
  else if(result.nodes_error||!result.nodes?.registered||result.nodes?.needs_verification){title='DNS 노드의 추가 확인이 필요합니다';note='게시 파일은 확인됐습니다. 노드별 정책 버전·보고 시각·DNS 응답 결과를 확인하세요.';label='노드 상태 확인';target='deployment';}
  else{normal=true;title='게시 정책과 노드 보고를 확인했습니다';note='이 결과는 등록 노드 기준입니다. LAN 단말의 실제 DNS 이용과 우회 경로는 별도 검증 대상입니다.';label='상세 근거 확인';target='deployment';}
  document.getElementById('attention-title').textContent=title;document.getElementById('attention-note').textContent=note;
  const button=document.getElementById('attention-action');button.textContent=label+' →';button.dataset.go=target;
  document.querySelector('.attention-panel').dataset.tone=normal?'normal':'warning';
}
'''
