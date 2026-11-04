"""Offline guide interaction/layout acceptance with real assembled cloud assets.

Only the tutorial controller runs. Authentication and read-only menu navigation
are synthetic UI states, not authentication/backend verification. Every request
is intercepted; no production service or credential is used.
Run: python3 -B tests/browser/dashboard_tutorial.py
"""
from pathlib import Path
import json
import os
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from cloud.assets import assets
from cloud.tutorial import JS as GUIDE_JS
from policy_server.console_assets import HTML as LOCAL_HTML
from playwright.sync_api import sync_playwright

OUT=Path(os.environ.get('ALEPH_SCREENSHOTS','/tmp/aleph-tutorial-artifacts'))
ORIGIN='https://dashboard-guide.test'
VIEWPORTS=((320,568),(390,844),(768,1024),(1440,900),(812,375))
NAV=r'''
let currentView='overview';
window.guideNavigations=[];
function navigateTo(view){
  guideNavigations.push(view);currentView=view;
  document.querySelectorAll('[data-panel]').forEach(el=>el.hidden=el.dataset.panel!==view);
  document.querySelector('#page-title').textContent=view;
  document.querySelector('#page-title').focus();
  document.dispatchEvent(new Event('ops:view'));
}
'''


def geometry(page):
    return page.evaluate('''() => {
      const rect=el=>el.getBoundingClientRect(),g=rect(document.querySelector('#cloud-guide'));
      const footer=rect(document.querySelector('.cloud-guide-footer'));
      const controls=[...document.querySelectorAll('#cloud-guide button')].filter(el=>rect(el).height>0).map(el=>({id:el.id,...rect(el).toJSON()}));
      return {guide:g.toJSON(),footer:footer.toJSON(),controls,width:innerWidth,height:innerHeight,
        overflow:document.documentElement.scrollWidth>innerWidth,
        panelOverflow:document.querySelector('#cloud-guide').scrollWidth>document.querySelector('#cloud-guide').clientWidth};
    }''')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    html,css,_=assets()
    html=re.sub(r'<script\b[^>]*>.*?</script>','',html,flags=re.S)
    html=re.sub(r'<link\b[^>]*rel="stylesheet"[^>]*>','',html)
    assert 'cloud-guide' not in LOCAL_HTML
    results=[]
    with sync_playwright() as p:
        opts={'headless':True}
        if os.getenv('CHROMIUM_PATH'):opts['executable_path']=os.environ['CHROMIUM_PATH']
        browser=p.chromium.launch(**opts)
        try:
            for connected in (False,True):
                page=browser.new_page(viewport={'width':1440,'height':900})
                errors=[];requests=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda req:requests.append((req.method,req.url)))
                def route(request):
                    if request.request.url==ORIGIN+'/dashboard':request.fulfill(status=200,content_type='text/html',body=html)
                    elif request.request.url==ORIGIN+'/':request.fulfill(status=200,content_type='text/html',body='<h1>Root landing fixture</h1>')
                    else:request.abort()
                page.route('**/*',route)
                page.goto(ORIGIN+'/dashboard',wait_until='domcontentloaded')
                page.add_style_tag(content=css)
                page.evaluate('''connected=>{
                  document.querySelector('#authorized').hidden=!connected;
                  document.querySelector('#login-view').hidden=connected;
                }''',connected)
                page.add_script_tag(content=NAV+'\n'+GUIDE_JS)
                assert page.locator('#cloud-guide').is_hidden()
                assert page.locator('a.brand').get_attribute('href')=='/'
                assert page.locator('.brand-mark,.brand-orbit,.brand-core').count()==0
                home=page.get_by_role('link',name='홈으로 이동',exact=True)
                assert home.is_visible() and home.get_attribute('href')=='/'
                assert page.locator('.main-column>.bottom-bar').evaluate("el=>parseFloat(getComputedStyle(el).paddingBottom)")>=88
                page.locator('#cloud-guide-open').focus();page.keyboard.press('Enter')
                assert page.locator('#cloud-guide').is_visible()
                assert page.evaluate('document.activeElement.id')=='cloud-guide-title'
                assert page.locator('#cloud-guide-open').get_attribute('aria-expanded')=='true'
                if not connected:assert 'Google' in page.locator('#cloud-guide-description').inner_text()
                for width,height in VIEWPORTS:
                    page.set_viewport_size({'width':width,'height':height})
                    # Return to the beginning before checking every step.
                    while not page.locator('#cloud-guide-prev').is_disabled():page.locator('#cloud-guide-prev').click()
                    for step in range(7):
                        size=geometry(page);g=size['guide'];footer=size['footer']
                        prefix=f'{connected}/{width}x{height}/step{step+1}'
                        assert not size['overflow'] and not size['panelOverflow'],(prefix,'horizontal overflow',size)
                        assert g['left']>=0 and g['top']>=0 and g['right']<=width+1 and g['bottom']<=height+1,(prefix,'offscreen guide',size)
                        assert footer['top']>=g['top'] and footer['bottom']<=height+1,(prefix,'footer offscreen',size)
                        close=next(c for c in size['controls'] if c['id']=='cloud-guide-close')
                        assert close['top']>=0 and close['right']<=width and close['bottom']<=height,(prefix,'close button offscreen',close)
                        for control in size['controls']:
                            assert control['height']>=44,(prefix,'small target',control)
                        assert page.locator('#cloud-guide-count').inner_text()==f'{step+1:02d} / 07'
                        assert page.locator('#cloud-guide-instructions li').count()==3
                        if step and not connected:assert page.locator('#cloud-guide-view').is_disabled()
                        if step in (0,5):page.screenshot(path=str(OUT/f'{"connected" if connected else "locked"}-{width}x{height}-step{step+1}.png'))
                        results.append({'connected':connected,'viewport':[width,height],'step':step+1,'geometry':size})
                        if step<6:page.locator('#cloud-guide-next').click()
                    assert page.evaluate('guideNavigations.length')==0
                    # An operation warning must remain visible above the HUD,
                    # including in a short landscape viewport.
                    page.evaluate("const toast=document.querySelector('#toast');toast.textContent='합성 오류 안내: 실제 작업을 실행하지 않았습니다.';toast.hidden=false")
                    toast=page.locator('#toast').bounding_box();hud=page.locator('#cloud-guide').bounding_box()
                    assert toast['y']+toast['height']<=hud['y'],(width,height,'toast overlaps guide',toast,hud)
                    close=page.locator('#cloud-guide-close').bounding_box()
                    assert close['y']+close['height']<=height,(width,height,'toast hides close control')
                    page.screenshot(path=str(OUT/f'{"connected" if connected else "locked"}-{width}x{height}-toast.png'))
                    page.evaluate("document.querySelector('#toast').hidden=true")
                # Completion resets; Escape dismissal restores focus; reopening
                # keeps progress only when dismissed before completion.
                page.locator('#cloud-guide-next').click();assert page.locator('#cloud-guide').is_hidden()
                page.locator('#cloud-guide-open').click();assert page.locator('#cloud-guide-count').inner_text()=='01 / 07'
                page.locator('#cloud-guide-next').click();page.locator('#cloud-guide-next').click()
                page.keyboard.press('Escape');assert page.locator('#cloud-guide').is_hidden()
                assert page.evaluate('document.activeElement.id')=='cloud-guide-open'
                assert page.locator('[data-cloud-guide-target]').count()==0
                page.locator('#cloud-guide-open').click();assert page.locator('#cloud-guide-count').inner_text()=='03 / 07'
                if connected:
                    page.locator('#reason').evaluate("el=>el.value='Unsubmitted review text'")
                    page.locator('#cloud-guide-view').click()
                    assert page.locator('#cloud-guide').is_hidden()
                    assert page.evaluate('guideNavigations')==['reviews']
                    assert page.evaluate('document.activeElement.id')=='page-title'
                    assert page.locator('#reason').input_value()=='Unsubmitted review text'
                    page.locator('#cloud-guide-open').click()
                # A non-modal HUD must not trap Tab focus in the guide.
                page.locator('#cloud-guide-next').focus();page.keyboard.press('Tab')
                assert not page.evaluate("!!document.activeElement.closest('#cloud-guide')")
                page.evaluate("document.dispatchEvent(new Event('ops:locked'))")
                assert page.locator('#cloud-guide').is_hidden()
                page.locator('#cloud-guide-open').click();assert page.locator('#cloud-guide-count').inner_text()=='01 / 07'
                page.emulate_media(reduced_motion='reduce',forced_colors='active')
                page.screenshot(path=str(OUT/f'{"connected" if connected else "locked"}-forced-colors.png'))
                page.keyboard.press('Escape')
                home.focus();page.keyboard.press('Enter')
                page.wait_for_url(ORIGIN+'/')
                assert page.locator('h1').inner_text()=='Root landing fixture'
                page.go_back(wait_until='domcontentloaded');page.wait_for_url(ORIGIN+'/dashboard')
                assert page.locator('#cloud-guide').is_hidden()
                page.locator('a.brand').focus();page.keyboard.press('Enter')
                page.wait_for_url(ORIGIN+'/')
                assert page.locator('h1').inner_text()=='Root landing fixture'
                page.go_back(wait_until='domcontentloaded');page.wait_for_url(ORIGIN+'/dashboard')
                assert page.locator('#cloud-guide').is_hidden()
                assert page.locator('a.brand').get_attribute('href')=='/'
                assert not errors,errors
                assert all(method=='GET' and url in (ORIGIN+'/',ORIGIN+'/dashboard') for method,url in requests),requests
                page.close()
        finally:browser.close()
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(f'Passed {len(results)} guide layout states, keyboard/focus/dismiss/navigation contracts and native root/back navigation.')

if __name__=='__main__':main()
