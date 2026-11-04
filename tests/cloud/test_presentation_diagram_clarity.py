"""Keep simulation boundaries visible while removing duplicate diagram copy."""
import json
from pathlib import Path
import unittest

WEB = Path(__file__).resolve().parents[2] / 'apps/web'


class DiagramClarityTests(unittest.TestCase):
    def test_policy_example_disclosure_is_independent_of_selected_state(self):
        source = (WEB / 'src/components/SlideVisual.tsx').read_text()
        lifecycle = source.split('function PolicyLifecycle(', 1)[1].split('function Topology(', 1)[0]
        self.assertIn('data-evidence-state="illustration"', lifecycle)
        self.assertIn('<p className="diagram-caption">설명용 예시 · ', lifecycle)
        data = json.loads((WEB / 'capstone/data/diagrams.json').read_text())
        self.assertEqual([item['phase'] for item in data['policyTimeline']], ['정상', '차단', '철회'])
        self.assertEqual([item['response'] for item in data['policyTimeline']],
                         ['A 203.0.113.42', 'NXDOMAIN', 'A 203.0.113.42'])
        self.assertIn('단말 캐시·재질의', data['policyTimeline'][2]['note'])

    def test_pipeline_detail_keeps_stage_output_without_repeating_stage_description(self):
        source = (WEB / 'src/components/SlideVisual.tsx').read_text()
        detail = source.split('<div className="policy-flow-detail"', 1)[1].split('</div>', 1)[0]
        self.assertIn('selected.artifact', detail)
        self.assertNotIn('selected.detail', detail)
        self.assertIn('<span>{stage.detail}</span>', source)

    def test_removed_review_strip_has_no_rendering_or_css_rules(self):
        for path in (WEB / 'src').rglob('*'):
            if path.suffix in ('.tsx', '.css'):
                with self.subTest(path=path.name):
                    self.assertNotIn('policy-review-gates', path.read_text())


if __name__ == '__main__':
    unittest.main()
