"""Dashboard-only, read-only usage guide. Never invokes an operation or login."""

HTML = r'''<button id="cloud-guide-open" class="cloud-guide-launcher" type="button" aria-controls="cloud-guide" aria-expanded="false" aria-haspopup="dialog"><span aria-hidden="true">?</span> 사용방법</button>
<section id="cloud-guide" class="cloud-guide" role="dialog" aria-modal="false" aria-labelledby="cloud-guide-title" aria-describedby="cloud-guide-description" hidden>
  <header class="cloud-guide-header"><span class="cloud-guide-label">ALEPH / QUICK GUIDE</span><button id="cloud-guide-close" class="cloud-guide-close" type="button" aria-label="사용방법 닫기">닫기 <span aria-hidden="true">×</span></button></header>
  <div class="cloud-guide-body">
    <div class="cloud-guide-step"><span id="cloud-guide-count"></span><span id="cloud-guide-section"></span></div>
    <progress id="cloud-guide-progress" max="7" value="1" aria-label="사용방법 진행 단계"></progress>
    <h2 id="cloud-guide-title" tabindex="-1"></h2>
    <p id="cloud-guide-description"></p>
    <ol id="cloud-guide-instructions"></ol>
    <p id="cloud-guide-boundary" class="cloud-guide-boundary"></p>
    <button id="cloud-guide-view" class="button outline" type="button"></button>
  </div>
  <footer class="cloud-guide-footer"><button id="cloud-guide-prev" class="button outline" type="button">← 이전</button><span>Esc로 닫기 · 언제든 다시 열기</span><button id="cloud-guide-next" class="button primary" type="button">다음 →</button></footer>
</section>'''

