# ALEPH 원격 정책 배포: 서명 · HTTPS Pull · 로컬 발행

이 경로는 **기존 `dnsmasq` 질의 처리와 분리된 배포 제어 평면**입니다.
원격 URL을 질의마다 조회하지 않습니다. 실제 LAN DNS(`192.168.7.69:53`)에는
인증·재전송·만료를 통과한 정책만 **기존 `system_dns.py publish`**로 반영합니다.
**DB/원격 API/AI 모델은 필수가 아니며 이 구현에 포함되지 않습니다.**

## 구조 및 책임

```text
사람이 승인한 policy.json
          │
          ▼
오프라인 Ed25519 서명자 (서명 개인키: DNS에 배포 금지)
          │
          ▼
정적 current.json ─ HTTPS (운영자가 관리하는 NGINX/웹 호스팅)
          │
          ▼
일반 사용자 aleph-policy-fetch  [TLS·서명·대상 장치 검사/수신함]
          │
          ▼
root aleph-policy-apply  [서명 재검증·버전 방어·배타잠금]
          │
          ▼
기존 ALEPH DNS publish  [원자적 정책 파일·에이전트 ACK]
          │
          ▼
dnsmasq 192.168.7.69:53  [로컬 QNAME 룰로 응답]
```

기존 DNS를 먼저 별도로 설치·검증해야 합니다. [LAN 설치·복구](../infra/edge/README.md).
다운로드 실패·TLS 오류·HTTP 304·서명 오류·버전 역행은 DNS 차단 목록을 **즉시 비우지 않습니다**.
기존 DNS 에이전트가 보존한 마지막 정상 정책은 **원래 규칙/정책 만료시각까지만 유효**합니다.
Google 결과의 최신성/이용 조건을 우회해 무기한 차단하는 기능은 제공하지 않습니다.

## 1. 원격 정책 생성 서버에서 키 준비

Python 3.11+, `python3-cryptography` (또는 `apps/policy-sync/requirements.txt`)
및 기존 `apps/dns-agent/src` 정책 파서가 필요합니다.

```sh
sudo apt-get install -y python3-cryptography openssl
export PYTHONPATH="$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src"

# *오프라인 또는 비공개 서명 계정*에서 수행. 공개 웹 루트에 넣지 말 것.
umask 077
mkdir -p "$HOME/aleph-signing"
openssl genpkey -algorithm Ed25519 -out "$HOME/aleph-signing/signing.pem"
openssl pkey -in "$HOME/aleph-signing/signing.pem" -pubout \
  -out "$HOME/aleph-signing/public.pem"
python3 -m aleph_policy_sync key-id \
  --public-key "$HOME/aleph-signing/public.pem"
```

출력한 64자 `key_id`를 기록합니다. **개인키는 원격 생성기의 제한된 서명 환경에만** 둡니다.
공개키는 DNS 서버의 root 관리 `/etc/aleph-policy-sync/trust/<key_id>.pem`으로 전달합니다.
공개키도 변조되지 않도록 관리자가 fingerprint를 교차 확인해야 합니다.

## 2. 승인 정책 서명 및 게시

`/private/approved-policy.json`은 이미 검토된 완전한 ALEPH JSON 정책입니다.
예시에서는 실습용으로 `python3 scripts/build_campaign_policy.py > /private/approved-policy.json`을
사용할 수 있습니다. 이 스크립트는 **실제 악성 URL 목록을 생성하지 않습니다**.

```sh
mkdir -m 700 -p "$HOME/aleph-signing/releases"
python3 -m aleph_policy_sync sign \
  --policy /private/approved-policy.json \
  --device-id edge-69 --sequence 1 \
  --private-key "$HOME/aleph-signing/signing.pem" \
  --confirm-replacement \
  --output "$HOME/aleph-signing/releases/edge-69-1.json"
```

`--sequence`는 장치별로 반드시 **단조 증가**하도록 관리합니다. 같은 번호에 다른 정책을
서명하더라도 DNS 적용기는 거부합니다. 외부 검증·점수 컷·승인·도메인 선정은 서명 **이전**에 끝납니다.
새 정책은 전체 교체 스냅샷이므로 기존 규칙을 누락하면 정상 철회될 수 있습니다.
사람이 검토한 빈 정책을 전체 철회하려면 **별도 `--confirm-empty`**가 필요하며
서명 내용에도 `withdraw_all`이라는 의도가 포함됩니다.

서명된 JSON(비밀키 없음)만 HTTPS 배포 서버에 게시합니다. 예: NGINX 설정 샘플
[nginx-policy-feed.conf](../infra/edge/policy-sync/nginx-policy-feed.conf).

```sh
# 서명 서버와 웹 호스트가 다른 경우 scp 등 승인된 관리 채널로 전달.
# 웹 서버에서 root로 실행. 파일의 최종 이름은 원자적 rename으로 교체.
sudo install -d -o root -g root -m 0755 /srv/aleph-policy-feed/edge-69
sudo install -o root -g root -m 0644 /private/release/edge-69-1.json \
  /srv/aleph-policy-feed/edge-69/.current.new
sudo mv -Tf /srv/aleph-policy-feed/edge-69/.current.new \
  /srv/aleph-policy-feed/edge-69/current.json
```

위 `/private/release/edge-69-1.json`은 관리 채널로 전송한 위치의 예시입니다.
**공개 배포 URL 접근 제어와 TLS 인증서 설정은 운영자의 책임**입니다.
서명 검증은 무결성을 확인하지만 **누구나 접근 가능한 웹 서버에서 정책 내용의 비밀성까지 보장하지는 않습니다**.
인증이 필요한 환경에서는 HTTPS 프록시에 접근 제어를 구성하고,
수신기의 `--token-file`(비공개 0600 파일)을 사용할 수 있습니다.

