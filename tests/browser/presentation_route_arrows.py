"""The route diagram keeps arrowheads undistorted at different widths."""
from playwright.sync_api import expect


def check_route_arrows(browser, origin):
    for width, height in ((1440, 900), (1024, 768), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
        try:
            page.goto(f"{origin}/capstone#topology-public")
            expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
            visual = page.get_by_role('button', name='도식', exact=True)
            if visual.is_visible():
                visual.click()
            routes = page.locator('.slide-active .dns-route-topology')
            expect(routes).to_be_visible()
            expect(routes.locator('.dns-route-explanation')).to_have_count(0)
            heads = routes.locator('.dns-route-head')
            expect(heads).to_have_count(4)
            for head in heads.all():
                box = head.bounding_box()
                assert 10 <= box['width'] <= 14 and 10 <= box['height'] <= 14, (width, box)
            for index, name in enumerate(('정책 사전 배포', '보호 DNS 선택', '다른 DNS 경로')):
                button = routes.get_by_role('button', name=name, exact=True)
                button.click()
                expect(button).to_have_attribute('aria-pressed', 'true')
                expect(routes).to_have_attribute('data-stage', str(index))
                expect(routes.locator('.dns-route-explanation')).to_have_count(0)
        finally:
            page.close()
    print('DNS route arrows: fixed arrowhead geometry, three selections and no explanation panel verified')
