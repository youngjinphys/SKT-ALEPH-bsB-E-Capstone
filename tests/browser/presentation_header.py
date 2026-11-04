"""Native dashboard navigation and responsive presentation header checks."""
from pathlib import Path
import os
import re

from playwright.sync_api import expect


def check_header_navigation(browser, origin):
    page = browser.new_page(reduced_motion='reduce')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        # The Next-only test server does not run Vercel's control-service rewrite.
        # This fixture tests native navigation/history, not dashboard authentication.
        page.route(f'{origin}/dashboard', lambda route: route.fulfill(
            status=200, content_type='text/html', body='<main><h1>Dashboard route reached</h1></main>'))
        for width, height in ((1440, 900), (1024, 768), (768, 1024), (390, 844), (320, 740)):
            page.set_viewport_size({'width': width, 'height': height})
            page.goto(f'{origin}/capstone#8')
            expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
            link = page.get_by_role('link', name='운영 대시보드로 이동', exact=True)
            expect(link).to_have_attribute('href', '/dashboard')
            expect(link).to_have_text('대시보드')
            assert link.get_attribute('target') is None
            expect(link).to_be_visible()
            for zoom in ('', '2'):
                page.locator('.deck-root').evaluate('(el, zoom) => { el.style.zoom = zoom; }', zoom)
                # Include the optional microphone-stop action without opening a
                # permission dialog or activating audio in the test environment.
                for microphone in (False, True):
                    if microphone:
                        page.locator('.deck-header-actions').evaluate("""el => {
                            const b=document.createElement('button'); b.id='header-mic-fixture';
                            b.className='mic-active'; b.textContent='● 끄기'; el.append(b);
                        }""")
                    result = page.locator('.deck-topbar').evaluate("""header => {
                        const h=header.getBoundingClientRect(), items=[header.querySelector('.deck-logo'),
                            ...header.querySelector('.deck-header-actions').children].filter(el=>el.getClientRects().length);
                        const failures=[];
                        for(let i=0;i<items.length;i++){
                            const el=items[i],r=el.getBoundingClientRect(),range=document.createRange();
                            if(r.left<h.left-1 || r.right>h.right+1 || r.top<h.top-1 || r.bottom>h.bottom+1)failures.push('header item outside header');
                            range.selectNodeContents(el);
                            for(const t of range.getClientRects())if(t.width&&t.height&&(t.left<r.left-1||t.right>r.right+1))failures.push('header label clips');
                            for(const other of items.slice(i+1)){
                                const o=other.getBoundingClientRect();
                                if(Math.min(r.right,o.right)-Math.max(r.left,o.left)>1 && Math.min(r.bottom,o.bottom)-Math.max(r.top,o.top)>1)failures.push('header actions overlap');
                            }
                        }
                        return {failures};
                    }""")
                    assert not result['failures'], (width, height, zoom, microphone, result)
                    if microphone:
                        page.locator('#header-mic-fixture').evaluate('el => el.remove()')
                page.locator('.deck-root').evaluate("el => { el.style.zoom = ''; }")
            screenshots = Path(os.environ.get('ALEPH_HEADER_SCREENSHOTS', '/tmp/aleph-build-artifacts/header'))
            screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshots / f'presentation-header-{width}x{height}.png'))
            link.focus()
            expect(link).to_be_focused()
            link.press('Enter')
            expect(page).to_have_url(f'{origin}/dashboard')
            expect(page.get_by_role('heading', name='Dashboard route reached')).to_be_visible()
            page.go_back()
            expect(page).to_have_url(f'{origin}/capstone#8')
            expect(page.locator('.slide-active .deck-slide')).to_have_attribute('aria-label', re.compile('^9번째 슬라이드'))
        assert not errors, errors
        print('Presentation dashboard header: five widths, 200% zoom, microphone layout, Enter and Back passed', flush=True)
    finally:
        page.close()
