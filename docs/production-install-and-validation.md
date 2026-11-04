# 운영 설치 및 인수 — 원격 정책 서버와 사설 DNS

**필요:** Ubuntu Server(systemd/NGINX), Python 3.11+, python3-cryptography, 신뢰 가능한 HTTPS 인증서, 동기화된 NTP 시각, 운영 복구용 SSH. 아래 호스트명과 주소는 예시이며 실제 값으로 바꾸세요. GitHub CI 성공은 실제 LAN 인수를 보장하지 않습니다.

## 시스템 역할

| 역할 | 예시 주소 | 설치 대상 |
| --- | --- | --- |
| 원격 정책 서버 | policy.example.org, ops.example.org | 정책 수집·서명 정책 공개 파일·HTTPS 관제 콘솔·서명 상태 수신 |
| 사설 DNS | 192.168.7.69:53 | 관리형 DNS·서명 정책 Pull/root 적용·서명 상태 발행 |
| 독립 서명자 | 별도 관리 단말 | 정책 **개인 서명키** 보관 및 승인된 정책에만 Ed25519 서명 |

정책 서명 개인키는 정책 서버의 수집/웹 콘솔이나 DNS 노드에 놓지 않습니다. DNS 텔레메트리에는 **별도로 생성한 장치 개인키**만 DNS 노드에 설치합니다. 정책 서버가 192.168.x.x 노드에 직접 접속할 필요가 없습니다.

## 0. 각 서버에서 동일한 검토 커밋 체크아웃

원격 정책 서버와 DNS 노드 **각각**에서 정상적으로 접근 가능한 소스 위치에 저장소를 다운로드합니다. 운영자 전용 계정에서 실행하고 root로 `git clone`하지 마세요.

```bash
git clone https://github.com/youngjinphys/SKT-ALEPH-bsB-E-Capstone.git
cd SKT-ALEPH-bsB-E-Capstone
git fetch origin main
git checkout --detach <검토한-main-commit-SHA>
git rev-parse HEAD
git status --short
```

`<검토한-main-commit-SHA>`는 GitHub Actions가 통과한 동일한 완전한 SHA로 두 서버 모두 바꿉니다. `git status --short` 결과로 로컬 수정 여부를 확인하세요. 소스 내용과 `/opt/aleph-policy-code` 런타임의 일치성 검사는 별도로 수행하며, 단순 파일 일치가 공급망의 신뢰를 의미하지는 않습니다.

## 1. 독립 정책 서명자: 최초 키

```bash
umask 077
mkdir -p "$HOME/aleph-signing"; chmod 700 "$HOME/aleph-signing"
openssl genpkey -algorithm Ed25519 -out "$HOME/aleph-signing/policy.pem"
chmod 600 "$HOME/aleph-signing/policy.pem"
openssl pkey -in "$HOME/aleph-signing/policy.pem" -pubout \
  -out "$HOME/aleph-signing/policy-public.pem"
```

공개키만 안전한 경로로 두 서버에 전달하고 fingerprint를 독립적으로 비교합니다.

## 2. 원격 정책 서버: 새 설치

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-cryptography nginx openssl
sudo install -o root -g root -m 0600 /secure/google-api-key /root/aleph-google.key
sudo install -o root -g root -m 0644 /secure/policy-public.pem /root/aleph-policy.pub
sudo bash scripts/deploy/install-policy-server.sh \
  --server-name policy.example.org --device-id edge-69 \
  --api-key-file /root/aleph-google.key --public-key /root/aleph-policy.pub \
  --accept-openphish-terms --ack-url-disclosure --ack-noncommercial-use
