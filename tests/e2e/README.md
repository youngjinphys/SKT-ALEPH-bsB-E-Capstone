# 통합 검증 범위

실행 가능한 로컬 DNS 통합 시험은 [DNS tests](../../apps/dns-agent/tests/test_integration.py)에 있습니다.
정상 응답을 주는 통제된 upstream, 정책 차단·SUBTREE·WARN/ALLOW·철회·만료·UDP/TCP·부모 종료를 검증합니다.
원래 NXDOMAIN인 `.test` 응답만으로 차단을 입증하지 않습니다.

이 폴더에 아직 구현하지 않은 종단 간 경로는 원격 정책 인증/다운로드 → DNS → 실제 HTTPS 안내·신고 접수입니다.
포털 화면 검사는 DNS 정책과 사용자 세션이 연결됐다는 증거가 아닙니다.
동작 결과에는 소스 SHA, 정책 해시, 명령·원문 로그, 환경, 미실행 항목을 함께 기록합니다.
