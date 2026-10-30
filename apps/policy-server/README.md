# 정책 서버 및 위협 인텔리전스

**현재 구현:** 로컬·단발성 **실제 URL 후보 수집 → Google Safe Browsing v5 검증 → 사람 검토 초안 → DNS 정책 생성** 도구입니다. 원격 검토 API·데이터베이스·자동 차단 서비스는 아직 없습니다. **서명된 정책 파일을 원격 HTTPS로 배포하고 로컬에서 검증 후 발행하는 별도 도구**는 [정책 배포 가이드](../../docs/policy-distribution.md)에 구현돼 있습니다. 다만 별도 systemd 설정이 필요하고 기본 DNS 설치에 자동 포함되지는 않습니다.

[실행 코드](../../scripts/build_real_threat_policy.py) · [오프라인 보안 테스트](../../tests/intel/test_real_threat_policy.py)

## 처음 실행하기

아래 작업은 서버의 DNS·방화벽에 아무런 변경도 주지 않습니다. **실제 위협 URL을 방문하지도 않습니다.** 외부로 요청하는 주소는 OpenPhish 공식 공개 피드와 Google Safe Browsing API뿐입니다.

```sh
mkdir -p /tmp/aleph-intel
chmod 700 /tmp/aleph-intel

# OpenPhish Community Feed 약관을 읽고 수락한 경우만 사용
python3 scripts/build_real_threat_policy.py collect \
  --source openphish --accept-openphish-terms \
  --limit 100 --output /tmp/aleph-intel/candidates.json

# 개인·비밀 URL을 보내지 말 것. 공개 피드 URL이 Google에 전달됩니다.
read -rsp 'Google Safe Browsing API key: ' SAFE_BROWSING_API_KEY; echo
export SAFE_BROWSING_API_KEY
python3 scripts/build_real_threat_policy.py verify \
  --input /tmp/aleph-intel/candidates.json \
  --output /tmp/aleph-intel/verified.json \
  --ack-url-disclosure --ack-noncommercial-use
unset SAFE_BROWSING_API_KEY

# 기본적으로 승인된 규칙은 0개입니다.
python3 scripts/build_real_threat_policy.py review-template \
  --input /tmp/aleph-intel/verified.json \
  --output /tmp/aleph-intel/reviews.json
```

생성 파일은 사용자 소유의 `0600` 권한으로 저장합니다. 실제 URL·API 키·검증된 사이트 목록을 공개 GitHub, DNS 로그, 발표자료 등에 옮기지 마세요. `review-template`의 `reviews`가 비어 있다면 **확인된 후보가 없거나 Google 응답이 정확히 일치하지 않았던 것**이지 사이트들이 안전하다는 증거가 아닙니다.

## 승인과 정책 만들기 (기본적으로 차단 금지)

`reviews.json`의 각 항목은 **`approved: false`**, **`acknowledge_subtree: false`**로 생성됩니다. 사람이 사이트/도메인 전체 소유 및 정상 서비스 영향, 피드 출처, 오탐 가능성을 확인한 경우에만 해당 항목의 `reviewer`·15자 이상의 `reason`을 채우고 두 값을 `true`로 바꿀 수 있습니다.

**절대 경로 한 개의 피싱 정보를 곧바로 도메인·하위 도메인 전부의 악성 판정으로 간주하지 마세요.** 공유 호스팅 및 고위험 플랫폼 도메인은 이 도구에서 차단을 아예 거부합니다. URL만 확인된 피싱과 일반 DNS QNAME 기반 차단은 정확하게 일치하지 않습니다.

Google이 반환한 증거가 **`cacheDuration` 안이고 조회 후 30분 이내**일 때만 승인 가능하며, 생성된 각 BLOCK의 기한은 최대 15분으로 제한됩니다. 증거가 만료되면 다시 API에 확인하고 새 검토 초안을 작성해야 합니다.

