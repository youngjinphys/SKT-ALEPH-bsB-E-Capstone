"""Offline browser acceptance of local + /dashboard adapters using synthetic data.

A loopback HTTP transport binding is used so Chromium's managed network policy
need not be weakened. Real API handlers/storage are exercised, not canned UI
JSON. No production session, credential, provider or external site is used.
"""
from pathlib import Path
import http.client,json,os,re,subprocess,sys,time
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from cloud.assets import assets
from policy_server.console_assets import HTML,CSS,JS
from policy_server import intel
from playwright.sync_api import sync_playwright
OUT=Path(os.environ.get('ALEPH_SCREENSHOTS','/tmp/aleph-browser-artifacts'));OUT.mkdir(parents=True,exist_ok=True)

def request(port,url,options=None):
    options=options or {};headers=dict(options.get('headers',{}));method=options.get('method','GET')
    if method=='POST':headers['Origin']=f'http://127.0.0.1:{port}'
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=20)
    conn.request(method,url,body=options.get('body'),headers=headers)
    reply=conn.getresponse();result=dict(status=reply.status,body=reply.read().decode(),headers=dict(reply.getheaders()));conn.close();return result

def main():
    fixture=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('console_fixture.py'))],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if fixture.poll() is not None:raise RuntimeError(fixture.stderr.read().decode())
            try:
                if request(18766,'/dashboard')['status']==200:break
            except OSError:time.sleep(.05)
        assertions=[]
        with sync_playwright() as p:
            opts={'headless':True,'args':['--no-sandbox']}
            if os.getenv('CHROMIUM_PATH'):opts['executable_path']=os.environ['CHROMIUM_PATH']
            browser=p.chromium.launch(**opts)
            for mode,port in [('cloud',18766),('local',18765)]:
                page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_default_timeout(4000)
                html,css,js=assets() if mode=='cloud' else (HTML,CSS,JS)
                html=re.sub(r'<link[^>]+href="/(?:dashboard/assets/)?console.css"[^>]*>','',html)
                html=re.sub(r'<script[^>]+src="/(?:dashboard/assets/)?console.js"[^>]*></script>','',html)
                page.expose_binding('__testFetch',lambda source,url,options:request(port,url,options))
                page.set_content(html,wait_until='domcontentloaded');page.add_style_tag(content=css)
                page.add_script_tag(content="window.fetch=async(url,opts)=>{const r=await window.__testFetch(String(url),opts||{});return new Response(r.body,{status:r.status,headers:r.headers});};")
                page.add_script_tag(content=js)
                if mode=='local':
                    page.locator('#token').fill('a'*48);page.locator('#login-form button').click()
                page.wait_for_selector('#authorized:not([hidden])')
                page.wait_for_selector('body[data-mode='+mode+']')
                assert page.locator('#runtime-label').inner_text();assertions.append(mode+': capabilities')
                page.wait_for_selector('#obs-latency-chart svg')
                assert page.locator('#obs-udp').inner_text()!='—'
                assert page.locator('#obs-latency-chart .obs-point').count()>20
                page.locator('#obs-window').select_option('15')
                page.wait_for_function('document.querySelectorAll("#obs-table tr").length < 20')
                page.locator('#obs-metric').select_option('memory_used_pct')
                assert page.locator('#obs-metric-chart svg').count()==1
                page.locator('#obs-pause').click()
                assert page.locator('#obs-pause').get_attribute('aria-pressed')=='true'
                assert '일시정지' in page.locator('#obs-live').inner_text()
                page.locator('#obs-pause').click()
                page.locator('#obs-device').select_option('edge-70')
                assert page.locator('#obs-udp').inner_text()=='—'
                assert page.locator('#obs-latency-chart svg').count()==0
                page.locator('#obs-device').select_option('edge-69')
                page.locator('#obs-window').select_option('60')
                page.wait_for_function("document.querySelector('#obs-cpu')?.textContent.includes('60')")
                for chart in ('obs-cpu-chart','obs-host-chart','obs-traffic-chart','obs-quality-chart'):
                    assert page.locator('#'+chart+' svg').count()==1, mode+': missing '+chart
                assert 'eth0' in page.locator('#obs-interface').inner_text()
                page.locator('#obs-quality-target').select_option('upstream')
                assert page.locator('#obs-quality-chart circle').count()>0
                page.locator('#obs-quality-target').select_option('local')
                assert page.locator('#obs-resource-table tr').count()>0
                assertions.append(mode+': CPU/network rates and independent quality charts')
                page.locator('#observatory').scroll_into_view_if_needed()
                page.screenshot(path=str(OUT/f'{mode}-telemetry-desktop.png'),full_page=True)
                page.locator('#observatory').screenshot(path=str(OUT/f'{mode}-telemetry-detail.jpg'),type='jpeg',quality=70)
                page.emulate_media(reduced_motion='reduce')
                assert page.locator('#obs-live').evaluate("e=>getComputedStyle(e,'::before').animationName")=='none'
                page.emulate_media(reduced_motion='no-preference')
                assertions.append(mode+': telemetry charts/filter/pause/missing/reduced-motion')

                page.locator('[data-view=reviews]').click();page.wait_for_timeout(200)
                if mode=='cloud':
                    assert page.locator('.intel-refresh-panel').is_hidden()
                    assert page.locator('#cloud-evidence-form').is_visible()
                    # Real preview endpoint, native modal, cancellation and confirmation.
                    now=datetime.now(timezone.utc);url='https://new-fixture-threat.example.org/login'
                    col=intel.collect_urls((url+'\n').encode(),source='openphish',fetched_at=now)
                    verified=intel.verify_collected(col,'test-key',checked_at=now,fetch=lambda *a,**k:json.dumps({'threats':[{'url':url,'threatTypes':['SOCIAL_ENGINEERING']}],'cacheDuration':'300s'}).encode())
                    page.locator('#cloud-evidence').set_input_files({'name':'verified.json','mimeType':'application/json','buffer':json.dumps(verified).encode()})
                    page.locator('#cloud-evidence-form button[type=submit]').click()
                    page.wait_for_selector('#cloud-evidence-preview:not([hidden])')
                    page.locator('#cloud-evidence-commit').click()
                    page.wait_for_selector('#ops-confirm[open]')
                    assert page.locator('#ops-confirm-submit').is_disabled()
                    page.screenshot(path=str(OUT/'cloud-import-confirmation.png'))
                    page.keyboard.press('Escape');assert not page.locator('#ops-confirm').is_visible()
                    assert len(json.loads(request(port,'/api/ops/reviews')['body'])['items'])==4
                    page.locator('#cloud-evidence-commit').click();page.locator('#ops-confirm-input').fill('IMPORT_VERIFIED');page.locator('#ops-confirm-submit').click()
                    page.wait_for_function('document.querySelectorAll(".review-item").length===1')
                    assert not json.loads(request(port,'/api/ops/reviews')['body'])['items'][0]['approved']
                    assertions.append('cloud: preview/cancel/import/reset approvals')
                else:
                    assert page.locator('.intel-refresh-panel').is_visible()
                    page.locator('#reset-reviews').click();page.wait_for_selector('#ops-confirm[open]');page.keyboard.press('Escape')
                    assertions.append('local: reset modal cancel')
                page.evaluate('document.activeElement?.blur();window.scrollTo({top:0,left:0,behavior:"instant"})')
                page.screenshot(path=str(OUT/f'{mode}-reviews-desktop.png'),full_page=True)
                page.locator('[data-view=deployment]').click();page.wait_for_timeout(150)
                assert page.locator('[data-panel=deployment] #nodes-list').count()==1
                assert page.locator('[data-panel=deployment] #published-list').count()==1
                page.locator('#node-search').fill('edge-70');page.wait_for_function('document.querySelectorAll(".node-card").length===1')
                assert 'edge-70' in page.locator('.node-card').inner_text()
                page.locator('#node-search').fill('');page.locator('#node-state-filter').select_option('attention')
                page.wait_for_function('document.querySelectorAll(".node-card").length===1')
                page.locator('#node-state-filter').select_option('all');assertions.append(mode+': node search/filter')
                # Let a real automatic polling cycle wait on its reads. The
                # last verified DOM must stay in place throughout the wait,
                # without enabling actions against unchecked observations.
                page.evaluate("""window.__normalFetch=window.fetch;window.__pendingReads=[];
                  window.__oldNode=document.querySelector('.node-card');
                  window.__oldRule=document.querySelector('.published-row');
                  window.fetch=(url,opts)=>String(url).includes('/deployment')||String(url).endsWith('/nodes')
                    ?new Promise(resolve=>window.__pendingReads.push(async()=>resolve(await window.__normalFetch(url,opts))))
                    :window.__normalFetch(url,opts);""")
                page.wait_for_selector('[data-panel=deployment][data-read-state=refreshing]',timeout=15000)
                assert page.locator('#deployment-sequence').inner_text()=='12'
                assert page.locator('.node-card').count()==2
                assert page.evaluate("window.__oldNode===document.querySelector('.node-card') && window.__oldRule===document.querySelector('.published-row')")
                assert all(button.is_disabled() for button in page.locator('#nodes-list button').all())
                assert '마지막 조회' in page.locator('#deployment-observed').inner_text()
                page.screenshot(path=str(OUT/f'{mode}-background-refresh.png'),full_page=True)
                page.evaluate('Promise.all(window.__pendingReads.map(release=>release()))')
                page.wait_for_selector('[data-panel=deployment]:not([aria-busy])')
                assert page.evaluate("window.__oldNode===document.querySelector('.node-card') && window.__oldRule===document.querySelector('.published-row')")
                assert all(button.is_enabled() for button in page.locator('#nodes-list button').all())
                page.evaluate('window.fetch=window.__normalFetch')
                assertions.append(mode+': automatic refresh keeps identical rows and disables stale mutations')
                # A failed node read must remove stale successful reports while
                # preserving the independently verified publication response.
                page.evaluate("""window.__normalFetch=window.fetch;window.fetch=async(url,opts)=>String(url).endsWith('/nodes')?new Response(JSON.stringify({error:'synthetic node outage'}),{status:503,headers:{'Content-Type':'application/json'}}):window.__normalFetch(url,opts)""")
                page.locator('#deployment-refresh').click();page.wait_for_timeout(300)
                assert page.locator('.node-card[data-tone="good"]').count()==0, mode+': stale green reports after node outage'
                assert page.locator('#deployment-sequence').inner_text()=='12', mode+': independent publication lost'
                assert page.locator('#nodes-read-error').is_visible()
                page.locator('#node-search').fill('anything')
                assert '확인할 수 없습니다' in page.locator('#nodes-list').inner_text()
                page.locator('#node-search').fill('')
                page.screenshot(path=str(OUT/f'{mode}-partial-outage.png'),full_page=True)
                page.evaluate('window.fetch=window.__normalFetch')
                page.locator('#nodes-refresh').click()
                page.wait_for_function('document.querySelectorAll(".node-card").length===2')
                assert page.locator('#nodes-read-error').is_hidden()
                assertions.append(mode+': partial node outage fails closed and recovers')
                # Selected-target publication must not keep showing the default.
                page.locator('#deployment-device-select').select_option('edge-70')
                page.wait_for_function('document.getElementById("deployment-device").textContent==="edge-70"')
                assert page.locator('#deployment-sequence').inner_text()=='5'
                assert '보고 없음' in page.locator('#edge-apply-state').inner_text()
                page.locator('#deployment-device-select').select_option('edge-69')
                page.wait_for_function('document.getElementById("deployment-device").textContent==="edge-69"')
                assert page.locator('#deployment-sequence').inner_text()=='12'
                assert page.locator('#fleet-read-summary').inner_text()=='1 / 2개 DNS 응답 검증'
                assertions.append(mode+': target-specific publication and truthful fleet summary')
                # A slower response for the previous selection cannot repaint
                # the newly selected node's proof or policy rules.
                page.evaluate("""window.__normalFetch=window.fetch;window.__delayed=false;window.fetch=(url,opts)=>{
                  if(String(url).endsWith('/deployment/edge-69')&&!window.__delayed){window.__delayed=true;return new Promise(resolve=>window.__releaseOld=async()=>resolve(await window.__normalFetch(url,opts)));}
                  return window.__normalFetch(url,opts);
                };""")
                page.locator('#deployment-device-select').select_option('edge-70')
                page.wait_for_function('document.getElementById("deployment-sequence").textContent==="5"')
                page.locator('#deployment-device-select').select_option('edge-69')
                page.wait_for_function('typeof window.__releaseOld==="function"')
                page.locator('#deployment-device-select').select_option('edge-70')
                page.wait_for_function('document.getElementById("deployment-sequence").textContent==="5"')
                page.evaluate('window.__releaseOld()');page.wait_for_timeout(120)
                assert page.locator('#deployment-device').inner_text()=='edge-70'
                assert page.locator('#deployment-sequence').inner_text()=='5'
                page.evaluate('window.fetch=window.__normalFetch')
                page.locator('#deployment-device-select').select_option('edge-69')
                page.wait_for_function('document.getElementById("deployment-sequence").textContent==="12"')
                assertions.append(mode+': stale target response ignored')
                page.evaluate("""window.__normalFetch=window.fetch;window.fetch=async(url,opts)=>String(url).includes('/deployment')?new Response(JSON.stringify({error:'synthetic publisher outage'}),{status:503,headers:{'Content-Type':'application/json'}}):window.__normalFetch(url,opts)""")
                page.locator('#deployment-refresh').click()
                page.wait_for_selector('#publication-read-error:not([hidden])')
                assert page.locator('#deployment-sequence').inner_text()=='–'
                assert page.locator('.published-row').count()==0
                assert page.locator('.node-card').count()==2
                page.evaluate('window.fetch=window.__normalFetch')
                page.locator('#deployment-refresh').click()
                page.wait_for_function('document.getElementById("deployment-sequence").textContent==="12"')
                assertions.append(mode+': publication outage clears proof and preserves node read')
                # Collapsed enrollment remains keyboard-accessible and belongs
                # to this view rather than leaking onto unrelated pages.
                page.locator('.node-enrollment summary').focus();page.keyboard.press('Enter')
                assert page.locator('#node-register-form').is_visible()
                page.locator('.node-enrollment summary').press('Enter')
                assert page.locator('#node-register-form').is_hidden()


                page.locator('#toast').evaluate('element=>element.hidden=true')
                page.evaluate('document.activeElement?.blur();window.scrollTo({top:0,left:0,behavior:"instant"})');page.wait_for_timeout(120)
                page.screenshot(path=str(OUT/f'{mode}-deployment-desktop.png'),full_page=True)
                for width in (320,390,768):
                    page.set_viewport_size({'width':width,'height':844});page.wait_for_timeout(150)
                    overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    if overflow:
                        print(page.evaluate('''[...document.querySelectorAll('body *')].map(el=>({tag:el.tagName,id:el.id,cls:el.className,rect:el.getBoundingClientRect().toJSON()})).filter(x=>x.rect.width>0&&(x.rect.right>innerWidth+1||x.rect.left< -1)).slice(0,15)'''))
                    assert not overflow,f'{mode}: overflow {width}'
                    page.evaluate('document.activeElement?.blur();window.scrollTo({top:0,left:0,behavior:"instant"})');page.wait_for_timeout(180)
                    if width<=390:
                        for item in page.locator('[data-view]').all():
                            box=item.bounding_box()
                            assert box and box['x']>=0 and box['x']+box['width']<=width and box['height']>=44,f'{mode}: hidden/small navigation target'
                        status=page.locator('#deployment-state').bounding_box()
                        assert status and status['y']<740,f'{mode}: mobile hides actual policy status below excessive header'
                    page.screenshot(path=str(OUT/f'{mode}-deployment-{width}.png'),full_page=False)
                    assertions.append(mode+f': responsive {width}')
                page.set_viewport_size({'width':1440,'height':1000});page.locator('[data-view=overview]').click();page.wait_for_timeout(150)
                page.evaluate('document.activeElement?.blur();window.scrollTo({top:0,left:0,behavior:"instant"})')
                page.screenshot(path=str(OUT/f'{mode}-overview-desktop.png'),full_page=True)
                assert page.locator('#nodes-list').is_hidden()
                page.evaluate("""window.__normalFetch=window.fetch;window.fetch=async(url,opts)=>String(url).endsWith('/overview')?new Response(JSON.stringify({error:'synthetic overview outage'}),{status:503,headers:{'Content-Type':'application/json'}}):window.__normalFetch(url,opts)""")
                page.locator('#refresh-button').click()
                page.wait_for_selector('#overview-read-error:not([hidden])')
                assert page.locator('#fleet-correlated').inner_text()=='–'
                assert page.locator('#stat-candidates').inner_text()=='–'
                assert '미확인' in page.locator('#overview-deploy-state').inner_text()
                page.evaluate('window.fetch=window.__normalFetch')
                page.locator('#refresh-button').click()
                page.wait_for_function('document.getElementById("stat-candidates").textContent!=="–"')
                assertions.append(mode+': overview outage clears stale metrics')

                for width in (390,768):
                    page.set_viewport_size({'width':width,'height':844});page.wait_for_timeout(120)
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), f'{mode}: telemetry overflow {width}'
                    page.locator('#observatory').scroll_into_view_if_needed()
                    page.screenshot(path=str(OUT/f'{mode}-telemetry-{width}.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':1000})

                if mode=='cloud':
                    page.locator('[data-view=audit]').click()
                    page.wait_for_selector('#storage-panel[data-state="NORMAL"]')
                    assert page.locator('#storage-meters').is_visible()
                    assert 'fixture@example.org' in page.locator('#audit-list').inner_text()
                    page.screenshot(path=str(OUT/'cloud-storage-audit-desktop.png'),full_page=True)
                    page.evaluate('''window.__healthyFetch=window.fetch;window.fetch=async(url,opts)=>String(url).endsWith('/cloud/storage')?new Response(JSON.stringify({error:'synthetic outage'}),{status:503,headers:{'Content-Type':'application/json'}}):window.__healthyFetch(url,opts)''')
                    page.locator('#storage-reload').click()
                    page.wait_for_selector('#storage-panel[data-state="UNAVAILABLE"]')
                    assert page.locator('#storage-meters').is_hidden()
                    assert '확인할 수 없습니다' in page.locator('#storage-state').inner_text()
                    page.evaluate('window.fetch=window.__healthyFetch')
                    assertions.append('cloud: storage diagnostics, actor identity and fail-closed outage')
                page.locator('#logout-button').click();page.wait_for_selector('#login-view:not([hidden])')
                assert page.locator('#deployment-sequence').text_content()=='–'
                assert page.locator('#stat-candidates').text_content()=='–'
                assert page.locator('.node-card').count()==0
                assert page.locator('.published-row').count()==0
                assert page.locator('#audit-list').text_content()==''
                assert not page.locator('#ops-confirm').is_visible();assertions.append(mode+': lock')
                assert not errors,errors
                page.close()
            browser.close()
        (OUT/'results.json').write_text(json.dumps({'assertions':assertions,'page_errors':0,'transport':'loopback binding to actual HTTP handlers','live_providers':False},ensure_ascii=False,indent=2))
        print(json.dumps({'passed':len(assertions),'screenshots':str(OUT),'checks':assertions},ensure_ascii=False))
    finally:
        fixture.terminate()
        try:fixture.wait(5)
        except subprocess.TimeoutExpired:fixture.kill();fixture.wait()
if __name__=='__main__':main()
