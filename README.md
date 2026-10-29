# SKT ALEPH · E조 Capstone

**피싱 의심 도메인의 정책 검증, DNS 차단·철회, 장애 복구를 재현하는 보안 프로젝트입니다.**
Linux 서버에서 허용된 LAN 클라이언트의 UDP/TCP 53번 질의를 처리할 수 있습니다.

| 구성 | 현재 상태 |
| --- | --- |
| [DNS / 시스템 배포](infra/edge/README.md) | 사설 IPv4, 전용 systemd 계정·nftables, 정책 적용·복구 및 제거 |
| [합성 정책](packages/policy-contract/campaigns/README.md) | `.test` 캠페인 4개, 정책 검증·만료·승인 시험 |
| [실제 URL 후보 도구](apps/policy-server/README.md) | OpenPhish 후보 수집, Google Safe Browsing v5 조회, 수동 승인·만료 정책 생성. **DNS 자동 배포 없음** |
| [프론트엔드](apps/warning-portal/README.md) | 정적 차단·경고 안내. 실제 DNS 차단을 HTTPS 화면으로 자동 전환하지 않음 |
| [HTTP 비교 시연](docs/demo.md) | 별도 HTTP 302 실습. HTTPS 리다이렉트가 아님 |
| 원격 정책 서버 | 인증·원격 발행 API·DB·AI 탐지 모델은 미구현 |

## 격리된 Linux DNS 설치

Python 3.11+, systemd, 관리자 권한과 서버의 **고정 사설 IPv4**가 필요합니다. DNS/방화벽·원래 DHCP DNS 및 복구 경로를 먼저 점검하세요.

```sh
sudo apt update
sudo apt install -y python3 dnsmasq-base dnsutils nftables iproute2
python3 scripts/build_campaign_policy.py > /tmp/aleph-policy.json

# 미리보기: 단일 활성 사설 IPv4/NIC 자동 탐색, 시스템 변경 없음
python3 infra/edge/system_dns.py install \
  --upstream 9.9.9.9 --policy /tmp/aleph-policy.json

# 탐지된 192.168.7.69 IP·NIC와 허용 대역을 확인한 뒤에만 설치
sudo python3 infra/edge/system_dns.py install \
  --client-cidr 192.168.7.0/24 \
  --upstream 9.9.9.9 --policy /tmp/aleph-policy.json --apply
```

다중 NIC·Docker·VPN으로 후보가 모호하면 `--listen-ip 192.168.7.69`를 명시합니다. `--client-cidr`는 방화벽 허용 범위이므로 설치 시 직접 승인해야 합니다. 설치 성공 후 **다른 LAN 단말에서** UDP/TCP 53을 검증하고 DHCP DNS를 변경하세요.

```sh
dig @192.168.7.69 example.org A
dig +tcp @192.168.7.69 example.org A
sudo systemctl status aleph-dns.service --no-pager
```

정책을 재발행하려면 `sudo python3 infra/edge/system_dns.py publish --policy /tmp/new-policy.json`을 사용합니다. **입력용 `/tmp` 파일은 자동 감시 대상이 아닙니다.** [설치·발행·제거 및 기존 설치 업그레이드](infra/edge/README.md) 절차를 따르세요.

## DNS 정책 JSON 작성과 적용

`/tmp/aleph-policy.json`은 **입력 파일**입니다. `nano`로 수정만 해서는 이미 설치된 LAN DNS가 갱신되지 않습니다. 실행 중인 서비스가 읽는 파일은 `/etc/aleph-dns/policy.json`이며, 검증된 정책을 발행하려면 `publish`를 호출해야 합니다. **전체 정책을 교체하는 스냅샷**이므로 다른 기존 규칙을 누락하지 마세요.

