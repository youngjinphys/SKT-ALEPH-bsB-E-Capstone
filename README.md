# SKT ALEPH E조 Capstone

피싱 도메인의 **정책 검증·차단·철회·복구**를 실험하는 Protective DNS 프로젝트입니다. Linux LAN DNS, 별도 안내 포털, 실제 URL 후보 수집기를 포함합니다. **자동 AI 탐지·원격 검토 API/DB·HTTPS 강제 안내는 미구현**입니다. 단, 서명된 정책 파일의 HTTPS 수신과 로컬 발행을 위한 **선택형 동기화 도구**는 구현되어 있습니다.

## 시작하기

요구사항: Linux, Python 3.11+, `dnsmasq-base`, `dnsutils`. 시스템 설치에는 systemd·nftables와 관리자 권한도 필요합니다.

```sh
sudo apt update && sudo apt install -y python3 dnsmasq-base dnsutils nftables iproute2
export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -m dns_agent example > /tmp/aleph-policy.json
python3 -m dns_agent validate /tmp/aleph-policy.json
```

### 1. 격리 DNS 실습 (기본 NXDOMAIN)

```sh
python3 -m dns_agent run /tmp/aleph-policy.json \
  --upstream 9.9.9.9 \
  --state-dir "$HOME/.local/state/aleph-dns-lab"
# 다른 터미널:
dig @127.0.0.1 -p 35353 blocked.test A
```

실습용 `.test` 응답은 원래 NXDOMAIN일 수 있으므로 **차단 성공의 단독 증거가 아닙니다**. 정상 응답을 제공하는 격리 upstream에서 적용 전후를 비교하는 통합 시험을 사용하세요. 원래 시스템 DNS 설정과 방화벽은 변경되지 않습니다.

유명 사이트 세 곳을 차단 대상으로 삼아 **본인만 사용하는 격리 고포트**에서
시험할 수도 있습니다. 이 도메인은 정상 사이트이며 악성 판정이 아닙니다.
정책은 15분 동안 `naver.com`, `daum.net`, `google.com`과 각 하위 도메인을
차단합니다. 자동 발행하지 않으며, 생성된 파일은 전체 정책을 교체하므로
승인 없이 운영 DNS에 발행해서는 안 됩니다. 승인된 운영 시험이라면 현재 유효
규칙을 보존하고 새 발행 시각과 제한된 만료 시각을 적용하며, 복구 정책을 미리
준비해야 합니다.

```sh
# 실행마다 독립된 0700 임시 디렉터리 사용
lab_dir=$(mktemp -d "${TMPDIR:-/tmp}/aleph-site-lab.XXXXXXXX")
python3 scripts/build_site_test_policy.py > "$lab_dir/policy.json"
python3 -m dns_agent validate "$lab_dir/policy.json"
python3 -m dns_agent run "$lab_dir/policy.json" \
  --upstream 9.9.9.9 --state-dir "$lab_dir/state"
# 다른 터미널에서: upstream의 정상 응답과 격리 DNS의 NXDOMAIN을 비교
dig @9.9.9.9 naver.com A
dig @127.0.0.1 -p 35353 naver.com A
dig +tcp @127.0.0.1 -p 35353 daum.net AAAA
dig @127.0.0.1 -p 35353 google.com A
```

끝나면 실행 중인 실습 터미널에서 `Ctrl+C`로 종료합니다. 정책은 고포트에만
적용되므로 브라우저의 기본 DNS가 자동으로 바뀌지는 않습니다. 만료 후에는
새 파일을 생성해야 합니다. 운영에 발행하면 해당 사이트와 하위 도메인의 실제
사용자 접근을 방해합니다.

### 2. 선택형 HTTP 차단·경고 안내 (허가된 실습 VM)

기본 DNS에서는 `BLOCK → NXDOMAIN`, `WARN/ALLOW → 비차단`입니다. **다음 실습에서만** 승인된 `BLOCK/WARN`의 DNS A 응답을 안내 서버 IP로 바꾸고, 실제 요청한 `Host`와 DNS 에이전트가 수락한 정책을 검증해 `302`로 기존 포털 화면에 연결합니다. HTTPS/HSTS에는 동작하지 않으며 연결 오류를 유발할 수 있습니다.

