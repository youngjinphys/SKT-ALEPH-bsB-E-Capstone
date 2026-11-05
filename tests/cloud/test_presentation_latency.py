"""Presentation wording regression checks; deleted CSV validation is not retained."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'apps/web'

class PresentationLatencyTests(unittest.TestCase):
    def test_latency_difference_wraps_between_phrases_without_shrinking_text(self):
        component=(WEB/'src/components/PiNetworkPlan.tsx').read_text()
        styles=(WEB/'src/components/pi-network-plan.css').read_text()
        self.assertIn("</span>{' '}<span>· ",component)
        self.assertIn('.latency-delta>span{white-space:nowrap}',styles)
        self.assertIn('repeat(auto-fit,minmax(min(100%,9em),1fr))',styles)

    def test_latency_presentation_keeps_one_population_and_preserves_other_experiments(self):
        data=json.loads((WEB/'capstone/data/dns-latency.json').read_text())
        self.assertEqual([s['id'] for s in data['series']], [
            'cold_local_first', 'cold_direct_first', 'warm_paired', 'instrument_warm'])
        warm=next(s for s in data['series'] if s['id']=='warm_paired')
        self.assertEqual([a['id'] for a in warm['arms']], ['no_dns','local_upstream','local_repeat'])
        self.assertEqual(sum(a['n'] for a in warm['arms']),120)
        self.assertEqual(sum(a['success'] for a in warm['arms']),120)
        self.assertEqual([a['p50'] for a in warm['arms']],[43.285,49.444,46.3485])
        component=(WEB/'src/components/PiNetworkPlan.tsx').read_text()
        self.assertIn("item.id==='warm_paired'",component)
        self.assertNotIn('setSeriesId',component)
        self.assertNotIn('<button',component)
        self.assertIn("arm.id==='no_dns'||arm.id==='local_upstream'",component)
        self.assertNotIn('Pi 재조회',component)
        self.assertNotIn('latency-quality',component)
        self.assertNotIn('latency-source',component)
        self.assertNotIn('440 / 440',component)

    def test_presenter_notes_describe_fixed_comparison(self):
        slide=json.loads((WEB/'capstone/data/slides/22-pi-network-plan.json').read_text())
        self.assertNotIn('화면을 바꾸면',slide['notes'])
        self.assertIn('화면에는 일반 도메인 40개의 공용 DNS 직접 질의와 Pi 첫 조회 80건',slide['notes'])
        self.assertIn('보조 기록',slide['notes'])

    def test_prototype_summary_no_longer_claims_counterexample(self):
        slide=json.loads((WEB/'capstone/data/slides/13-precedents.json').read_text())
        self.assertNotIn('반례', json.dumps(slide,ensure_ascii=False))
        self.assertEqual(slide['reading']['rows'][2][1],'정책 승인·서명·집행·철회')
        # The Pi result is an observed response; its policy cause remains unknown.
        bypass=json.loads((WEB/'capstone/data/slides/09-bypass.json').read_text())
        self.assertIn('공개 리졸버 1.1.1.1로 별도 질의',bypass['notes'])
        self.assertIn('기존 사설 DNS 실험과 별개',bypass['notes'])
        self.assertIn('사용자가 지정한 Pi DNS로 A 질의를 실제 실행',bypass['notes'])
        self.assertIn('활성 정책은 인증에 실패해 확인하지 못했습니다',bypass['notes'])
        self.assertIn('NXDOMAIN만으로 BLOCK 정책',bypass['notes'])
        self.assertIn('pi-dns-block-20261105',bypass['sources'])
        self.assertNotIn('block-test-loopback-20261104',bypass['sources'])

if __name__ == '__main__':unittest.main()
