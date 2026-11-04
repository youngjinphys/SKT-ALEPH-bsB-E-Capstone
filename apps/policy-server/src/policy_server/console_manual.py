"""Accessible manual domain workflow matching the shared dark console palette."""
HTML=r'''
<section class="surface manual-console" aria-labelledby="manual-title" id="manual-console">
  <div class="manual-heading"><div><div class="overline">MANUAL FQDN / SUBTREE POLICY</div>
    <h3 id="manual-title">수동 FQDN 블랙리스트</h3>
    <p>위협정보 수집과 별개로 검토자가 차단 도메인을 등록합니다. 미서명 초안에만 반영하며 DNS는 바로 변경되지 않습니다.</p></div>
    <span class="manual-total" id="manual-total" role="status">조회 대기</span></div>
  <div class="manual-layout">
    <form id="manual-form" class="manual-form">
      <div class="manual-fields">
        <label>FQDN<input id="manual-domain" type="text" maxlength="253" autocomplete="off" required placeholder="phishing.example.net"></label>
        <label>규칙 만료 시각<input id="manual-expires" type="datetime-local" required></label>
        <label>검토자<input id="manual-reviewer" maxlength="80" required autocomplete="off" placeholder="검토자"></label>
      </div>
      <label>등록 근거<textarea id="manual-reason" rows="2" minlength="15" maxlength="400" required placeholder="차단 필요성과 오탐 가능성, 영향 범위를 명확히 기록하세요."></textarea></label>
      <label class="check-row"><input type="checkbox" id="manual-ack" required><span>이 도메인과 모든 하위 도메인(SUBTREE) 차단 영향을 이해하고 승인합니다.</span></label>
      <div class="manual-actions"><button class="button primary" id="manual-save" type="submit">검토 후 블랙리스트 등록 →</button>
      <span class="fine-print">별도 서명 · 게시 절차 필요</span></div>
    </form>
    <section class="manual-registry" aria-label="등록된 수동 FQDN">
      <div class="manual-registry-heading"><h4>등록된 규칙</h4><button id="manual-reload" class="text-button" type="button">다시 조회 ↻</button></div>
      <div class="manual-list" id="manual-list" role="list" aria-live="polite"><p class="muted-copy">조회 대기</p></div>
      <p>만료된 FQDN은 새 정책 초안에서 제외됩니다. 등록을 해제해도 이미 게시한 DNS 정책은 자동으로 변경되지 않습니다.</p>
    </section>
  </div>
</section>'''
CSS=r'''
.manual-console{margin:20px 0;padding:25px;background:linear-gradient(135deg,rgba(32,39,58,.96),rgba(24,33,44,.96));border:1px solid rgba(180,164,211,.3)}
.manual-heading{display:flex;gap:16px;justify-content:space-between;align-items:flex-start;margin-bottom:22px}
.manual-heading h3{font-size:21px;letter-spacing:-.025em;margin:6px 0 10px}
.manual-heading p{font-size:12px;line-height:1.7;color:var(--ops-text-secondary);margin:0;max-width:670px}
.manual-total{flex:0 0 auto;font-size:11px;color:var(--tone-lilac,#bca9dc);border:1px solid rgba(188,169,220,.4);background:rgba(188,169,220,.12);border-radius:24px;padding:7px 12px}
.manual-layout{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,.88fr);gap:20px}
.manual-form{display:grid;gap:13px;align-content:start;min-width:0}
.manual-fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.manual-fields label:last-child{grid-column:1/-1}
.manual-form label{display:grid;gap:8px;font-size:11px;color:#b8c8d5}
.manual-form input:not([type=checkbox]),.manual-form textarea{width:100%;min-width:0;background:#101a28;color:#eef4f9;border:1px solid #536275;border-radius:9px;padding:10px 12px;font-size:12px}
.manual-form .check-row{display:flex;align-items:flex-start;line-height:1.65}
.manual-form .check-row input{accent-color:var(--tone-lilac,#bca9dc);margin:4px 4px 0 0}
.manual-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.manual-actions .button{background:var(--tone-lilac,#bca9dc);color:#211a2c;border-color:var(--tone-lilac,#bca9dc)}
.manual-actions .fine-print{font-size:10px;color:#a8b7c5}
.manual-registry{min-width:0;background:rgba(12,22,35,.53);padding:16px;border:1px solid rgba(160,172,190,.26);border-radius:12px}
.manual-registry-heading{display:flex;align-items:center;gap:9px;justify-content:space-between;margin-bottom:12px}
.manual-registry h4{font-size:13px;margin:0}
.manual-registry>p{font-size:10px;line-height:1.7;color:#9eadbd;margin:13px 0 0}
.manual-list{display:grid;gap:9px;max-height:420px;overflow:auto}
.manual-item{padding:12px;background:rgba(30,41,57,.8);border:1px solid rgba(170,173,206,.28);border-left:3px solid var(--tone-lilac,#bca9dc);border-radius:10px}
.manual-item[data-state=expired]{border-left-color:var(--tone-muted,#a9b5c4)}
.manual-item-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.manual-item strong{font-size:12px;color:#edf1f7;overflow-wrap:anywhere}
.manual-item small{display:block;margin-top:7px;color:#b3c4d0;font-size:10px;line-height:1.6;overflow-wrap:anywhere}
.manual-item button{margin-top:5px;font-size:10px}
.manual-source-flow{display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:11px}
.manual-source-flow strong{color:var(--tone-lilac,#bca9dc)}
.manual-source-flow span{color:#b6c5d4}
.intel-refresh-panel[data-status=NOT_CONFIGURED] #intel-state{color:var(--tone-amber,#ddbc88)}
@media(max-width:980px){.manual-layout{grid-template-columns:1fr}}
@media(max-width:640px){.manual-console{padding:17px}.manual-heading{flex-wrap:wrap}.manual-fields{grid-template-columns:1fr}.manual-fields label:last-child{grid-column:auto}.manual-actions button{width:100%}}
@media(forced-colors:active){.manual-console,.manual-registry,.manual-item{background:Canvas;color:CanvasText;border-color:CanvasText}.manual-total{color:CanvasText;border-color:CanvasText}}
'''
JS=r'''
let manualData=null;
function manualDefaultDate(){
  if($('manual-expires').value)return;
  const d=new Date(Date.now()+4*3600000);
  const local=new Date(d.getTime()-d.getTimezoneOffset()*60000);
  $('manual-expires').value=local.toISOString().slice(0,16);
}
function renderManual(){
  const list=$('manual-list');list.replaceChildren();
  if(!manualData){list.append(empty('수동 규칙 조회 실패'));return;}
  const valid=manualData.entries.filter(x=>!x.expired&&!x.unsafe_boundary);
  showText('manual-total','유효 '+valid.length+'건 / 전체 '+manualData.entries.length+'건');
  if(!manualData.entries.length){list.append(empty('아직 등록된 FQDN이 없습니다.'));return;}
  for(const item of manualData.entries){
    const card=node('article','manual-item');card.setAttribute('role','listitem');
    card.dataset.state=item.expired?'expired':'active';
    const head=node('div','manual-item-head');
    head.append(node('strong','',item.domain),pill(item.unsafe_boundary?'공용 접미사·보호 경계 위반':item.expired?'만료':'수동 승인',item.unsafe_boundary?'bad':item.expired?'muted':'warn'));
    const remove=node('button','text-button','등록 해제');
    remove.type='button';remove.addEventListener('click',()=>removeManual(item).catch(displayError));
    card.append(head,node('small','',item.reviewer+' · 만료 '+fmt(item.expires_at)),
                node('small','',item.reason),remove);list.append(card);
  }
}
async function removeManual(item){
  if(!manualData||!token)return;
  const rev=manualData.revision;
  if(!await confirmOperation({title:'FQDN 등록 해제',
       description:'등록 기록만 해제합니다. 기존에 서명·게시한 정책이나 DNS는 즉시 변경되지 않습니다.',
       phrase:'REMOVE_MANUAL_BLOCK',facts:[['FQDN',item.domain],['차단 범위','SUBTREE']],
       action:'수동 등록 해제'}))return;
  const result=await api('/api/manual/remove',{
    domain:item.domain,expected_revision:rev,confirm:'REMOVE_MANUAL_BLOCK'});
  toast(result.domain+' 수동 등록을 해제했습니다. 게시된 DNS 정책은 그대로입니다.');
  if(token&&currentView==='drafts')await loadDrafts();
}
bindAsyncForm('manual-form',async e=>{
  e.preventDefault();
  try{
    if(!manualData)throw Error('수동 FQDN 목록을 먼저 조회하세요.');
    const value=$('manual-expires').value,when=new Date(value);
    if(!value||!Number.isFinite(when.getTime()))throw Error('규칙 만료 시각이 필요합니다.');
    const request={
      domain:$('manual-domain').value.trim(),
      reviewer:$('manual-reviewer').value.trim(),
      reason:$('manual-reason').value.trim(),
      expires_at:when.toISOString(),
      acknowledge_subtree:$('manual-ack').checked,
      expected_revision:manualData.revision
    };
    const preview=await api('/api/manual/preview',request);
    if(!await confirmOperation({title:'수동 FQDN 차단 승인',
      description:'등록은 별도 서명 전 목록에만 반영됩니다. DNS를 변경하려면 새 정책을 서명·게시해야 합니다.',
      phrase:'UPSERT_MANUAL_SUBTREE',
      facts:[['FQDN',preview.domain],['영향 범위','SUBTREE · 하위 도메인 포함'],
             ['만료',fmt(preview.expires_at)],['근거',preview.reason]],
      action:'FQDN 저장'}))return;
    const result=await api('/api/manual/save',{...request,confirm:'UPSERT_MANUAL_SUBTREE'});
    toast(result.domain+' 수동 FQDN을 등록했습니다. 미서명 초안을 생성하세요.');
    $('manual-form').reset();manualDefaultDate();
    if(token&&currentView==='drafts')await loadDrafts();
  }catch(error){displayError(error);}
});
$('manual-reload').addEventListener('click',()=>loadDrafts().catch(displayError));
document.addEventListener('ops:locked',()=>{
  manualData=null;$('manual-form').reset();$('manual-list').replaceChildren();
  showText('manual-total','인증 후 조회');
});
'''