# 승인된 사용 조건과 프리뷰를 확인한 뒤 동일한 인자 끝에 --apply 추가
```

NGINX 443/TLS의 정책 사이트 vhost에 `/etc/nginx/snippets/aleph-policy-feed.conf`를 포함합니다. 설치기가 TLS 인증서 또는 vhost를 자동 수정하지는 않습니다. 비공개 상태와 공개 피드는 서로 다른 경로입니다: `/var/lib/aleph-policy-server`, `/srv/aleph-policy-feed/edge-69/current.json`.

인증된 관제 웹 앱은 **별도 비특권 서비스**로 설치합니다.

```bash
sudo bash scripts/deploy/install-operations-console.sh \
  --origin https://ops.example.org --device-id edge-69 \
  --admin-cidr 10.10.20.0/24
# 실사용 VPN 관리망으로 교체하고 프리뷰 후 --apply 추가
```

NGINX 443/TLS의 운영 사이트 vhost 안에 `/etc/nginx/snippets/aleph-ops-console.conf`를 포함합니다. `/etc/nginx/conf.d/aleph-ops-limits.conf`는 NGINX HTTP 컨텍스트에 있어야 합니다.

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl status aleph-ops-console.service aleph-policy-refresh.timer --no-pager
sudo ss -lntp | grep ':8765'
```

관제 서비스는 내부 `127.0.0.1:8765`에서 실행되고 NGINX가 `https://ops.example.org`로 연결합니다. `--origin`을 설정하면 Host/Origin이 일치해야 하므로 단순히 브라우저에서 `http://127.0.0.1:8765`로 접근하는 터널은 인증에 실패할 수 있습니다. 실제 HTTPS 관리 도메인을 VPN으로 이용하세요. 액세스 토큰은 `sudo cat /var/lib/aleph-ops-console/token`으로 제한된 터미널에서 확인합니다. 관리 API와 위협 URL을 인터넷에 공개하지 마세요.

### GUI 수집·GSB 검증 연결 (원격 정책 서버, 선택 사항)

기존 정책 서버의 자동 12시간 refresh 타이머 외에 GUI로 즉시 검증할 때는 로컬 Unix 소켓 브리지를 설치합니다. API 키는 기존 `aleph-policy-server` 소유 0600 파일에 유지되며, 관제 웹 프로세스에 키·root·임의 URL 수집 권한을 부여하지 않습니다.

```bash
sudo bash scripts/deploy/install-intel-refresh-bridge.sh
# 서비스와 권한을 검토한 뒤:
sudo bash scripts/deploy/install-intel-refresh-bridge.sh --apply
sudo systemctl status aleph-intel-refresh.socket --no-pager
```

위협 검토 메뉴에서 세 가지 사용 약관 확인 후 **OpenPhish + GSB 새로 검증**을 클릭합니다. 상태 확인 후 **최신 검증 자료 가져오기**를 별도로 실행해야 리뷰 목록이 갱신됩니다. 이전 승인 기록은 0700 비공개 보관 경로로 백업하고 신규 승인값은 모두 `false`로 만듭니다. 기존 서명·배포·DNS 적용은 자동으로 실행하지 않습니다.

## 3. 사설 DNS 노드: 새 설치

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-cryptography dnsmasq-base dnsutils nftables iproute2
export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -B -m dns_agent example > /tmp/aleph-bootstrap.json
sudo install -o root -g root -m 0644 /secure/policy-public.pem /root/aleph-policy.pub
sudo bash scripts/deploy/install-dns-server.sh \
  --listen-ip 192.168.7.69 --interface eth0 --client-cidr 192.168.7.0/24 \
  --upstream 9.9.9.9 --bootstrap-policy /tmp/aleph-bootstrap.json \
  --public-key /root/aleph-policy.pub --device-id edge-69 \
  --policy-url https://policy.example.org/v1/policies/edge-69/current.json