```sh
# 새 실습 정책 만들기(현재 UTC 기준 시간 자동 생성) 및 편집
python3 scripts/build_campaign_policy.py > /tmp/aleph-policy.json
nano /tmp/aleph-policy.json

# JSON 구문 검사. 정책 의미 검사는 다음 명령에서 수행
python3 -m json.tool /tmp/aleph-policy.json > /dev/null
export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -m dns_agent validate /tmp/aleph-policy.json

# 위 검증과 운영 서비스의 허용 범위를 모두 통과한 경우에만 발행
sudo python3 infra/edge/system_dns.py publish --policy /tmp/aleph-policy.json
sudo journalctl -u aleph-dns -n 60 --no-pager
```

JSON은 최상위 **객체** 하나이며, 그 안의 `rules` 배열에 규칙 객체를 추가합니다. 각 항목은 쉼표로 구분하고 마지막에는 쉼표를 붙이지 않습니다. JSON에는 `//` 주석을 쓸 수 없습니다.

아래는 **구조 설명용 JSON 템플릿**입니다. `YYYY-MM-DD...`는 실제 값이 아니므로, 실행할 때는 **현재 UTC 발행시각 및 유효기간 안의 만료시각**으로 모두 교체해야 합니다. 자동으로 유효한 예시를 만들려면 위의 캠페인 생성 명령이나 `python3 -m dns_agent example`을 이용하세요.

```json
{
  "issued_at": "YYYY-MM-DDTHH:MM:SS+00:00",
  "expires_at": "YYYY-MM-DDTHH:MM:SS+00:00",
  "rules": [
    {
      "domain": "blocked.test",
      "decision": "BLOCK",
      "scope": "SUBTREE",
      "approved": true,
      "expires_at": "YYYY-MM-DDTHH:MM:SS+00:00",
      "evidence": "reviewed-lab-fixture"
    }
  ]
}
```

| JSON 키 | 허용 형식·값 | 의미와 제약 |
| --- | --- | --- |
| `issued_at` | 시간대가 포함된 ISO 8601 문자열 | **정책 전체의 발행시각.** 기존 수락본보다 오래되면 거부. 같은 발행시각에 내용이 달라도 거부. 현재 시각보다 60초 넘게 미래여서는 안 됨 |
| `expires_at` | ISO 8601 문자열 | **전체 정책 만료시각.** `issued_at`보다 나중이며 차이는 최대 **7일**. 현재 만료된 정책은 발행 거부 |
| `rules` | JSON 배열(최대 10,000개) | 전체 규칙의 집합. 필드 누락·잘못된 규칙이 있으면 해당 정책 전체가 거부됨 |
| `rules[].domain` | `"blocked.test"` 등 ASCII 도메인 | URL·IP가 아닌 도메인 이름. 기본 설치는 `.test`만 허용. 공용 도메인은 **설치 시** `--allow-public-domains` 승인이 필요 |
| `rules[].decision` | `"BLOCK"`, `"WARN"`, `"ALLOW"` | `BLOCK`만 DNS 차단. 나머지 둘은 이 정책에서 차단하지 않으며 안전성을 보증하지 않음 |
| `rules[].scope` | `"SUBTREE"` | 해당 도메인과 모든 하위 도메인에 적용. `"EXACT"`는 지원하지 않음 |
| `rules[].approved` | `true`, `false` (따옴표 없음) | `true`이고 `BLOCK`이며 유효한 경우에만 차단. 서명·발행자 인증을 의미하지 않음 |
| `rules[].expires_at` | ISO 8601 문자열 | **개별 규칙 만료시각.** `issued_at`보다 이후이고 **전체 `expires_at` 이하여야 함** |
| `rules[].evidence` | 1–256자 문자열 | 사람이 검토한 근거·사례 식별자. 근거를 적었다고 자동 승인되는 것은 아님 |

실제 값을 가진 예시 파일은 `python3 -m dns_agent example > /tmp/aleph-example.json`으로 생성할 수 있습니다. **예시 도메인 `.test`를 우선 사용**하세요. `naver.com`처럼 정상 서비스의 최상위 도메인을 차단하면 메일·로그인·여러 하위 서비스까지 영향을 받을 수 있으므로, 허가된 격리 실습 외에는 사용하지 마세요.

