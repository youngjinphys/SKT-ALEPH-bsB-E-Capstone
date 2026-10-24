# Policy Server — 원격 제어 평면 (미구현)

**계획**: 검증된 IOC 수집·중복 제거, 분류 근거·만료 기록, 사람 승인·철회, 버전별 정책 산출물을 관리하고 로컬 DNS 에이전트에 정책을 제공합니다.

## 예정 하위 구획
- `src/policy_server/intel/`: 출처·관측 시각·정규화
- `src/policy_server/review/`: 검토/승인/오탐 처리
- `src/policy_server/publisher/`: 정책 버전·배포 산출물
- `src/policy_server/api/`: 정책 조회/상태 API (경로·인증 미확정)
- `tests/`: 모듈 단위 테스트

**MVP 유연성**: 중앙 DB·서명·원격 API가 준비되지 않았다면 `packages/policy-contract/`의 검증된 로컬 정책 파일로 DNS 실험을 먼저 수행할 수 있습니다. 정책 점수는 직접 자동 차단으로 연결하지 않습니다.

**보안 경계**: 서버 발급 토큰·개인키·운영 DB는 커밋하지 않으며 로컬 적용기의 관리자 권한을 서버에 전달하지 않습니다.

실행 명령/언어/DBMS/접근제어: **아직 팀 미확정·미구현**.
