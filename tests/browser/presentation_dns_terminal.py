"""The terminal distinguishes a stored public record from an unexecuted Pi DNS example."""
from pathlib import Path
import json
import re
from playwright.sync_api import expect
from presentation_controls import _assert_readable

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = json.loads((ROOT/'apps/web/public/capstone/evidence/google-dns-observation.json').read_text())
PI_CAPTURE = json.loads((ROOT/'apps/web/public/capstone/evidence/pi-dns-block-20261105.json').read_text())
PI_QUERY = PI_CAPTURE['block_queries'][0]
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
    if not _visible_without_scrolling(target):
        page.screenshot(path=str(OUT/f'terminal-unreachable-{context}-{direction}.png'),full_page=True)
        geometry=target.evaluate('''el=>[el,...function*(node){while(node.parentElement){node=node.parentElement;yield node}}(el)].map(node=>{
            const r=node.getBoundingClientRect(),s=getComputedStyle(node);
            return {tag:node.tagName,class:node.className,top:r.top,bottom:r.bottom,left:r.left,right:r.right,scrollTop:node.scrollTop,scrollHeight:node.scrollHeight,clientHeight:node.clientHeight,overflowY:s.overflowY,justifyContent:s.justifyContent,flexShrink:s.flexShrink};
        })''')
        raise AssertionError((context,'unreachable with wheel',geometry))


