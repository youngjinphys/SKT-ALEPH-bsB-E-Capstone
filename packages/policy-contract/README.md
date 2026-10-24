# Policy Contract — 공통 인터페이스 (초안 위치)

로컬 DNS와 원격 서버의 구현 코드를 서로 import하지 않고 **버전 있는 JSON 계약**으로 연계합니다.

## 예정 구조
- `schema/`: 정식 JSON Schema 및 스키마 버전
- `examples/`: 테스트용 승인/거부 정책 예제
- `test-vectors/`: 동일 입력을 양쪽 모듈이 판정하는 계약 테스트

## 팀이 합의할 최소 필드
`policy_version`, `fqdn_ascii`(IDNA ASCII), `match_scope`(EXACT vs SUBTREE), `action`, `approved`, `source_ids`, `evidence_ids`, `verified_at`, `expires_at`. 정책 버전과 스키마 버전은 개념적으로 다릅니다.

- 원문 URL, 경로, IP 리터럴, 잘못된 이름·중복·미지원 액션은 거부해야 합니다.
- 위험 점수 `risk_score` 및 임계치 `70`은 검증된 자동 차단 규칙이 아닙니다.
- `.test` 예시는 실제 위협 IOC가 아닙니다. 예제는 **격리 시험 전용**입니다.
- 고정 스키마를 임의로 확정하지 않기 위해 현재 `schema/`와 `examples/`는 **비어 있습니다**. M0 담당자가 원본 계약·수령 확인·반례를 제공한 후 검증된 파일을 추가합니다.
