"""The shared console palette conveys categories without weakening state cues."""
from pathlib import Path
import re
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'apps'/name/'src') for name in ('policy-server','policy-sync','dns-agent')]


def contrast(a,b):
    def lum(v):
        rgb=[int(v[i:i+2],16)/255 for i in (1,3,5)]
        rgb=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in rgb]
        return sum(x*w for x,w in zip(rgb,(.2126,.7152,.0722)))
    x,y=sorted((lum(a),lum(b)))
    return (y+.05)/(x+.05)


class PaletteTests(unittest.TestCase):
    def setUp(self):
        path=ROOT/'apps/policy-server/src/policy_server/console_palette.py'
        self.assertTrue(path.exists(),'semantic console palette missing')
        from policy_server.console_palette import CSS
        self.css=CSS
        self.tokens=dict(re.findall(r'--(tone-[a-z]+):\s*(#[0-9a-f]{6})',CSS))

    def test_shared_assets_include_palette_after_component_themes(self):
        from policy_server.console_assets import CSS
        self.assertTrue(CSS.rstrip().endswith(self.css.rstrip()))

    def test_muted_category_colors_have_legible_surface_contrast(self):
        roles=('sky','sage','lilac','amber','rose')
        self.assertEqual(len({self.tokens['tone-'+r] for r in roles}),5)
        for role in roles:
            for surface in ('#141b27','#1b2431','#21202c','#172822'):
                with self.subTest(role=role,surface=surface):
                    self.assertGreaterEqual(contrast(self.tokens['tone-'+role],surface),4.5)
        self.assertGreaterEqual(contrast(self.tokens['tone-sage'],'#10211c'),4.5)

    def test_stale_unknown_and_forced_colors_remain_explicit(self):
        for required in ('[data-status="stale"]','[data-state="warning"]',
                         '[data-state="error"]','[data-state="paused"]',
                         '@media (forced-colors: active)', 'CanvasText', 'Highlight'):
            self.assertIn(required,self.css)
        self.assertNotIn('animation:',self.css)
        self.assertNotIn('filter: grayscale',self.css)
        self.assertNotIn('display:none',self.css)

    def test_protocol_and_metric_accents_follow_their_own_legend(self):
        for selector in ('.obs-line.udp','.obs-line.tcp','.obs-key.udp',
                         '.obs-key.tcp','#obs-hit','#obs-cpu-chart','#obs-host-chart',
                         '#obs-traffic-chart','#obs-quality-chart'):
            self.assertIn(selector,self.css)
        self.assertIn('stroke-dasharray: 5 3',self.css)
        self.assertIn('option[value="memory_used_pct"]:checked',self.css)


if __name__=='__main__':unittest.main()
