"""Verify slide #3 evidence, alignment, and responsive containment locally.

Run after apps/web `npm run check`. No production service or account is used.
"""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import time
from urllib.request import build_opener, ProxyHandler
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'apps/web'
PORT = int(os.environ.get('ALEPH_PRESENTATION_EVIDENCE_PORT', '18773'))
ORIGIN = f'http://127.0.0.1:{PORT}'
OUT = Path(os.environ.get('ALEPH_SCREENSHOTS', '/tmp/aleph-slide-three-evidence'))


def check(page, width, height, reduced):
    page.set_viewport_size({'width': width, 'height': height})
    page.emulate_media(reduced_motion=reduced)
    page.goto(ORIGIN + '/capstone#friction')
    expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
    stat = page.locator('.slide-active .series-statistic')
    expect(stat).to_have_count(1)
    expect(stat.locator('strong')).to_have_text('3,103,438개')
    expect(stat.locator('.series-statistic-period')).to_have_text('2025.05.01–2026.04.30 · 1년 관측')
    expect(page.locator('.slide-active .series-column-chart')).to_have_count(0)
    expect(page.locator('.slide-active .independent-series')).to_have_count(2)
    stat.scroll_into_view_if_needed()
    geometry = stat.evaluate('''el => {
      const r=el.getBoundingClientRect(), box=el.closest('.independent-series').getBoundingClientRect();
      const range=document.createRange();range.selectNodeContents(el.querySelector('strong'));
      const text=range.getBoundingClientRect();
      return {cardInside:r.left>=box.left&&r.right<=box.right,
        textInside:text.left>=box.left&&text.right<=box.right,
        noHorizontalOverflow:document.documentElement.scrollWidth<=innerWidth,
        numberVisible:r.width>0&&r.height>0,
        ariaHidden:el.closest('[aria-hidden="true"]')!==null};
    }''')
    assert all(geometry[k] for k in ('cardInside','textInside','noHorizontalOverflow','numberVisible')), geometry
    assert not geometry['ariaHidden'], geometry
    links = page.locator('.slide-active .independent-series .series-footer a')
    expect(links).to_have_count(3)
    urls = links.evaluate_all('els=>els.map(el=>el.href)')
    assert 'https://cybercrimeinfocenter.squarespace.com/phishing-activity-year-over-year-numbers-may-april-2026' in urls
    assert 'https://interisle.net/research-methodology' in urls
    assert not any('apwg' in url for url in urls), urls
    # Reload and direct navigation preserve the displayed source and fixed count.
    page.reload()
    expect(stat.locator('strong')).to_have_text('3,103,438개')
    stat.scroll_into_view_if_needed()
    page.screenshot(path=str(OUT / f'slide-three-{width}x{height}-{reduced}.png'), full_page=True)
    return {'width':width,'height':height,'motion':reduced,**geometry}