## 3. DNS 서버 192.168.7.69에 수신·적용 서비스 설치

먼저 해당 장치에 기존 ALEPH DNS가 설치·정상 작동하고,
`system_dns.py publish`를 수동으로 실행할 수 있는지 확인합니다.
원격 다운로드 코드의 임의 Git checkout을 root 서비스에서 직접 실행하지 마세요.
**서버에서 검토한 소스 전체를 root 소유의 읽기 전용 설치 경로로 복사**하고
그 SHA를 기록한 뒤 사용합니다. 실행 코드·상위 디렉터리를 일반 사용자가 변경할 수 없어야 합니다.

```sh
# Git 저장소 루트에서 수행. 실제 설치 전 소스/소유권을 검토.
sudo install -d -o root -g root -m 0755 /opt/aleph-policy-code
sudo cp -a apps infra /opt/aleph-policy-code/
sudo chown -R root:root /opt/aleph-policy-code
sudo find /opt/aleph-policy-code -type d -exec chmod 0755 {} +
sudo find /opt/aleph-policy-code -type f -exec chmod 0644 {} +

sudo apt-get install -y python3-cryptography
sudo useradd --system --user-group --no-create-home \
  --home-dir /var/lib/aleph-policy-fetch --shell /usr/sbin/nologin \
  aleph-policy-fetch

sudo install -d -o root -g root -m 0755 /etc/aleph-policy-sync/trust
sudo install -o root -g root -m 0644 /private/transferred-public.pem \
  /etc/aleph-policy-sync/trust/PUT_YOUR_64_CHARACTER_KEY_ID_HERE.pem
```

`useradd`는 해당 전용 사용자가 아직 없을 때만 수행합니다. 기존 사용자와 충돌하면
무조건 새로 만들지 말고 관리자가 조사해야 합니다. `private` 경로와 키 이름은 실제 환경으로 교체합니다.

[시스템 서비스 예시](../infra/edge/policy-sync/)에서 `POLICY_HOST`,
`edge-69`, 루트 설치 경로, TLS 인증서/인증 수단을 검토한 뒤 아래 네 unit을
`/etc/systemd/system`에 root 소유로 배치합니다.

- `aleph-policy-fetch.service` / `.timer`: **일반 사용자**, 30초 간격 HTTPS Pull, 서명 확인 후 개인 수신함에 원자적 저장
- `aleph-policy-apply.service` / `.timer`: **root**, 15초 간격 서명·시퀀스 재검증, 기존 DNS `publish`로 로컬 발행

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now aleph-policy-fetch.timer aleph-policy-apply.timer
sudo systemctl start aleph-policy-fetch.service
sudo systemctl start aleph-policy-apply.service
sudo journalctl -u aleph-policy-fetch -u aleph-policy-apply -n 100 --no-pager
```

소스 루트가 위 배포 스크립트와 달라졌다면 unit의 `PYTHONPATH`와 `--dns-admin`을
동시에 갱신해야 합니다. `PYTHONPATH`가 사용자 쓰기 가능한 경로를 가리키지 않는지 검증하세요.
기존 `system_dns.py publish`의 root 파일·잠금·상태 검증은 그대로 적용됩니다.

**단일 테스트 요청(시스템 변경 없음):**

```sh
PYTHONPATH="$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src" \
  python3 -m aleph_policy_sync verify \
  --snapshot /private/edge-69-1.json --device-id edge-69 \
  --trust-dir /private/trusted-public-keys
```

## 오류·모니터링·복구 경계

| 상황 | 동작 |
| --- | --- |
| TLS/서명 실패, HTTP 302, 잘못된 JSON, 과도한 크기 | 새 파일 수신 거절. 기존 DNS 정책 그대로 |
| HTTP `304 Not Modified` | 이미 검증된 기존 수신함 유지. DNS 변경 없음 |
| 시퀀스 역행 또는 같은 시퀀스의 다른 정책 | 관리자 적용기가 거부. 이전 실행 상태 유지 |
| 서명·정책의 만료 | 새 적용 거부. 기존 DNS가 개별 규칙/전체 만료 처리 |
| `publish` 실패 | 시퀀스 적용 완료 기록 안 함. 오류와 적용기의 복구 상태 점검 필요 |
| 검증된 새 빈 정책 | 서명된 `withdraw_all` 의도 확인 후 정상 철회 허용 |
| fetch/apply 중복 실행 | 각각 배타 파일 잠금으로 직렬화/충돌 거부 |

**독립적으로 측정해야 하는 것:** 클라이언트/브라우저/상위 캐시의 이전 A·NXDOMAIN 잔존,
재시작 중 단절, DNSSEC, CNAME/HTTPS/SVCB 응답 체인, 외부 DoH/VPN, 단말 IPv6 DNS.
기존 dnsmasq는 `cache-size=0`, `local-ttl=0`이고 QNAME `SUBTREE` 판정만 합니다.
IP IOC의 역방향 조회나 CNAME 역별칭을 완전한 블랙리스트로 펼치지 않습니다.
악성 IP→전체 공유 호스트 차단은 과차단 위험이 커 자동 변환하지 않습니다.

**보안 한계:** 이것은 단일 서명 권한에 기반한 작은 배포 프로토콜이며 TUF 전체 구현은 아닙니다.
서명 키 탈취·악의적 관리자·로컬 root 침해·정책 생성기 자체의 오판·시계 조작은
별도의 대응이 필요합니다. 키 교체 시 새 공개키를 사전 배포하고 이전 키를 회수하세요.
`192.168.7.69` 장비에서의 실제 LAN·방화벽·재부팅·시스템 설치 검증은 별도로 수행해야 합니다.
