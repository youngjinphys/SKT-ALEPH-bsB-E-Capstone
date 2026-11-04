"""Bundled no-dependency browser operator interface."""
JS = r""""use strict";
// Security: no token persistence, no external dependencies, no untrusted innerHTML.
const $ = (id) => document.getElementById(id);
const panelTitles = {
  overview:["운영 개요","정책 근거, 승인, 서명 게시 상태를 하나의 화면에서 확인합니다.","Operations"],
  reviews:["위협 검토","위협정보 검증 결과에 대한 수동 승인과 근거를 기록합니다.","Threat review"],
  engine:["위험도 제안","EXACT 범위의 비집행 정책 제안과 관리 목록을 확인합니다.","Risk proposals"],
  drafts:["DNS 정책 초안","수동 FQDN과 승인된 외부 위협정보를 결합해 미서명 DNS 정책을 만듭니다.","DNS drafts"],
  deployment:["배포 현황","서명된 게시물의 상태를 검증하고 DNS 적용 경계를 확인합니다.","Distribution"],
  audit:["작업 기록","검토·설정·초안 변경 기록을 살펴봅니다.","Audit trail"]
};
let token = null;
let currentView = "overview";
let reviewData = null;
let buildReviewContext = null;
let selectedReview = null;
let intelLatest = null;
let intelReviewRevision = null;
let intelContextRevision = null;
let selectedDeploymentDevice = "";
let defaultDeploymentDevice = "";
let nodesReadValid = false;
// In-memory display identity only. Never reuse observations across a session or target.
let deploymentSnapshot = null;
let deploymentReadPending = false;
let lastNodeRender = null;
let intelStatusEpoch = 0;
let publishedRules = [];
let lastActivity = Date.now();
let sessionEpoch = 0;
let viewEpoch = 0;
const viewRequestEpochs = Object.create(null);
function currentRequest(name) {
  const view = viewEpoch;
  const session = sessionEpoch;
  const id = (viewRequestEpochs[name] || 0) + 1;
  viewRequestEpochs[name] = id;
  return () => !!token && session === sessionEpoch && view === viewEpoch &&
      id === viewRequestEpochs[name] && currentView === name;
}
function staleRequest() {
  const error = Error("STALE_SESSION");
  error.stale = true;
  return error;
}
function displayError(error) {
  if(!error.stale) toast(error.message,true);
}
const SESSION_IDLE_MS = 15 * 60 * 1000;
let toastTimer = null;
const fmt = (value) => {
  if (!value) return "–";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "–" : date.toLocaleString("ko-KR", {dateStyle:"medium",timeStyle:"short"});
};
const showText = (id, content) => { $(id).textContent = content === null || content === undefined ? "–" : String(content); };
const node = (tag, className, value) => {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (value !== undefined) result.textContent = String(value);
  return result;
};
const pill = (text, className) => node("span","mini-badge" + (className ? " "+className : ""),text);
const empty = (message) => node("div","empty-list",message);
function toast(message, error) {
  if (toastTimer) clearTimeout(toastTimer);
  const popup=$("toast");
  popup.textContent=message;
  popup.className=error?"toast error":"toast";
  popup.hidden=false;
  toastTimer=setTimeout(()=>{popup.hidden=true;},5200);
}
async function api(path, data) {
  if (!token) throw Error("먼저 인증해야 합니다.");
  if(!$("authorized").hidden && expireIdleSession()) throw staleRequest();
  const activeToken=token, epoch=sessionEpoch;
  const stillCurrent=()=>token===activeToken && epoch===sessionEpoch;
  const headers={"Authorization":"Bearer "+activeToken};
  if (data !== undefined) headers["Content-Type"]="application/json";
  let response;
  const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),20000);
  try {
    try {
    response=await fetch(path,{
      method:data===undefined?"GET":"POST",
      headers:headers,
      cache:"no-store",
      signal:controller.signal,
      credentials:"omit",
      mode:"same-origin",
      ...(data===undefined?{}:{body:JSON.stringify(data)})
    });
  } catch (_) {
    if(!stillCurrent()) throw staleRequest();
    throw Error("콘솔 서버에 연결할 수 없습니다.");
  }
  if(!stillCurrent()) throw staleRequest();
  // Authorization loss must clear protected observations even if the error body
  // is empty, HTML, or malformed JSON. Never treat it as a recoverable read error.
  if(response.status===401 || response.status===403) {
    if(!$("authorized").hidden) lock();
    const error=Error(response.status===403?"운영자 권한을 확인할 수 없습니다. 다시 인증하세요.":"인증에 실패했습니다. 액세스 토큰을 확인하세요.");
    error.status=response.status;
    throw error;
  }
  let body;
  try {body=await response.json();} catch (_){
    if(!stillCurrent()) throw staleRequest();
    throw Error("서버 응답 형식이 올바르지 않습니다.");
  }
  if(!stillCurrent()) throw staleRequest();
  if(!response.ok){const error=Error(body.error||"요청이 거부되었습니다.");error.status=response.status;throw error;}
  if(!$("authorized").hidden)
    showText("last-checked",new Date().toLocaleTimeString("ko-KR",{hour:"2-digit",minute:"2-digit",second:"2-digit"}));
  return body;
  } finally {clearTimeout(deadline);}
}
function lock() {
  cancelConfirmation();
  document.dispatchEvent(new Event("ops:locked"));
  opsCapabilities=null;
  lastNodeItems=[];
  delete document.body.dataset.mode;
  $("nodes-list").replaceChildren();
  sessionEpoch++;
  viewEpoch++;
  token=null;
  deploymentSnapshot=null;
  deploymentReadPending=false;
  lastNodeRender=null;
  const deploymentPanel=document.querySelector('[data-panel="deployment"]');
  deploymentPanel.removeAttribute("aria-busy");
  delete deploymentPanel.dataset.readState;
  clearSelectedPublication();
  for(const id of ["stat-candidates","stat-approved","stat-fresh","stat-drafts","fleet-registered","fleet-applied","fleet-correlated","fleet-pending","overview-eligible","overview-next-expiry","overview-verified","nav-review-count","node-visible-count","edge-read-node","edge-read-received","edge-read-policy","edge-read-dns"])showText(id,null);
  for(const id of ["overview-deploy-state","overview-deploy-detail","attention-title","attention-note","fleet-read-summary","edge-apply-state","edge-apply-note","deployment-observed"])showText(id,"인증 후 조회");
  $("overview-deploy-dot").classList.remove("verified","error");
  $("audit-list").replaceChildren();
  for(const id of ["overview-read-error","publication-read-error","nodes-read-error"])setReadError(id,null);
  publishedRules=[];
  reviewData=null;
  buildReviewContext=null;
  selectedReview=null;
  intelLatest=null;
  intelReviewRevision=null;
  intelContextRevision=null;
  selectedDeploymentDevice="";
  defaultDeploymentDevice="";
  $("deployment-device-select").replaceChildren(new Option("기본 게시 대상",""));
  delete $("deployment-device-select").dataset.options;
  lastNodeItems=[];
  nodesReadValid=false;
  $("nodes-list").replaceChildren();
  intelStatusEpoch++;
  $("intel-import").disabled=true;
  $("intel-refresh-form").reset();
  showText("intel-state","인증 필요");
  showText("intel-checked","–");
  showText("intel-counts","–");
  showText("intel-run","–");
  showText("intel-note","");
  $("review-form").hidden=true;
  $("review-empty").hidden=false;
  $("reviewer").value="";
  $("reason").value="";
  $("review-list").replaceChildren();
  $("draft-list").replaceChildren();
  $("draft-impact").hidden=true;
  $("draft-impact").replaceChildren();
  $("published-list").replaceChildren();
  $("evaluation-result").replaceChildren();
  showText("last-checked","–");
  $("authorized").hidden=true;
  $("login-view").hidden=false;
  $("logout-button").hidden=true;
  $("token").value="";
  $("connection-dot").classList.remove("online");
  showText("connection-text","콘솔 인증 필요");
  showText("verification-status","인증 필요");
  const refreshPanel=document.querySelector(".intel-refresh-panel");
  if(refreshPanel) delete refreshPanel.dataset.status;
}
function unlock() {
  sessionEpoch++;
  $("authorized").hidden=false;
  $("login-view").hidden=true;
  $("logout-button").hidden=false;
  $("connection-dot").classList.add("online");
  showText("connection-text","콘솔 연결됨");
  lastActivity=Date.now();
  showText("hero-date",new Date().toLocaleDateString("ko-KR",{year:"numeric",month:"long",day:"numeric"}));
  setView("overview");
  loadCapabilities();
}
function setView(name) {
  if(!token||!panelTitles[name]) return;
  showText("verification-status","선택한 화면의 상태 조회 중");
  currentView=name;
  document.body.dataset.activeView=name;
  viewEpoch++;
  document.querySelectorAll("[data-panel]").forEach((el)=>{el.hidden=el.dataset.panel!==name;});
  document.querySelectorAll("[data-view]").forEach((el)=>{
    const active=el.dataset.view===name;
    el.classList.toggle("active",active);
    if(active)el.setAttribute("aria-current","page"); else el.removeAttribute("aria-current");
  });
  showText("page-title",panelTitles[name][0]);
  showText("page-description",panelTitles[name][1]);
  showText("crumb-current",panelTitles[name][2]);
  document.title="ALEPH · "+panelTitles[name][0]+" | DNS Operations";
  refreshView(name).catch(displayError);
  document.dispatchEvent(new Event("ops:poll-view"));
}
function navigateTo(name) {
  if(!token || !panelTitles[name]) return;
  setView(name);
  // Keyboard and mobile navigation return to the new page heading.
  $("page-title").focus({preventScroll:false});
}
async function refreshView(name) {
  // Keep the polling cycle active until BOTH reads settle. A quick overview
  // failure must not start the next poll while analytics is still in flight.
  if(name==="overview") {
    const results=await Promise.allSettled([loadOverview(),loadAnalytics()]);
    const failed=results.find(result=>result.status==="rejected");
    if(failed)throw failed.reason;
    return {partial:false};
  }
  if(name==="reviews") return Promise.all([loadReviews(),loadIntelStatus()]);
  if(name==="engine") return loadEngine();
  if(name==="drafts") return loadDrafts();
  if(name==="deployment") return loadDeployment();
  if(name==="audit") return loadAudit();
}
const deployLabel = (data) => ({
  NOT_CONFIGURED:"게시 경로 미설정",
  SIGNED_FILE_VERIFIED:"서명된 게시 파일 확인",
  NO_PUBLISHED_FILE:"게시 파일 없음",
  PUBLICATION_EXPIRED:"서명된 게시물의 유효기간 만료",
  VERIFICATION_FAILED:"서명 검증 실패"
})[data.state]||data.state||"미확인";
function deployDescription(data) {
  return ({
    SIGNED_FILE_VERIFIED:"서명·유효기간을 확인한 게시 정책입니다. DNS 노드 적용은 별도 보고와 비교합니다.",
    PUBLICATION_EXPIRED:"게시 정책의 유효기간이 지났습니다. 과거 서명과 현재 적용 상태를 구분해 확인하세요.",
    NO_PUBLISHED_FILE:"이 장치의 게시 정책이 없습니다. 독립 서명한 정책의 게시 상태를 확인하세요.",
    VERIFICATION_FAILED:"서명 또는 정책 구조를 검증하지 못했습니다. 정상 게시로 판단하지 않습니다.",
    NOT_CONFIGURED:"게시 정책 저장소가 연결되지 않았습니다. 운영 환경 설정을 확인하세요."
  })[data.state]||"게시 정책 상태를 확인할 수 없습니다.";
}
async function loadOverview() {
  const stillCurrent=currentRequest("overview");
  let result;
  setReadError("overview-read-error",null);
  try {result=await api("/api/overview");}
  catch(error){
    if(stillCurrent()){
      setReadError("overview-read-error","운영 상태 조회 실패 · 이전 수치를 현재 상태로 표시하지 않습니다. 다시 조회하세요.");
      for(const id of ["stat-candidates","stat-approved","stat-fresh","stat-drafts","fleet-registered","fleet-applied","fleet-correlated","fleet-pending","overview-eligible","overview-next-expiry","overview-verified"])showText(id,null);
      showText("overview-deploy-state","게시 정책 미확인");showText("overview-deploy-detail","이번 조회에서 게시 근거를 확인할 수 없습니다.");
      $("overview-deploy-dot").classList.remove("verified");$("overview-deploy-dot").classList.add("error");
      showText("attention-title","운영 상태를 다시 확인하세요");showText("attention-note","연결 실패로 현재 근거를 검증하지 못했습니다. 이전 정상 상태를 사용하지 않습니다.");
      document.querySelector(".attention-panel").dataset.tone="warning";
      document.querySelector(".verification-strip").dataset.state="error";showText("verification-status","조회 실패 · 미확인");
    }
    throw error;
  }
  if(!stillCurrent()) return;
  renderAttention(result);
  showText("stat-candidates",result.candidates);
  showText("stat-approved",result.approved);
  showText("stat-fresh",result.fresh);
  showText("stat-drafts",result.drafts);
  showText("fleet-registered",result.nodes?.registered??"–");
  showText("fleet-applied",result.nodes?.local_attested??"–");
  showText("fleet-correlated",result.nodes?.dns_correlated??"–");
  showText("fleet-pending",result.nodes?.needs_verification??"–");
  const fleetAlert=$("fleet-alert");
  fleetAlert.hidden=!result.nodes_error;
  fleetAlert.textContent=result.nodes_error?
    "노드 등록정보 또는 상태 보고를 검증하지 못했습니다. 노드 상태는 미확인입니다.":"";

  showText("overview-eligible",result.eligible);
  showText("overview-next-expiry",fmt(result.next_expiry));
  showText("nav-review-count",result.candidates);
  showText("overview-verified",result.evidence_missing?"검증 파일 미등록":fmt(result.verified_at));
  showText("overview-deploy-state",deployLabel(result.deployment));
  const deployment=result.deployment;
  showText("overview-deploy-detail",deployDescription(deployment));
  const dot=$("overview-deploy-dot");
  dot.classList.toggle("verified",deployment.state==="SIGNED_FILE_VERIFIED");
  dot.classList.toggle("error",deployment.state==="VERIFICATION_FAILED");
  const missing=result.evidence_missing;
  const evidenceError=result.evidence_error===true;
  const valid=result.fresh;
  const due=result.next_expiry?new Date(result.next_expiry).getTime()-new Date(result.observed_at).getTime():Infinity;
  const health=$("evidence-health");
  health.hidden=!evidenceError&&!missing&&valid>0&&due>120000;
  if(evidenceError){
    showText("evidence-health-title","검토 증거를 읽거나 검증할 수 없습니다.");
    showText("evidence-health-note","검토 파일·증거의 무결성과 권한을 확인하세요. DNS 노드 상태는 별도로 조회됩니다.");
  }else if(missing){
    showText("evidence-health-title","검증된 위협정보가 등록되지 않았습니다.");
    showText("evidence-health-note","수집 시스템에서 검증한 verified.json을 리뷰어 전용 작업 공간으로 안전하게 전달해야 합니다.");
  }else if(valid===0){
    showText("evidence-health-title","현재 유효한 위협 증거가 없습니다.");
    showText("evidence-health-note","지난 검토 기록은 남아 있지만 정책 생성에 사용할 최신 증거가 없습니다. 새 검증 결과가 필요합니다.");
  }else if(due<=120000){
    showText("evidence-health-title","위협 증거 만료가 임박했습니다.");
    showText("evidence-health-note","승인·초안 생성·서명까지 처리하기 전에 증거와 유효기간을 다시 확인하세요.");
  }
  const strip=document.querySelector(".verification-strip");
  strip.dataset.state=missing||valid===0||evidenceError||result.nodes_error||
                       result.drafts_error||deployment.state!=="SIGNED_FILE_VERIFIED"?"warning":"normal";
  if(evidenceError||result.nodes_error||deployment.state==="VERIFICATION_FAILED")
    strip.dataset.state="error";
  const notice=evidenceError?"증거 검증 실패":
    result.nodes_error?"노드 상태 검증 불가":
    deployment.state==="VERIFICATION_FAILED"?"게시 서명 검증 실패":
    deployment.state==="PUBLICATION_EXPIRED"?"서명 게시 만료 · DNS 미검증":
    missing?"증거 미등록":
    valid===0?"유효 증거 없음":
    valid+"건 증거 유효 · 노드별 보고 별도 확인";
  showText("verification-status",notice);
}

const intelStates={
  IDLE:"대기 중",RUNNING:"OpenPhish·GSB 검증 실행 중",
  SUCCESS:"최근 수동 갱신 성공",ERROR:"최근 수동 갱신 실패",
  INTERRUPTED:"갱신 작업 중단",NOT_CONFIGURED:"OpenPhish·GSB 연동 미설정",EXPIRED:"검증 결과 만료",
  UNAVAILABLE:"수집 서비스 연결 불가"
};
async function loadIntelStatus() {
  const epoch=++intelStatusEpoch, session=sessionEpoch;
  let status;
  try {status=await api("/api/intel");}
  catch(error){
    if(epoch===intelStatusEpoch && session===sessionEpoch){
      intelLatest=null;intelReviewRevision=null;
      $("intel-import").disabled=true;$("intel-refresh").disabled=true;
      showText("intel-state","조회 실패 · 미확인");
      showText("intel-note","오래된 수집 정보로 가져오기를 진행하지 않습니다. 상태를 다시 조회하세요.");
    }
    throw error;
  }
  if(epoch!==intelStatusEpoch || session!==sessionEpoch || currentView!=="reviews") return;
  const refreshPanel=document.querySelector(".intel-refresh-panel");

  if(refreshPanel){refreshPanel.hidden=false;refreshPanel.dataset.status=status.state||"UNAVAILABLE";}
  intelLatest=status.latest||null;
  intelReviewRevision=status.review_revision||null;
  intelContextRevision=status.context_revision||null;
  showText("intel-state",intelStates[status.state]||status.state||"확인 불가");
  showText("intel-checked",fmt(intelLatest?.checked_at));
  showText("intel-counts",intelLatest?
    intelLatest.verified+"건 / "+intelLatest.review_proposals+"건":"–");
  showText("intel-run",intelLatest?.run||"–");
  const importable=!!(intelLatest?.run && intelLatest?.fingerprint && intelReviewRevision && intelContextRevision &&
    status.state!=="UNAVAILABLE" && status.state!=="NOT_CONFIGURED");
  $("intel-import").disabled=!importable;
  $("intel-refresh").disabled=status.state==="UNAVAILABLE"||status.state==="NOT_CONFIGURED"||
                              status.state==="RUNNING"||status.cooldown_seconds>0;
  let note="";
  if(status.state==="NOT_CONFIGURED")note="클라우드에서 수집하려면 GSB API 키·허가된 OpenPhish 이용 권한이 필요합니다. 수동 FQDN은 정책 초안 메뉴에서 등록할 수 있습니다." ;
  else if(status.state==="UNAVAILABLE")note="수집 서비스 소켓·systemd 상태를 확인하세요.";
  else if(status.state==="RUNNING")note="위협정보 다운로드와 Google 검증을 진행 중입니다. 완료될 때까지 기존 증거와 승인을 유지합니다.";
  else if(status.state==="ERROR")note="최근 갱신 실패. 기존 검증·승인 데이터는 유지됐습니다. 수집기 journal에서 원인을 확인하세요.";
  else if(status.state==="INTERRUPTED")note="수집기가 재시작되어 마지막 요청이 중단됐습니다. 기존 데이터를 유지합니다.";
  else note="새 검증 자료를 가져오면 이전 승인 기록은 비공개 보관 후 초기화됩니다. 초안·게시 정책은 바뀌지 않습니다.";
  if(status.cooldown_seconds>0)note+=" 다음 수동 요청 가능 시간까지 약 "+Math.ceil(status.cooldown_seconds/60)+"분.";
  if(intelLatest && intelLatest.unassigned_expressions>0)
    note+=" Google 검색 결과에 특정 URL과 정확히 연결되지 않은 표현식 "+
      intelLatest.unassigned_expressions+"건이 포함됐으며, 자동 승인되지 않습니다.";
  showText("intel-note",note);
}

function renderReviews() {
  if(!reviewData) return;
  const list=$("review-list");
  list.replaceChildren();
  const q=$("review-search").value.trim().toLowerCase();
  const filter=$("review-filter").value;
  const items=reviewData.items.filter((item)=>{
    if(q&&!item.domain.toLowerCase().includes(q)) return false;
    if(filter==="pending"&&item.approved) return false;
    if(filter==="approved"&&!item.approved) return false;
    if(filter==="expired"&&item.fresh) return false;
    return true;
  });
  showText("review-visible",items.length);
  showText("review-pending",reviewData.items.filter(x=>!x.approved).length);
  showText("review-active-approved",reviewData.items.filter(x=>x.approved&&x.eligible).length);
  showText("review-limited",reviewData.items.filter(x=>!x.eligible).length);
  if(reviewData.missing) {list.append(empty("검증 파일이 없습니다. 검토자 전용 workspace/verified.json에 최신 검증 결과를 안전하게 복사하세요."));return;}
  if(!items.length) {list.append(empty("조건에 맞는 검토 후보가 없습니다."));return;}
  items.forEach((item)=>{
    const row=node("button","review-item"+(selectedReview&&selectedReview.id===item.id?" selected":""));
    row.type="button";
    const left=node("div","");
    left.append(node("strong","",item.domain),node("small","",item.threat_types.join(" · ")||"위협 유형 미확인"));
    const right=node("div","review-badges");
    right.append(pill(item.approved?"승인 기록":"미승인",item.approved?"good":""),
                 pill(item.eligible?"검토 가능":item.eligibility_reason==="SHARED_HOSTING_BOUNDARY"?"범위 제한":"만료·제한",
                      item.eligible?"good":"warn"));
    row.append(left,right);
    row.addEventListener("click",()=>selectReview(item.id));
    list.append(row);
  });
}
function selectReview(id) {
  const item=reviewData&&reviewData.items.find((x)=>x.id===id);
  if(!item)return;
  selectedReview=item;
  $("review-form").hidden=false;
  $("review-empty").hidden=true;
  showText("review-domain",item.domain);
  showText("review-threat",item.threat_types.join(" / "));
  showText("review-expires",fmt(item.valid_until));
  showText("review-ref",item.url_sha256.slice(0,20)+"…");
  showText("review-source",item.source);
  $("reviewer").value=item.reviewer;
  $("reason").value=item.reason;
  $("approve").checked=item.approved;
  $("ack-subtree").checked=item.acknowledge_subtree;
  $("approve").disabled=!item.eligible&&!item.approved;
  const reason={
    REVIEWABLE:"증거가 유효합니다. SUBTREE 차단 범위와 오탐 위험을 직접 검토한 뒤 승인할 수 있습니다.",
    EVIDENCE_EXPIRED:"증거 유효기간이 지났습니다. 승인하려면 다시 수집·검증해야 합니다.",
    EVIDENCE_TOO_OLD:"조회 근거가 오래되었습니다. 재검증된 증거가 필요합니다.",
    EVIDENCE_FROM_FUTURE:"증거 시각이 서버보다 미래입니다. 시계·수집 경로를 확인하세요.",
    SHARED_HOSTING_BOUNDARY:"공유 호스팅·고영향 도메인입니다. 이 도구에서는 SUBTREE 차단 승인을 허용하지 않습니다."
  };
  const note=$("review-eligibility");
  note.textContent=reason[item.eligibility_reason]||"증거가 유효하지 않습니다.";
  note.dataset.state=item.eligible?"normal":item.eligibility_reason==="SHARED_HOSTING_BOUNDARY"?"error":"warning";
  renderReviews();
}
async function loadReviews() {
  const stillCurrent=currentRequest("reviews");
  let next;
  try {next=await api("/api/reviews");}
  catch(error) {
    if(stillCurrent()){
      reviewData=null; selectedReview=null;
      $("review-form").hidden=true;
      $("review-empty").hidden=false;
      $("review-list").replaceChildren(empty(
        "검토 파일과 최신 증거가 일치하지 않거나 읽을 수 없습니다. 자료를 확인한 뒤 ‘검토 기록 초기화’를 실행하세요."));
    }
    throw error;
  }
  if(!stillCurrent()) return;
  reviewData=next;
  showText("verification-status",next.missing?"검토 근거 미등록":next.items.length+"건 검토 항목 · "+next.items.filter(x=>x.fresh).length+"건 유효");
  showText("nav-review-count",reviewData.items.length);
  if(selectedReview) {
    const still=reviewData.items.find((x)=>x.id===selectedReview.id);
    if(still && still.revision===selectedReview.revision) selectedReview=still;
    else {
      if(still) toast("검토 기록이 다른 탭에서 변경되었습니다. 다시 선택해 확인하세요.",true);
      selectedReview=null;
      $("review-form").hidden=true;
      $("review-empty").hidden=false;
    }
  }
  renderReviews();
}
async function loadEngine() {
  const stillCurrent=currentRequest("engine");
  const result=await api("/api/engine");
  if(!stillCurrent()) return;
  const conf=result.config;
  showText("verification-status","위험도 제안 설정 · DNS 미변경");
  showText("engine-configured",result.configured?"구성 저장됨":"미설정");
  $("engine-version").value=conf?conf.policy_version:"v0.8-operator";
  $("engine-threshold").value=conf?conf.warn_threshold:70;
  $("engine-admin").value=conf?conf.admin_blocked_domains.join("\n"):"";
  $("engine-approved").value=conf?conf.approved_malicious_domains.join("\n"):"";
  $("engine-official").value=conf?conf.official_domains.join("\n"):"";
  $("engine-sources").value=conf?conf.score_sources.join("\n"):"lab-scanner";
}
const lines = (id) => $(id).value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
function updateBuildAvailability(){
  const state=buildReviewContext;
  const ready=state&&!state.blocked&&
    (!state.expired.length||$("confirm-expired-exclusion").checked)&&
    (state.ruleCount>0||$("confirm-empty-replacement").checked);
  $("build-form").querySelector('button[type="submit"]').disabled=!ready;
}
$("confirm-expired-exclusion").addEventListener("change",updateBuildAvailability);
$("confirm-empty-replacement").addEventListener("change",updateBuildAvailability);
async function loadDrafts() {
  const stillCurrent=currentRequest("drafts");
  buildReviewContext=null;
  $("confirm-expired-exclusion").checked=false;
  $("confirm-empty-replacement").checked=false;
  $("build-form").querySelector('button[type="submit"]').disabled=true;
  const [drafts,reviewResult,manualResult]=await Promise.allSettled([api("/api/drafts"),api("/api/reviews"),api("/api/manual")]);
  if(!stillCurrent()) return;
  if(drafts.status!=="fulfilled")throw drafts.reason;
  if(manualResult.status!=="fulfilled")throw manualResult.reason;
  if(reviewResult.status!=="fulfilled")throw reviewResult.reason;
  const items=drafts.value,reviewed=reviewResult.value;
  manualData=manualResult.value;manualDefaultDate();renderManual();
  const ready=reviewed?.items.filter(x=>x.approved&&x.eligible).length||0;
  const local=manualData.entries.filter(x=>!x.expired&&!x.unsafe_boundary).length;
  const expired=reviewed.items.filter(x=>x.approved&&["EVIDENCE_EXPIRED","EVIDENCE_TOO_OLD"].includes(x.eligibility_reason));
  const blocked=manualData.entries.some(x=>!x.expired&&x.unsafe_boundary)||
    reviewed.items.some(x=>x.approved&&!x.eligible&&!expired.includes(x));
  $("build-expired-section").hidden=!expired.length;
  $("confirm-expired-exclusion").required=!!expired.length;
  $("build-expired-list").replaceChildren(...expired.map(x=>node("li","",x.domain+" · 검증 "+fmt(x.checked_at)+" · 만료 "+fmt(x.valid_until)+" · "+x.id.slice(0,12))));
  $("build-empty-section").hidden=!!(ready+local)||blocked;
  $("confirm-empty-replacement").required=!(ready+local)&&!blocked;
  buildReviewContext={fingerprint:reviewed?.fingerprint||null,
    review_set_revision:reviewed?.review_set_revision||"NOT_PRESENT",
    manual_revision:manualData.revision,expired,blocked,ruleCount:ready+local};
  showText("build-review-summary","외부 검증 승인 "+ready+"건 + 수동 FQDN "+local+"건 · 전체 교체 스냅샷");
  if(blocked)showText("build-review-summary","공용 접미사·보호 경계 또는 유효하지 않은 승인 기록을 먼저 검토/해제하세요. 초안 생성은 차단됩니다.");
  updateBuildAvailability();
  showText("verification-status",items.length+"개 미서명 초안 · 독립 서명 필요");
  showText("draft-count",items.length);
  const list=$("draft-list");
  list.replaceChildren();
  if(!items.length){list.append(empty("생성된 초안이 없습니다. 검토를 완료한 후 정책을 생성하세요."));return;}
  items.forEach((item)=>{
    const wrapper=node("div","draft-item");
    const heading=node("strong","",item.name);
    const meta=node("div","draft-meta",item.rules+"개 규칙 · 만료 "+fmt(item.expires_at));
    const actions=node("div","draft-actions");
    actions.append(pill(item.expired?"만료됨":"미서명",item.expired?"bad":"warn"));
    const download=node("button","text-button","JSON 다운로드 ↓");
    download.type="button";
    download.addEventListener("click",()=>downloadDraft(item.name).catch(displayError));
    actions.append(download);
    const preview=node("button","text-button","변경 영향 확인 ↗");
    preview.type="button";
    preview.addEventListener("click",()=>previewDraft(item.name).catch(displayError));
    actions.append(preview);
    wrapper.append(heading,meta,actions);
    list.append(wrapper);
  });
}
async function previewDraft(name) {
  const impact=await api("/api/drafts/"+encodeURIComponent(name)+"/impact");
  if(currentView!=="drafts") return;
  const el=$("draft-impact");
  el.hidden=false;
  el.replaceChildren();
  const heading=node("h3","",name+" · 교체 영향 미리보기");
  el.append(heading);
  if(!impact.comparison_available){
    el.append(node("p","muted-copy","검증된 게시 기준선이 없습니다. 기존 정책 철회 여부는 확인할 수 없습니다."));
    return;
  }
  el.append(node("p","muted-copy",
    "서명된 로컬 게시 파일의 시퀀스 "+impact.baseline_sequence+"와 비교했습니다. 실제 DNS 적용과는 별개입니다."));
  const body=node("div","impact-metrics");
  for(const [label,count,state] of [
    ["신규 차단",impact.added_count,"normal"],
    ["차단 철회",impact.withdrawn_count,impact.withdrawn_count>0?"warning":"normal"],
    ["유효기간 단축",impact.shortened_count,impact.shortened_count>0?"warning":"normal"]]){
    const metric=node("div","impact-metric");
    metric.dataset.state=state;
    metric.append(node("span","",label),node("strong","",count));
    body.append(metric);
  }
  el.append(body);
  if(impact.requires_withdrawal_ack){
    el.append(node("p","impact-warning",
      "주의: 기존 차단 철회 또는 수명 단축이 예상됩니다. 독립 서명·발행 전에 영향 검토와 --ack-withdrawals 동의가 필요합니다."));
  }
  for(const [label,list] of [["신규 차단",impact.added_sample],["차단 철회",impact.withdrawn_sample],["유효기간 단축",impact.shortened_sample]]){
    if(list.length)el.append(node("p","impact-sample",label+" (최대 20건): "+list.join(", ")));
  }
}
async function downloadDraft(name) {
  if(!token || expireIdleSession())throw staleRequest();
  const activeToken=token, epoch=sessionEpoch;
  const response=await fetch("/api/drafts/"+encodeURIComponent(name)+"/download",{
    headers:{"Authorization":"Bearer "+activeToken},cache:"no-store",credentials:"omit",mode:"same-origin"
  });
  if(!token || token!==activeToken || sessionEpoch!==epoch) throw staleRequest();
  if(!response.ok){let data={};try{data=await response.json();}catch(_){}throw Error(data.error||"초안 다운로드 실패");}
  const blob=await response.blob();
  if(!token || token!==activeToken || sessionEpoch!==epoch) throw staleRequest();
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");
  link.href=url;link.download=name;document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
  toast("정책 초안을 다운로드했습니다. 독립 서명자 검토가 필요합니다.");
}
function renderPublished() {
  const list=$("published-list");
  list.replaceChildren();
  const query=$("published-search").value.trim().toLowerCase();
  const filtered=publishedRules.filter(r=>r.domain.toLowerCase().includes(query));
  showText("published-count",filtered.length+" / "+publishedRules.length);
  if(!filtered.length){list.append(empty("서명 검증된 게시 규칙이 없거나 검색 결과가 없습니다."));return;}
  filtered.slice(0,200).forEach((rule)=>{
    const row=node("div","published-row");
    row.append(node("strong","",rule.domain),
               pill(rule.decision,rule.decision==="BLOCK"?"bad":""),
               node("span","",fmt(rule.expires_at)));
    list.append(row);
  });
  if(filtered.length>200)list.append(empty("첫 200건을 표시 중입니다. 검색어를 좁혀주세요."));
}

const nodeStates={
  NO_REPORT:["보고 없음","warn"],
  STALE:["최근 상태 보고 만료","warn"],
  CLOCK_SKEW:["노드/서버 시각 오차 확인 필요","bad"],
  INVALID_REPORT:["보고 서명/구조 검증 실패","bad"],
  REKEY_PENDING:["장치 키 교체 후 새 보고 대기","warn"],
  DNS_ATTESTATION_FAILED:["노드 적용 검증 실패","bad"],
  NO_POLICY:["수락된 정책 없음","warn"],
  LOCAL_DNS_PROBE_FAILED:["로컬 DNS 응답 검사 실패","bad"],
  LOCAL_DNS_VERIFIED:["로컬 정책·DNS 응답·상위 DNS 양성 기준 일치","good"],
  LOCAL_DNS_UNCORROBORATED:["로컬 DNS 응답 관측 · 양성 기준 미설정","warn"],
  LOCAL_DNS_REFERENCE_UNVERIFIED:["상위 DNS 양성 기준 확인 실패","warn"],
  LOCAL_POLICY_ATTESTED:["로컬 정책 적용 검증됨","good"],
  POLICY_MISMATCH:["게시 정책과 노드 정책 불일치","bad"],
  POLICY_EXPIRED:["적용 기록은 만료된 게시물과 일치","warn"],
  PUBLISHER_UNVERIFIED:["게시 기준선 검증 불가","warn"]
};
function edgeApplyCopy(nodes, deployment) {
  if(!Array.isArray(nodes)) return ["적용 상태 확인 불가","장치 보고 조회가 실패했습니다. 이전 성공 상태를 현재 상태로 사용하지 않습니다."];
  const selected=nodes.find(item=>item.device_id===deployment.device);
  if(!selected) return ["선택 장치의 등록 정보 없음","해당 게시 대상의 장치를 등록해야 인증된 보고와 비교할 수 있습니다."];
  if(selected.state==="LOCAL_DNS_VERIFIED")return ["선택 노드 · DNS 응답 확인","선택한 장치의 정책 신원과 로컬 응답 및 독립 상위 DNS 양성 기준이 일치합니다. LAN 전체 보호는 별도입니다."];
  if(selected.state==="NO_REPORT")return ["선택 노드 · 보고 없음","장치는 등록됐지만 유효한 상태 보고가 아직 도착하지 않았습니다."];
  if(selected.state==="POLICY_EXPIRED" || deployment.state==="PUBLICATION_EXPIRED")return ["선택 노드 · 게시 만료","서명 신원이 맞더라도 유효기간이 지난 규칙은 현재 보호로 표시하지 않습니다."];
  return ["선택 노드 · "+(nodeStates[selected.state]?.[0]||"미확인"),"정책 버전, 보고 시각, 로컬 응답과 비교 기준을 아래 장치별 근거에서 확인하세요."];
}
function renderNodes(items) {
  if(!nodesReadValid)return;
  lastNodeItems=Array.isArray(items)?items:[];
  lastNodeRender=nodeRenderIdentity(lastNodeItems);
  const query=$("node-search").value.trim().toLowerCase();
  const filter=$("node-state-filter").value;
  items=lastNodeItems.filter(item=>[item.label,item.device_id,item.dns_address].join(" ").toLowerCase().includes(query) &&
    (filter==="all"||filter==="attention"&&item.state!=="LOCAL_DNS_VERIFIED"||filter==="verified"&&item.state==="LOCAL_DNS_VERIFIED"));
  showText("node-visible-count",items.length+" / "+lastNodeItems.length+"개");
  const list=$("nodes-list");
  list.replaceChildren();
  if(!Array.isArray(items)||!items.length){
    list.append(empty(lastNodeItems.length?"검색·상태 필터와 일치하는 노드가 없습니다.":"등록된 DNS 노드가 없습니다. 별도 공개키를 신뢰 디렉터리에 배치한 후 장치를 등록하세요."));
    return;
  }
  items.forEach(item=>{
    const article=node("article","node-card");
    const heading=node("div","node-head");
    const left=node("div","");
    left.append(node("strong","",item.label),node("small","mono",item.device_id+" · "+item.dns_address+":53"));
    const [title,kind]=nodeStates[item.state]||["미확인","warn"];
    article.dataset.tone=kind;
    heading.append(left,pill(title,kind));
    article.append(heading);
    const facts=node("div","node-facts");
    for(const [label,value] of [
      ["마지막 수신",fmt(item.received_at)],["노드 시퀀스",item.policy_sequence??"–"],
      ["게시 시퀀스",item.published_sequence??"–"],
      ["DNS 적용 확인",item.dns_applied===true?"노드 내부 확인":item.dns_applied===false?"불일치":"미확인"],
      ["로컬 UDP",item.probe?.udp===true?"NXDOMAIN 관측":item.probe?.udp===false?"응답 불일치":"미실시"],
      ["로컬 TCP",item.probe?.tcp===true?"NXDOMAIN 관측":item.probe?.tcp===false?"응답 불일치":"미실시"],
      ["상위 DNS 양성 기준",item.probe?.baseline===true?"UDP/TCP A 응답 확인":item.probe?.baseline===false?"양성 응답 미확인":"검증 미설정/구형 보고"]
    ]){
      const field=node("div","");
      field.append(node("span","",label),node("strong","",value));
      facts.append(field);
    }
    article.append(facts);
    if(item.policy_sha256){
      article.append(node("div","node-hash mono","노드 SHA-256 "+item.policy_sha256.slice(0,32)+"…"));
    }
    const footer=node("div","node-footer");
    footer.append(node("span","",item.lan_verified?"LAN 검증됨":"LAN 클라이언트 미검증"));
    const remove=node("button","text-button","등록 해제");
    remove.type="button";
    remove.disabled=deploymentReadPending;
    remove.addEventListener("click",async()=>{
      if(!nodesReadValid||deploymentReadPending)return;
      if(!await confirmOperation({title:"DNS 노드 등록 해제",description:"이 장치의 상태 보고 신뢰를 해제합니다. DNS 데몬이나 정책 파일을 원격으로 삭제하지 않습니다. 같은 장치 키는 재등록할 수 없습니다.",phrase:"UNREGISTER_NODE",facts:[["장치",item.device_id],["사설 IP",item.dns_address],["현재 공개키",item.key_id]],action:"등록 해제"}))return;
      try{
        if(!nodesReadValid||deploymentReadPending||!lastNodeItems.some(current=>current.device_id===item.device_id&&current.key_id===item.key_id))throw Error("장치 상태를 다시 조회한 뒤 실행하세요.");
        await api("/api/nodes/unregister",{device_id:item.device_id,confirm:"UNREGISTER_NODE",expected_key_id:item.key_id});
        toast("노드 등록이 해제되었습니다. 과거 보고 기록은 보존됩니다.");
        await loadDeployment();
      }catch(e){displayError(e);}
    });
    footer.append(remove);
    article.append(footer);
    list.append(article);
  });
}
function nodeRenderIdentity(items) {
  return JSON.stringify([items,$("node-search").value,$("node-state-filter").value]);
}
function setReadError(id,message) {
  const el=$(id);el.textContent=message||"";el.hidden=!message;
}
function renderDeploymentTargets(items, publication, requested) {
  const select=$("deployment-device-select");
  const choices=new Map();
  if(defaultDeploymentDevice)choices.set(defaultDeploymentDevice,defaultDeploymentDevice+" · 기본 게시 대상");
  if(publication?.device)choices.set(publication.device,publication.device+" · 게시 대상");
  if(requested&&!choices.has(requested))choices.set(requested,requested+" · 선택 대상");
  for(const item of items||[])choices.set(item.device_id,item.label+" · "+item.device_id);
  const options=JSON.stringify([...choices]);
  if(select.dataset.options!==options){
    select.replaceChildren();
    if(!choices.size)select.append(new Option("기본 게시 대상",""));
    for(const [value,label] of choices)select.append(new Option(label,value));
    select.dataset.options=options;
  }
  select.value=selectedDeploymentDevice;
}
function clearSelectedPublication() {
  publishedRules=[];$("published-list").replaceChildren();showText("published-count","–");
  for(const id of ["deployment-device","deployment-sequence","deployment-hash","deployment-blocks","deployment-expires","deployment-key"])
    showText(id,null);
  showText("deployment-state","게시 정책 확인 중");
  showText("deployment-message","현재 서명·유효기간과 정책 신원을 다시 확인합니다.");
  showText("published-note","조회 중 · 이전 규칙을 현재 정책으로 표시하지 않습니다.");
}
async function loadDeployment() {
  const stillCurrent=currentRequest("deployment"),requested=selectedDeploymentDevice;
  const panel=document.querySelector('[data-panel="deployment"]');
  const previous=deploymentSnapshot?.session===sessionEpoch && deploymentSnapshot.target===requested?deploymentSnapshot:null;
  deploymentReadPending=true;
  panel.setAttribute("aria-busy","true");
  panel.dataset.readState=previous?"refreshing":"loading";
  setReadError("publication-read-error",null);setReadError("nodes-read-error",null);
  nodesReadValid=false;
  if(!previous){
    deploymentSnapshot=null;
    clearSelectedPublication();lastNodeItems=[];lastNodeRender=null;$("nodes-list").replaceChildren(empty("서명된 장치 보고를 확인 중입니다."));
    showText("node-visible-count","–");showText("fleet-read-summary","장치 보고 확인 중");
    showText("edge-apply-state","선택 장치 확인 중");showText("edge-apply-note","선택 대상의 현재 상태를 확인합니다.");
    for(const id of ["edge-read-node","edge-read-received","edge-read-policy","edge-read-dns"])showText(id,null);
  }
  $("nodes-list").querySelectorAll("button").forEach(button=>{button.disabled=true;});
  showText("deployment-observed",previous?"갱신 중 · 마지막 조회 "+previous.observed:"조회 중");
  showText("verification-status",previous?"갱신 중 · 아래는 마지막 조회 결과이며 현재 상태를 재확인합니다.":"선택한 장치 상태 조회 중");
  const [publication,reports]=await Promise.allSettled([
    api("/api/deployment"+(requested?"/"+encodeURIComponent(requested):"")),api("/api/nodes")]);
  if(!stillCurrent() || requested!==selectedDeploymentDevice)return;
  deploymentReadPending=false;
  panel.removeAttribute("aria-busy");
  const data=publication.status==="fulfilled"?publication.value:null;
  const nodes=reports.status==="fulfilled"?reports.value:null;
  if(data){
    if(!defaultDeploymentDevice&&!requested)defaultDeploymentDevice=data.device||"";
    selectedDeploymentDevice=requested||data.device||"";
    publishedRules=Array.isArray(data.rules)?data.rules:[];
    if(!previous||previous.publication!==JSON.stringify(publishedRules))renderPublished();
    showText("deployment-state",deployLabel(data));showText("deployment-message",deployDescription(data));
    showText("deployment-device",data.device||requested);showText("deployment-sequence",data.sequence);
    showText("deployment-hash",data.policy_sha256||null);showText("deployment-blocks",data.active_blocks);
    showText("deployment-expires",fmt(data.expires_at));showText("deployment-key",data.key_id||null);
    showText("published-note",data.state==="PUBLICATION_EXPIRED"?
      "유효기간이 지난 서명 게시물입니다. 아래는 이력이며 현재 차단 목록이 아닙니다.":
      "선택 대상의 서명된 게시 파일 · DNS 적용 보고는 별도 검증합니다.");
  }else{
    clearSelectedPublication();
    showText("deployment-state","게시 정책 확인 불가");showText("deployment-message","조회 실패. 파일이 없거나 규칙이 0개라는 의미가 아닙니다.");
    showText("published-note","현재 게시 규칙을 확인할 수 없습니다. 다시 조회하세요.");
    $("published-list").replaceChildren(empty("게시 근거 미확인 · 조회를 다시 시도하세요."));
    setReadError("publication-read-error","게시 정책을 조회하지 못했습니다. 장치 보고는 독립적으로 표시됩니다.");
  }
  renderDeploymentTargets(nodes,data,requested);
  if(nodes){
    nodesReadValid=true;
    if(!previous||lastNodeRender!==nodeRenderIdentity(nodes))renderNodes(nodes);
    $("nodes-list").querySelectorAll("button").forEach(button=>{button.disabled=false;});
    const good=nodes.filter(x=>x.state==="LOCAL_DNS_VERIFIED").length;
    showText("fleet-read-summary",good+" / "+nodes.length+"개 DNS 응답 검증");
    const selected=nodes.find(x=>x.device_id===selectedDeploymentDevice);
    showText("edge-read-node",selected?.label||selectedDeploymentDevice||null);
    showText("edge-read-received",fmt(selected?.received_at));
    showText("edge-read-policy",selected?.dns_applied===true?"게시 정책과 일치":selected?.dns_applied===false?"게시 정책과 불일치":"미확인");
    showText("edge-read-dns",selected?nodeStates[selected.state]?.[0]||"미확인":"등록 정보 없음");
  }else{
    lastNodeItems=[];lastNodeRender=null;$("nodes-list").replaceChildren(empty("현재 장치 보고를 확인할 수 없습니다. 이전 정상 상태를 숨겼습니다."));
    showText("fleet-read-summary","장치 보고 미확인");showText("node-visible-count","–");
    for(const id of ["edge-read-node","edge-read-received","edge-read-policy","edge-read-dns"])showText(id,null);
    setReadError("nodes-read-error","노드 상태 조회 실패 · 게시 정책은 별도로 검증합니다. 장치 상태를 다시 조회하세요.");
  }
  const [title,note]=edgeApplyCopy(nodes,data?{...data,device:data.device||selectedDeploymentDevice}:{device:selectedDeploymentDevice,state:"UNAVAILABLE"});
  showText("edge-apply-state",title);showText("edge-apply-note",note);
  // Never report the selected publication as corroborated if the two independent
  // reads crossed a publication change. The next read can resolve the mismatch.
  const selected=nodes?.find(x=>x.device_id===selectedDeploymentDevice);
  if(data && selected && (selected.published_sequence!==data.sequence || selected.published_sha256!==data.policy_sha256)){
    showText("edge-apply-state","선택 노드 · 비교 기준 재확인");
    showText("edge-apply-note","두 조회 사이 게시 상태가 달라졌거나 검증 가능한 게시물이 없습니다. 다시 조회해 같은 기준선에서 비교하세요.");
    showText("edge-read-policy","비교 기준 미일치");
  }
  const partial=!data||!nodes;
  const observed=new Date().toLocaleTimeString("ko-KR");
  // Remember only successful identities. A confirmed failed read is cleared,
  // not retained as a stale green success; the other domain remains independent.
  deploymentSnapshot={session:sessionEpoch,target:selectedDeploymentDevice,observed,
    publication:data?JSON.stringify(publishedRules):null};
  showText("deployment-observed",(partial?"일부 확인 불가 · ":"조회 완료 · ")+observed);
  showText("verification-status",partial?"부분 조회 실패 · 미확인 항목 확인 필요":deployLabel(data)+" · "+$("fleet-read-summary").textContent);
  document.querySelector(".verification-strip").dataset.state=partial?"error":"normal";
  panel.dataset.readState=partial?"partial":"ready";
  return {partial};
}
async function loadAudit() {
  const stillCurrent=currentRequest("audit");
  const events=await api("/api/audit");
  if(!stillCurrent()) return;
  showText("verification-status","로컬 작업 기록 · 변조 방지 감사 증명 아님");
  const list=$("audit-list");
  list.replaceChildren();
  if(!events.length){list.append(empty("이 콘솔에서 기록한 작업이 아직 없습니다."));return;}
  events.slice().reverse().forEach((item)=>{
    const row=node("div","audit-entry");
    row.append(node("span","",fmt(item.at)),
               node("strong","",item.event),
               node("span","mono",item.draft||item.reference||item.version||item.fingerprint||"–"));
    list.append(row);
  });
}
$("login-form").addEventListener("submit",async(e)=>{
  e.preventDefault();
  const submitted=$("token").value.trim();
  if(!submitted) return;
  // Invalidate pending attempts before assigning a different credential.
  sessionEpoch++;
  token=submitted;
  const attempt=sessionEpoch;
  try {
    await api("/api/deployment");
    if(sessionEpoch!==attempt || token!==submitted) return;
    $("token").value="";
    unlock();
  } catch(err) {
    if(sessionEpoch!==attempt || token!==submitted) return;
    lock();
    displayError(err);
  }
});
$("logout-button").addEventListener("click",lock);
$("refresh-button").addEventListener("click",()=>{if(token)refreshView(currentView).then(result=>{if(token&&!result?.partial)toast("최신 상태를 조회했습니다.");}).catch(displayError);});
document.querySelectorAll("[data-view]").forEach((el)=>el.addEventListener("click",()=>navigateTo(el.dataset.view)));
document.querySelectorAll("[data-go]").forEach((el)=>el.addEventListener("click",()=>navigateTo(el.dataset.go)));

$("intel-status-reload").addEventListener("click",()=>loadIntelStatus().catch(displayError));
bindAsyncForm("intel-refresh-form",async(event)=>{
  event.preventDefault();
  const button=$("intel-refresh");
  button.disabled=true;
  try {
    const result=await api("/api/intel/refresh",{
      accept_openphish_terms:$("intel-terms").checked,
      ack_url_disclosure:$("intel-disclosure").checked,
      ack_noncommercial:$("intel-noncommercial").checked
    });
    $("intel-refresh-form").reset();
    if(result.accepted)toast(result.state==="SUCCESS"?"OpenPhish·GSB 검증 완료. 확인 후 가져오세요.":"위협정보 검증 요청됨. 정책은 자동 변경되지 않습니다.");
    else if(result.state==="RUNNING")toast("수집기가 이미 검증을 진행하고 있습니다.");
    else toast("요청 간격 제한 중입니다. "+Math.ceil((result.retry_after_seconds||0)/60)+"분 뒤 다시 요청하세요.",true);
    await loadIntelStatus();
  }catch(error){displayError(error);}
  finally{if(token && currentView==="reviews")loadIntelStatus().catch(displayError);}
});
$("intel-import").addEventListener("click",async()=>{
  const latest=intelLatest, revision=intelReviewRevision, context=intelContextRevision;
  if(!latest||!revision||!context)return;
  if(!await confirmOperation({title:"새 검증 자료 가져오기",description:"기존 검토 기록은 비공개 보관하고 새 항목은 미승인으로 시작합니다. 초안·게시 정책과 DNS는 그대로 유지합니다.",phrase:"IMPORT_VERIFIED",facts:[["수집 Run",latest.run],["검증 URL",latest.verified],["검토 후보",latest.review_proposals]],action:"자료 가져오기"}))return;
  const button=$("intel-import");
  button.disabled=true;
  try{
    const answer=await api("/api/intel/import",{
      run:latest.run,fingerprint:latest.fingerprint,
      review_revision:revision,context_revision:context,confirm:"IMPORT_VERIFIED"
    });
    selectedReview=null;
    reviewData=null;
    $("review-form").hidden=true;
    $("review-empty").hidden=false;
    await Promise.all([loadReviews(),loadIntelStatus()]);
    toast(answer.already_current?"이미 같은 검증 자료를 사용하고 있습니다.":
      "새 검증 근거 "+answer.verified+"건을 가져왔습니다. 모든 승인 항목을 다시 검토해야 합니다.");
  }catch(error){displayError(error);}
  finally{if(token && currentView==="reviews")loadIntelStatus().catch(displayError);}
});
$("node-search").addEventListener("input",()=>renderNodes(lastNodeItems));
$("node-state-filter").addEventListener("change",()=>renderNodes(lastNodeItems));
$("review-search").addEventListener("input",renderReviews);
$("published-search").addEventListener("input",renderPublished);
$("review-filter").addEventListener("change",renderReviews);
bindAsyncForm("review-form",async(e)=>{
  e.preventDefault();
  if(!selectedReview||!reviewData)return;
  const approved=$("approve").checked;
  try {
    await api("/api/reviews/save",{
      id:selectedReview.id, fingerprint:reviewData.fingerprint,
      revision:selectedReview.revision, approved:approved, acknowledge_subtree:$("ack-subtree").checked,
      reviewer:$("reviewer").value, reason:$("reason").value
    });
    const savedId=selectedReview.id;
    selectedReview=null;
    await loadReviews();
    if(reviewData?.items.some(item=>item.id===savedId))selectReview(savedId);
    toast("검토 기록을 저장했습니다. DNS에는 적용되지 않았습니다.");
  } catch(err){if(err.message.includes("Review changed")){
      selectedReview=null;
      $("review-form").hidden=true;
      $("review-empty").hidden=false;
      await loadReviews().catch(displayError);
    }
    displayError(err);}
});
$("reset-reviews").addEventListener("click",async()=>{
  try {
    const context=await api("/api/reviews/reset-context");
    if(!await confirmOperation({title:"검토 승인 기록 초기화",description:"현재 근거에 대한 승인 기록을 미승인 상태로 바꿉니다. 기존 정책 초안·게시·DNS 상태는 변경하지 않습니다.",phrase:"RESET_REVIEWS",facts:[["근거 지문",context.fingerprint]],action:"승인 기록 초기화"}))return;
    await api("/api/reviews/reset",{
      confirm:"RESET_REVIEWS",fingerprint:context.fingerprint,
      review_set_revision:context.review_set_revision
    });
    selectedReview=null;
    $("review-form").hidden=true;
    $("review-empty").hidden=false;
    await loadReviews();
    toast("승인 기록을 초기화했습니다.");
  } catch(err){displayError(err);}
});
bindAsyncForm("engine-form",async(e)=>{
  e.preventDefault();
  const threshold=Number($("engine-threshold").value);
  try{
    await api("/api/engine",{
      policy_version:$("engine-version").value.trim(),
      warn_threshold:threshold,
      admin_blocked_domains:lines("engine-admin"),
      approved_malicious_domains:lines("engine-approved"),
      official_domains:lines("engine-official"),
      score_sources:lines("engine-sources")
    });
    showText("engine-configured","구성 저장됨");
    toast("제안 엔진 설정을 저장했습니다. 이 설정은 DNS를 변경하지 않습니다.");
  } catch(err){displayError(err);}
});
bindAsyncForm("evaluate-form",async(e)=>{
  e.preventDefault();
  try{
    const result=await api("/api/evaluate",{domain:$("evaluate-domain").value.trim()});
    const proposal=result.proposal;
    const card=$("evaluation-result");
    card.replaceChildren();
    card.dataset.action=proposal.action;
    card.append(node("div","empty-symbol","◇"),
                node("strong","",proposal.action+" · "+proposal.domain),
                node("p","",proposal.reason_code+" · "+proposal.scope+" · 제안 전용 (미집행)"));
  }catch(err){displayError(err);}
});
bindAsyncForm("build-form",async(e)=>{
  e.preventDefault();
  try{
    const state=buildReviewContext;
    if(!state?.manual_revision) throw Error("정책 수집/수동 목록을 새로 조회한 뒤 생성하세요.");
    const result=await api("/api/build",{
      fingerprint:state.fingerprint,
      review_set_revision:state.review_set_revision,
      manual_revision:state.manual_revision,
      confirm_replacement:$("confirm-replacement").checked,
      acknowledge_user_notice:$("confirm-notice").checked,
      excluded_expired_review_ids:$("confirm-expired-exclusion").checked?state.expired.map(x=>x.id):[],
      confirm_empty_replacement:$("confirm-empty-replacement").checked
    });
    $("confirm-replacement").checked=false;
    $("confirm-notice").checked=false;
    await loadDrafts();
    toast(result.rules+"개 규칙을 생성했습니다. 초안은 미서명·미배포 상태입니다.");
  }catch(err){displayError(err);}
});
$("deployment-device-select").addEventListener("change",()=>{
  selectedDeploymentDevice=$("deployment-device-select").value;
  loadDeployment().catch(displayError);
});
$("deployment-refresh").addEventListener("click",()=>loadDeployment().then(result=>{if(result&&!result.partial)toast("선택 대상의 게시 상태를 다시 검증했습니다.");}).catch(displayError));
$("nodes-refresh").addEventListener("click",()=>loadDeployment().then(result=>{if(result&&!result.partial)toast("등록 장치의 서명 상태를 조회했습니다.");}).catch(displayError));
bindAsyncForm("node-register-form",async(e)=>{
  e.preventDefault();
  try{
    const result=await api("/api/nodes/register",{
      device_id:$("node-id").value.trim(),
      label:$("node-label").value.trim(),
      dns_address:$("node-address").value.trim(),
      key_id:$("node-key").value.trim()
    });
    $("node-register-form").reset();
    toast(result.device_id+" 노드를 등록했습니다. 실제 DNS 상태 보고를 확인하세요.");
    await loadDeployment();
  }catch(error){displayError(error);}
});
lock();

// Client-side idle lock must run before an interaction can reset the idle clock.
for(const eventName of ["pointerdown","keydown"]) {
  document.addEventListener(eventName,(event)=>{
    if(token && expireIdleSession()){
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    lastActivity=Date.now();
  },{capture:true});
}
function expireIdleSession() {
  if(token && Date.now()-lastActivity>=SESSION_IDLE_MS) {
    lock();
    toast("15분간 조작이 없어 콘솔 세션을 잠갔습니다.",true);
    return true;
  }
  return false;
}
window.setInterval(()=>{
  if(!token || expireIdleSession() || document.hidden || currentView!=="reviews")return;
  loadIntelStatus().catch(displayError);
},10000);
// Form views are not refreshed behind the operator's edits.
document.addEventListener("visibilitychange",()=>{
  if(!document.hidden && token && !expireIdleSession() && currentView==="reviews")
    loadIntelStatus().catch(displayError);
});
"""

from .console_workbench import JS as WORKBENCH_JS
JS = WORKBENCH_JS + "\n" + JS

from .console_observability import JS as OBS_JS
JS += "\n" + OBS_JS

from .console_live import JS as LIVE_JS
JS += "\n" + LIVE_JS

from .console_manual import JS as MANUAL_JS
JS += "\n" + MANUAL_JS