def check_references(page, width, height):
    page.set_viewport_size({'width': width, 'height': height})
    page.emulate_media(reduced_motion='reduce')
    page.goto(ORIGIN+'/capstone#sources')
    expect(page.locator('.deck-root')).to_have_attribute('data-hydrated','true')
    root=page.locator('.slide-active .reference-slide')
    expect(root).to_be_visible()
    expect(page.locator('a[href*="/capstone/references"]')).to_have_count(0)
    expect(root.locator('a')).to_have_count(37)
    expect(root.locator('details')).to_have_count(5)
    expect(page.get_by_role('button',name='부록 장으로 이동',exact=True)).to_have_count(0)
    assert page.locator('.slide-active .slide-overline').inner_text().startswith('15 / 15')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(OUT/f'references-slide-{width}x{height}.png'),full_page=True)
    for group in root.locator('details').all():
        summary=group.locator('summary')
        summary.click()
        expect(group).to_have_attribute('open','')
        for link in group.locator('a').all():
            assert link.get_attribute('href').startswith('https://')
            assert link.get_attribute('rel')=='noopener noreferrer'
        last=group.locator('a').last
        page.mouse.move(width/2,height/2)
        for _ in range(32):
            if last.evaluate('el=>{const r=el.getBoundingClientRect();const v=document.querySelector("#slide-area").getBoundingClientRect();return r.top>=v.top&&r.bottom<=v.bottom&&r.left>=0&&r.right<=innerWidth}'):break
            page.mouse.wheel(0,350);page.wait_for_timeout(30)
        else:raise AssertionError(('Last source unreachable with wheel',width,group.inner_text()))
        summary.click();expect(group).not_to_have_attribute('open','')
    page.goto(ORIGIN+'/capstone#sources')
    expect(page.locator('.deck-root')).to_have_attribute('data-hydrated','true')
    summary=page.locator('.reference-slide summary').first
    summary.focus();page.keyboard.press('Enter')
    expect(page.locator('.reference-slide details').first).to_have_attribute('open','')
    page.keyboard.press('ArrowLeft');expect(page).to_have_url(ORIGIN+'/capstone#13')
    page.keyboard.press('ArrowRight');expect(page).to_have_url(ORIGIN+'/capstone#14')
    expect(page.locator('.reference-slide')).to_be_visible()
    page.goto(ORIGIN+'/capstone#architecture')
    expect(page.locator('.deck-root')).to_have_attribute('data-hydrated','true')
    label=page.locator('.slide-active .policy-flow-stage strong').nth(1)
    expect(label).to_have_text('정책기반 위험도 판정')
    assert label.evaluate('el=>{const r=el.getBoundingClientRect(),p=el.closest("button").getBoundingClientRect();return r.left>=p.left&&r.right<=p.right}')
    return {'width':width,'height':height,'referencesSlide':True,'sources':37,'pipelineLabel':True}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(mode='w+') as log:
        server = subprocess.Popen(['npm','run','start','--','--hostname','127.0.0.1','--port',str(PORT)],cwd=WEB,
            env={**os.environ,'PLAYWRIGHT_LOCAL_HTTP':'1'},stdout=log,stderr=subprocess.STDOUT)
        try:
            opener=build_opener(ProxyHandler({})); deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if server.poll() is not None:
                    log.seek(0);raise RuntimeError(log.read())
                try:
                    with opener.open(ORIGIN+'/capstone',timeout=2) as response:
                        if response.status==200:break
                except OSError:time.sleep(.1)
            else:raise TimeoutError('Local server not ready')
            with sync_playwright() as p:
                options={'headless':True}
                if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
                browser=p.chromium.launch(**options)
                try:
                    page=browser.new_page();errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    results=[check(page,w,h,m) for w,h in ((1440,900),(1280,720),(390,844),(320,568),(844,390)) for m in ('reduce','no-preference')]
                    results += [check_references(page,w,h) for w,h in ((1440,900),(390,844),(320,568))]
                    for width,height in ((1440,900),(390,844),(320,568)):
                        page.set_viewport_size({'width':width,'height':height})
                        page.goto(ORIGIN+'/capstone#pi-network-plan')
                        expect(page.locator('.deck-root')).to_have_attribute('data-hydrated','true')
                        full=page.get_by_role('button',name='전체 보기',exact=True)
                        if full.count() and full.is_visible():full.click()
                        chart=page.locator('.slide-active #latency-chart')
                        expect(chart).to_have_attribute('data-metric','combined')
                        expect(chart.locator('.latency-delta>span')).to_have_count(4)
                        for chunk in chart.locator('.latency-delta>span').all():
                            geometry=chunk.evaluate('''el => {
                              const r=el.getBoundingClientRect(),column=el.closest('dd').getBoundingClientRect();
                              const range=document.createRange();range.selectNodeContents(el);
                              const css=getComputedStyle(el);
                              return {nowrap:css.whiteSpace==='nowrap',
                                oneLine:range.getBoundingClientRect().height<=parseFloat(css.lineHeight)+1,
                                fits:r.left>=column.left-1&&r.right<=column.right+1};
                            }''')
                            assert all(geometry.values()),(width,height,chunk.inner_text(),geometry)
                        chart.scroll_into_view_if_needed()
                        chart.screenshot(path=str(OUT/f'latency-chart-{width}x{height}.png'))
                        page.screenshot(path=str(OUT/f'latency-page-{width}x{height}.png'))
                        results.append({'latencyViewport':[width,height],'phraseChunks':4,'phraseContainment':True})
                        print(f'PASS latency phrase containment {width}x{height}',flush=True)
                    assert not errors,errors
                    (OUT/'results.json').write_text(json.dumps(results,indent=2))
                finally:browser.close()
            print(f'PASS: 10 slide #3 states and 3 reference/pipeline-label states; screenshots in {OUT}')
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
