"""Bundled no-dependency browser operator interface."""
JS = r""""use strict";
// Security: no token persistence, no external dependencies, no untrusted innerHTML.
const $ = (id) => document.getElementById(id);
const panelTitles = {
  overview:["운영 개요","정책 근거, 승인, 서명 게시 상태를 하나의 화면에서 확인합니다.","Operations"],
  reviews:["위협 검토","위협정보 검증 결과에 대한 수동 승인과 근거를 기록합니다.","Threat review"],
  engine:["정책 제안 엔진","EXACT 범위의 비집행 정책 제안을 관리합니다.","Decision engine"],
  drafts:["정책 초안","검토된 증거를 실제 정책 생성 엔진에 연결합니다.","Draft builder"],
  deployment:["배포 현황","서명된 게시물의 상태를 검증하고 DNS 적용 경계를 확인합니다.","Distribution"],
  audit:["작업 기록","검토·설정·초안 변경 기록을 살펴봅니다.","Audit trail"]
};
let token = null;
let currentView = "overview";
let reviewData = null;
let selectedReview = null;
let publishedRules = [];
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
  const headers={"Authorization":"Bearer "+token};
  if (data !== undefined) headers["Content-Type"]="application/json";
  let response;
  try {
    response=await fetch(path,{
      method:data===undefined?"GET":"POST",
      headers:headers,
      cache:"no-store",
      credentials:"omit",
      mode:"same-origin",
      ...(data===undefined?{}:{body:JSON.stringify(data)})
    });
  } catch (_) {
    throw Error("콘솔 서버에 연결할 수 없습니다.");
  }
  let body;
  try {body=await response.json();} catch (_){throw Error("서버 응답 형식이 올바르지 않습니다.");}
  if(response.status===401) {
    lock();
    throw Error("인증에 실패했습니다. 액세스 토큰을 확인하세요.");
  }
  if(!response.ok) throw Error(body.error||"요청이 거부되었습니다.");
  return body;
}
function lock() {
  token=null;
  reviewData=null;
  selectedReview=null;
  $("authorized").hidden=true;
  $("login-view").hidden=false;
  $("logout-button").hidden=true;
  $("token").value="";
  $("connection-dot").classList.remove("online");
  showText("connection-text","인증 필요");
}
function unlock() {
  $("authorized").hidden=false;
  $("login-view").hidden=true;
  $("logout-button").hidden=false;
  $("connection-dot").classList.add("online");
  showText("connection-text","검토자 세션");
  showText("hero-date",new Date().toLocaleDateString("ko-KR",{year:"numeric",month:"long",day:"numeric"}));
  setView("overview");
}
function setView(name) {
  if(!token||!panelTitles[name]) return;
  currentView=name;
  document.querySelectorAll("[data-panel]").forEach((el)=>{el.hidden=el.dataset.panel!==name;});
  document.querySelectorAll("[data-view]").forEach((el)=>{
    const active=el.dataset.view===name;
    el.classList.toggle("active",active);
    if(active)el.setAttribute("aria-current","page"); else el.removeAttribute("aria-current");
  });
  showText("page-title",panelTitles[name][0]);
  showText("page-description",panelTitles[name][1]);
  showText("crumb-current",panelTitles[name][2]);
  refreshView(name).catch(e=>toast(e.message,true));
}
async function refreshView(name) {
  if(name==="overview") return loadOverview();
  if(name==="reviews") return loadReviews();
  if(name==="engine") return loadEngine();
  if(name==="drafts") return loadDrafts();
  if(name==="deployment") return loadDeployment();
  if(name==="audit") return loadAudit();
}
const deployLabel = (data) => ({
  NOT_CONFIGURED:"게시 경로 미설정",
  SIGNED_FILE_VERIFIED:"서명된 게시 파일 확인",
  NO_PUBLISHED_FILE:"게시 파일 없음",
  VERIFICATION_FAILED:"서명 또는 유효기간 검증 실패"
})[data.state]||data.state||"미확인";
async function loadOverview() {
  const result=await api("/api/overview");
  showText("stat-candidates",result.candidates);
  showText("stat-approved",result.approved);
  showText("stat-fresh",result.fresh);
  showText("stat-drafts",result.drafts);
  showText("nav-review-count",result.candidates);
  showText("overview-verified",result.evidence_missing?"검증 파일 미등록":fmt(result.verified_at));
  showText("overview-deploy-state",deployLabel(result.deployment));
  const deployment=result.deployment;
  showText("overview-deploy-detail",deployment.message||"DNS 적용은 별도 검증이 필요합니다.");
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
  if(reviewData.missing) {list.append(empty("검증 파일이 없습니다. 검토자 전용 workspace/verified.json에 최신 검증 결과를 안전하게 복사하세요."));return;}
  if(!items.length) {list.append(empty("조건에 맞는 검토 후보가 없습니다."));return;}
  items.forEach((item)=>{
    const row=node("button","review-item"+(selectedReview&&selectedReview.id===item.id?" selected":""));
    row.type="button";
    const left=node("div","");
    left.append(node("strong","",item.domain),node("small","",item.threat_types.join(" · ")||"위협 유형 미확인"));
    const right=node("div","review-badges");
    right.append(pill(item.approved?"승인":"대기",item.approved?"good":""),
                 pill(item.fresh?"신선":"만료",item.fresh?"":"bad"));
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
  renderReviews();
}
async function loadReviews() {
  reviewData=await api("/api/reviews");
  showText("nav-review-count",reviewData.items.length);
  if(selectedReview) {
    const still=reviewData.items.find((x)=>x.id===selectedReview.id);
    if(still) selectedReview=still;
    else {selectedReview=null;$("review-form").hidden=true;$("review-empty").hidden=false;}
  }
  renderReviews();
}
async function loadEngine() {
  const result=await api("/api/engine");
  const conf=result.config;
  showText("engine-configured",result.configured?"구성 저장됨":"미설정");
  $("engine-version").value=conf?conf.policy_version:"v0.8-operator";
  $("engine-threshold").value=conf?conf.warn_threshold:70;
  $("engine-admin").value=conf?conf.admin_blocked_domains.join("\n"):"";
  $("engine-approved").value=conf?conf.approved_malicious_domains.join("\n"):"";
  $("engine-official").value=conf?conf.official_domains.join("\n"):"";
  $("engine-sources").value=conf?conf.score_sources.join("\n"):"lab-scanner";
}
const lines = (id) => $(id).value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
async function loadDrafts() {
  const items=await api("/api/drafts");
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
    download.addEventListener("click",()=>downloadDraft(item.name).catch(e=>toast(e.message,true)));
    actions.append(download);
    wrapper.append(heading,meta,actions);
    list.append(wrapper);
  });
}
async function downloadDraft(name) {
  if(!token)throw Error("인증이 필요합니다.");
  const response=await fetch("/api/drafts/"+encodeURIComponent(name)+"/download",{
    headers:{"Authorization":"Bearer "+token},cache:"no-store",credentials:"omit",mode:"same-origin"
  });
  if(!response.ok){let data={};try{data=await response.json();}catch(_){}throw Error(data.error||"초안 다운로드 실패");}
  const blob=await response.blob();
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
async function loadDeployment() {
  const data=await api("/api/deployment");
  publishedRules=Array.isArray(data.rules)?data.rules:[];
  renderPublished();
  showText("deployment-state",deployLabel(data));
  showText("deployment-message",data.message||"검증 가능한 현재 게시 정책이 없습니다.");
  showText("deployment-device",data.device);
  showText("deployment-sequence",data.sequence);
  showText("deployment-hash",data.policy_sha256?data.policy_sha256.slice(0,28)+"…":null);
  showText("deployment-blocks",data.active_blocks);
  showText("deployment-expires",fmt(data.expires_at));
}
async function loadAudit() {
  const events=await api("/api/audit");
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
  token=submitted;
  try {
    await api("/api/deployment");
    $("token").value="";
    unlock();
  } catch(err) {
    lock();
    toast(err.message,true);
  }
});
$("logout-button").addEventListener("click",lock);
$("refresh-button").addEventListener("click",()=>{if(token)refreshView(currentView).then(()=>toast("최신 상태를 조회했습니다.")).catch(e=>toast(e.message,true));});
document.querySelectorAll("[data-view]").forEach((el)=>el.addEventListener("click",()=>setView(el.dataset.view)));
document.querySelectorAll("[data-go]").forEach((el)=>el.addEventListener("click",()=>setView(el.dataset.go)));
$("review-search").addEventListener("input",renderReviews);
$("published-search").addEventListener("input",renderPublished);
$("review-filter").addEventListener("change",renderReviews);
$("review-form").addEventListener("submit",async(e)=>{
  e.preventDefault();
  if(!selectedReview||!reviewData)return;
  const approved=$("approve").checked;
  try {
    await api("/api/reviews/save",{
      id:selectedReview.id, fingerprint:reviewData.fingerprint,
      approved:approved, acknowledge_subtree:$("ack-subtree").checked,
      reviewer:$("reviewer").value, reason:$("reason").value
    });
    await loadReviews();
    toast("검토 기록을 안전하게 저장했습니다. DNS에는 적용되지 않았습니다.");
  } catch(err){toast(err.message,true);}
});
$("reset-reviews").addEventListener("click",async()=>{
  const word=window.prompt("모든 승인 기록을 초기화합니다. RESET_REVIEWS를 입력하세요.");
  if(word!=="RESET_REVIEWS")return;
  try {
    await api("/api/reviews/reset",{confirm:"RESET_REVIEWS"});
    selectedReview=null;
    $("review-form").hidden=true;
    $("review-empty").hidden=false;
    await loadReviews();
    toast("승인 기록을 초기화했습니다.");
  } catch(err){toast(err.message,true);}
});
$("engine-form").addEventListener("submit",async(e)=>{
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
  } catch(err){toast(err.message,true);}
});
$("evaluate-form").addEventListener("submit",async(e)=>{
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
  }catch(err){toast(err.message,true);}
});
$("build-form").addEventListener("submit",async(e)=>{
  e.preventDefault();
  try{
    const state=await api("/api/reviews");
    if(!state.fingerprint) throw Error("먼저 검증된 정책 후보를 등록해야 합니다.");
    const result=await api("/api/build",{
      fingerprint:state.fingerprint,
      confirm_replacement:$("confirm-replacement").checked,
      acknowledge_user_notice:$("confirm-notice").checked
    });
    $("confirm-replacement").checked=false;
    $("confirm-notice").checked=false;
    await loadDrafts();
    toast(result.rules+"개 규칙을 생성했습니다. 초안은 미서명·미배포 상태입니다.");
  }catch(err){toast(err.message,true);}
});
$("deployment-refresh").addEventListener("click",()=>loadDeployment().then(()=>toast("게시 상태를 다시 검증했습니다.")).catch(e=>toast(e.message,true)));
lock();
"""