CSS = r'''
/* The brand link and tutorial exist only in /dashboard's assembled assets. */
a.brand{color:inherit;text-decoration:none;border-radius:10px}a.brand:hover strong{color:var(--cyan)}
a.brand:focus-visible{outline:2px solid var(--cyan);outline-offset:6px}
.cloud-guide-launcher,.cloud-guide{position:fixed;right:max(20px,env(safe-area-inset-right));bottom:max(20px,env(safe-area-inset-bottom));z-index:45}
.cloud-guide-launcher{display:inline-flex;gap:10px;align-items:center;min-height:48px;padding:10px 17px;border:1px solid #72d8e8;border-radius:999px;background:#102e42;color:#e4fbff;font-size:13px;font-weight:750;box-shadow:0 8px 30px #0007}
.cloud-guide-launcher>span{display:grid;place-items:center;width:24px;height:24px;border:1px solid #72d8e8;border-radius:50%;color:#91eef2;font-size:15px}
.cloud-guide-launcher:focus-visible{z-index:46}
.cloud-guide{width:390px;max-width:calc(100vw - 32px);max-height:calc(100vh - 40px);max-height:calc(100dvh - 40px);display:flex;flex-direction:column;border:1px solid #5296ad;border-radius:18px;background:#0b2335;color:#edf8fc;box-shadow:0 20px 80px #0009;overflow:hidden}
.cloud-guide-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 14px 9px 20px;border-bottom:1px solid #2c5165;background:#113147;flex:none}
.cloud-guide-label{font-size:10px;letter-spacing:.13em;font-weight:800;color:#95e6ed}
.cloud-guide-close{display:flex;align-items:center;gap:10px;border:0;background:transparent;color:#c8e2eb;font-size:12px;min-height:44px;padding:8px}
.cloud-guide-close span{font-size:22px;line-height:1}
.cloud-guide-body{padding:19px 20px 20px;overflow-y:auto;overscroll-behavior:contain;min-height:0}
.cloud-guide-step{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px;font-size:11px;font-weight:700;color:#a8cbd8}
#cloud-guide-count{color:#7ee4e9;font-variant-numeric:tabular-nums}
#cloud-guide-progress{display:block;appearance:none;width:100%;height:3px;border:0;border-radius:3px;overflow:hidden;background:#294c60;margin-bottom:20px;color:#7ee4e9}
#cloud-guide-progress::-webkit-progress-bar{background:#294c60}#cloud-guide-progress::-webkit-progress-value{background:#7ee4e9}#cloud-guide-progress::-moz-progress-bar{background:#7ee4e9}
.cloud-guide h2{font-size:22px;line-height:1.35;letter-spacing:-.035em;margin:0 0 12px;outline-offset:4px}
.cloud-guide p{font-size:13px;line-height:1.8;color:#c0d6e1;margin:0 0 15px;word-break:keep-all;overflow-wrap:anywhere}
.cloud-guide ol{padding-left:20px;margin:0 0 17px;color:#d4e5ed;font-size:12px;line-height:1.8}
.cloud-guide li{padding-left:3px;margin:0 0 7px;word-break:keep-all;overflow-wrap:anywhere}
.cloud-guide li::marker{color:#79dbe2;font-weight:750}
.cloud-guide .cloud-guide-boundary{border-left:2px solid #d1ac75;padding:9px 12px;background:#163044;color:#e3d1b2;font-size:11px;line-height:1.75;border-radius:0 6px 6px 0}
.cloud-guide .button{min-height:44px;font-size:12px}.cloud-guide .button:hover{transform:none}
#cloud-guide-view{width:100%;justify-content:space-between}
.cloud-guide-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:13px 16px;border-top:1px solid #2c5165;background:#0d293d;flex:none}
.cloud-guide-footer>span{font-size:9px;color:#a7bfce;line-height:1.6;max-width:95px;text-align:center;word-break:keep-all}
.cloud-guide-footer .button{padding:9px 12px;white-space:nowrap}
[data-cloud-guide-target]{outline:2px dashed #7ee4e9!important;outline-offset:4px}
.toast{bottom:84px;z-index:70}
body.cloud-guide-visible .toast{top:20px;bottom:auto;max-height:110px;overflow-y:auto}
body:has(.toast:not([hidden])) .cloud-guide{max-height:min(70vh,calc(100vh - 150px));max-height:min(70dvh,calc(100dvh - 150px))}
.main-column>.bottom-bar{padding-bottom:88px}
@media(max-width:700px){.cloud-guide-launcher{position:static;align-self:flex-end;margin:12px 16px 0;box-shadow:none}.cloud-guide{right:max(16px,env(safe-area-inset-right));bottom:max(16px,env(safe-area-inset-bottom));width:390px;max-height:70vh;max-height:70dvh}.cloud-guide-body{padding:16px}.cloud-guide h2{font-size:20px}.cloud-guide-header{padding-left:16px}.cloud-guide-footer{padding:10px 12px;gap:8px}}
@media(max-height:500px){.cloud-guide{max-height:calc(100vh - 24px);max-height:calc(100dvh - 24px);bottom:12px}.cloud-guide-header{padding-block:2px}.cloud-guide-footer{padding-block:6px}}
@media(forced-colors:active){.cloud-guide,.cloud-guide-header,.cloud-guide-footer,.cloud-guide-launcher,.cloud-guide .cloud-guide-boundary{background:Canvas;color:CanvasText;border-color:CanvasText}.cloud-guide p,.cloud-guide li,.cloud-guide li::marker,.cloud-guide-label,.cloud-guide-step,#cloud-guide-count,.cloud-guide-close,.cloud-guide-footer>span,.cloud-guide-launcher>span{color:CanvasText}[data-cloud-guide-target]{outline-color:Highlight!important}}
'''