```sh
# 터미널 A: 전용 상태 디렉터리의 DNS 모드 (127.0.0.1:35353)
python3 -m dns_agent run /tmp/aleph-policy.json \
  --upstream 9.9.9.9 \
  --state-dir "$HOME/.local/state/aleph-http-lab" \
  --http-sink-ip 127.0.0.1 --ack-http-sinkhole

# 터미널 B: 정책 기반 HTTP 서버 (38080)와 정적 포털 (35173)
python3 -m dns_agent.http_notice \
  --listen-ip 127.0.0.1 --client-cidr 127.0.0.1/32 \
  --state-dir "$HOME/.local/state/aleph-http-lab" \
  --static-dir "$PWD/apps/warning-portal/public" \
  --http-port 38080 --portal-port 35173 --ack-plaintext-only

# 터미널 C: 실제 DNS 응답과 HTTP 302를 별도로 대조
dig @127.0.0.1 -p 35353 blocked.test A
dig @127.0.0.1 -p 35353 warn.test A
curl --noproxy '*' --head \
  --resolve blocked.test:38080:127.0.0.1 http://blocked.test:38080/
curl --noproxy '*' --head \
  --resolve warn.test:38080:127.0.0.1 http://warn.test:38080/
```

**주의:** 고포트 `35353`/`38080` 실습은 브라우저 기본 DNS(53)/HTTP(80)와 다릅니다. 실제 `192.168.7.X → 192.168.7.69` 기본 HTTP 접속에는 해당 VM의 **53번 DNS와 80번 HTTP 안내 서버**가 필요하고, 포털 포트도 클라이언트가 접근할 수 있어야 합니다. 이 실험 모드는 기존 관리형 `aleph-dns.service`의 기본 설정에 자동 적용되지 않으며, 이를 위해 운영 서비스 파일을 직접 편집해서는 안 됩니다. [HTTP 실습 및 서버별 권한·포트 조건](docs/http-notice.md)을 확인하세요.

### 3. LAN DNS 설치 (`192.168.7.69`, HTTP 기능 기본 꺼짐)

```sh
python3 scripts/build_campaign_policy.py > /tmp/aleph-policy.json
# 실제 주소/NIC 자동 탐색만, 시스템 변경 없음
python3 infra/edge/system_dns.py install \
  --upstream 9.9.9.9 --policy /tmp/aleph-policy.json
# 확인된 사설 IP·NIC와 승인된 클라이언트 범위를 이용한 명시적 설치
sudo python3 infra/edge/system_dns.py install \
  --client-cidr 192.168.7.0/24 \
  --upstream 9.9.9.9 --policy /tmp/aleph-policy.json --apply

# 다른 LAN 단말에서 확인
dig @192.168.7.69 example.org A
dig +tcp @192.168.7.69 example.org A
```

DNS 정책 갱신은 입력 파일 수정만으로 되지 않습니다. 검증한 전체 정책을 **수동 발행**해야 합니다.

```sh
python3 -m dns_agent validate /tmp/aleph-policy.json
sudo python3 infra/edge/system_dns.py publish --policy /tmp/aleph-policy.json
sudo journalctl -u aleph-dns -n 60 --no-pager
```

### 설치 후 업데이트와 정책 확인

서버에서 `git pull --ff-only`를 해도 실행 중인 엔진은 바뀌지 않습니다.
관리형 설치는 저장소가 아닌 `/opt/aleph-dns/src`의 복사본을 실행하기 때문입니다.
기존 설치를 지우고 다시 설치할 필요는 없으며, 관리형 `upgrade --apply`로
기존 정책·상태를 보존하면서 갱신합니다. 업그레이드는 DNS를 일시 중단하므로
대체 DNS와 복구 접속 수단을 먼저 확보하고 유효한 정책을 확인해야 합니다.
지원되지 않는 구형 설치나 만료된 정책은 별도 점검이 필요합니다.

