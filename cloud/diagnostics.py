"""Cloud-only capacity UI. Counts describe stored state, not DNS protection."""
HTML = r'''<section class="surface storage-panel" aria-labelledby="storage-title" id="storage-panel">
  <div class="section-top"><div><div class="overline">DURABLE STATE / CAPACITY</div><h2 id="storage-title">운영 저장소 여유</h2><p class="muted-copy">증거 보관·정책 초안이 저장 한도에 도달하기 전에 확인합니다.</p></div><button class="button outline" type="button" id="storage-reload">다시 조회</button></div>
  <p id="storage-state" class="storage-state" role="status">아직 조회하지 않았습니다.</p>
  <div class="storage-meters" id="storage-meters" hidden>
    <div><label for="storage-bytes-meter">상태 스냅샷 용량 <strong id="storage-bytes">–</strong></label><meter id="storage-bytes-meter" min="0" max="100" low="75" high="90" optimum="0" value="0">0%</meter></div>
    <div><label for="storage-files-meter">저장 파일 수 <strong id="storage-files">–</strong></label><meter id="storage-files-meter" min="0" max="100" low="75" high="90" optimum="0" value="0">0%</meter></div>
  </div>
  <div id="storage-groups" class="storage-groups"></div>
  <p class="fine-print" id="storage-note">한도는 운영 상태 스냅샷 기준입니다. 원본 증거·서명키·파일 내용은 이 화면에 노출하지 않습니다.</p>
</section>'''

CSS = r'''
.storage-panel{margin-bottom:22px;border-color:var(--ops-line)}
.storage-panel .section-top{align-items:center}.storage-panel h2{margin:6px 0 0;font-size:20px}
.storage-panel .muted-copy{margin:8px 0 0}.storage-state{font-size:13px;color:#b8d0e0;line-height:1.7;margin:18px 0 14px}
.storage-panel[data-state="WARNING"] .storage-state,.storage-panel[data-state="CRITICAL"] .storage-state{color:#f6d69b}
.storage-panel[data-state="UNAVAILABLE"] .storage-state{color:#f8b7c1}
.storage-meters{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin:10px 0 18px}
.storage-meters label{display:flex;justify-content:space-between;gap:10px;font-size:12px;margin:0 0 8px;color:#aec5d7}
.storage-meters strong{font-variant-numeric:tabular-nums;color:#e5f4fa}
.storage-meters meter{width:100%;height:12px;display:block;accent-color:#83d7cd}
.storage-groups{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.storage-groups span{font-size:11px;padding:7px 10px;border:1px solid var(--ops-line);border-radius:7px;color:#b4cada;background:rgba(4,19,32,.22)}
@media(max-width:700px){.storage-panel .section-top{align-items:flex-start;flex-wrap:wrap}.storage-meters{grid-template-columns:1fr;gap:17px}.storage-groups span{font-size:12px}.storage-panel .fine-print{font-size:11px}}
@media(forced-colors:active){.storage-panel,.storage-groups span{background:Canvas;color:CanvasText;border-color:CanvasText}.storage-state{color:CanvasText}}
'''

JS = r'''
const auditLabels={
  cloud_operator_committed:'운영자 변경 저장',cloud_verified_evidence_imported:'검증 자료 가져오기',
  cloud_public_key_trusted:'공개키 신뢰 등록',cloud_signed_policy_published:'서명 정책 게시',
  node_registered:'DNS 노드 등록',node_unregistered:'DNS 노드 등록 해제',
  unsigned_policy_built:'정책 초안 생성',review_updated:'검토 기록 저장',reviews_reset:'검토 초기화',
  proposal_config_updated:'제안 엔진 설정',intel_refresh_requested:'위협정보 갱신 요청',
  verified_intel_imported:'검증 자료 반영'
};
function auditEventLabel(event){return auditLabels[event]||event;}
function auditReference(item){
  if(item.actor)return item.actor+' · '+(item.action||'변경')+' · r'+item.state_revision;
  return item.draft||item.device||item.reference||item.version||item.fingerprint||'–';
}
let storageRequest=0;
async function loadStorageHealth(){
  if(!token||currentView!=='audit')return;
  const epoch=sessionEpoch,view=viewEpoch,request=++storageRequest;
  const current=()=>token&&epoch===sessionEpoch&&view===viewEpoch&&request===storageRequest;
  const panel=$('storage-panel'),button=$('storage-reload');
  button.disabled=true;button.setAttribute('aria-busy','true');
  panel.dataset.state='LOADING';showText('storage-state','영속 저장소의 사용량을 확인합니다.');
  try{
    const result=await api('/api/ops/cloud/storage');
    if(!current())return;
    panel.dataset.state=result.state;
    const labels={NORMAL:'저장 여유가 있습니다.',WARNING:'저장 한도에 가까워지고 있습니다.',CRITICAL:'새 증거·초안 저장 전에 용량 점검이 필요합니다.'};
    showText('storage-state',(labels[result.state]||'상태 확인 필요')+' · 리비전 '+result.revision+' · '+fmt(result.observed_at));
    showText('storage-bytes',(result.bytes_used/1048576).toFixed(2)+' / '+(result.bytes_limit/1048576).toFixed(0)+' MiB');
    showText('storage-files',result.file_count+' / '+result.file_limit);
    $('storage-meters').hidden=false;
    for(const [id,value] of [['storage-bytes-meter',result.bytes_used/result.bytes_limit*100],['storage-files-meter',result.file_count/result.file_limit*100]]){
      $(id).value=Math.min(100,value);$(id).textContent=value.toFixed(1)+'%';
    }
    const groups=$('storage-groups');groups.replaceChildren();
    for(const [name,label] of [['archives','증거 보관'],['drafts','정책 초안'],['publications','게시 정책'],['trust','신뢰 공개키'],['audit','작업 로그'],['other','기타 상태']])
      groups.append(node('span','',label+' '+result.groups[name].file_count+'개'));
    showText('storage-note','자료를 자동 삭제하지 않습니다. 한도 경고 시 검토된 백업·보존 절차를 사용하고, 노드 재생 방지 카운터와 신뢰 기록은 임의로 지우지 마세요.');
  }catch(error){
    if(!current()||error.stale)return;
    panel.dataset.state='UNAVAILABLE';$('storage-meters').hidden=true;$('storage-groups').replaceChildren();
    showText('storage-bytes','–');showText('storage-files','–');
    showText('storage-state','저장소 상태를 확인할 수 없습니다. 빈 저장소나 정상 상태로 판단하지 않습니다.');
    showText('storage-note','인증과 저장소 연결을 확인하고 다시 조회하세요. 실제 데이터와 DNS 상태는 이 조회가 변경하지 않습니다.');
  }finally{
    if(request===storageRequest){button.disabled=false;button.removeAttribute('aria-busy');}
  }
}
$('storage-reload').addEventListener('click',loadStorageHealth);
document.addEventListener('ops:view',event=>{
  if(event.detail.view==='audit')loadStorageHealth();
});
document.addEventListener('ops:locked',()=>{
  storageRequest++;$('storage-panel').dataset.state='LOCKED';
  $('storage-meters').hidden=true;$('storage-groups').replaceChildren();
  $('storage-reload').disabled=false;$('storage-reload').removeAttribute('aria-busy');
  showText('storage-bytes','–');showText('storage-files','–');showText('storage-state','인증 후 조회합니다.');
});
'''
