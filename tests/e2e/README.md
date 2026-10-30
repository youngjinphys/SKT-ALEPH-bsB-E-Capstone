# 통합 시험

- [DNS 통합 시험](../../apps/dns-agent/tests/test_integration.py): 실제 dnsmasq·통제 upstream, 기본 BLOCK NXDOMAIN, WARN/ALLOW 통과, 선택형 HTTP 안내 모드의 A·AAAA·HTTPS 타입, UDP/TCP와 철회.
- [HTTP 안내 시험](test_http_policy_notice.py): 활성 정책/설정 해시 일치, 승인된 BLOCK/WARN 302, 요청 Host/URL 위조 거부, 정상·미승인 도메인 미프록시, 정적 자산 화이트리스트·보안 헤더·오류 시 503.
- [HTTP 실습 가이드](../../docs/http-notice.md): 기본 포트 53/80의 LAN 접근과 고포트 루프백 시험의 차이.

DNS 응답과 HTTP 302를 함께 검증하더라도 실제 HTTPS 인증·운영 LAN 이용자 경험·자동 신고 접수는 검증되지 않습니다.
