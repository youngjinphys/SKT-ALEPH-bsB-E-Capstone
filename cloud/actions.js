let cloudEvidencePreview=null;
let cloudPublicationPreview=null;
let cloudEvidenceVersion=0;
let cloudPublicationVersion=0;
let cloudTrustVersion=0;
// An upload spans File.text(), preview HTTP and operator confirmation. API's
// per-request session guard alone cannot bind that whole sequence.
function cloudOperation(version){
  const epoch=sessionEpoch,view=viewEpoch,credential=token,revision=version();
  return (completed=false)=>{
    if(!credential||token!==credential||epoch!==sessionEpoch||view!==viewEpoch||(!completed&&revision!==version()))
      throw staleRequest();
  };
}
// Cloud adaptation: no operator bearer credential exists in browser JS.
let cloudLoggingOut=false;
async function cloudLoginAvailability(current){
  if(!current())return;
  const link=document.querySelector('.cloud-google');
  // Do not retain a clickable provider link after a failed re-check.
  link.removeAttribute('href');link.setAttribute('aria-disabled','true');link.setAttribute('tabindex','-1');
  link.textContent='Google 로그인 연결 확인 중';
  try{
    const response=await fetch('/api/oauth?action=status',{credentials:'same-origin',cache:'no-store'});
    if(!current())return;
    const status=response.ok?await response.json():{state:'unknown'};
    if(!current())return;
    if(status.state==='enabled'){
      link.setAttribute('href','/api/oauth?action=start&next=/dashboard');
      link.removeAttribute('aria-disabled');link.removeAttribute('tabindex');
      link.textContent='Google로 로그인 →';
      showText('cloud-login-message','Google 로그인 후 관제센터에 연결하세요. 승인된 이메일만 운영자 권한을 받습니다.');
    }else{
      link.removeAttribute('href');link.setAttribute('aria-disabled','true');link.setAttribute('tabindex','-1');
      link.textContent='Google 로그인 설정 확인 필요';
      showText('cloud-login-message',status.state==='disabled'
        ?'Google 인증 제공자가 비활성화되어 있습니다. 관리자가 Supabase의 Google 제공자와 OAuth 콜백을 설정해야 로그인할 수 있습니다.'
        :'Google 인증 상태를 확인할 수 없습니다. 잠시 후 현재 로그인으로 연결 버튼을 다시 누르세요.');
    }
  }catch{
    if(current())showText('cloud-login-message','로그인 제공자 상태 확인 실패. 다시 연결해 주세요.');
  }
}
async function cloudConnect(){
  if(cloudLoggingOut)return;
  lock();
  const attempt=sessionEpoch;
  const current=()=>attempt===sessionEpoch&&!cloudLoggingOut;
  showText('cloud-login-message','Google 세션과 DNS 운영자 권한을 확인합니다.');
  try{
    const pinSession=await cloudPinStatus(current);
    if(!current())return;
    const auth=pinSession?{ok:true}:await fetch('/api/auth',{credentials:'same-origin',cache:'no-store'});
    if(!current())return;
    if(!auth.ok){
      if(auth.status===401)await cloudLoginAvailability(current);
      else showText('cloud-login-message',auth.status===403?'현재 계정은 이 사이트의 접근 권한이 없습니다.':'로그인 공급자를 확인할 수 없습니다. 공개 페이지는 계속 사용할 수 있습니다.');
      return;
    }
    token='cookie-session';
    const identity=await api('/api/ops/session');
    if(!current())return;
    unlock();
    showText('connection-text','운영자 · '+identity.email);
  }catch(error){
    if(!current()||error.stale)return;
    lock();
    showText('cloud-login-message',error.message||'관제 서버 연결 실패');
  }
}
$('cloud-logout').addEventListener('click',async()=>{
  if(cloudLoggingOut)return;
  cloudLoggingOut=true;
  lock();
  const attempt=sessionEpoch;
  try{
    if(cloudPinLoginPending)await cloudPinLoginPending;
    const pinLogout=await fetch('/api/ops/test-auth',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({action:'logout'})});
    if(!pinLogout.ok)throw Error('테스트 세션 로그아웃 실패');
    const response=await fetch('/api/auth',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({action:'logout'})});
    if(attempt!==sessionEpoch)return;
    if(response.ok)window.location.assign('/');
    else showText('cloud-login-message','로그아웃 결과를 완전히 확인하지 못했습니다. 원격 세션 폐기는 별도 확인이 필요합니다.');
  }catch{
    if(attempt===sessionEpoch)showText('cloud-login-message','로그아웃 요청의 완료를 확인할 수 없습니다.');
  }finally{cloudLoggingOut=false;}
});
async function cloudFile(id,current){
  current();
  const file=$(id).files[0];
  if(!file||file.size>2*1024*1024)throw Error('2 MiB 이하의 JSON 파일을 선택하세요.');
  const text=await file.text();
  current();
  if($(id).files[0]!==file)throw staleRequest();
  let value;
  try{value=JSON.parse(text);}catch{throw Error('올바른 JSON 파일을 선택하세요.');}
  if(!value||typeof value!=='object'||Array.isArray(value))throw Error('JSON 객체 파일을 선택하세요.');
  return value;
}
function showPreview(target,metrics,note){
  const container=$(target);container.replaceChildren();
  const grid=node('div','preview-grid');
  for(const [label,value,warning] of metrics){
    const cell=node('div','');cell.append(node('small','',label),node('strong',warning?'warning':'',value));grid.append(cell);
  }
  container.append(grid,node('p','preview-fingerprint',note));
}
function clearEvidencePreview(){
  cloudEvidenceVersion++;cloudEvidencePreview=null;
  $('cloud-evidence-preview').hidden=true;$('cloud-evidence-commit').disabled=true;
  $('cloud-evidence-summary').replaceChildren();
}
function clearPublicationPreview(){
  cloudPublicationVersion++;cloudPublicationPreview=null;
  $('cloud-publish-preview').hidden=true;$('cloud-publish-commit').disabled=true;
  $('cloud-publish-summary').replaceChildren();
}
$('cloud-evidence').addEventListener('change',clearEvidencePreview);
for(const id of ['cloud-policy','cloud-publish-device','cloud-publish-sequence']){
  $(id).addEventListener('input',clearPublicationPreview);
  $(id).addEventListener('change',clearPublicationPreview);
}
for(const id of ['cloud-key-role','cloud-key','cloud-key-confirm']){
  const invalidate=()=>{cloudTrustVersion++;$('cloud-key-result').textContent='';};
  $(id).addEventListener('input',invalidate);$(id).addEventListener('change',invalidate);
}
document.addEventListener('ops:view',event=>{
  if(event.detail.view!=='reviews')clearEvidencePreview();
  if(event.detail.view!=='deployment'){clearPublicationPreview();cloudTrustVersion++;}
});
document.addEventListener('ops:locked',()=>{
  clearEvidencePreview();clearPublicationPreview();cloudTrustVersion++;
  $('cloud-evidence-form').reset();$('cloud-publish-form').reset();$('cloud-key-form').reset();
  $('cloud-key-result').textContent='';
});
bindAsyncForm('cloud-evidence-form',async()=>{
  clearEvidencePreview();
  const current=cloudOperation(()=>cloudEvidenceVersion);
  try{
    const verified=await cloudFile('cloud-evidence',current);
    current();
    const preview=await api('/api/ops/cloud/evidence/preview',{verified});
    current();
    cloudEvidencePreview={verified,preview,epoch:sessionEpoch,current,committing:false};
    showPreview('cloud-evidence-summary',[
      ['검증 URL',preview.verified],['유효 근거',preview.fresh,!preview.fresh],['검토 후보',preview.review_proposals]
    ],'조회 '+fmt(preview.checked_at)+' · 지문 '+preview.fingerprint+(preview.importable?' · 모든 신규 승인은 미승인 상태로 시작합니다.':' · 유효한 근거가 없어 가져올 수 없습니다. 다시 수집하세요.'));
    $('cloud-evidence-preview').hidden=false;$('cloud-evidence-commit').disabled=!preview.importable;
  }catch(error){displayError(error);}
});
$('cloud-evidence-commit').addEventListener('click',async()=>{
  const pending=cloudEvidencePreview;
  if(!pending||pending.epoch!==sessionEpoch||!pending.preview.importable||pending.committing)return;
  const accepted=await confirmOperation({title:'검증 자료 가져오기',description:'기존 검토 자료를 비공개 보관하고 새 승인 목록을 미승인 상태로 시작합니다. 이미 게시한 정책과 DNS 노드에는 변경을 보내지 않습니다.',phrase:'IMPORT_VERIFIED',facts:[['검증 URL',pending.preview.verified],['검토 후보',pending.preview.review_proposals],['근거 지문',pending.preview.fingerprint]],action:'새 근거 가져오기'});
  if(!accepted||cloudEvidencePreview!==pending)return;
  const button=$('cloud-evidence-commit');button.disabled=true;
  try{
    pending.current();pending.committing=true;
    const result=await api('/api/ops/cloud/evidence',{verified:pending.verified,confirm:'IMPORT_VERIFIED',context_revision:pending.preview.context_revision,fingerprint:pending.preview.fingerprint});
    pending.current();
    clearEvidencePreview();$('cloud-evidence-form').reset();selectedReview=null;await loadReviews();
    toast(result.already_current?'이미 동일한 근거를 사용 중입니다. 기존 승인을 유지합니다.':'검증 자료를 가져왔습니다. 신규 항목은 모두 미승인입니다.');
  }catch(error){if(cloudEvidencePreview===pending)clearEvidencePreview();displayError(error);}
});
bindAsyncForm('cloud-key-form',async()=>{
  const current=cloudOperation(()=>cloudTrustVersion);
  try{
    current();
    if(!$('cloud-key-confirm').checked)throw Error('공개키 소유자와 지문 확인이 필요합니다.');
    const body={role:$('cloud-key-role').value,public_key:$('cloud-key').value.trim()};
    const preview=await api('/api/ops/cloud/trust/preview',body);
    current();
    const accepted=await confirmOperation({title:'공개키 신뢰 등록',description:'아래 지문을 별도의 관리 채널에서 받은 값과 비교하세요. 정책 서명키와 장치 상태 보고키는 분리해야 합니다.',phrase:'TRUST_PUBLIC_KEY',facts:[['용도',body.role==='policy'?'독립 정책 서명자':'장치 상태 보고'],['SHA-256 지문',preview.key_id]],action:'공개키 신뢰 등록'});
    if(!accepted)return;
    current();
    const result=await api('/api/ops/cloud/trust',{...body,expected_key_id:preview.key_id,confirm:'TRUST_PUBLIC_KEY'});
    current();
    showText('cloud-key-result','신뢰 지문: '+result.key_id);$('cloud-key').value='';$('cloud-key-confirm').checked=false;
    toast('공개키를 등록했습니다. 장치 등록에는 이 지문을 사용하세요.');
  }catch(error){displayError(error);}
});
bindAsyncForm('cloud-publish-form',async()=>{
  clearPublicationPreview();
  const current=cloudOperation(()=>cloudPublicationVersion);
  try{
    // Snapshot every form value before the first asynchronous operation.
    const device=$('cloud-publish-device').value.trim();
    const sequence=Number($('cloud-publish-sequence').value);
    const envelope=await cloudFile('cloud-policy',current);
    current();
    const body={device_id:device,envelope,expected_sequence:sequence,ack_withdrawals:false,ack_key_rotation:false};
    if(!Number.isSafeInteger(body.expected_sequence)||body.expected_sequence<0)throw Error('정확한 현재 게시 시퀀스를 입력하세요.');
    const preview=await api('/api/ops/cloud/publish/preview',body);
    current();
    cloudPublicationPreview={body,preview,epoch:sessionEpoch,current,committing:false};
    showPreview('cloud-publish-summary',[
      ['신규 차단',preview.added_count],['차단 철회',preview.withdrawn_count,preview.withdrawn_count>0],['유효기간 단축',preview.shortened_count,preview.shortened_count>0]
    ],'시퀀스 '+preview.expected_sequence+' → '+preview.sequence+' · 만료 '+fmt(preview.expires_at)+' · SHA-256 '+preview.policy_sha256+(preview.requires_key_rotation?' · 서명키 변경 승인이 필요합니다.':''));
    $('cloud-publish-preview').hidden=false;$('cloud-publish-commit').disabled=false;
  }catch(error){displayError(error);}
});
$('cloud-publish-commit').addEventListener('click',async()=>{
  const pending=cloudPublicationPreview;
  if(!pending||pending.epoch!==sessionEpoch||pending.committing)return;
  if(pending.preview.requires_withdrawals&&!$('cloud-withdrawals').checked){toast('미리보기의 차단 철회·수명 단축 영향을 확인하고 체크하세요.',true);return;}
  if(pending.preview.requires_key_rotation&&!$('cloud-rotation').checked){toast('정책 서명키 변경을 확인하고 체크하세요.',true);return;}
  const accepted=await confirmOperation({title:'서명된 정책 게시',description:'검증한 서명 정책을 장치의 HTTPS 피드에 게시합니다. DNS 적용 완료 여부는 이후 수신되는 노드 보고로 별도 확인합니다.',phrase:'PUBLISH_POLICY',facts:[['장치',pending.body.device_id],['시퀀스',pending.preview.expected_sequence+' → '+pending.preview.sequence],['차단 철회',pending.preview.withdrawn_count],['수명 단축',pending.preview.shortened_count]],action:'서명 정책 게시'});
  if(!accepted||cloudPublicationPreview!==pending)return;
  const button=$('cloud-publish-commit');button.disabled=true;
  try{
    pending.current();pending.committing=true;
    const result=await api('/api/ops/cloud/publish',{...pending.body,ack_withdrawals:$('cloud-withdrawals').checked,ack_key_rotation:$('cloud-rotation').checked});
    pending.current(true);
    if(cloudPublicationPreview===pending){
      clearPublicationPreview();$('cloud-publish-sequence').value=result.sequence;$('cloud-withdrawals').checked=false;$('cloud-rotation').checked=false;
    }
    const success='장치 '+pending.body.device_id+'에 정책 시퀀스 '+result.sequence+'를 게시했습니다. DNS 적용은 별도 확인하세요.';
    toast(success);
    try{
      const status=await loadDeployment();pending.current(true);
      if(status?.partial)toast(success+' 일부 상태 조회에 실패했습니다. 다시 조회하세요.',true);
    }catch(error){
      if(error.stale)throw error;
      pending.current(true);toast(success+' 상태 조회에 실패했습니다. 다시 조회하세요.',true);
    }
  }catch(error){if(cloudPublicationPreview===pending)clearPublicationPreview();displayError(error);}
});
cloudConnect();