# DNS·방화벽·롤백 경로 검토 후 동일 인자에 --apply 추가
```

기본 53/UDP/TCP 포트 사용 여부, VLAN, 라우터/DHCP의 DNS 안내 및 IPv6 경로를 직접 확인합니다. 설치기는 클라이언트 DHCP와 라우터를 자동 수정하지 않습니다. 비특권 fetch/root apply는 별도 타이머입니다.

## 4. 노드의 상태 보고용 키와 양방향 검증

DNS 노드에서 정책 키와 **다른** Ed25519 장치 키를 생성합니다.

```bash
sudo install -d -o root -g root -m 0700 /root/aleph-ops-secrets
sudo openssl genpkey -algorithm Ed25519 -out /root/aleph-ops-secrets/status.pem
sudo chmod 0600 /root/aleph-ops-secrets/status.pem
sudo openssl pkey -in /root/aleph-ops-secrets/status.pem -pubout \
  -out /root/aleph-ops-secrets/status.pub
```

장치 **공개키만** 원격 정책 서버에 전달합니다. 정책 서버에서 fingerprint를 검증하고 신뢰 목록에 설치합니다.

```bash
export PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
KEY_ID="$(python3 -B -m aleph_policy_sync key-id --public-key /secure/status.pub)"
sudo install -o root -g root -m 0644 /secure/status.pub \
  "/etc/aleph-ops-nodes/trust/$KEY_ID.pem"
```

GUI의 **DNS 노드 등록** 화면에 장치 ID `edge-69`, IP `192.168.7.69`, 이름, 키 fingerprint를 입력합니다. DNS 노드에서:

```bash
sudo bash scripts/deploy/install-dns-telemetry.sh \
  --device-id edge-69 --listen-ip 192.168.7.69 \
  --probe-upstream 1.1.1.1 \
  --report-url https://ops.example.org/v1/nodes/report \
  --private-key /root/aleph-ops-secrets/status.pem \
  --public-key /root/aleph-ops-secrets/status.pub
# 확인 후 동일 인자에 --apply 추가
```

`--probe-upstream`은 별도 비교용 DNS입니다. 실제 차단 도메인에 정상 A 레코드가 없다면 단순 NXDOMAIN을 성공으로 판정하지 않습니다. 서명 정책의 검토·서명·root 발행은 [원격 배포 가이드](remote-policy-deployment.md)에 따라 별도로 실행합니다.


**장치 키 재등록:** 노드를 등록 해제하면 해당 장치 상태 보고 공개키 지문은 신뢰 기록(format 2)의 retired-key 목록에 원자적으로 보관됩니다. 같은 개인키/공개키로 재등록하는 것은 거부됩니다. 노드 재등록에는 *새로운* 장치 전용 Ed25519 키 쌍 생성, 새 공개키의 별도 검증 및 신뢰 등록이 필요합니다. 등록된 새 키로 유효한 보고가 들어오기 전에는 `REKEY_PENDING`으로 처리하고 이전 보고를 운영 정상으로 인정하지 않습니다.

## 5. 실제 운영 검증

```bash
# 원격 정책 서버
sudo systemctl status aleph-ops-console.service aleph-policy-refresh.timer --no-pager
sudo journalctl -u aleph-ops-console -n 80 --no-pager
# DNS 노드
sudo systemctl status aleph-dns aleph-policy-fetch.timer aleph-policy-apply.timer \
  aleph-ops-collect.timer aleph-ops-send.timer --no-pager
