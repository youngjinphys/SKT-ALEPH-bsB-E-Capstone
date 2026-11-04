"""DNS narrative: one condition, two exclusive branches, no sequential A/B edge."""
import os
from pathlib import Path
from playwright.sync_api import expect

VIEWPORTS = ((320, 568), (390, 844), (768, 1024), (1024, 768),
             (1366, 768), (1440, 900), (1920, 1080))


def check_dns_decision(browser, origin):
    output = Path(os.getenv("ALEPH_SCREENSHOTS", "/tmp/aleph-build-artifacts")) / "dns-decision"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    for width, height in VIEWPORTS:
        page = browser.new_page(viewport={"width": width, "height": height},
                                reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(origin + "/capstone#dns")
        expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
        points = page.get_by_role('button', name='요점', exact=True)
        if points.is_visible():
            points.click()
        branch = page.locator('.slide-active [data-dns-decision=exclusive]')
        expect(branch).to_be_visible()
        expect(branch.get_by_role('heading', name='승인된 BLOCK 범위에 일치하나요?')).to_be_visible()
        expect(branch.get_by_text('한 질의에는 둘 중 하나만 실행', exact=False)).to_be_visible()
        expect(branch.locator('[data-policy-match]')).to_have_count(2)
        yes = branch.locator('[data-policy-match=yes]')
        no = branch.locator('[data-policy-match=no]')
        expect(yes).to_contain_text('예 · 일치')
        expect(yes).to_contain_text('NXDOMAIN 응답 · 업스트림 조회 없음')
        expect(no).to_contain_text('아니오 · 불일치')
        expect(no).to_contain_text('업스트림 DNS로 질의 전달')
        # Siblings stay on the same row even at 320px. Neither becomes a next step.
        a, b = yes.bounding_box(), no.bounding_box()
        assert abs(a['y'] - b['y']) < 1 and a['x'] + a['width'] < b['x'], (width, a, b)
        geometry = branch.evaluate('''root => {
            const box = root.getBoundingClientRect();
            return {inside:box.left>=0 && box.right<=innerWidth,
                clipped:[...root.querySelectorAll('h2,h3,p,span,li')].filter(el =>
                    el.scrollWidth>el.clientWidth+1 || el.scrollHeight>el.clientHeight+1).map(el=>el.textContent),
                stems:[root.querySelector('ul'),...root.querySelectorAll('li')].every(el =>
                    getComputedStyle(el,'::before').content!=='none')};
        }''')
        assert geometry['inside'] and not geometry['clipped'] and geometry['stems'], (width, geometry)
        branch.scroll_into_view_if_needed()
        page.screenshot(path=str(output / f'dns-or-{width}x{height}.png'), full_page=True)
        # The new group introduces no focus trap and survives pane changes/re-entry.
        visual = page.get_by_role('button', name='도식', exact=True)
        if visual.is_visible():
            visual.click()
            expect(branch).to_be_hidden()
            points.click()
            expect(branch).to_be_visible()
        page.locator('#slide-area').focus()
        page.keyboard.press('ArrowRight')
        expect(page.locator('.slide-active [data-dns-decision]')).to_have_count(0)
        page.keyboard.press('ArrowLeft')
        if points.is_visible():
            points.click()
        expect(page.locator('.slide-active [data-dns-decision=exclusive]')).to_be_visible()
        page.close()
    assert not errors, errors
    print(f'DNS exclusive decision checks passed: {len(VIEWPORTS)} viewports')
