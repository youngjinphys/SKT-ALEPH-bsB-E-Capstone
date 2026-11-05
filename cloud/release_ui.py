"""Target-specific handoff from unsigned drafts to the existing signed feed."""
HTML=r'''
<section id="cloud-policy-handoff" class="surface cloud-tools policy-handoff" aria-labelledby="handoff-title">
  <div class="overline">PREPARE → SIGN → PUBLISH → VERIFY</div>
  <h3 id="handoff-title">장치별 배포 준비</h3>
  <p class="muted-copy">초안과 실제 장치 ID를 선택하면 서명에 필요한 시퀀스와 정책 수신 주소를 확인할 수 있습니다. 개인키는 독립 서명자가 보관합니다.</p>
  <form id="handoff-form" class="handoff-form">
    <label>정책 초안<select id="handoff-draft" required><option value="">초안 조회 후 선택</option></select></label>
    <label>대상 장치 ID<input id="handoff-device" required maxlength="64" pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,63}" placeholder="등록한 장치 ID · 예: edge-69"></label>
    <button type="submit" class="button outline">배포 준비 확인</button>
  </form>
  <p id="handoff-status" role="status" aria-live="polite">대상 선택 후 읽기 전용으로 확인합니다.</p>
  <div id="handoff-result" hidden>
    <div id="handoff-summary" class="handoff-summary"></div>
    <ol class="handoff-steps">
      <li><h4>초안 다운로드와 독립 서명</h4><p id="handoff-sign-note"></p><button id="handoff-download" type="button" class="text-button">선택 초안 다운로드 ↓</button><pre id="handoff-sign-command"></pre></li>
      <li><h4>공개키 확인과 정책 게시</h4><p>정책 서명자의 공개키 지문을 별도로 비교하고, 서명 봉투를 업로드해 변경 영향을 검토하세요.</p><button id="handoff-publish" type="button" class="button primary">서명 정책 게시로 이동 →</button><p>장치별 HTTPS 피드</p><code id="handoff-feed"></code></li>
      <li><h4>DNS 노드의 정책 수신 설정</h4><p>상태 보고 등록과 정책 수신 설치는 별도입니다. 아래는 신규 설치 미리보기입니다. 네트워크·공개키·부트스트랩 경로를 실제 값으로 바꾸세요. 기존 설치는 운영 가이드의 업그레이드 절차를 사용합니다.</p><pre id="handoff-node-command"></pre><p id="handoff-node-state"></p></li>
      <li><h4>실제 적용 확인</h4><p>배포 현황에서 대상 장치의 게시 시퀀스·정책 해시와 서명된 적용 보고를 비교하세요. 이후 별도 LAN 클라이언트에서 UDP·TCP 응답을 검증합니다.</p></li>
    </ol>
  </div>
</section>'''
CSS=r'''
.policy-handoff{margin-top:22px;border-color:#426a80;scroll-margin-top:100px}.policy-handoff h3{font-size:21px;margin:8px 0 14px}
.handoff-form{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr) auto;gap:14px;align-items:end;margin-top:20px}
.handoff-form label{display:grid;gap:8px;font-size:12px;color:#b8cbd7}.handoff-form input,.handoff-form select{width:100%;min-width:0}
.handoff-summary{padding:16px;border:1px solid #426a80;border-radius:10px;line-height:1.8;overflow-wrap:anywhere}
.handoff-summary strong{display:block;font-size:17px}.handoff-steps{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding-left:23px;margin:24px 0 0}
.handoff-steps li{min-width:0;padding:0 14px 12px 4px}.handoff-steps h4{font-size:14px;margin:0 0 10px}
.handoff-steps p,#handoff-status{font-size:12px;line-height:1.8;color:#b0c5d5}.handoff-steps pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#081c2b;padding:14px;border-radius:8px;font-size:11px;line-height:1.8;color:#cee3ef}
#handoff-feed{display:block;overflow-wrap:anywhere;font-size:12px;line-height:1.8}.handoff-form .button{margin:0!important}
@media(max-width:900px){.policy-handoff{scroll-margin-top:190px}.handoff-form,.handoff-steps{grid-template-columns:1fr}.handoff-form .button{width:100%}}
'''
JS=r'''
let handoffVersion=0,handoffPlan=null;
function clearHandoff(){
  handoffVersion++;handoffPlan=null;$('handoff-result').hidden=true;
  showText('handoff-status','초안과 장치를 선택한 뒤 다시 조회하세요.');
}
function cloudDraftOptions(items){
  const value=$('handoff-draft').value;
  $('handoff-draft').replaceChildren(node('option','','초안 선택'),...items.map(item=>{
    const option=node('option','',item.name+(item.expired?' · 만료':''));option.value=item.name;return option;
  }));
  $('handoff-draft').firstElementChild.value='';
  if(items.some(item=>item.name===value))$('handoff-draft').value=value;
  clearHandoff();
}
function openCloudHandoff(name){
  $('handoff-draft').value=name;clearHandoff();
  $('cloud-policy-handoff').scrollIntoView({block:'start',behavior:'instant'});$('handoff-device').focus({preventScroll:true});
}
for(const id of ['handoff-draft','handoff-device']){
  $(id).addEventListener('input',clearHandoff);$(id).addEventListener('change',clearHandoff);
}
document.addEventListener('ops:locked',()=>{clearHandoff();$('handoff-form').reset();$('handoff-draft').replaceChildren();showText('handoff-status','운영자 인증 후 조회합니다.');});
document.addEventListener('ops:view',()=>clearHandoff());
// These commands are displayed as text, never executed or interpolated in HTML.
const handoffQuote=value=>"'"+String(value).replaceAll("'","'\\''")+"'";
const handoffCommand=args=>args.map(handoffQuote).join(' ');
bindAsyncForm('handoff-form',async()=>{
  clearHandoff();const current=cloudOperation(()=>handoffVersion);
  const name=$('handoff-draft').value,device=$('handoff-device').value.trim();
  showText('handoff-status','현재 정책과 대상 장치를 확인 중입니다.');
  try{
    const plan=await api('/api/ops/drafts/'+encodeURIComponent(name)+'/handoff/'+encodeURIComponent(device));current();
    handoffPlan={...plan,current};
    const target=plan.target,draft=plan.draft;
    const box=$('handoff-summary');box.replaceChildren(node('strong','',target.device_id+' · 시퀀스 '+target.current_sequence+' → '+target.next_sequence),
      node('p','',draft.rules+'개 규칙 · 만료 '+fmt(draft.expires_at)+' · 남은 시간 '+Math.floor(draft.remaining_seconds/60)+'분'),node('p','mono','정규화 정책 SHA-256 '+draft.policy_sha256),node('p','mono','다운로드 파일 SHA-256 '+draft.download_sha256));
    showText('handoff-sign-note',plan.signing.can_sign?'초안을 검토한 뒤 서명하세요. 개인키와 파일 경로는 서명자 환경에서 지정합니다.':
      ({EXPIRED:'초안이 만료됐습니다. 새 초안을 생성하세요.',SHORT_LIFETIME:'남은 시간이 5분 미만입니다. 서명·노드 수신 중 만료될 수 있어 새 초안을 권장합니다.',NOT_NEWER_THAN_PUBLICATION:'게시 정책보다 발급 시각이 늦은 새 초안이 필요합니다.',NODE_SEQUENCE_AHEAD:'노드가 보고한 정책 시퀀스가 이 서버의 게시 기록보다 앞섭니다. 기존 정책 서버와 노드 replay 상태를 먼저 조정해야 합니다.'}[plan.signing.reason]||'서명 조건을 다시 확인하세요.'));
    const pythonpath=plan.signing.pythonpath_components||['apps/dns-agent/src','apps/policy-sync/src'];
    showText('handoff-sign-command',plan.signing.can_sign?'export PYTHONPATH='+handoffQuote(pythonpath.join(':'))+'\n'+handoffCommand(plan.signing.argv_template):'서명 준비 조건을 확인하고 새로 조회하세요.');
    $('handoff-publish').disabled=!plan.signing.can_sign;
    showText('handoff-node-command',handoffCommand(plan.node_install.argv_template));showText('handoff-feed',plan.feed.url);
    showText('handoff-node-state',target.registered?'등록된 장치입니다. 상태 보고와 정책 수신 서비스 설정을 각각 확인하세요.':'아직 등록되지 않은 장치입니다. 공개 등록 파일과 실제 장치 ID를 먼저 확인하세요.');
    if(target.node_state)$('handoff-node-state').append(node('span','',' 보고 상태 '+target.node_state.state+' · 노드 정책 시퀀스 '+(target.node_sequence??'미확인')+' · 노드 보고 시각 '+fmt(target.node_state.report_at)));
    $('handoff-sign-note').append(node('span','',' 서버에 신뢰 등록된 정책 공개키 '+plan.signing.key_ids.length+'개. 노드의 신뢰키 설치는 별도로 확인하세요.'));
    if(plan.signing.requires_empty_confirmation)$('handoff-sign-note').append(node('p','','이 초안은 빈 전체 교체 정책입니다. 모든 차단 철회와 --confirm-empty를 별도로 검토하세요.'));
    $('handoff-result').hidden=false;showText('handoff-status','조회 '+fmt(new Date().toISOString())+' · 이후 게시 기록·유효기간은 다시 확인합니다. 아직 서명·게시·DNS 적용 전입니다.');
  }catch(error){try{current();}catch(_){return;}if(error.stale)return;showText('handoff-status',error.message);displayError(error);}
});
$('handoff-download').addEventListener('click',()=>{if(handoffPlan){try{handoffPlan.current();downloadDraft(handoffPlan.draft.name).catch(displayError);}catch(error){displayError(error);}}});
$('handoff-publish').addEventListener('click',async()=>{
  if(!handoffPlan)return;
  const plan=handoffPlan,button=$('handoff-publish');
  if(button.disabled)return;
  button.disabled=true;
  try{
    plan.current();
    const fresh=await api('/api/ops/drafts/'+encodeURIComponent(plan.draft.name)+'/handoff/'+encodeURIComponent(plan.target.device_id));plan.current();
    if(!fresh.signing.can_sign||fresh.target.current_sequence!==plan.target.current_sequence||fresh.draft.policy_sha256!==plan.draft.policy_sha256){
      clearHandoff();showText('handoff-status','배포 기준이나 서명 준비 조건이 바뀌었습니다. 다시 조회하고 시퀀스·유효기간을 검토하세요.');return;
    }
    clearPublicationPreview();$('cloud-publish-form').reset();
    $('cloud-publish-device').value=plan.target.device_id;$('cloud-publish-sequence').value=plan.target.current_sequence;
    selectedDeploymentDevice=plan.target.device_id;navigateTo('deployment');
    $('cloud-publication-tools').open=true;$('cloud-publication-tools').scrollIntoView({block:'start'});$('cloud-policy').focus();
  }catch(error){try{plan.current();displayError(error);}catch(_){} }
  finally{if(handoffPlan===plan)button.disabled=!plan.signing.can_sign;}
});
'''
