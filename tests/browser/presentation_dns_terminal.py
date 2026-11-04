"""The terminal is a stored capture, never an executable shell or live DNS test."""
from pathlib import Path
import json
import re
from playwright.sync_api import expect
from presentation_controls import _assert_readable

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = json.loads((ROOT/'apps/web/public/capstone/evidence/dns-terminal-20261104.json').read_text())
OUT = Path('/tmp/aleph-build-artifacts/dns-terminal')


def _visible_without_scrolling(locator):
    return locator.evaluate("""el => {
        const r=el.getBoundingClientRect();
        let left=0,right=innerWidth,top=0,bottom=innerHeight;
        for(let p=el.parentElement;p;p=p.parentElement){
            const c=getComputedStyle(p),b=p.getBoundingClientRect();
            if(/hidden|clip|auto|scroll/.test(c.overflowX)){left=Math.max(left,b.left);right=Math.min(right,b.right);}
            if(/hidden|clip|auto|scroll/.test(c.overflowY)){top=Math.max(top,b.top);bottom=Math.min(bottom,b.bottom);}
        }
        return r.width>0&&r.height>0&&r.left>=left-1&&r.right<=right+1&&r.top>=top-1&&r.bottom<=bottom+1;
    }""")


def _wheel_reach(page,target,direction,context):
    # Deliver actual wheel input inside the visible visual column. Do not use
    # scrollIntoView, locator.hover/click, or focus, which can force a hidden
    # overflow container to scroll and mask the user's mouse/touch defect.
    point=page.locator('.slide-active .slide-visual-container').evaluate("""el=>{
        const r=el.getBoundingClientRect(),v=document.querySelector('#slide-area').getBoundingClientRect();
        const top=Math.max(r.top,v.top,0),bottom=Math.min(r.bottom,v.bottom,innerHeight);
        return {x:Math.min(innerWidth-16,Math.max(16,r.left+r.width/2)),y:bottom>top?(top+bottom)/2:(v.top+v.bottom)/2};
    }""")
    page.mouse.move(point['x'],point['y'])
    for _ in range(24):
        if _visible_without_scrolling(target):return
        page.mouse.wheel(0,direction*500)
        page.wait_for_timeout(70)
    assert _visible_without_scrolling(target),(context,'unreachable with wheel')


def _check_natural_reachability(page,context):
    first=page.get_by_role('group',name='검증 자료 선택',exact=True).get_by_role('button').first
    last=page.locator('.dns-terminal-routes button').last
    _wheel_reach(page,last,1,context)
    page.screenshot(path=str(OUT/f'terminal-scroll-end-{context}.png'),full_page=True)
    _wheel_reach(page,first,-1,context)
    first.focus()
    for _ in range(24):
        focused=page.locator(':focus')
        assert _visible_without_scrolling(focused),(context,'focused control clipped')
        if last.evaluate('el=>el===document.activeElement'):break
        page.keyboard.press('Tab')
    else:raise AssertionError((context,'terminal control missing from Tab order'))


def _assert_terminal_visibility(page):
    result=page.locator('.dns-terminal').evaluate(r"""root=>{
        const rgba=value=>value.match(/[\d.]+/g).map(Number);
        const luminance=rgb=>rgb.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
        const body=getComputedStyle(root.querySelector('.dns-terminal-body'));
        const surface=rgba(body.backgroundColor),alpha=surface[3]??1;
        // White behind the glass is the lightest possible backing. Foreground
        // must remain clear even then, not only against the current dark slide.
        const worst=surface.slice(0,3).map(v=>v*alpha+255*(1-alpha));
        const samples=[root.querySelector('.dns-terminal-command'),root.querySelector('.dns-terminal-output'),...root.querySelectorAll('.dns-terminal-output span')];
        const contrast=samples.map(el=>{const fg=luminance(rgba(getComputedStyle(el).color)),bg=luminance(worst);return(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)});
        const output=getComputedStyle(root.querySelector('.dns-terminal-output'));
        return {minContrast:Math.min(...contrast),fontSize:parseFloat(output.fontSize),lineHeight:parseFloat(output.lineHeight)/parseFloat(output.fontSize),textShadow:output.textShadow,filter:getComputedStyle(root).filter,backdrop:getComputedStyle(root).backdropFilter,whiteSpace:output.whiteSpace};
    }""")
    assert result['minContrast']>=7,result
    assert result['fontSize']>=13,result
    assert result['lineHeight']>=1.5,result
    assert result['textShadow']=='none' and result['filter']=='none',result
    assert result['whiteSpace']=='pre-wrap',result
    assert 'blur(20px)' in result['backdrop'],result