```sh
# 실제 사용자에게 제공할 경고·Google 출처 및 정확도 한계 표시가
# 법적/운영상 마련됐을 때만 다음 명령을 사용하십시오.
python3 scripts/build_real_threat_policy.py build \
  --input /tmp/aleph-intel/verified.json \
  --reviews /tmp/aleph-intel/reviews.json \
  --output /tmp/aleph-intel/approved-policy.json \
  --confirm-replacement --acknowledge-user-notice

# 별도 검증. 이미 설치된 DNS는 직접 갱신하지 않습니다.
export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -m dns_agent validate /tmp/aleph-intel/approved-policy.json
```

**중요:** 결과 정책은 지정한 목록으로 전체 차단 정책을 *교체*하는 스냅샷입니다. 기존 승인 목록이 있다면 무심코 덮어써서 차단이 철회될 수 있습니다. 수동 검토 및 기존 정책 병합/안전한 철회 계획 없이 `publish`를 실행하지 마세요. 신규 설치에서는 별도 도메인 허용 모드가 필요 없습니다. 다만 **구형 모드가 남아 있는 이전 설치는** 백업을 갖춘 `upgrade`를 수행해야 하며, 기존 설치 파일을 직접 덮어써서는 안 됩니다. 운영 설치 변경/인수 및 정책 승인 권한은 이 도구가 대행하지 않습니다.

## 승인한 정책의 서명·원격 전달

원격 전송에는 [독립 정책 동기화](../../docs/policy-distribution.md)의 Ed25519
스냅샷을 사용합니다. Google API 응답을 DNS 서버가 직접 조회하지 않으며,
위협 후보와 승인 기록을 DNS에서 재판정하지 않습니다. 새로운 정책은 유효한
기존 목록을 보존하는 **완전한 교체 스냅샷**으로 서명해야 합니다.
서명 또는 전송 실패가 현재 DNS 블랙리스트를 즉시 비우지는 않지만,
개별 규칙의 만료는 독립적으로 작동합니다.

## 데이터 출처, API 및 이용 조건

- **OpenPhish Community:** 공식 [Community Feed](https://openphish.com/phishing_feeds.html). 약 12시간 간격의 제한된 피드이며, [이용 조건](https://openphish.com/terms.html)에 재배포·상업적 활용 등 제한이 있습니다. 학교·팀 내 공유/공개 결과물 재사용도 별도 검토해야 합니다.
- **Google Safe Browsing v5:** [`GET /v5/urls:search`](https://developers.google.com/safe-browsing/reference/rest/v5/urls/search). 최대 50 URL/요청, 여기서는 짧은 GET 길이를 위해 최대 15개씩 전송합니다. **원본 URL이 Google로 공개**되고, 표현식 결과가 조회 URL과 다를 수 있습니다. 다른 표현식을 특정 URL의 일치로 속여 정책에 넣지 않습니다. 결과가 비었다고 안전함을 주장하지 않습니다. Google 약관상 **비상업적 용도**, [출처 표시·30분 최신성·경고 정확도 한계](https://developers.google.com/safe-browsing/terms)가 필수입니다.
- **URLhaus (선택적 오프라인 입력):** `collect --source local-urlhaus --feed-file /private/urls.txt --output ...`로 **이미 적법하게 받은 텍스트 URL 목록**만 가져올 수 있습니다. URLhaus는 피싱 전용이 아닌 악성코드 배포 URL 데이터입니다. [공식 API](https://urlhaus.abuse.ch/api/)에서 별도 인증키가 필요합니다. 이 도구는 URLhaus 인증키를 수집하거나 URLhaus에 직접 접속하지 않습니다.

현재 인텔 파이프라인은 Google API 키가 없는 환경에서 라이브 URL 검증을 수행할 수 없으며, Google 자체 조회 결과에도 오탐·미탐이 있을 수 있습니다. 검증 아티팩트와 승인 파일은 운영 서명·RBAC·신뢰된 데이터베이스가 아닙니다. 후속 서버화 단계에서는 권한, 감사, 공급망 신뢰, 실시간 재검증, 정식 정책 계약, 철회 절차를 추가해야 합니다.

## 안전 시험

```sh
python3 -m unittest discover -s tests/intel -p 'test_*.py' -v
```

테스트는 **가상의 URL·모의 Google 응답만 사용**합니다. 실제 악성 웹페이지를 탐색하지 않고, DNS/방화벽/공용 정책 파일을 변경하지 않습니다.
