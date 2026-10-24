"""외부 의존성 없는 프론트엔드 기본 테스트 (DNS/HTTPS 기능 테스트 아님)."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attrs = []

    def handle_starttag(self, tag, attrs):
        self.attrs.append((tag, dict(attrs)))


class PortalTests(unittest.TestCase):
    def read(self, name):
        return (PUBLIC / name).read_text(encoding='utf-8')

    def test_expected_pages_and_assets(self):
        for name in ['index.html', 'phishing-block.html', 'phishing-warning-continue.html', 'portal.css', 'portal.js', 'favicon.svg']:
            with self.subTest(name=name):
                self.assertGreater((PUBLIC / name).stat().st_size, 250)

    def test_accessible_layout_navigation(self):
        for page in ['index.html', 'phishing-block.html', 'phishing-warning-continue.html']:
            with self.subTest(page=page):
                text = self.read(page)
                parser = Elements()
                parser.feed(text)
                links = [d['href'] for tag, d in parser.attrs if tag == 'a' and 'href' in d]
                scripts = [d.get('src') for tag, d in parser.attrs if tag == 'script']
                css = [d.get('href') for tag, d in parser.attrs if tag == 'link' and d.get('rel') == 'stylesheet']
                self.assertEqual(scripts, ['./portal.js'])
                self.assertEqual(css, ['./portal.css'])
                self.assertIn('#main', links)
                self.assertEqual(sum(tag == 'main' for tag, _ in parser.attrs), 1)
                self.assertEqual(sum(tag == 'h1' for tag, _ in parser.attrs), 1)
                self.assertIn('lang="ko"', text)
                self.assertIn('noindex, nofollow, noarchive', text)
                self.assertIn('aria-current="page"', text)
                for link in links:
                    if link.startswith('./'):
                        self.assertTrue((PUBLIC / link[2:]).exists(), f'{page}: {link}')
                    else:
                        self.assertTrue(link.startswith('#'), f'External link: {page}: {link}')

    def test_block_warning_have_distinct_samples_and_safe_form(self):
        for page, mode, score in [('phishing-block.html', 'block', '94'), ('phishing-warning-continue.html', 'warn', '72')]:
            with self.subTest(page=page):
                html = self.read(page)
                self.assertIn(f'data-mode="{mode}"', html)
                self.assertIn(f'aria-valuenow="{score}"', html)
                self.assertIn('실측 결과 아님', html)
                self.assertIn('reported-reason', html)
                self.assertIn('draft-box', html)
                self.assertIn('접수 서버는 아직', html)
                self.assertNotIn('<form action=', html)
                parser = Elements()
                parser.feed(html)
                self.assertTrue(all('name' not in attrs for tag, attrs in parser.attrs if tag in {'input', 'textarea', 'button'}))
                self.assertNotIn('<script>', html)
                self.assertNotIn('history.back()', html)
        self.assertNotIn('continue-button', self.read('phishing-block.html'))
        self.assertIn('continue-dialog', self.read('phishing-warning-continue.html'))

    def test_no_untrusted_url_based_redirect_or_network_request(self):
        script = self.read('portal.js')
        for snippet in ['location.search', 'location.hash', 'URLSearchParams', 'location.href', 'history.back(', 'fetch(', 'XMLHttpRequest', 'localStorage', 'sessionStorage', 'innerHTML']:
            # JS 코멘트에 검색 키워드가 들어갈 수 있으므로 실행문의 제한 패턴만 별도 확인
            if snippet == 'innerHTML':
                self.assertNotIn('.innerHTML', script)
            elif snippet in ['location.search', 'location.hash']:
                self.assertNotIn('window.' + snippet, script)
                self.assertNotRegex(script, r'(?<![a-zA-Z])' + re.escape(snippet))
            else:
                self.assertNotIn(snippet, script)
        self.assertIn('event.preventDefault()', script)
        self.assertIn('navigator.clipboard?.writeText', script)
        self.assertIn('draftText.value =', script)
        self.assertIn('window.close()', script)

    def test_vercel_security_headers(self):
        data = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
        self.assertEqual(data['outputDirectory'], 'public')
        headers = dict((h['key'], h['value']) for h in data['headers'][0]['headers'])
        csp = headers['Content-Security-Policy']
        for directive in ["default-src 'none'", "frame-ancestors 'none'", "form-action 'none'", "connect-src 'none'", "script-src 'self'", "style-src 'self'"]:
            self.assertIn(directive, csp)
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')

    def test_original_files_are_unchanged(self):
        known = {
            'phishing-block.html': '02f078a5f91e1f7e27e81ff87781d223431b4205da71267666ce5434ed6b4cd8',
            'phishing-warning-continue.html': '139717218ee50c50b95f9dd2e664a25dbe1118f79fef1da161f50863f3ab4dd3',
        }
        for name, digest in known.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((ROOT / 'originals' / name).read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