### 공용 도메인 규칙이 적용되지 않을 때

```sh
# (1) 파일 전체 구조·시간·규칙 관계 확인 (공용 도메인 검증만 명시적으로 허용)
python3 -m json.tool /tmp/aleph-policy.json > /dev/null
PYTHONPATH="$PWD/apps/dns-agent/src" python3 -m dns_agent validate \
  /tmp/aleph-policy.json --allow-public-domains

# (2) 운영 서버가 공용 도메인 모드로 설치되어 있는지 확인
sudo systemctl cat aleph-dns.service | grep '^ExecStart='

# (3) 실제 발행된 규칙과 dnsmasq의 현재 설정 확인
sudo grep -o '"domain":"naver.com"' /etc/aleph-dns/policy.json || true
sudo grep -F 'address=/naver.com/' /var/lib/aleph-dns/active.conf || true
sudo journalctl -u aleph-dns -n 80 --no-pager

# (4) 다른 LAN 클라이언트에서 실제 서버의 TCP 응답 확인
dig +tcp @192.168.7.69 naver.com A
```

`validate --allow-public-domains`는 **로컬 검증만** 바꾸며 설치된 서비스의 권한을 변경하지 않습니다. 운영 DNS의 systemd `ExecStart`에 `--allow-public-domains`가 없다면 `publish`에 임의 옵션을 붙여도 공용 도메인이 활성화되지 않습니다. 기존 설치 변경은 서비스 중단 및 복구 절차를 갖추어 [설치·업그레이드 안내](infra/edge/README.md)를 따르세요. 또한 `issued_at`이 이전 발행본과 같거나, 개별 `expires_at`이 전체 만료보다 늦거나, 발행시각 기준 전체 유효기간이 7일을 초과하면 거부됩니다. `publish`의 **`APPLIED` 또는 `UNCHANGED and ACKNOWLEDGED`** 결과와 서비스 로그를 확인해야 합니다.

## 실제 위협 인텔리전스 (미승인 후보부터 시작)

[실제 URL 수집·Google 검증·사람 승인 사용법](apps/policy-server/README.md)을 참고하세요. Google API 키와 각 공급자의 이용 조건 수락이 있어야 실제 온라인 검증을 수행할 수 있습니다. **원본 URL을 Google에 전달하며, DNS 전체 도메인 차단으로 변환하면 과차단 위험이 있습니다.** 후보 수집·검증은 DNS 정책을 자동 변경하지 않습니다. Google을 근거로 한 경고·차단에는 최신성·출처 표시 조건이 필요합니다.

## 검증과 한계

```sh
export PYTHONPATH="$PWD/apps/dns-agent/src"
REQUIRE_DNSMASQ=1 python3 -m unittest discover -s apps/dns-agent/tests -v
python3 -m unittest discover -s tests/policy -v
python3 -m unittest discover -s tests/intel -v
python3 -m unittest discover -s tests/deployment -v
python3 -m unittest discover -s apps/warning-portal/tests -v
```

**보호 범위:** `BLOCK`은 요청한 도메인과 모든 하위 이름에 NXDOMAIN을 반환합니다(`SUBTREE`). `WARN/ALLOW`는 차단하지 않으며, CNAME 응답 체인·DoH/VPN·기존 DNS 캐시·HTTPS 경고 화면까지 통제하지 않습니다. 외부 위협 피드 및 URL 조회는 **피싱 탐지율 또는 운영 LAN 안전성을 입증하지 않습니다.**

[아키텍처](docs/architecture.md) · [감사](docs/review/commit-audit-20261027.md) · [위협 모델](docs/threat-model.md) · [검증 범위](docs/validation-matrix.md) · [Notion](https://app.notion.com/p/4025db6797f0809ea74ffd4cf2b96240)
