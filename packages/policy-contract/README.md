# 현재 구현의 정책 입력

이 형식은 격리 DNS 구현과 테스트의 계약입니다. **팀의 운영 합의·원격 API 명세가 아닙니다.**
기존 제출본의 `[{"domain":"..."}]`은 단순 차단목록이었습니다. 새 입력과 혼동하면
WARN/ALLOW도 차단될 수 있으므로 구형 입력을 자동 추측·변환하지 않습니다.

| 필드 | 의미 |
| --- | --- |
| `issued_at` / `expires_at` | 시간대가 있는 발행·만료 시각. 최대 유효기간 7일 |
| `rules[].domain` | ASCII 이름. 소문자·끝 점 하나 정규화, 기본 `.test`만 허용 |
| `rules[].decision` | BLOCK/WARN/ALLOW. 점수로 판정하지 않음 |
| `rules[].scope` | SUBTREE만 지원. 정확한 단일 이름으로 오해하지 않음 |
| `rules[].approved` | 검토된 로컬 파일의 집행 플래그. 인증 수단은 아님 |
| `rules[].expires_at` / `evidence` | 항목 만료와 짧은 근거 참조 |

검증기는 중복 JSON 키·도메인, 미지 필드, 잘못된 이름/시각, 상하위 판정 충돌을 거부합니다. 입력뿐 아니라 정규화·이스케이프한 정책도 1 MiB 이내여야 합니다.
유효하지만 미승인/만료된 항목만 제외하며, 잘못된 항목 하나를 조용히 버리고 나머지를 적용하지 않습니다.
동일한 발행시각에 다른 내용이나 이전 발행시각의 정책을 다시 적용하지 않습니다.

[JSON Schema](schema/policy.schema.json)는 구조 검사입니다. 시각 간 관계·기한·IP·예약 이름·범위 충돌 등은
`dns_agent.policy.parse_policy`의 의미 검증도 필요합니다. IDNA 변환/유사 문자 분석은 공급자 측에서 검토하며
로컬 파서는 Unicode 입력을 임의로 고치지 않습니다.

[합성 캠페인 실습 데이터](campaigns/README.md)는 4개 가상 캠페인을 카탈로그로 보관하고 `scripts/build_campaign_policy.py`로 현재 유효한 평면 정책 JSON을 만듭니다. 캠페인 그룹 메타데이터를 기존 파서의 `rules`에 직접 넣지 않으며, `evidence`에 가상 캠페인·사례 출처를 기록합니다. 이 데이터는 **실제 IOC·외부 정보 피드·팀의 운영 승인 자료가 아닙니다.**

[예제](examples/lab-policy.json)는 날짜가 고정된 참고 자료입니다. 실제 테스트에는
`python3 -m dns_agent example`로 새 데이터를 생성합니다. [반례](test-vectors/cases.json)는 정책이 아닙니다.
해시·발행시각은 문서의 버전명 대신 사용하는 표기가 아니라, 실행 중 재전송/내용 충돌을 점검하는 보안 데이터입니다.