sudo systemctl start aleph-policy-fetch.service aleph-policy-apply.service
sudo systemctl start aleph-ops-collect.service aleph-ops-send.service
sudo journalctl -u aleph-ops-collect -u aleph-ops-send -n 80 --no-pager
# 허가된 별도 LAN 단말에서
dig @192.168.7.69 example.org A
dig +tcp @192.168.7.69 example.org AAAA
```

운영 GUI에서 등록 노드·서명된 보고·정책 시퀀스·SHA-256·수신시각·로컬 적용·UDP/TCP와 독립 비교 결과를 확인합니다. 원격 정책 게시 성공과 LAN 클라이언트의 실제 보호 성공은 구분합니다. 장애/재부팅, DNS 캐시·DoH·VPN·IPv6, 키 회수·교체, 만료 후 동작은 별도 LAN 인수 테스트가 필요합니다.

## 6. **기존 설치**의 코드 업그레이드

새 설치용 `install-policy-server.sh`·`install-dns-server.sh`의 `--apply`는 기존 설치를 덮어쓰지 않습니다. 기존 장비는 상태와 개인키를 보존하는 별도 **코드 전용 업그레이드**를 사용합니다. 현재 적용된 정책의 짧은 유효기간 때문에 유지보수 창이 필요합니다.

정책 서버:

```bash
sudo systemctl stop aleph-policy-refresh.timer aleph-policy-refresh.service aleph-ops-console.service
# 브리지가 설치돼 있다면 다음 둘도 중지
sudo systemctl stop aleph-intel-refresh.socket aleph-intel-refresh.service
bash scripts/deploy/upgrade-policy-runtime.sh --role policy
sudo bash scripts/deploy/upgrade-policy-runtime.sh --role policy --apply
sudo systemctl start aleph-ops-console.service aleph-policy-refresh.timer
# 브리지가 기존에 설치·활성화돼 있었다면:
sudo systemctl start aleph-intel-refresh.socket
```

DNS 노드(기존 DNS 데몬은 유지하며 정책 동기화·관제 타이머만 중단):

```bash
sudo systemctl stop aleph-policy-fetch.timer aleph-policy-apply.timer \
  aleph-ops-collect.timer aleph-ops-send.timer
sudo systemctl stop aleph-policy-fetch.service aleph-policy-apply.service \
  aleph-ops-collect.service aleph-ops-send.service
bash scripts/deploy/upgrade-policy-runtime.sh --role dns
sudo bash scripts/deploy/upgrade-policy-runtime.sh --role dns --apply
sudo systemctl start aleph-policy-fetch.timer aleph-policy-apply.timer \
  aleph-ops-collect.timer aleph-ops-send.timer
```

**사전 활성화돼 있던 타이머만 재시작**하세요. 업데이트는 `/opt/aleph-policy-code`만 변경하고 `/etc`, `/var/lib`, `/srv`의 데이터는 보존합니다. 변경 전 소스는 `/opt/.aleph-policy-code.rollback`에 남으며, 다른 업데이트를 수행하기 전에 검증·보관해야 합니다. 두 rename 사이 전원 장애가 나면 백업을 수동 복원해야 할 수 있습니다. **서비스 설정이 없던 장비에 신규 systemd 단위/NGINX snippet까지 설치해주지는 않습니다.**

## 7. 안전 경계

노드 내부의 서명 영수증은 운영 체제나 개인키가 탈취된 상황을 탐지하는 TPM 원격 attestation은 아닙니다. GUI 단일 Bearer 토큰은 다중 운영자 SSO/RBAC가 아니며 로컬 감사 로그도 변경 불가능한 기록이 아닙니다. 별도 LAN 관측·현장 인수·24시간 지속 보호는 운영 환경과 정책 갱신 주기에 따라 검증해야 합니다.

## 배포 소스 일치 검사 (운영 보호)

관제·텔레메트리 최초 설치기는 `--apply` 전에 **현재 체크아웃과 서버의 `/opt/aleph-policy-code`**에 설치된 Python/JSON 모듈 전체의 내용 SHA-256 및 소유권/쓰기 권한을 확인합니다. 구버전·누락·변조·여분 모듈이 있으면 서비스 설치를 중단합니다. 기존 장비라면 먼저 코드 전용 업그레이드를 수행한 다음 신규 서비스 설치기를 실행하세요. 코드 업그레이드 역시 임시로 스테이징한 런타임의 동일성을 검사한 뒤 실제 디렉터리를 교체합니다.

이 검사는 GitHub 커밋 서명이나 공급망 출처 검증을 대신하지 않습니다. 따라서 검토된 `main` 커밋을 명시적으로 체크아웃하고, 운영자가 체크아웃의 출처·변경 여부를 확인해야 합니다.
