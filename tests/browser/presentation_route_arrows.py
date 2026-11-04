"""Every route case shows one DNS, with truthful and undistorted connectors."""
import os
from pathlib import Path
from playwright.sync_api import expect


def check_route_arrows(browser, origin):
    output = Path(os.getenv('ALEPH_SCREENSHOTS', '/tmp/aleph-build-artifacts')) / 'dns-route-cases'
    output.mkdir(parents=True, exist_ok=True)
    cases = ((1440, 900, 1), (1920, 1080, 1), (1366, 768, 1), (1024, 768, 1),
             (768, 1024, 1), (390, 844, 1), (320, 568, 1),
             (1440, 900, 1.25), (1440, 900, 2))
    for width, height, zoom in cases:
        page = browser.new_page(viewport={'width': width, 'height': height}, reduced_motion='reduce')
        try:
            page.goto(f'{origin}/capstone#topology-public')
            expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
            if zoom != 1:
                page.evaluate('zoom => document.body.style.zoom = zoom', str(zoom))
            visual = page.get_by_role('button', name='도식', exact=True)
            if visual.is_visible():
                visual.click()
            routes = page.locator('.slide-active .dns-route-topology')
            expect(routes).to_be_visible()
            selected_boxes = []
            for index, name in enumerate(('정책 사전 배포', '보호 DNS 선택', '다른 DNS 경로')):
                button = routes.get_by_role('button', name=name, exact=True)
                button.click()
                expect(button).to_have_attribute('aria-pressed', 'true')
                expect(routes).to_have_attribute('data-stage', str(index))
                expect(routes.locator('.dns-route-explanation')).to_have_count(0)
                # No hidden or fading second DNS can survive a case change.
                resolver = routes.locator('.dns-route-resolver')
                expect(resolver).to_have_count(1)
                expect(resolver).to_have_attribute('data-resolver', 'external' if index == 2 else 'protected')
                expect(routes.locator('.dns-route-protected')).to_have_count(0 if index == 2 else 1)
                expect(routes.locator('.dns-route-bypass')).to_have_count(1 if index == 2 else 0)
                expect(routes.locator('.dns-route-policy')).to_have_count(1 if index == 0 else 0)
                expect(routes.locator('.dns-route-client')).to_have_count(0 if index == 0 else 1)
                expect(routes.locator('.dns-route-policy-line')).to_have_count(1 if index == 0 else 0)
                expect(routes.locator('.dns-route-answer')).to_have_count(0 if index == 0 else 2)
                if index == 2:
                    expect(resolver).to_contain_text('다른 DNS로 변경')
                    expect(resolver).to_contain_text('이 보호 DNS를 거치지 않음')
                panel_width = routes.evaluate('el => el.clientWidth - parseFloat(getComputedStyle(el).paddingLeft) - parseFloat(getComputedStyle(el).paddingRight)')
                vertical = panel_width <= 440
                heads = routes.locator('.dns-route-head:visible')
                expect(heads).to_have_count(1 if index == 0 else 2)
                expect(heads.first).to_have_attribute('data-direction', 'down' if vertical else 'right')
                if index != 0:
                    expect(heads.last).to_have_attribute('data-direction', 'up' if vertical else 'left')
                for head in heads.all():
                    box = head.bounding_box()
                    assert 10 <= box['width']/zoom <= 14 and 10 <= box['height']/zoom <= 14, (width, zoom, box)
                geometry = routes.evaluate('''root => {
                    const a=root.querySelector('.dns-route-source').getBoundingClientRect();
                    const b=root.querySelector('.dns-route-transfer').getBoundingClientRect();
                    const c=root.querySelector('.dns-route-resolver').getBoundingClientRect();
                    const vertical=c.top>a.bottom-1, failures=[];
                    if(vertical ? !(a.bottom<=b.top+1 && b.bottom<=c.top+1) : !(a.right<=b.left+1 && b.right<=c.left+1)) failures.push('connector overlaps a card');
                    for(const card of root.querySelectorAll('.dns-route-node')) {
                        const box=card.getBoundingClientRect();
                        for(const el of card.querySelectorAll('strong,small,span')) {
                            const range=document.createRange();range.selectNodeContents(el);
                            for(const r of range.getClientRects()) if(r.left<box.left-1 || r.right>box.right+1 || r.top<box.top-1 || r.bottom>box.bottom+1) failures.push('text outside card');
                        }
                    }
                    if(root.scrollWidth>root.clientWidth+1) failures.push('horizontal overflow');
                    return failures;
                }''')
                assert not geometry, (width, height, zoom, index, geometry)
                if index > 0:
                    selected_boxes.append(resolver.evaluate('el => { const r=el.getBoundingClientRect(), m=el.parentElement.getBoundingClientRect(); return {x:r.left-m.left,y:r.top-m.top,width:r.width,height:r.height}; }'))
                routes.scroll_into_view_if_needed()
                page.screenshot(path=str(output / f'case-{index}-{width}x{height}-zoom{zoom}.png'), full_page=True)
            for key in ('x', 'y', 'width', 'height'):
                assert abs(selected_boxes[0][key]-selected_boxes[1][key]) <= 1, (width, height, zoom, key, selected_boxes)
            for name in ('보호 DNS 선택', '다른 DNS 경로', '보호 DNS 선택'):
                routes.get_by_role('button', name=name, exact=True).click()
                expect(routes.locator('.dns-route-resolver')).to_have_count(1)
            expect(routes.locator('.dns-route-resolver')).to_have_attribute('data-resolver', 'protected')
        finally:
            page.close()
    print(f'DNS route cases passed: one DNS per case, explicit replacement, truthful policy/query paths and fixed arrowheads in {len(cases)} viewport/zoom states')
