"""Presentation wording regression checks; deleted CSV validation is not retained."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'apps/web'

class PresentationLatencyTests(unittest.TestCase):
    def test_prototype_summary_no_longer_claims_counterexample(self):
        slide=json.loads((WEB/'capstone/data/slides/13-precedents.json').read_text())
        self.assertNotIn('반례', json.dumps(slide,ensure_ascii=False))
        self.assertEqual(slide['reading']['rows'][2][1],'정책 승인·서명·집행·철회')
        # Preserve the real counterexample discussion and limitations on slide #9.
        bypass=json.loads((WEB/'capstone/data/slides/09-bypass.json').read_text())
        self.assertIn('CNAME',bypass['notes'])
        self.assertIn('SUBTREE',bypass['notes'])
        self.assertIn('차단 응답은 관측되지 않았습니다',bypass['notes'])

if __name__ == '__main__':unittest.main()
