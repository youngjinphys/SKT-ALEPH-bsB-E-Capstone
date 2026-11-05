"""Direct presentation copy retains factual scope and safety disclosures."""
import json
from pathlib import Path
import re
import unittest

WEB = Path(__file__).resolve().parents[2] / 'apps/web'
DATA = WEB / 'capstone/data'
# Target rhetorical contrast, not functional negatives such as collection bans,
# NXDOMAIN, unsupported features, uncertain results or security warnings.
CONTRAST = re.compile(r'아닙니다|아니라|뜻하지(?:는)?\s*않|의미하지(?:는)?\s*않|입증하지(?:는)?\s*않')

# These exact sentences state evidence and TLS limits, rather than an editorial
# contrast. Keep the exemption narrow and separately require each disclosure.
SCOPE_DISCLOSURES = (
    '선례는 운영 가능성을 보여 주지만 저희 제안이 이미 배포됐다는 뜻은 아닙니다.',
    'HTTPS에서 원래 호스트의 인증서 검증을 우회해 안내할 수 있다는 의미도 아닙니다.',
    'warning.or.kr은 차단 안내 선례이며, 임의 HTTPS 리다이렉트 또는 ISP 참여의 증거가 아닙니다.',
    'ISP 참여나 HTTPS 안내 구현의 증거는 아닙니다.',
)


def editorial_contrast(text):
    for disclosure in SCOPE_DISCLOSURES:
        text = text.replace(disclosure, '')
    return CONTRAST.search(text)


def read_json(path):
    return json.loads(path.read_text())


class PresentationDirectCopyTests(unittest.TestCase):
    def test_all_authored_slides_and_script_use_direct_descriptions(self):
        for path in sorted((DATA / 'slides').glob('*.json')):
            with self.subTest(path=path.name):
                self.assertIsNone(editorial_contrast(path.read_text()))
        for name in ('diagrams.json', 'dns-latency.json', 'landing.json'):
            with self.subTest(data=name):
                self.assertIsNone(editorial_contrast((DATA / name).read_text()))
        script = (WEB / 'docs/presentation/final-20min-scenario.md').read_text()
        self.assertIsNone(editorial_contrast(script))

    def test_visible_source_notes_use_direct_descriptions(self):
        sequence = read_json(DATA / 'sequence.json')
        active = {item['id'] for item in sequence['slides']}
        sources = read_json(DATA / 'sources.json')
        for path in (DATA / 'slides').glob('*.json'):
            slide = read_json(path)
            if slide['id'] not in active:
                continue
            for key in slide.get('sources', []):
                with self.subTest(slide=slide['id'], source=key):
                    self.assertIsNone(editorial_contrast(sources[key].get('note', '')))

    def test_scope_disclosures_are_preserved_without_allowing_other_contrast(self):
        slide = read_json(DATA / 'slides/12-topology-public.json')
        scenario = (WEB / 'docs/presentation/final-20min-scenario.md').read_text()
        source = read_json(DATA / 'sources.json')['warning-page']['note']
        for disclosure in SCOPE_DISCLOSURES[:2]:
            self.assertIn(disclosure, slide['notes'])
            self.assertIn(disclosure, scenario)
        self.assertIn(SCOPE_DISCLOSURES[2], slide['presentation']['reviewNote'])
        self.assertIn(SCOPE_DISCLOSURES[3], source)
        self.assertIsNone(editorial_contrast(' '.join(SCOPE_DISCLOSURES)))
        self.assertIsNotNone(editorial_contrast('이것은 A가 아니라 B입니다.'))
        self.assertIsNotNone(editorial_contrast('이것은 단순한 설명이 아닙니다.'))

    def test_measurement_scope_and_statistical_limits_remain_explicit(self):
        friction = read_json(DATA / 'slides/01-friction.json')
        self.assertIn('등록 도메인', friction['notes'])
        self.assertIn('해당 피드', friction['notes'])
        self.assertIn('별도의 인과 분석', friction['notes'])
        latency = read_json(DATA / 'slides/22-pi-network-plan.json')['notes']
        for phrase in ('일반 도메인 40개', 'Pi 첫 조회 80건', '활성 차단 규칙 0건',
                       '같은 장비에서 정책 적용 전후', '별도 포트', 'p50과 p95'):
            self.assertIn(phrase, latency)
        data = read_json(DATA / 'dns-latency.json')
        self.assertEqual((data['rows'], data['excluded']), (446, 6))
        self.assertIn('각각 별도 분석', data['statistics']['interpretation'])

    def test_security_conditions_remain_explicit(self):
        architecture = read_json(DATA / 'slides/04-architecture.json')['notes']
        for phrase in ('위협 근거가 0건', '추가 근거', 'EXACT 입력은 거부',
                       '하위 서비스 영향', '게시 성공과 실제 적용은 따로 확인'):
            self.assertIn(phrase, architecture)
        protocol = read_json(DATA / 'slides/07-http.json')['notes']
        for phrase in ('원래 호스트의 신뢰된 인증서', 'TLS 신원 검증', '후속 항목'):
            self.assertIn(phrase, protocol)
        policy = read_json(DATA / 'slides/06-policy-demo.json')['notes']
        for phrase in ('일반 전달을 유지', '추가 근거가 필요한 검토 상태', '자기 유효기간까지만'):
            self.assertIn(phrase, policy)

    def test_simulation_keeps_fiction_and_no_collection_disclosures(self):
        component = (WEB / 'src/components/FishingDemo.tsx').read_text()
        self.assertIsNone(CONTRAST.search(component))
        for phrase in ('교육용 가상 법률 사이트', '합성 실습 설정', '교육용 가상 프로필',
                       '수집하거나 전송하지 않습니다', '개인정보·결제정보를 받지 않으며 실제 상담은 제공하지 않습니다'):
            self.assertIn(phrase, component)
        self.assertNotRegex(component, r'<(?:input|form)\b')


if __name__ == '__main__':
    unittest.main()