JS = r'''
// A non-modal, explicitly opened guide. Steps never submit forms, import files,
// approve reviews, register keys/nodes, publish policies, or alter DNS settings.
(() => {
  const byId=id=>document.getElementById(id);
  const guide=byId('cloud-guide'),launcher=byId('cloud-guide-open');
  const steps=[
    {section:'시작하기',title:'관제 흐름, 차근차근',view:null,
      description:'검토 → 초안 → 독립 서명 → 게시 → 실제 노드 확인. 각 단계의 의미를 먼저 살펴보세요.',
      instructions:['이전·다음으로 사용방법을 읽습니다. 화면은 자동으로 이동하지 않습니다.','“해당 화면 보기”를 누르면 메뉴로 이동합니다. 안내를 닫아도 현재 화면은 유지됩니다.','상단의 집 아이콘 “홈” 또는 왼쪽 위 ALEPH✳ PROTECTIVE DNS를 누르면 홈(/)으로 돌아갑니다.'],
      boundary:'이 가이드는 설명만 제공합니다. 승인·등록·게시 작업은 실행하지 않습니다.'},
    {section:'운영 개요',title:'수치보다 먼저, 상태 확인',view:'overview',
      description:'정책 근거와 DNS 노드의 최신 관측을 한 화면에서 확인합니다.',
      instructions:['검토 후보·승인 기록·미서명 초안 수를 확인합니다. 차단 성공 횟수와는 다릅니다.','관측 패널에서 장치·시간 범위·지표를 선택하고 필요하면 자동 조회를 일시정지합니다.','보고 시각과 “미확인” 표시를 확인하세요. 누락된 관측은 정상으로 판단하지 않습니다.'],
      boundary:'게시 정책 확인, 노드 내부 DNS 검증, LAN 전체 보호는 서로 다른 상태입니다.'},
    {section:'위협 검토',title:'근거와 차단 범위를 검토',view:'reviews',
      description:'외부 수집기의 verified.json을 미리 본 뒤, 후보별 근거를 사람이 확인합니다.',
      instructions:['검증 결과 JSON을 선택하고 후보 수·유효기간을 먼저 미리 봅니다.','검색·필터로 후보를 찾아 위협 유형, 증거 만료, SUBTREE 영향을 확인합니다.','실제 승인은 검토자 식별명과 구체적인 승인 근거를 입력한 뒤 별도로 수행합니다.'],
      boundary:'새 검증 자료를 가져오면 기존 승인은 별도 보관 후 초기화됩니다. 가져오기 자체가 DNS를 차단하지 않습니다.'},
    {section:'위험도 제안',title:'제안 결과와 집행은 별개',view:'engine',
      description:'도메인에 대한 위험도 제안을 확인하는 공간입니다.',
      instructions:['현재 제안 엔진 설정을 먼저 확인합니다.','도메인을 입력해 평가 결과와 근거를 확인합니다.','목록·임계값을 바꿀 때는 저장 전 변경 내용을 직접 검토합니다.'],
      boundary:'위험도 제안이나 엔진 설정 저장만으로 DNS 차단 정책이 게시·적용되지는 않습니다.'},
    {section:'DNS 정책 초안',title:'승인된 근거로 미서명 초안',view:'drafts',
      description:'유효한 검토 근거로 정책 초안을 만들고 변경 영향을 확인합니다.',
      instructions:['검토 근거의 유효성을 확인하고 전체 교체·사용자 안내·차단 범위를 검토합니다.','초안 생성 후 목록에서 다운로드와 변경 영향 확인 기능을 사용합니다.','정책 서명은 독립 서명 절차로 수행하고, 개인키는 업로드하지 않습니다.'],
      boundary:'초안은 미서명 JSON입니다. 생성·다운로드는 서명·게시·DNS 적용 완료를 뜻하지 않습니다.'},
    {section:'배포 현황',title:'연결된 노드의 보고까지 확인',view:'deployment',
      description:'게시된 정책과 장치가 보낸 서명 보고를 각각 확인합니다.',
      instructions:['처음 연결하는 장치는 “노드 연결 파일 등록”을 펼쳐 실제 노드에서 만든 공개 등록 파일을 확인합니다.','게시 대상 장치를 선택하고 정책 시퀀스·해시·서명 상태를 비교합니다.','장치 보고 시각과 로컬 DNS 응답 비교를 확인합니다. 보고가 없으면 정상으로 간주하지 않습니다.'],
      boundary:'장치 등록은 DNS 설정을 바꾸지 않습니다. 서명 정책 게시·키 신뢰 변경은 별도 확인이 필요하며 LAN 보호도 별도 검증합니다.'},
    {section:'작업 기록',title:'무엇이 바뀌었는지 돌아보기',view:'audit',
      description:'운영 저장소의 여유와 조회 가능한 작업 이력을 확인합니다.',
      instructions:['운영 저장소 여유에서 사용량과 진단 상태를 확인합니다.','작업 기록의 시각·이벤트·참조를 확인해 변경 맥락을 살펴봅니다.','필요할 때 “사용방법”으로 이 안내를 다시 열 수 있습니다.'],
      boundary:'작업 이력은 변조 방지된 승인 증명이 아니며, 저장소 진단은 DNS 보호 상태와 다릅니다.'}
  ];
  let index=0,returnFocus=null;
  const connected=()=>!byId('authorized').hidden;
  function clearTarget(){document.querySelectorAll('[data-cloud-guide-target]').forEach(el=>el.removeAttribute('data-cloud-guide-target'));}
  function markTarget(){
    clearTarget();
    if(guide.hidden)return;
    const step=steps[index];
    const target=connected()?(step.view?document.querySelector('[data-view="'+step.view+'"]'):document.querySelector('a.brand')):byId('login-view');
    if(target)target.setAttribute('data-cloud-guide-target','');
  }
  function render(focus=false){
    const step=steps[index],isConnected=connected();
    byId('cloud-guide-count').textContent=String(index+1).padStart(2,'0')+' / '+String(steps.length).padStart(2,'0');
    byId('cloud-guide-section').textContent=step.section;
    byId('cloud-guide-progress').max=steps.length;byId('cloud-guide-progress').value=index+1;
    byId('cloud-guide-title').textContent=step.title;
    byId('cloud-guide-description').textContent=index===0&&!isConnected?'먼저 Google 로그인 후 승인된 운영자 권한으로 연결하세요. 테스트 PIN은 관리자가 활성화한 경우에만 사용할 수 있습니다.':step.description;
    const list=byId('cloud-guide-instructions');list.replaceChildren();
    step.instructions.forEach(text=>{const li=document.createElement('li');li.textContent=text;list.append(li);});
    byId('cloud-guide-boundary').textContent=step.boundary;
    byId('cloud-guide-prev').disabled=index===0;
    byId('cloud-guide-next').textContent=index===steps.length-1?'가이드 마침 ✓':'다음 →';
    const viewButton=byId('cloud-guide-view');viewButton.hidden=!step.view;viewButton.disabled=!isConnected;
    viewButton.textContent=isConnected?step.section+' 화면 보기 →':'운영자 연결 후 이동 가능';
    markTarget();
    if(focus){byId('cloud-guide-title').focus({preventScroll:true});guide.querySelector('.cloud-guide-body').scrollTop=0;}
  }
  function close(restore=true){
    if(guide.hidden)return;
    guide.hidden=true;launcher.hidden=false;launcher.setAttribute('aria-expanded','false');
    document.body.classList.remove('cloud-guide-visible');clearTarget();
    if(restore){const target=returnFocus?.isConnected&&!returnFocus.closest('[hidden]')?returnFocus:launcher;target.focus({preventScroll:true});}
    returnFocus=null;
  }
  launcher.addEventListener('click',()=>{
    if(!guide.hidden)return;
    returnFocus=document.activeElement;guide.hidden=false;launcher.hidden=true;launcher.setAttribute('aria-expanded','true');
    document.body.classList.add('cloud-guide-visible');render(true);
  });
  byId('cloud-guide-close').addEventListener('click',()=>close());
  byId('cloud-guide-prev').addEventListener('click',()=>{if(index>0){index--;render(true);}});
  byId('cloud-guide-next').addEventListener('click',()=>{if(index===steps.length-1){index=0;close();}else{index++;render(true);}});
  byId('cloud-guide-view').addEventListener('click',()=>{
    const step=steps[index];if(!connected()||!step.view)return;
    // Only explicit menu navigation uses the shared read-only view lifecycle.
    // Collapse first so a mobile HUD cannot obscure the newly selected screen.
    close(false);
    if(currentView!==step.view)navigateTo(step.view);
    else byId('page-title').focus({preventScroll:false});
  });
  document.addEventListener('keydown',event=>{
    if(event.key!=='Escape'||guide.hidden||document.querySelector('dialog[open]'))return;
    event.preventDefault();close();
  });
  document.addEventListener('ops:locked',()=>{index=0;close();});
  document.addEventListener('ops:view',()=>{if(!guide.hidden)render();});
})();
'''
