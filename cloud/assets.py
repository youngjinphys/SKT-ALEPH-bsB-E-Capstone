"""Reuse the original operations UI without modifying its local-token version."""
from functools import lru_cache
from pathlib import Path
import re
from policy_server.console_assets import HTML,CSS,JS
from .diagnostics import HTML as STORAGE_HTML,CSS as STORAGE_CSS,JS as STORAGE_JS
from .onboarding import HTML as ENROLL_HTML,CSS as ENROLL_CSS,JS as ENROLL_JS
from .tutorial import HTML as GUIDE_HTML,CSS as GUIDE_CSS,JS as GUIDE_JS
from .release_ui import HTML as RELEASE_HTML,CSS as RELEASE_CSS,JS as RELEASE_JS

def replace_once(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Console integration anchor changed')
    return text.replace(old,new,1)

@lru_cache(maxsize=2)
def assets(surface=""):
    if surface not in ("", "sites"): surface=""
    html=HTML.replace('/console.css','/dashboard/assets/console.css').replace('/console.js','/dashboard/assets/console.js')
    brand='<div class="brand"><div><strong>ALEPH<span class="brand-asterisk">✳</span></strong><small>PROTECTIVE DNS</small></div></div>'
    html=replace_once(html,brand,brand.replace('<div class="brand">','<a class="brand" href="/" aria-label="ALEPH PROTECTIVE DNS 홈">',1)[:-6]+'</a>')
    html=replace_once(html,'    <main class="content"',GUIDE_HTML+'\n    <main class="content"')
    html=html.replace('LOCAL CONTROL PLANE','VERCEL CONTROL PLANE').replace('로컬 게시 파일','게시 정책 저장소')
    html=re.sub(r'<form id="login-form">.*?</form>', '''<form id="login-form"><input id="token" type="hidden"><p id="cloud-login-message">Google 세션을 확인한 후 별도의 DNS 운영자 권한을 검사합니다.</p><button type="submit" class="button primary wide">현재 로그인으로 관제센터 연결 →</button></form><a href="/api/oauth?action=start&amp;next=/dashboard" class="button outline wide cloud-google">Google로 로그인 →</a><details class="cloud-login-help"><summary>처음 접속하시나요? 로그인 방법</summary><p>Google로 로그인한 뒤 이 페이지로 돌아옵니다. 이미 로그인했다면 ‘현재 로그인으로 관제센터 연결’을 누르세요.</p><p>관제 운영자 권한은 사이트 로그인과 별개입니다. 등록되지 않은 계정은 관리자에게 이메일 승인을 요청해야 합니다.</p><p>‘Google 로그인 설정 확인 필요’가 표시되면 관리자에게 인증 공급자 설정을 요청하세요. 로컬 콘솔의 액세스 토큰이나 임의 비밀번호는 이 페이지에서 사용하지 않습니다.</p></details><a href="/" class="text-button cloud-home">홈으로 돌아가기</a>''',html,count=1)
    html=html.replace('서버 로컬 토큰으로 인증합니다. 토큰은 브라우저 메모리에만 유지되며 저장하지 않습니다.','동일한 사이트의 Google 인증을 사용합니다. 로그인만으로 DNS 정책 권한이 부여되지는 않습니다.')
    html=html.replace('로컬 바인딩 · API 접근 제어 · DNS 무변경','HttpOnly 세션 · 운영자 승인 · 서명 검증')
    html=replace_once(html,'<div class="topbar-actions">','<div class="topbar-actions"><a href="/" class="quiet-button dashboard-home" aria-label="홈으로 이동"><svg class="dashboard-home-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M9 21v-8h6v8"/></svg><span class="dashboard-home-label">홈</span></a><a href="/capstone" class="quiet-button">발표 ↗</a><button id="cloud-logout" class="quiet-button" type="button">계정 로그아웃</button>')
    evidence='''<section class="surface cloud-tools"><div class="overline">EXTERNAL COLLECTOR / VERIFIED SNAPSHOT</div><h3>수집 자료를 검토 대기열로</h3><p class="muted-copy">외부 OpenPhish·GSB 수집기의 verified.json을 검사합니다. 변경 전 후보 수와 유효기간을 확인하고, 기존 승인은 별도 보관 후 초기화합니다.</p><form id="cloud-evidence-form"><label for="cloud-evidence">검증 결과 JSON · 최대 2 MiB</label><input id="cloud-evidence" type="file" accept=".json,application/json" required><button class="button outline" type="submit">검증 자료 미리보기</button></form><div id="cloud-evidence-preview" class="cloud-preview" hidden aria-live="polite"><h4>가져오기 전 확인</h4><div id="cloud-evidence-summary"></div><button id="cloud-evidence-commit" class="button primary" type="button">확인 후 가져오기</button></div></section>'''
    html=replace_once(html,'<div class="split-view">',evidence+'<div class="split-view">')
    controls='''<details class="surface cloud-tools" id="cloud-publication-tools"><summary>서명 정책 게시 · 공개키 신뢰 관리</summary><div class="overline">CLOUD TRUST & SIGNED PUBLICATION</div><h2>신뢰 공개키와 서명된 정책</h2><p class="muted-copy">정책 개인키는 업로드하지 마세요. 기존 서명 도구에서 생성한 서명 봉투만 게시할 수 있습니다. 게시 완료와 DNS 적용 완료는 별개입니다.</p><div class="dashboard-grid two-equal"><form id="cloud-key-form"><label for="cloud-key-role">공개키 용도</label><select id="cloud-key-role"><option value="node">DNS 상태 보고 장치</option><option value="policy">독립 정책 서명자</option></select><label for="cloud-key">Ed25519 공개키 PEM</label><textarea id="cloud-key" rows="4" maxlength="4096" placeholder="-----BEGIN PUBLIC KEY-----" required></textarea><label class="check-row"><input id="cloud-key-confirm" type="checkbox" required><span>별도 채널로 공개키 지문과 소유자를 확인했습니다.</span></label><button type="submit" class="button outline">공개키 지문 확인</button><p id="cloud-key-result" class="fine-print" role="status"></p></form><form id="cloud-publish-form"><label for="cloud-publish-device">배포 대상 장치 ID</label><input id="cloud-publish-device" value="edge-69" required><label for="cloud-publish-sequence">현재 게시 시퀀스 (최초는 0)</label><input id="cloud-publish-sequence" type="number" min="0" step="1" value="0" required><label for="cloud-policy">독립 서명자가 서명한 정책 봉투 JSON</label><input id="cloud-policy" type="file" accept=".json,application/json" required><label class="check-row"><input id="cloud-withdrawals" type="checkbox"><span>기존 차단 철회 또는 만료 단축 영향을 확인했습니다.</span></label><label class="check-row"><input id="cloud-rotation" type="checkbox"><span>정책 서명키 변경을 확인했습니다.</span></label><button type="submit" class="button primary">서명·변경 영향 미리보기</button></form></div><div id="cloud-publish-preview" class="cloud-preview" hidden aria-live="polite"><h4>게시 전 변경 영향</h4><div id="cloud-publish-summary"></div><button type="button" class="button primary" id="cloud-publish-commit">확인 후 서명 정책 게시</button></div></details>'''
    html=replace_once(html,'<div class="surface published-list-surface">',ENROLL_HTML+controls+'<div class="surface published-list-surface">')
    html=replace_once(html,'<section class="view" data-panel="audit" hidden>','<section class="view" data-panel="audit" hidden>'+STORAGE_HTML)
    html=replace_once(html,'<section id="draft-impact"',RELEASE_HTML+'<section id="draft-impact"')
    pin_form = '<form id="cloud-pin-form" hidden><h3>테스트 PIN 로그인</h3><p>공유 PIN은 개인 신원을 확인하지 않습니다. 15분 후 다시 로그인해야 합니다.</p><label for="cloud-pin">PIN (8~12자리)</label><input id="cloud-pin" type="password" inputmode="numeric" pattern="[0-9]{8,12}" minlength="8" maxlength="12" autocomplete="off" required><div id="cloud-extra-row" hidden><label for="cloud-access-code">추가 접근 코드</label><input id="cloud-access-code" type="password" maxlength="128" autocomplete="off"></div><button id="cloud-pin-submit" class="button primary wide" type="submit">테스트 PIN으로 로그인</button><p id="cloud-pin-message" role="status" aria-live="polite"></p></form>'
    html = html.replace('<details class="cloud-login-help">', pin_form + '<details class="cloud-login-help">') if '<details class="cloud-login-help">' in html else html.replace('<a href="/" class="text-button cloud-home">', pin_form + '<a href="/" class="text-button cloud-home">')
    script=JS.replace('/api/','/api/ops/').replace('credentials:"omit"','credentials:"same-origin"')
    script=script.replace('const headers={"Authorization":"Bearer "+activeToken};','const headers={};')
    script=script.replace('headers:{"Authorization":"Bearer "+activeToken}','headers:{}')
    start=script.index('$("login-form").addEventListener("submit",async(e)=>{')
    end=script.index('$("logout-button").addEventListener',start)
    script=script[:start]+'$("login-form").addEventListener("submit",async(e)=>{e.preventDefault();await cloudConnect();});\n'+script[end:]
    # Cloud diagnostics extend view lifecycle and audited actor presentation.
    # Exact anchors fail loudly if the shared controller contract changes.
    script=replace_once(script,'  refreshView(name).catch(displayError);',
                        '  document.dispatchEvent(new CustomEvent("ops:view",{detail:{view:name}}));\n  refreshView(name).catch(displayError);')
    script=replace_once(script,'node("strong","",item.event),','node("strong","",auditEventLabel(item.event)),')
    script=replace_once(script,'  const items=drafts.value,reviewed=reviewResult.value;',
                        '  const items=drafts.value,reviewed=reviewResult.value;\n  cloudDraftOptions(items);')
    script=replace_once(script,'    actions.append(preview);',
                        '    actions.append(preview);\n    const handoff=node("button","text-button","장치별 배포 준비 →");handoff.type="button";handoff.addEventListener("click",()=>openCloudHandoff(item.name));actions.append(handoff);')
    script=replace_once(script,'node("span","mono",item.draft||item.reference||item.version||item.fingerprint||"–"));',
                        'node("span","mono",auditReference(item)));')
    actions=Path(__file__).with_name('actions.js').read_text()
    if surface=='sites':
        start=actions.index('// Cloud adaptation:')
        end=actions.index('async function cloudFile(',start)
        actions=actions[:start]+Path(__file__).with_name('sites_actions.js').read_text()+'\n'+actions[end:]
        html=re.sub(r'<a href="/api/oauth[^>]+>.*?</a>', '<a href="/signin-with-chatgpt?return_to=%2Fdashboard" target="_top" class="button outline wide cloud-sites-signin">ChatGPT로 로그인 →</a>',html,count=1)
        html=replace_once(html,pin_form,'')
        html=re.sub(r'<details class="cloud-login-help">.*?</details>','<details class="cloud-login-help"><summary>처음 접속하시나요? 로그인 방법</summary><p>ChatGPT로 로그인한 뒤 현재 로그인으로 관제센터 연결을 누르세요. 기존 운영자 허용목록에 등록된 이메일만 접근할 수 있습니다.</p></details>',html,count=1)
        html=replace_once(html,'<button id="cloud-logout" class="quiet-button" type="button">계정 로그아웃</button>','<a id="cloud-logout" class="quiet-button" href="/signout-with-chatgpt?return_to=%2F" target="_top">계정 로그아웃</a>')
        html=html.replace('Google 세션을 확인한 후 별도의 DNS 운영자 권한을 검사합니다.','ChatGPT 로그인과 DNS 운영자 권한을 확인합니다.').replace('동일한 사이트의 Google 인증을 사용합니다.','동일한 Sites의 ChatGPT 인증을 사용합니다.').replace('VERCEL CONTROL PLANE','SITES CONTROL PLANE').replace('HttpOnly 세션','ChatGPT 인증')
        html=html.replace('/dashboard/assets/console.css','/dashboard/assets/console.css?surface=sites').replace('/dashboard/assets/console.js','/dashboard/assets/console.js?surface=sites')
        script=script.replace('인증에 실패했습니다. 액세스 토큰을 확인하세요.','ChatGPT로 로그인한 뒤 관제센터에 다시 연결하세요.')
        pin_script=''
    else:
        pin_script=Path(__file__).with_name('pin_actions.js').read_text()
    script+='\n'+STORAGE_JS+'\n'+pin_script+'\n'+actions
    css=CSS+'\n'+STORAGE_CSS+'\n.dashboard-home{gap:7px;min-width:64px}.dashboard-home-icon{flex:0 0 18px;width:18px;height:18px}.cloud-tools{margin-bottom:22px}.cloud-tools input[type=file]{padding:10px;color:inherit;max-width:100%}.cloud-tools form>.button{margin-top:15px}.cloud-google{margin-top:12px}.cloud-home{display:block;margin-top:20px;text-align:center}.cloud-tools p[role=status]{overflow-wrap:anywhere}.cloud-tools form{min-width:0}\n'
    return html,css+'\n'+ENROLL_CSS+'\n'+GUIDE_CSS+'\n'+RELEASE_CSS,script+'\n'+ENROLL_JS+'\n'+GUIDE_JS+'\n'+RELEASE_JS
