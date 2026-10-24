"""선택적 Chromium UI 상호작용 검사.

환경의 로컬 네트워크/파일 탐색 제한을 회피하기 위해 DOM에 정적 페이지를 넣고
동일 CSS와 JS를 주입합니다. 서버 라우팅·응답 헤더·TLS·DNS 테스트는 아닙니다.
"""
from __future__ import annotations

from pathlib import Path
import shutil

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def run():
    binary = shutil.which('chromium') or shutil.which('google-chrome')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=binary, args=['--no-sandbox'])
        css = (PUBLIC / 'portal.css').read_text(encoding='utf-8')
        javascript = (PUBLIC / 'portal.js').read_text(encoding='utf-8')

        def render(page, filename):
            html = (PUBLIC / filename).read_text(encoding='utf-8')
            html = html.replace('<link rel="stylesheet" href="./portal.css">', '')
            html = html.replace('<script src="./portal.js" defer></script>', '')
            page.set_content(html, wait_until='load')
            page.add_style_tag(content=css)
            page.add_script_tag(content=javascript)

        for viewport in ({'width': 1366, 'height': 900}, {'width': 375, 'height': 812}):
            context = browser.new_context(viewport=viewport, color_scheme='dark')
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))

            render(page, 'index.html')
            assert page.locator('h1').count() == 1
            assert '정상 통과' in page.locator('main').inner_text()
            assert page.locator('body').evaluate('el => el.scrollWidth <= innerWidth')
            render(page, 'phishing-block.html')
            assert page.locator('.risk-score strong').inner_text() == '94'
            assert page.locator('#continue-button').count() == 0
            assert page.locator('body').evaluate('el => el.scrollWidth <= innerWidth')
            render(page, 'phishing-warning-continue.html')
            assert page.locator('.risk-score strong').inner_text() == '72'
            assert not page.locator('#report-form button[type=submit]').is_disabled()
            page.locator('#continue-button').click()
            assert page.locator('#continue-dialog').evaluate('el => el.open')
            assert page.url == 'about:blank'  # 방문 URL로 자동 이동하지 않음
            page.locator('[data-close]').click()
            assert not page.locator('#continue-dialog').evaluate('el => el.open')
            page.locator('#reported-domain').fill('https://evil.example/path')
            page.locator('#reported-reason').fill('정상 서비스로 확인되어 검토를 요청합니다')
            page.locator('#report-form button[type=submit]').click()
            assert 'ASCII 도메인' in page.locator('#form-error').inner_text()
            page.locator('#reported-domain').fill('example.test')
            page.locator('#report-form button[type=submit]').click()
            assert page.locator('#draft-box').is_visible()
            assert 'example.test' in page.locator('#draft-text').input_value()
            assert '미제출' in page.locator('#draft-text').input_value()
            page.locator('#copy-draft').click()
            assert '복사' in page.locator('#form-status').inner_text()
            assert page.locator('body').evaluate('el => el.scrollWidth <= innerWidth')
            assert errors == [], errors
            print(f'PASS chromium simulated-DOM interactions {viewport["width"]}px')
            context.close()
        browser.close()


if __name__ == '__main__':
    run()