def _check_natural_reachability(page,context,last_selector='.dns-terminal-status a',last_focus_selector=None):
    first=page.get_by_role('group',name='질의 이름 선택',exact=True).get_by_role('button').first
    last=page.locator(last_selector)
    _wheel_reach(page,last,1,context)
    page.screenshot(path=str(OUT/f'terminal-scroll-end-{context}.png'),full_page=True)
    _wheel_reach(page,first,-1,context)
    focus_target=page.locator(last_focus_selector) if last_focus_selector else last
    first.focus()
    for _ in range(24):
        focused=page.locator(':focus')
        assert _visible_without_scrolling(focused),(context,'focused control clipped')
        if focus_target.evaluate('el=>el===document.activeElement'):break
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
        const samples=[root.querySelector('.dns-terminal-command'),root.querySelector('.dns-terminal-output'),...root.querySelectorAll('.dns-terminal-output span,.dns-terminal-result')];
        const contrast=samples.map(el=>{const css=getComputedStyle(el),fg=luminance(rgba(css.color)),bg=luminance(el.matches('.dns-terminal-result')?rgba(css.backgroundColor):worst);return(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)});
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
    google=CAPTURE
    expected='\n'.join([google['header'],google['flags'],';; QUESTION SECTION:',google['question'],';; ANSWER SECTION:',*google['answers'],f";; Query time: {google['queryMs']} msec"])
    total=0
    for width,height in ((1440,900),(1366,768),(390,844),(390,720),(320,667)):
        context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce')
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def open_terminal():
            page.goto(origin+'/capstone#8')
            expect(page.locator('.deck-root')).to_have_attribute('data-hydrated','true')
            visual=page.locator('.slide-active').get_by_role('button',name='시각 자료',exact=True)
            if visual.count() and visual.is_visible():visual.click()
            expect(page.locator('.server-dns-observation')).to_have_attribute('data-evidence-state','captured')
            page.bring_to_front()
        try:
            open_terminal()
            assert page.evaluate('document.characterSet')=='UTF-8'
            assert page.evaluate('''async()=>{
                const loaded=(await Promise.all([400,700].map(weight=>document.fonts.load(`${weight} 16px "Aleph DNS UI"`,'실제 질의 기록')))).flat();
                await document.fonts.ready;
                return loaded.length===2&&loaded.every(font=>font.status==='loaded');
            }''')
            root=page.locator('.server-dns-observation')
            choices=root.get_by_role('group',name='질의 이름 선택',exact=True)
            expect(choices.get_by_role('button')).to_have_count(2)
            expect(root.get_by_role('group')).to_have_count(1)
            _assert_terminal_visibility(page)
            _check_natural_reachability(page,f'{width}x{height}')
            for domain in ('google.com','block.test'):
                choices.get_by_role('button',name=domain,exact=True).click()
                text=root.inner_text()
                if domain=='google.com':
                    for removed in ('example.com','기본 DNS','SERVER:','+time','+tries','+tcp'):
                        assert removed not in text,(width,height,domain,removed)
                    assert not re.search(r'\b(?:TCP|UDP)\b',text,re.IGNORECASE),(width,height,domain,'transport detail visible')
                assert '\ufffd' not in text
                expected_code='NOERROR' if domain=='google.com' else PI_QUERY['rcode']
                expected_count=f"ANSWER: {google['answerCount']}" if domain=='google.com' else f"ANSWER: {PI_QUERY['answer_count']}"
                tone='success' if domain=='google.com' else 'negative'
                results=root.locator('.dns-terminal-output .dns-terminal-result')
                expect(results).to_have_text([expected_code,expected_count])
                for token in results.all():
                    expect(token).to_have_attribute('data-result',tone)
                    expect(token).to_have_css('font-weight','700')
                    expect(token).to_have_css('text-decoration-line','underline')
                expect(root.locator('.dns-terminal-status .dns-terminal-result')).to_have_text(expected_code)
                if domain=='google.com': assert '1.1.1.1' in text and all(line.split()[-1] in text for line in google['answers'])
                if domain=='google.com':
                    expect(root).to_have_attribute('data-evidence-state','captured')
                    expect(root).to_have_attribute('data-query-id',google['id'])
                    expect(root.locator('.dns-terminal-command')).to_have_attribute('data-command-display','summary')
                    expect(root.locator('.dns-terminal-command code')).to_have_text('dig @1.1.1.1 google.com A')
                    expect(root.locator('.dns-terminal-excerpt')).to_have_text('공개 DNS 별도 관측 · 1.1.1.1 · 명령 옵션 일부 생략')
                    expect(root.locator('.server-dns-heading h3')).to_have_text('공개 DNS 질의 기록')
                    assert 'SERVER ·' not in text and 'server / dig' not in text
                    assert root.locator('.dns-terminal-output').inner_text()==expected
                    expect(root.locator('.dns-terminal-status time')).to_have_attribute('datetime',google['timestamp'])
                    expect(root.locator('.dns-terminal-pending')).to_have_count(0)
                    for selector in ('.dns-terminal-command','.dns-terminal-output','.dns-terminal-status'):
                        _assert_readable(root.locator(selector),(width,height,domain,selector))
                else:
                    expect(root).to_have_attribute('data-evidence-state','captured')
                    expect(root).to_have_attribute('data-query-id','pi-dns-block-20261105')
                    expect(root.locator('.server-dns-heading h3')).to_have_text('Pi DNS 질의 기록')
                    expect(root.locator('.dns-terminal-command')).to_have_attribute('data-command-display','recorded')
                    expect(root.locator('.dns-terminal-command code')).to_have_text(' '.join(PI_QUERY['command']))
                    assert root.locator('.dns-terminal-output code').text_content()==PI_QUERY['stdout']
                    expect(root.locator('.dns-terminal-status time')).to_have_attribute('datetime',PI_QUERY['started_at'])
                    link=root.get_by_role('link',name='기록 ↗',exact=True)
                    expect(link).to_have_attribute('href','/capstone/evidence/pi-dns-block-20261105.json')
                    for absent in ('NXDOMAIN (expected)','ANSWER: 0 (expected)','NOT RUN','예시 · 미실행'):
                        assert absent not in text,(width,height,absent)
                    _assert_terminal_visibility(page)
                    _check_natural_reachability(page,f'{width}x{height}-pi-record')
                    for selector in ('.dns-terminal-command','.dns-terminal-output','.dns-terminal-status'):
                        _assert_readable(root.locator(selector),(width,height,domain,selector))
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(OUT/f'terminal-{domain}-{width}x{height}.png'),full_page=True)
                total+=1
            if width==1440:
                unchanged=root.locator('.dns-terminal-output').inner_text()
                page.emulate_media(forced_colors='active')
                for token in root.locator('.dns-terminal-result').all():
                    expect(token).to_have_css('font-weight','700')
                    expect(token).to_have_css('text-decoration-line','underline')
                assert root.locator('.dns-terminal-output').inner_text()==unchanged
                page.emulate_media(forced_colors='none')
            # A return to the public captured case must not retain the fixture state.
            choices.get_by_role('button',name='google.com',exact=True).click()
            expect(root).to_have_attribute('data-evidence-state','captured')
            assert root.locator('.dns-terminal-output').inner_text()==expected
            _check_natural_reachability(page,f'{width}x{height}-roundtrip')
            # Both native domain buttons retain global slide-arrow behavior.
            for domain in ('google.com','block.test'):
                for key,destination in (('ArrowLeft',7),('ArrowRight',9)):
                    open_terminal()
                    button=page.get_by_role('group',name='질의 이름 선택',exact=True).get_by_role('button',name=domain,exact=True)
                    button.click();expect(button).to_be_focused()
                    assert button.evaluate('el=>el.tabIndex')==0
                    page.keyboard.press(key)
                    expect(page).to_have_url(origin+f'/capstone#{destination}')
                    expect(page.locator('#slide-area')).to_be_focused()
            open_terminal()
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
                page.locator('.server-dns-observation').evaluate('''root=>{
                    const entries=[root,...root.querySelectorAll('*')].map(el=>[el,parseFloat(getComputedStyle(el).fontSize)]);
                    entries.forEach(([el,size])=>el.style.fontSize=`${size*2}px`);
                }''')
                # The removed fixture wrapper must not leave the real dashboard
                # shrinking/centering oversized content above scrollTop=0.
                panel=page.locator('.dns-evidence-dashboard')
                expect(panel).to_have_css('flex-shrink','0')
                expect(panel).to_have_css('max-height','none')
                expect(panel).to_have_css('overflow-y','visible')
                _check_natural_reachability(page,'1366x768-text-size-200percent')
            assert not errors,errors
        finally:context.close()
    print(f'DNS terminal: {total} two-record states, 20 domain-to-arrow cases, stored public and Pi DNS transcripts, fonts, glass, wheel/Tab and text stress verified')
