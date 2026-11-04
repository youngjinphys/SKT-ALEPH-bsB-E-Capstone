"""Actual offline handlers + browser: explicit stale exclusion and empty draft."""
from pathlib import Path
import json,os,re,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from cloud.assets import assets
from policy_server.console_assets import HTML,CSS,JS
from playwright.sync_api import sync_playwright
from console_smoke import request

OUT=Path(os.environ.get('ALEPH_SCREENSHOTS','/tmp/aleph-policy-review-browser'))
OUT.mkdir(parents=True,exist_ok=True)


def main():
    fixture=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('console_fixture.py'))],
        cwd=ROOT,env={**os.environ,'ALEPH_BROWSER_EXPIRED_REVIEWS':'1'},
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if fixture.poll() is not None:raise RuntimeError(fixture.stderr.read().decode())
            try:
                if request(18766,'/dashboard')['status']==200:break
            except OSError:time.sleep(.05)
        checks=[]
        with sync_playwright() as p:
            opts={'headless':True,'args':['--no-sandbox']}
            if os.getenv('CHROMIUM_PATH'):opts['executable_path']=os.environ['CHROMIUM_PATH']
            browser=p.chromium.launch(**opts)
            for mode,port in [('cloud',18766),('local',18765)]:
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_default_timeout(5000)
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
                page.locator('[data-view=drafts]').click()
                page.wait_for_selector('#build-expired-section:visible')
                assert page.locator('#build-expired-list li').count()==1
                assert page.locator('#build-empty-section').is_visible()
                button=page.locator('#build-form button[type=submit]')
                assert button.is_disabled()
                page.locator('#confirm-expired-exclusion').check()
                assert button.is_disabled()
                page.locator('#confirm-empty-replacement').check()
                assert button.is_enabled()
                page.locator('#confirm-empty-replacement').uncheck()
                assert button.is_disabled()
                checks.append(mode+': separate confirmations cannot substitute for each other')
                page.locator('#manual-domain').fill('manual-incident.example.net')
                page.locator('#manual-reviewer').fill('Synthetic reviewer')
                page.locator('#manual-reason').fill('Synthetic independent manual review with checked subtree impact')
                page.locator('#manual-ack').check();page.locator('#manual-save').click()
                page.wait_for_selector('#ops-confirm[open]')
                page.locator('#ops-confirm-input').fill('UPSERT_MANUAL_SUBTREE')
                page.locator('#ops-confirm-submit').click()
                page.wait_for_function('document.querySelectorAll("#manual-list .manual-item").length===1')
                assert not page.locator('#confirm-expired-exclusion').is_checked()
                assert page.locator('#build-empty-section').is_hidden()
                assert button.is_disabled()
                page.locator('#confirm-expired-exclusion').check()
                page.locator('#confirm-replacement').check();page.locator('#confirm-notice').check()
                assert button.is_enabled();before=page.locator('.draft-item').count();button.click()
                page.wait_for_function(f'document.querySelectorAll(".draft-item").length==={before+1}')
                checks.append(mode+': explicit stale exclusion builds a current manual rule')
                page.locator('#manual-list button').click();page.wait_for_selector('#ops-confirm[open]')
                page.locator('#ops-confirm-input').fill('REMOVE_MANUAL_BLOCK');page.locator('#ops-confirm-submit').click()
                page.wait_for_selector('#build-empty-section:visible')
                assert button.is_disabled()
                page.locator('#confirm-empty-replacement').check()
                assert button.is_disabled()
                page.locator('#confirm-expired-exclusion').check()
                page.locator('#confirm-replacement').check();page.locator('#confirm-notice').check()
                page.screenshot(path=str(OUT/f'{mode}-explicit-empty.png'),full_page=True)
                button.click();page.wait_for_function(f'document.querySelectorAll(".draft-item").length==={before+2}')
                prefix='/api/ops/' if mode=='cloud' else '/api/'
                options={'headers':{'Authorization':'Bearer '+'a'*48}} if mode=='local' else {}
                drafts=json.loads(request(port,prefix+'drafts',options)['body'])
                self_empty=[d for d in drafts if d['rules']==0]
                assert len(self_empty)==1
                assert json.loads(request(port,prefix+'reviews',options)['body'])['items'][0]['approved']
                assert json.loads(request(port,prefix+'deployment',options)['body'])['sequence']==12
                assert not errors,errors
                checks.append(mode+': explicit empty draft preserves approved records and signed feed')
                page.close()
            browser.close()
        (OUT/'results.json').write_text(json.dumps({'checks':checks,'live_providers':False},indent=2))
        print(json.dumps({'passed':len(checks),'checks':checks,'artifacts':str(OUT)}))
    finally:
        fixture.terminate()
        try:fixture.wait(timeout=5)
        except subprocess.TimeoutExpired:fixture.kill();fixture.wait()


if __name__=='__main__':main()
