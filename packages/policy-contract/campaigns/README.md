# 합성 피싱 캠페인 정책 데이터

`catalog.json`은 **교육용 가상 캠페인 4개와 `.test` 도메인 11개**를 정의합니다. 실존 피싱 도메인 목록, 외부 위협 인텔리전스, 실제 분석 점수 또는 팀이 승인한 운영 정책이 아닙니다.

| 캠페인 | 차단/검토 시나리오 |
| --- | --- |
| `credential-impersonation` | 계정 인증 사칭, 승인·미승인 BLOCK과 WARN |
| `invoice-imitation` | 청구서 사칭, BLOCK·WARN·ALLOW 비교 |
| `parcel-notification` | 배송 알림 사칭, 승인·미승인 BLOCK |
| `support-fraud` | 지원센터 사칭, BLOCK·WARN·ALLOW 비교 |

총 **BLOCK 6건(이 중 실습 승인 4건), WARN 3건, ALLOW 2건**입니다. 각 규칙은 별도의 짧은 유효기간과 가상 `case_id`를 가지고 있습니다. `approved=true`는 **통제된 실습의 입력값**이지 보안 담당자의 신원 확인이나 실제 IOC 심사 완료의 증거가 아닙니다.

## 정책 파일 생성 (DNS를 실행하거나 수정하지 않음)

저장소 루트에서 실행합니다. Python 표준 라이브러리만 필요합니다.

```sh
python3 scripts/build_campaign_policy.py --list
python3 scripts/build_campaign_policy.py > /tmp/aleph-campaign-policy.json
python3 scripts/build_campaign_policy.py --campaign credential-impersonation > /tmp/aleph-credential-policy.json

export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -m dns_agent validate /tmp/aleph-campaign-policy.json
python3 -m dns_agent render /tmp/aleph-campaign-policy.json \
  --upstream 127.0.0.1 --upstream-port 35453

python3 -m unittest discover -s tests/policy -p 'test_*.py' -v
```

**정책은 생성할 때마다 현재 UTC 시각으로 발행됩니다.** 고정된 데이터 스냅샷을 Git에 넣으면 빠르게 만료되므로 실시간 유효 정책 결과물은 커밋하지 않습니다. `--issued-at 2030-01-01T00:00:00Z`는 **재현 가능한 테스트 출력용**이며 지금 시점의 적용 정책으로 사용해서는 안 됩니다.

JSON 입력 계약은 기존 파서와 동일한 **최상위 `issued_at`, `expires_at`, `rules`만** 포함합니다. 캠페인 이름·설명·개별 `case_id`는 카탈로그에 두고, `evidence`에 `synthetic-campaign:<campaign>:<case>` 형태로 출처를 보존합니다. `WARN`·`ALLOW`는 로컬 DNS 차단이 아니며, 승인되지 않은 BLOCK도 적용되지 않습니다. 도메인 범위는 `SUBTREE`이고 `EXACT`는 지원하지 않습니다.

이 기능은 **오프라인 파일 생성 도구**입니다. 원격 API·발행자 인증·서명·자동 갱신·실제 위협 캠페인 상관분석·실제 신고 접수는 포함하지 않습니다. 실제 IOC를 추가하려면 출처 검증·정상 서비스 영향·사람 승인·만료·철회·평가 자료·발행자 인증을 별도로 설계해야 합니다.

[정책 형식](../README.md) · [로컬 DNS 실행](../../../apps/dns-agent/README.md) · [캠페인 정책 생성기](../../../scripts/build_campaign_policy.py)