def check_dns_terminal(browser, origin):
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for width, height in ((1440,900),(1366,768),(390,844),(390,720),(320,667)):
        context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce')
        page=context.new_page()
        errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        def open_terminal():
            page.goto(origin+'/capstone#8')
            expect(page.locator('.deck-root')).to_have_attribute('data-hydrated','true')
            visual=page.locator('.slide-active').get_by_role('button',name='시각 자료',exact=True)
            if visual.count() and visual.is_visible():visual.click()
            expect(page.locator('.server-dns-observation')).to_be_visible()
            page.bring_to_front()
        try:
            open_terminal()
            assert page.evaluate('document.characterSet')=='UTF-8'
            # A real self-hosted Korean font must load, not silently use local fallbacks.
            assert page.evaluate('''async()=>{
                const loaded=(await Promise.all([400,700].map(weight=>document.fonts.load(`${weight} 16px "Aleph DNS UI"`,'실제 질의 기록')))).flat();
                await document.fonts.ready;
                return loaded.length===2&&loaded.every(font=>font.status==='loaded');
            }''')
            _assert_terminal_visibility(page)
            _check_natural_reachability(page,f'{width}x{height}')
            for query in CAPTURE['queries']:
                root=page.locator('.server-dns-observation')
                root.get_by_role('group',name='저장된 질의 이름 선택',exact=True).get_by_role('button',name=query['domain'],exact=True).click()
                root.get_by_role('group',name='저장된 전송 방식 선택',exact=True).get_by_role('button',name=query['transport'],exact=True).click()
                routes=root.get_by_role('group',name='저장된 DNS 경로 선택',exact=True)
                route=routes.get_by_role('button',name=re.compile('^사설 DNS' if query['route']=='private' else '^기본 DNS'))
                route.click()
                expect(root).to_have_attribute('data-query-id',query['id'])
                expect(root.locator('.dns-terminal-command code')).to_have_text(query['command'])
                output=root.locator('.dns-terminal-output').inner_text()
                expected='\n'.join([query['header'],query['flags'],';; QUESTION SECTION:',query['question'],';; ANSWER SECTION:',*query['answers'],f";; Query time: {query['queryMs']} msec",query['server']])
                assert output==expected,(width,height,query['id'],'transcript changed')
                assert output.count('[REDACTED]')==query['answerCount']
                assert f"Query time: {query['queryMs']} msec" in output
                assert query['server'] in output
                assert '\ufffd' not in root.inner_text()
                assert not re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',root.inner_text())
                expect(root.locator('.dns-terminal-status time')).to_have_attribute('datetime',query['timestamp'])
                for selector in ('.dns-terminal-command','.dns-terminal-output','.dns-terminal-status'):
                    _assert_readable(root.locator(selector),(width,height,query['id'],selector))
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                total+=1
            # Each new ordinary choice preserves the user's global arrow behavior.
            for group_name in ('저장된 질의 이름 선택','저장된 전송 방식 선택','저장된 DNS 경로 선택'):
                for ordinal in (0,1):
                    for key,destination in (('ArrowLeft',7),('ArrowRight',9)):
                        open_terminal()
                        button=page.get_by_role('group',name=group_name,exact=True).get_by_role('button').nth(ordinal)
                        button.click();expect(button).to_be_focused()
                        assert button.evaluate('el=>el.tabIndex')==0
                        page.keyboard.press(key)
                        expect(page).to_have_url(origin+f'/capstone#{destination}')
                        expect(page.locator('#slide-area')).to_be_focused()
            open_terminal()
            page.locator('.dns-terminal').scroll_into_view_if_needed()
            page.screenshot(path=str(OUT/f'terminal-{width}x{height}.png'),full_page=True)
            if (width,height) in ((1440,900),(390,844)):
                page.emulate_media(reduced_motion='no-preference')
                page.goto(origin+'/capstone#7')
                expect(page.locator('.deck-root')).to_have_attribute('data-hydrated','true')
                page.locator('#slide-area').focus()
                page.keyboard.press('ArrowRight')
                expect(page).to_have_url(origin+'/capstone#8')
                expect(page.locator('.slide-leaving')).to_have_count(0)
                _check_natural_reachability(page,f'{width}x{height}-normal-motion')
                page.keyboard.press('ArrowRight')
                expect(page).to_have_url(origin+'/capstone#9')
                expect(page.locator('.slide-leaving')).to_have_count(0)
            if width==1366:
                open_terminal()
                page.evaluate('async()=>{await document.fonts.ready}')
                # A text-only size stress test, not a claim of browser pinch zoom.
                page.locator('.server-dns-observation').evaluate('''root=>{
                    const entries=[root,...root.querySelectorAll('*')].map(el=>[el,parseFloat(getComputedStyle(el).fontSize)]);
                    entries.forEach(([el,size])=>el.style.fontSize=`${size*2}px`);
                }''')
                _check_natural_reachability(page,'1366x768-text-size-200percent')
            assert not errors, errors
        finally:context.close()
    print(f'DNS terminal: {total} stored records, 60 choice-to-arrow cases, UTF-8, web fonts, high-contrast glass transcript, wheel/Tab reachability and text-size stress verified')
