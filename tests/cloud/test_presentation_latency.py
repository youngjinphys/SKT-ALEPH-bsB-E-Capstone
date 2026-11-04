"""Independently verify the unchanged percentile data used in the combined chart."""
from pathlib import Path
import csv
import hashlib
import json
import math
import unittest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'apps/web'

class PresentationLatencyTests(unittest.TestCase):
    def test_every_displayed_percentile_matches_pinned_csv(self):
        data = json.loads((WEB/'capstone/data/dns-latency.json').read_text())
        raw = (ROOT/'docs/review/dns-latency-arms-20261103.csv').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), data['source']['repositoryCsvSha256'])
        rows = list(csv.DictReader(raw.decode().splitlines()))
        self.assertEqual(len(rows), data['rows'])
        included = [r for r in rows if r['warmup_excluded']=='false']
        self.assertEqual(len(included), data['samples'])
        for series in data['series']:
            for arm in series['arms']:
                selected = [r for r in included if r['series']==series['id'] and r['arm']==arm['id']]
                self.assertEqual(len(selected), arm['n'])
                self.assertEqual(sum(r['ok']=='true' for r in selected), arm['success'])
                values = sorted(float(r['elapsed_ms']) for r in selected)
                for metric, proportion in [('p50', .5), ('p95', .95)]:
                    position=(len(values)-1)*proportion
                    lower=math.floor(position);upper=math.ceil(position)
                    expected=values[lower]+(values[upper]-values[lower])*(position-lower)
                    self.assertAlmostEqual(expected, arm[metric], places=10)

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
