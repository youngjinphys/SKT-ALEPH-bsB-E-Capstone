"""Cloud-only guide assembly and native landing navigation contracts."""
from html.parser import HTMLParser
import unittest
from cloud.assets import assets
from cloud.onboarding import HTML as ENROLL_HTML
from cloud.tutorial import HTML as GUIDE_HTML, CSS as GUIDE_CSS, JS as GUIDE_JS
from policy_server.console_assets import HTML as LOCAL_HTML, CSS as LOCAL_CSS, JS as LOCAL_JS


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.tags=[]; self.feed(html)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class TutorialAssets(unittest.TestCase):
    def test_dashboard_brand_is_one_native_same_origin_root_link(self):
        html, _, _ = assets()
        brands=[(tag,a) for tag,a in Tags(html).tags if a.get('class')=='brand']
        self.assertEqual(len(brands),1)
        tag, attrs=brands[0]
        self.assertEqual((tag,attrs['href']),('a','/'))
        self.assertNotIn('target',attrs)
        self.assertNotIn('onclick',attrs)
        self.assertIn('ALEPH',attrs['aria-label'])
        self.assertIn('PROTECTIVE DNS',html)

    def test_only_cloud_assets_include_guide(self):
        html,css,js=assets()
        self.assertEqual(html.count('id="cloud-guide"'),1)
        self.assertIn(GUIDE_HTML,html)
        self.assertIn(GUIDE_CSS,css)
        self.assertIn(GUIDE_JS,js)
        self.assertNotIn('cloud-guide',LOCAL_HTML+LOCAL_CSS+LOCAL_JS)
        self.assertIn('<div class="brand">',LOCAL_HTML)
        ids=[a['id'] for _,a in Tags(html).tags if 'id' in a]
        self.assertEqual(len(ids),len(set(ids)))

    def test_nonmodal_accessible_guide_is_hidden_until_requested(self):
        tags={a['id']:(tag,a) for tag,a in Tags(GUIDE_HTML).tags if 'id' in a}
        _,guide=tags['cloud-guide']
        self.assertEqual(guide['role'],'dialog')
        self.assertEqual(guide['aria-modal'],'false')
        self.assertIn('hidden',guide)
        self.assertIn(guide['aria-labelledby'],tags)
        self.assertIn(guide['aria-describedby'],tags)
        self.assertEqual(tags['cloud-guide-open'][1]['aria-expanded'],'false')
        self.assertEqual(tags['cloud-guide-open'][1]['type'],'button')
        self.assertEqual(tags['cloud-guide-title'][1]['tabindex'],'-1')
        self.assertFalse(any(tag=='form' for tag,_ in Tags(GUIDE_HTML).tags))

    def test_guide_does_not_add_privileged_operations_or_storage(self):
        for forbidden in ('fetch(', 'api(', 'localStorage', 'sessionStorage', '.submit(', 'innerHTML', 'cloudConnect(', 'cloudFile('):
            self.assertNotIn(forbidden,GUIDE_JS)
        self.assertIn('navigateTo(step.view)',GUIDE_JS)
        self.assertIn("document.addEventListener('ops:locked'",GUIDE_JS)
        self.assertIn('forced-colors:active',GUIDE_CSS)
        self.assertIn('노드 연결 파일 등록',ENROLL_HTML)
        self.assertIn('노드 연결 파일 등록',GUIDE_JS)

if __name__=='__main__':unittest.main()
