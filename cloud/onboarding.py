"""Guided, operator-approved device onboarding with no private-key upload."""
HTML = r'''<details class="surface cloud-tools node-onboarding" aria-labelledby="node-onboarding-title"><summary>노드 연결 파일 등록 · 처음 연결하는 장치</summary><div class="overline">CONNECT A REAL DNS NODE</div><h2 id="node-onboarding-title">노드 연결 파일 등록</h2><p class="muted-copy">Vercel은 내부 IP를 스캔하지 않습니다. 실제 DNS 노드에서 만든 공개 등록 파일을 확인하고, 그 노드가 외부 HTTPS로 상태를 전송하도록 연결합니다.</p><div class="onboarding-steps"><div><strong>01 · 노드에서 준비</strong><p>검토한 동일 커밋으로 설치된 코드를 갱신하고 아래 스크립트를 로컬에서 실행합니다. 기본 실행은 미리보기이며 <code>--apply</code>로 적용합니다.</p><pre>sudo python3 scripts/deploy/connect-node-dashboard.py \
  --device-id 실제_장치_ID --listen-ip 실제_내부_IP \
  --interface 실제_인터페이스 --label "DNS 서버 이름"</pre><p>출력: <code>/root/aleph-ops-secrets/node-enrollment.json</code>. 기존 개인키·보고 순번은 보존됩니다. --interface를 생략하면 지정한 내부 IP가 유일하게 할당된 로컬 NIC만 자동 선택합니다. 변경 전에 Vercel 수신 경로·TLS·시각을 검사합니다. 개인키 파일은 업로드하지 마세요.</p></div><div><strong>02 · 공개 등록 파일 확인</strong><form id="cloud-enroll-form"><label for="cloud-enroll-file">node-enrollment.json · 공개키와 장치 서명만 포함</label><input id="cloud-enroll-file" type="file" accept=".json,application/json" required><button type="submit" class="button primary">장치 정보·지문 확인 후 등록</button></form><p id="cloud-enroll-status" role="status" aria-live="polite">이미 등록된 노드는 삭제·재등록하지 마세요. 같은 장치 키와 순번을 보존하고 수집기를 갱신합니다.</p></div><div><strong>03 · 보고 수신 확인</strong><p>등록 후 노드에서 실행합니다.</p><pre>sudo systemctl start aleph-ops-collect.service
sudo systemctl start aleph-ops-send.service</pre><p>약 60초 간격의 보고가 연결됩니다. CPU·송수신 변화율은 같은 부팅의 두 관측이 필요합니다. 정책이 없어도 서버 자원은 관측할 수 있습니다.</p></div></div></details>'''
CSS = r'''.node-onboarding summary{cursor:pointer;font-size:13px;font-weight:700;min-height:24px}.node-onboarding[open] summary{margin-bottom:18px}.node-onboarding{border-color:#3c6879;background:linear-gradient(125deg,#122f41,#102336)}.onboarding-steps{display:grid;grid-template-columns:1.2fr 1fr;gap:20px;margin-top:20px}.onboarding-steps>div{min-width:0;border:1px solid #315063;border-radius:12px;padding:18px}.onboarding-steps>div:last-child{grid-column:1/-1}.onboarding-steps strong{font-size:13px;color:#a5e1e4}.onboarding-steps p{font-size:11px;line-height:1.8;color:#a4c0d1;margin:12px 0 0}.onboarding-steps pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#081c2b;padding:12px;border-radius:8px;font-size:11px;line-height:1.8;color:#cee3ef}.onboarding-steps code{overflow-wrap:anywhere}.onboarding-steps input{width:100%}@media(max-width:900px){.onboarding-steps{grid-template-columns:1fr}}'''
JS = r'''
let cloudEnrollVersion=0;
$('cloud-enroll-file').addEventListener('change',()=>{cloudEnrollVersion++;showText('cloud-enroll-status','파일을 선택했습니다. 실제 노드의 공개키 지문과 비교하세요.');});
document.addEventListener('ops:locked',()=>{cloudEnrollVersion++;$('cloud-enroll-file').value='';showText('cloud-enroll-status','운영자 인증 후 등록할 수 있습니다.');});
$('cloud-enroll-form').addEventListener('submit',async event=>{
  event.preventDefault();cloudEnrollVersion++;
  const current=cloudOperation(()=>cloudEnrollVersion);
  try{
    current();const f=$('cloud-enroll-file').files[0];
    if(!f||f.size>16384)throw Error('16 KiB 이하의 공개 node-enrollment.json 파일을 선택하세요.');
    const enrollment=await cloudFile('cloud-enroll-file',current);current();
    const preview=await api('/api/ops/cloud/enroll/preview',{enrollment});current();
    const accepted=await confirmOperation({title:'DNS 노드 신뢰·등록',description:'자체 서명은 키 보유만 확인합니다. 아래 지문이 실제 장치에서 출력한 값인지 별도로 확인하세요. 기존 장치·키를 덮어쓰지 않습니다.',phrase:'ENROLL_NODE',facts:[['장치 ID',preview.device_id],['DNS 주소',preview.dns_address],['장치 이름',preview.label],['공개키 SHA-256',preview.key_id]],action:preview.already_registered?'기존 등록 확인':'확인 후 노드 등록'});
    current();if(!accepted)return;
    const result=await api('/api/ops/cloud/enroll',{enrollment,expected_key_id:preview.key_id,confirm:'ENROLL_NODE'});current();
    showText('cloud-enroll-status',result.already_registered?'동일한 장치가 이미 등록되어 있습니다. 로컬 전송 서비스를 확인하세요.':'공개키와 장치를 함께 등록했습니다. 아직 정상 적용으로 판단하지 않으며 실제 서명 보고를 기다립니다.');
    $('cloud-enroll-file').value='';await loadDeployment();
  }catch(error){if(error.stale)return;try{current();showText('cloud-enroll-status',error.message);}catch(_){}displayError(error);}
});
'''
