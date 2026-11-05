"""Synthetic browser -> real API -> independent signer -> public feed acceptance."""
from pathlib import Path
import json, os, re, subprocess, sys, tempfile, time
from datetime import datetime, timedelta, timezone
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from cloud.assets import assets
from console_smoke import request
from playwright.sync_api import sync_playwright
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from aleph_policy_sync.snapshot import canonical, sign_policy, verify_envelope, public_key_id

OUT=Path(os.getenv('ALEPH_SCREENSHOTS','/tmp/aleph-policy-handoff'));OUT.mkdir(parents=True,exist_ok=True)
def call(path, body=None):
    result=request(18766,path,{} if body is None else {'method':'POST','headers':{'Content-Type':'application/json'},'body':json.dumps(body)})
    assert result['status']==200,result
    return json.loads(result['body'])

def main():
    env={**os.environ,'ALEPH_POLICY_FEED_ORIGIN':'https://skt-aleph-capstone.vercel.app'}
    log=tempfile.TemporaryFile()
    fixture=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('console_fixture.py'))],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=log)
    try:
        for _ in range(100):
            if fixture.poll() is not None:
                log.seek(0);raise RuntimeError(log.read().decode())
            try:
                if request(18766,'/dashboard')['status']==200:break
            except OSError:time.sleep(.05)
        manual=call('/api/ops/manual');reviews=call('/api/ops/reviews')
        call('/api/ops/manual/save',dict(domain='new-handoff.example.net',reviewer='Synthetic operator',
             reason='Synthetic browser release with reviewed subtree impact',acknowledge_subtree=True,
             expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
             expected_revision=manual['revision'],confirm='UPSERT_MANUAL_SUBTREE'))
        manual=call('/api/ops/manual')
        draft=call('/api/ops/build',dict(fingerprint=reviews['fingerprint'],review_set_revision=reviews['review_set_revision'],
             manual_revision=manual['revision'],confirm_replacement=True,acknowledge_user_notice=True,
             excluded_expired_review_ids=[],confirm_empty_replacement=False))
        raw=canonical(call('/api/ops/drafts/'+draft['draft']+'/download'))
        key=Ed25519PrivateKey.generate();pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        plan=call('/api/ops/drafts/'+draft['draft']+'/handoff/edge-70')
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);policy_file=base/'draft.json';private_file=base/'signer.pem';signed_file=base/'signed.json'
            policy_file.write_bytes(raw);policy_file.chmod(0o600)
            private_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));private_file.chmod(0o600)
            replacements={'python3':sys.executable,'<downloaded-draft.json>':str(policy_file),'<offline-private-key.pem>':str(private_file),'<new-signed-envelope.json>':str(signed_file)}
            argv=[replacements.get(arg,arg) for arg in plan['signing']['argv_template']]
            signing_env={**os.environ,'PYTHONPATH':os.pathsep.join(str(ROOT/part) for part in plan['signing']['pythonpath_components'])}
            subprocess.run(argv,cwd=ROOT,env=signing_env,check=True,capture_output=True,text=True)
            envelope=json.loads(signed_file.read_bytes())
        with sync_playwright() as p:
            options={'headless':True,'args':['--no-sandbox']}
            if os.getenv('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
            browser=p.chromium.launch(**options);page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_default_timeout(6000)
            html,css,js=assets();html=re.sub(r'<link[^>]+href="/dashboard/assets/console.css"[^>]*>','',html)
            html=re.sub(r'<script[^>]+src="/dashboard/assets/console.js"[^>]*></script>','',html)
            page.expose_binding('__testFetch',lambda source,url,options:request(18766,url,options))
            page.set_content(html);page.add_style_tag(content=css)
            page.add_script_tag(content="window.fetch=async(url,opts)=>{const r=await window.__testFetch(String(url),opts||{});return new Response(r.body,{status:r.status,headers:r.headers});};")
            page.add_script_tag(content=js);page.wait_for_selector('#authorized:not([hidden])')
            page.locator('[data-view=drafts]').click()
            page.locator('#handoff-draft').select_option(draft['draft'])
            page.locator('#handoff-device').fill('edge-70')
            before=request(18766,'/api/ops/drafts')['headers'].get('x-aleph-state-revision')
            page.locator('#handoff-form button[type=submit]').click()
            page.wait_for_selector('#handoff-result:not([hidden])')
            assert '5 → 6' in page.locator('#handoff-summary').inner_text()
            assert '/edge-70/current.json' in page.locator('#handoff-feed').inner_text()
            assert '--device-id' in page.locator('#handoff-sign-command').inner_text()
            assert '--apply' not in page.locator('#handoff-node-command').inner_text()
            assert request(18766,'/api/ops/drafts')['headers'].get('x-aleph-state-revision')==before
            page.locator('#cloud-policy-handoff').screenshot(path=str(OUT/'handoff-desktop.png'))
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.evaluate('document.activeElement?.blur()')
            page.locator('.draft-item').filter(has_text=draft['draft']).get_by_role('button',name='장치별 배포 준비 →').click()
            page.wait_for_function("document.activeElement.id==='handoff-device'")
            assert page.locator('#handoff-title').bounding_box()['y']>=164
            page.screenshot(path=str(OUT/'handoff-mobile.png'))
            page.locator('#handoff-form button[type=submit]').click();page.wait_for_selector('#handoff-result:not([hidden])')
            page.set_viewport_size({'width':1440,'height':1000})
            page.evaluate("""window.__normalFetch=window.fetch;window.fetch=async(url,opts)=>{
              const response=await window.__normalFetch(url,opts);
              if(String(url).includes('/handoff/')){const data=await response.json();data.target.current_sequence++;return new Response(JSON.stringify(data),{status:200});}
              return response;
            };""")
            page.locator('#handoff-publish').click()
            page.wait_for_function("document.querySelector('#handoff-status').textContent.includes('기준이나')")
            assert page.locator('[data-panel=drafts]').is_visible()
            page.evaluate('window.fetch=window.__normalFetch')
            page.locator('#handoff-form button[type=submit]').click();page.wait_for_selector('#handoff-result:not([hidden])')
            page.locator('#handoff-publish').click()
            page.wait_for_selector('#cloud-publish-form:visible')
            assert page.locator('#cloud-publish-device').input_value()=='edge-70'
            assert page.locator('#cloud-publish-sequence').input_value()=='5'
            page.locator('#cloud-key-role').select_option('policy');page.locator('#cloud-key').fill(pem)
            page.locator('#cloud-key-confirm').check();page.locator('#cloud-key-form button[type=submit]').click()
            page.wait_for_selector('#ops-confirm[open]');page.locator('#ops-confirm-input').fill('TRUST_PUBLIC_KEY');page.locator('#ops-confirm-submit').click()
            page.wait_for_function("document.querySelector('#cloud-key-result').textContent.includes('신뢰 지문')")
            page.locator('#cloud-policy').set_input_files({'name':'signed-policy.json','mimeType':'application/json','buffer':canonical(envelope)})
            page.locator('#cloud-publish-form button[type=submit]').click();page.wait_for_selector('#cloud-publish-preview:not([hidden])')
            page.locator('#cloud-rotation').check();page.locator('#cloud-withdrawals').check();page.locator('#cloud-publish-commit').click()
            page.wait_for_selector('#ops-confirm[open]');page.locator('#ops-confirm-input').fill('PUBLISH_POLICY');page.locator('#ops-confirm-submit').click()
            page.wait_for_function("document.querySelector('#deployment-sequence').textContent==='6'")
            page.screenshot(path=str(OUT/'published-desktop.png'),full_page=True)
            page.locator('[data-view=drafts]').click();page.locator('#handoff-draft').select_option(draft['draft']);page.locator('#handoff-device').fill('edge-70')
            page.locator('#handoff-form button[type=submit]').click();page.wait_for_selector('#handoff-result:not([hidden])')
            assert page.locator('#handoff-publish').is_disabled()
            assert '--sequence' not in page.locator('#handoff-sign-command').inner_text()
            page.evaluate("""window.__normalFetch=window.fetch;window.fetch=(url,opts)=>String(url).includes('/handoff/')?
              new Promise(resolve=>window.__releaseHandoff=()=>resolve(new Response(JSON.stringify({error:'obsolete error'}),{status:503}))):window.__normalFetch(url,opts);""")
            page.locator('#handoff-device').fill('edge-69');page.locator('#handoff-form button[type=submit]').click()
            page.wait_for_function('typeof window.__releaseHandoff==="function"')
            page.locator('#handoff-device').fill('edge-70');page.evaluate('window.__releaseHandoff()')
            page.wait_for_function("!document.querySelector('#handoff-form').dataset.busy")
            assert '다시 조회' in page.locator('#handoff-status').inner_text()
            assert 'obsolete error' not in page.locator('#toast').inner_text()
            assert not errors,errors
            browser.close()
        served=call('/v1/policies/edge-70/current.json')
        with tempfile.TemporaryDirectory() as folder:
            trust=Path(folder);public=trust/(public_key_id(key.public_key())+'.pem');public.write_text(pem);public.chmod(0o600)
            payload,policy=verify_envelope(canonical(served),expected_device='edge-70',trust_dir=trust)
            assert payload['sequence']==6 and any(r.domain=='new-handoff.example.net' for r in policy.rules)
        assert call('/v1/policies/edge-69/current.json')['payload']['sequence']==12
        print(json.dumps({'passed':True,'scope':'synthetic browser and actual HTTP/storage; independent signer; public feed verified; no live DNS apply','screenshots':str(OUT)}))
    finally:
        fixture.terminate();fixture.wait(timeout=10)
        log.close()

if __name__=='__main__':main()
