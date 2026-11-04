"""Protocol state arrows are forward, font-independent, and unclipped."""
import os
from pathlib import Path
from playwright.sync_api import expect


def check_protocol_edges(browser, origin):
    output = Path(os.getenv('ALEPH_SCREENSHOTS', '/tmp/aleph-build-artifacts')) / 'protocol-edges'
    output.mkdir(parents=True, exist_ok=True)
    cases = [(320, 568, 1), (390, 844, 1), (768, 1024, 1), (1024, 768, 1),
             (1366, 768, 1), (1440, 900, 1), (1920, 1080, 1),
             (1440, 900, 1.25), (1440, 900, 2)]
    for width, height, zoom in cases:
        page = browser.new_page(viewport={'width': width, 'height': height}, reduced_motion='reduce')
        page.goto(origin + '/capstone#http')
        expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
        if zoom != 1:
            page.evaluate('zoom => document.body.style.zoom = zoom', str(zoom))
        visual = page.get_by_role('button', name='도식', exact=True)
        if visual.is_visible():
            visual.click()
        root = page.locator('.slide-active .protocol-walkthrough')
        expect(root).to_be_visible()
        expect(root.locator('.protocol-standard-panel, #panel-standards, #tab-ede, #tab-sde')).to_have_count(0)
        assert '⊣' not in root.inner_text()
        for protocol in ('http', 'https'):
            button = page.get_by_role('button', name=protocol.upper(), exact=True)
            if button.is_visible():
                button.click()
            row = root.locator(f'[data-protocol={protocol}]')
            expect(row).to_be_visible()
            expect(row.locator('.restored-node')).to_have_count(3)
            edges = row.locator('.restored-protocol-arrow')
            expect(edges).to_have_count(2)
            panel_width = root.evaluate('el => el.clientWidth - parseFloat(getComputedStyle(el).paddingLeft) - parseFloat(getComputedStyle(el).paddingRight)')
            direction = 'down' if width <= 780 or panel_width <= 560 else 'right'
            for edge in edges.all():
                visible = edge.locator('svg:visible')
                expect(visible).to_have_count(1)
                expect(visible).to_have_attribute('data-direction', direction)
                geometry = visible.evaluate('''svg => {
                    const box=svg.getBoundingClientRect(), lane=svg.parentElement.getBoundingClientRect();
                    const before=svg.parentElement.previousElementSibling.getBoundingClientRect();
                    const after=svg.parentElement.nextElementSibling.getBoundingClientRect();
                    const vertical=svg.dataset.direction==='down';
                    return {sized:box.width>=12 && box.height>=12,
                        contained:box.left>=lane.left-1 && box.right<=lane.right+1 && box.top>=lane.top-1 && box.bottom<=lane.bottom+1,
                        forward:vertical ? before.bottom<=box.top+1 && box.bottom<=after.top+1 : before.right<=box.left+1 && box.right<=after.left+1,
                        clipping:getComputedStyle(svg.parentElement).overflow};
                }''')
                assert geometry['sized'] and geometry['contained'] and geometry['forward'], (width, height, zoom, protocol, geometry)
                assert geometry['clipping'] == 'visible', geometry
            for card in row.locator('.restored-node').all():
                readable = card.evaluate('''card => {
                    const box=card.getBoundingClientRect(), title=card.querySelector('strong');
                    const failures=[];
                    if(title.clientWidth < parseFloat(getComputedStyle(title).fontSize)*3.5) failures.push('title too narrow for a word');
                    for(const el of card.querySelectorAll('strong,small')) {
                        const range=document.createRange(); range.selectNodeContents(el);
                        for(const rect of range.getClientRects()) {
                            if(rect.left<box.left-1 || rect.right>box.right+1 || rect.top<box.top-1 || rect.bottom>box.bottom+1) failures.push('text outside card');
                        }
                    }
                    return failures;
                }''')
                assert not readable, (width, height, zoom, protocol, readable)
            # An arrow enters a failure state, not an HTTP request on the HTTPS lane.
            if protocol == 'https':
                expect(row.locator('.restored-node').last).to_contain_text('HTTP 이전 중단')
                expect(row.locator('.protocol-packet')).to_have_count(0)
            row.scroll_into_view_if_needed()
            page.screenshot(path=str(output / f'{protocol}-{width}x{height}-zoom{zoom}.png'), full_page=True)
        page.close()
    page = browser.new_page(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
    page.goto(origin + '/capstone#introduction')
    first = page.locator('.slide-active .intro-stage').first
    expect(first).to_be_visible()
    expect(first.locator('p')).to_have_count(0)
    expect(first).not_to_contain_text('조회 근거와 도메인 범위를 사람이 검토·승인')
    page.close()
    print(f'Protocol arrows and removed panels passed: {len(cases)} viewport/zoom cases; introduction caption absent')