현재 발행된 정책은 DNS 서버의 `/etc/aleph-dns/policy.json`, 에이전트의
수락 상태는 `/var/lib/aleph-dns/state.json`에 있습니다. 기본 관리형 DNS 서비스에는 원격 자동 갱신이 연결돼 있지 않습니다. 별도
`aleph-policy-fetch`/`aleph-policy-apply` 서비스를 설치하면 **서명 검증된 스냅샷만**
자동 발행하도록 구성할 수 있습니다. 직접 관리자가 `publish`하는 경로도 유지합니다. 서버에서 조회하거나 SSH로 정책 사본을 주고받는 방법,
코드 업그레이드·정책 발행·복구 절차는
[LAN DNS 가이드](infra/edge/README.md#엔진-코드-업데이트와-운영-서비스-반영)를 확인하세요.

### 4. 원격 서명 정책 배포 (선택)

원격 DB나 DNS 질의 중 원격 API 조회는 필요하지 않습니다. 사람 승인 후 생성한
**전체 정책 JSON**을 Ed25519로 서명하여 HTTPS 정적 엔드포인트에 게시하고,
별도 비특권 수신기가 이를 Pull합니다. root 적용기는 공개키·장치 ID·버전·유효기간을
재검증한 후 기존 `system_dns.py publish` 경로만 호출합니다.

```sh
# 원격 정책 생성기: 비공개 서명 계정, 키 파일은 0600
export PYTHONPATH="$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src"
python3 -m aleph_policy_sync sign \
  --policy /private/approved-policy.json \
  --private-key "$HOME/aleph-signing/signing.pem" \
  --device-id edge-69 --sequence 1 --confirm-replacement \
  --output "$HOME/aleph-signing/releases/edge-69-1.json"
```

키 준비·TLS 서버·DNS 측 systemd 타이머·검증 명령·복구는
**[원격 정책 배포 가이드](docs/policy-distribution.md)**를 따릅니다.
**이 스크립트 자체는 DNS 설정을 수정하지 않으며**, 실제 서버에 타이머를
설치하기 전에는 자동 갱신이 시작되지 않습니다. 다운로드 실패 시 마지막 정상 정책은
저장되지만 **그 정책의 만료기한을 무시하고 무기한 차단하지는 않습니다**.
HTTP 302 실습은 원격 동기화와 별개입니다.

실제 위협 후보 수집·Google Safe Browsing v5 검증은 [인텔 가이드](apps/policy-server/README.md), 배포·백업·기존 설치 업그레이드/제거는 [LAN DNS 가이드](infra/edge/README.md)를 따릅니다. 실제 URL을 발견했다고 도메인/하위 도메인을 자동 차단해서는 안 됩니다.

## 테스트·프로젝트 상태

```sh
REQUIRE_DNSMASQ=1 python3 -m unittest discover -s apps/dns-agent/tests -v
python3 -m unittest discover -s tests/policy -v
python3 -m unittest discover -s tests/intel -v
python3 -m unittest discover -s tests/deployment -v
python3 -m unittest discover -s tests/e2e -v
python3 -m unittest discover -s apps/warning-portal/tests -v
# 동기화 테스트: 서명·HTTPS TLS 루프백·root/비root 역할 분리
PYTHONPATH="$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src" \
  python3 -m unittest discover -s tests/policy_sync -p 'test_snapshot.py' -v
```

`BLOCK`은 기본적으로 도메인과 모든 하위 이름에 적용되는 `SUBTREE`입니다. `EXACT` 미지원, DNSSEC·CNAME 응답 체인·DoH/VPN·기존 연결/캐시·IPv6 클라이언트 경로는 별도 검증 대상입니다. 정책의 `approved=true` 자체가 출처 인증을 제공하지 않습니다.

[아키텍처](docs/architecture.md) · [시연](docs/demo.md) · [위협 모델](docs/threat-model.md) · [검증표](docs/validation-matrix.md) · [Notion](https://app.notion.com/p/4025db6797f0809ea74ffd4cf2b96240)
