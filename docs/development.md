# 개발·계약·배포 규칙

## 코드 소유 구획

- `apps/policy-server/`: IOC 수집·검토·정책 발행 API. 서비스 배포 독립.
- `apps/dns-agent/`: 정책 검증·로컬 DNS 구성·원복. 높은 권한이 필요한 적용 부분은 최소화하고 테스트 분리.
- `apps/warning-portal/`: 별도의 HTTPS 안내 및 신고. 정책 적용기의 관리자 권한을 갖지 않음.
- `packages/policy-contract/`: 서버·로컬 공용 **형식**과 계약 테스트 벡터. 런타임 구현 공유 금지.

팀 역할은 [Notion R&R](https://app.notion.com/p/4025db6797f081ccbc82ca5da82ba210) 기준 후보이며 담당자·리뷰어 수락은 별도 확인이 필요합니다.

## 계약 변경 순서

1. 스키마 제안과 정상·거부·경계 테스트 벡터를 같이 작성합니다.
2. 서버와 DNS 에이전트가 **독립적으로** 새 스키마를 검증하는지 확인합니다.
3. 서비스 배포 버전과 정책 데이터 버전의 호환·롤백·만료를 정의합니다.
4. 검증된 커밋·예제·테스트 로그를 Notion M0/M3 작업에 연결합니다.
5. 변경이 승인되기 전에는 샘플 데이터를 실제 차단 규칙에 적용하지 않습니다.

## CI와 검증 범위

`.github/workflows/baseline.yml`은 Python 표준 라이브러리 기반 `scripts/verify_baseline.py`만 실행합니다. 이 검사는 문서/디렉터리 누락, 흔한 위험 파일명 및 예제 JSON 구문을 확인하는 **정적 기준선 점검**입니다. 정상 DNS 응답, 정책 무결성, 실제 서비스 테스트나 비밀 내용 검색을 수행하지 않으며 **애플리케이션 기능 검증으로 표시해서는 안 됩니다.**

`apps/warning-portal/tests/`에는 포털 HTML·URL 오용 금지·원본 보존·보안 헤더의 정적 테스트를 추가했습니다. `.github/workflows/portal.yml`은 해당 변경 시 단위 검사와 JavaScript 문법 검사를 실행하도록 설정했습니다. Chromium DOM 시뮬레이션 검사는 선택 실행이며 실제 HTTP·TLS 및 DNS 연동 검증이 아닙니다.

DNS/원격 서버 코드가 구현되면 모듈별 단위·공통 계약 테스트를 추가하고, `packages/policy-contract/` 변경 시 원격 서버와 로컬 DNS 양쪽의 호환성을 검사합니다. 격리 VM의 DNS/HTTPS·원복 증빙은 별도 결과로 보관합니다. **테스트 부재를 통과 처리하지 않습니다.**
