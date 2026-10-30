# Linux DNS 서버 배포 · UDP/TCP 53

이 디렉터리는 **별도 Linux DNS 서버에 실제 LAN 질의를 받는 서비스**를 설치합니다.

**HTTP 안내 실험은 별도입니다.** 이 설치기는 기본 NXDOMAIN/WARN 비차단 DNS를 설치하며, 신규 HTTP 실습 옵션과 TCP 80/정적 포털 서비스를 자동 설치하지 않습니다. [선택형 HTTP 302 실습](../../docs/http-notice.md)은 허가된 독립 VM에서 먼저 검증하세요.
반면 `apps/dns-agent/`의 기본 실행은 `127.0.0.1:35353` 격리 시험입니다.

> **배포 경계:** 사설 IPv4의 지정된 LAN 인터페이스·고포트가 아닌 실제 53번, 전용 systemd
> 서비스 계정 및 nftables 테이블을 사용합니다. **운영 중인 다른 DNS 서버를 중단하거나
> `/etc/resolv.conf`, 공유기 DHCP, 기존 방화벽 테이블을 변경하지 않습니다.**
> DHCP와 클라이언트 변경은 설치·검증 후 관리자가 별도로 수행합니다.
>
> 전용 테이블은 설치별 식별자와 규칙 전체를 검사합니다. 다른 구성과 충돌하거나 내용이
> 바뀐 경우 자동으로 덮어쓰거나 삭제하지 않고 중단합니다. 다만 실행 중 방화벽을
> 계속 감시하지는 않으므로 다른 관리자의 변경 이후에는 별도 확인이 필요합니다.

## 필수 사전 점검

- Debian/Ubuntu Linux + systemd + Python 3.11 이상, `dnsmasq-base`, `dnsutils`, `nftables`, `iproute2`.
- 실제 인터페이스에 설정된 **고정 RFC1918 IPv4**, 그 인터페이스로 접속하는 허용 **/24 또는 더 좁은** 클라이언트 대역.
- **업스트림 DNS가 정상 응답**하고 자기 서버로 다시 돌아오지 않는지 확인. 다른 DNS 서비스가 LAN IP:53을 이미 사용하면 설치하지 않습니다.
- 기존 DHCP option 6, 클라이언트 고정 DNS, 방화벽 정책·복구 접속 수단을 기록하고 테스트 창을 확보합니다.
- 새 설치 시작 시 `inet aleph_dns` nftables 테이블, `/etc/aleph-dns`, `/opt/aleph-dns`, `/var/lib/aleph-dns`가 기존에 있다면 설치를 거부합니다. 이전 설치 또는 타 관리자의 설정인지 먼저 조사합니다.

```sh
ip -4 -br address
sudo ss -lunpt '( sport = :53 )'
sudo nft list tables
dig @9.9.9.9 example.org A
```

## 준비 및 실제 설치

저장소의 검증된 소스에서 실행합니다. 다음 명령의 `192.168.7.69`와 `192.168.7.0/24`는 예시이므로 **실제 서버 IP와 허용할 클라이언트 범위를 확인**하세요.

```sh
sudo apt update
sudo apt install -y python3 dnsmasq-base dnsutils nftables iproute2
python3 scripts/build_campaign_policy.py > /tmp/aleph-policy.json
export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -m dns_agent validate /tmp/aleph-policy.json

# 단일 활성 사설 IPv4 및 NIC 탐색과 CIDR 추천 (시스템 변경 없음)
python3 infra/edge/system_dns.py install \
  --upstream 9.9.9.9 --policy /tmp/aleph-policy.json

# 서버 IP·NIC를 확인하고 클라이언트 대역을 승인했을 때만 실제 설치
sudo python3 infra/edge/system_dns.py install \
  --client-cidr 192.168.7.0/24 \
  --upstream 9.9.9.9 --policy /tmp/aleph-policy.json --apply
```

IP와 NIC를 둘 다 생략하면 `ip -j -4 address show`를 조회해 **UP 상태인 비루프백 인터페이스의 유일한 RFC1918 사설 IPv4**를 찾습니다. Docker 브리지·VPN·여러 NIC 또는 한 NIC에 복수 사설 IP가 있으면 잘못 선택하는 대신 중단합니다. 이런 경우 `--listen-ip 192.168.7.69`를 명시하고 동일 주소가 여러 NIC에 있다면 `--interface`도 지정합니다. 자동 탐지 결과가 클라이언트에서 설정한 DNS 주소와 일치하는지 확인해야 합니다. `--client-cidr`가 없는 **미리보기**는 시스템 주소 프리픽스에서 `/24` 또는 더 좁은 대역을 **추천할 뿐 승인하지 않습니다**. 허용할 클라이언트 대역을 검토해야 하며, **`--apply`에는 `--client-cidr` 명시가 필수**입니다. 기존 설치라면 `install` 반복 대신 상태 진단·업그레이드 절차를 따르세요. `--upstream`과 `--policy` 역시 명시해야 합니다.

`--apply`는 기존 53번 충돌·LAN 인터페이스·nft 테이블 점유·설치 파일 존재·
정책 유효기간·dnsmasq/nft 명령을 확인하고, 새 전용 리소스를 설치합니다.
시스템 서비스가 시작된 뒤 **로컬 A/AAAA 및 대표 BLOCK 질의와 적용 정책 SHA**까지
확인해야 설치 성공을 보고합니다. 신규 설치 도중 오류가 나면 전용 서비스를 중단하고
이번 설치가 만든 자원을 되돌리도록 시도합니다. 소유권이나 내용이 달라지면
자동 정리를 중단하고 남은 자료를 보존합니다. 복구 자체가 실패하면
관련 오류와 남은 자원을 명시하므로 수동 점검이 필요합니다.

설치되는 구성:
- `/etc/aleph-dns/policy.json`: root 소유·서비스 그룹 읽기. 발행자 서명이 아니라 로컬 관리자 파일.
- `/etc/aleph-dns/firewall.json`, `options.json`: 전용 테이블의 설치별 식별자와 설정.
- `/opt/aleph-dns/firewall_guard.py`: 방화벽 생성·검사·제거 도구.
- `/opt/aleph-dns/src/dns_agent/`: root 소유, 일반 서비스 계정은 수정 불가.
- `/etc/aleph-dns/installed-code.json`: 설치 당시 root 관리 소스의 상대 경로·SHA-256 인벤토리. 서명·IOC 출처 인증은 아닙니다.
- `/var/lib/aleph-dns/`: 전용 0700 상태·복구 저널.
- `aleph-dns.service`(일반 `aleph-dns` 계정, 포트 53만 필요한 capability)와 `aleph-dns-firewall.service`.
- nftables `inet aleph_dns`: **지정 인터페이스·클라이언트 IPv4 CIDR 외의 DNS 접근 제한**.
  systemd `IPAddressDeny/Allow`도 사용하되 실제 커널 지원 및 다른 방화벽과의 공존을 검증해야 합니다.

systemd의 BPF 방화벽 준비 실패 로그가 있다면 서비스가 `active`여도
`IPAddressDeny/Allow`가 적용됐다고 판단할 수 없습니다. 서비스 cgroup의 실제
ingress·egress BPF 부착 상태를 확인하세요. nftables 입력 테이블의 검증은
systemd의 별도 송신 제한이 동작한다는 증거가 아닙니다.

이 설치의 추가 map-free cgroup BPF guard는 동일한 허용 IP 집합을 입력·출력에
적용하고, 프로그램 로드·부착·확인에 실패하면 DNS 시작을 거부합니다. 기존
systemd BPF가 있을 때는 교체하지 않고 함께 부착합니다. 이전 guard가 같은
cgroup에 남아 있거나 소유권을 확인할 수 없으면 자동 제거하지 않고 시작을
거부하므로 상태를 조사해야 합니다. 이 제한은 해당 cgroup의 직접 IP 패킷에
관한 것이며 AF_UNIX 프록시를 통한 간접 통신까지 차단하지 않습니다. systemd의
맵 오류 자체는 커널·systemd 구성에 따라 로그에 남을 수 있습니다.
guard는 unified cgroup v2와 cgroup skb BPF 다중 부착을 요구하며 현재 syscall
구현은 x86-64, AArch64, ARM EABI를 지원합니다. 설치·업그레이드 전에 두 BPF
프로그램의 로드 지원 여부를 점검하지만 실제 서비스 cgroup에서 부착이 성공할지는
시작 시 다시 확인합니다. 지원되지 않는 환경은 시작을 거부합니다.
상위 `system.slice` 또는 `-.slice`의 `IPAddressAllow`가 이 서비스의 허용 집합
밖의 IPv4 또는 IPv6를 포함하면 기존 허용 범위를 조용히 축소하지 않도록
설치·업그레이드 및 서비스 시작을 거부합니다. 상위 설정을 변경할 때는 서비스
관리 작업을 중지하고 재검증해야 하며, 실행 중 변경을 자동 감시하지 않습니다.

```sh
sudo journalctl -b --no-pager | grep -i 'bpf-firewall'
sudo systemctl show aleph-dns.service -p ControlGroup -p IPAddressAllow -p IPAddressDeny
```

## 실제 도메인 정책과 기존 설치 호환성

신규 설치의 정책 파서는 `.test`와 실제 ASCII 도메인을 구분하지 않고
**입력 유효성·범위·승인·유효기간**을 검사합니다. `--allow-public-domains` 같은
설치 모드는 더 이상 사용하지 않습니다. 단, 실제 도메인에 대한 정책 결정과
사용자 안내·오탐 대응 권한까지 자동 승인되는 것은 아닙니다.

과거 설치에서 도메인 모드가 저장된 경우 새 관리 명령의 `publish`는 이를
**구형 설치로 판정해 거부**합니다. 이미 실행 중인 서비스의 코드·systemd
실행 명령은 GitHub 업데이트만으로 바뀌지 않습니다. 관리자가 운영 중인
DNS 클라이언트를 다른 리졸버로 우선 전환하고, 아래의 `upgrade`로
구형 구성의 원본·상태·코드를 안전하게 백업한 다음 새 서비스와 설정을
설치해야 합니다. 업그레이드된 `options.json`에는 구형 모드가 남지 않습니다.

합성 `.test` 데이터는 격리된 기능 시험에서만 사용합니다. 실사용 정책을
생성할 때는 [실제 위협 인텔리전스와 수동 승인](../../apps/policy-server/README.md)을
따르고 **공유 호스팅·하위 도메인 차단 영향**을 검토하세요.
단순히 정책 파일에 `approved=true`를 넣는 것만으로 진짜 안전한 차단 목록이
되는 것은 아닙니다.

## 엔진 코드 업데이트와 운영 서비스 반영

### 무엇을 갱신해야 하나요?

서버의 Git 체크아웃과 실제 서비스 코드는 다릅니다. 설치기는 저장소의
`apps/dns-agent/src`를 `/opt/aleph-dns/src`에 복사하고 systemd는 이 설치본을
실행합니다. 따라서 **Git pull이나 기존 서비스 재시작만으로 새 엔진 코드가
설치되지 않습니다.** 기존 설치를 삭제하거나 `install --apply`를 반복하지 말고
검증된 저장소에서 아래의 `upgrade --apply`를 사용하세요. `publish`는 정책을
갱신하는 명령이며 엔진 코드를 갱신하지 않습니다.

### 업그레이드 전 준비

1. 관리자 PC와 다른 클라이언트들을 정상 동작하는 대체 DNS로 전환하고 SSH 등
   DNS와 독립적인 복구 접속 수단, 백업 공간과 점검 시간을 확보합니다.
   업그레이드 중 전용 DNS와 방화벽 서비스가 중단됩니다.
2. 설치·발행·제거 및 다른 `systemctl`·nftables 관리 작업을 중지합니다.
   구버전의 잠금은 모든 관리 명령을 직렬화하지 않습니다.
3. DNS 서버에서 설치된 엔진으로 정책을 확인합니다. `expired`가 `true`면
   유효한 정책이 필요하며, `expired: false`여도 개별 규칙 만료로
   `active_blocks`가 0일 수 있습니다. 만료가 임박하지 않았는지도 확인하세요.

   ```sh
   sudo env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/aleph-dns/src /usr/bin/python3 -m dns_agent validate /etc/aleph-dns/policy.json
   sudo systemctl is-active aleph-dns.service aleph-dns-firewall.service
   ```

   만료됐거나 업그레이드 중 만료될 수 있다면 실행 전에 새로 검토·승인한 유효
   정책을 확보하고, 현재 설치에 맞는 `publish` 명령으로 먼저 발행해 수락을
   확인합니다. 최신 업그레이드 명령은 만료된 정책을 서비스 중단 전에 거부합니다.
   다만 검사 후 중단 사이 만료되거나 다른 관리자가 직접 파일을 변경하면
   중단 뒤 검사에서 실패해 수동 복구가 필요할 수 있습니다.

   기존에 만료된 정책 파일을 그대로 보존하는 것이 목적이라면, 현재 DNS가 이미
   만료된 규칙을 적용하지 않는다는 점을 확인한 뒤 아래 업그레이드 명령에
   `--preserve-expired-policy`를 명시할 수 있습니다. 이 옵션은 정책을 갱신하거나
   만료된 차단을 되살리지 않습니다. 원본 정책과 상태는 백업에 유지되며, 정상
   운용을 위한 새 정책 발행은 별도 작업입니다.

   과거 설치가 `allow_public_domains` 옵션을 사용한다면 최신 관리 명령의
   `publish`가 구형 설치를 거부할 수 있습니다. 설치 당시의 **검증된 관리 코드
   버전**을 별도로 확보한 경우에만, 그 버전의 저장소에서 동일한 `publish --policy`
   명령으로 새 정책을 발행하고 수락을 확인하세요. 그 버전과 옵션이 확인되지
   않거나 발행에 실패하면 추측하여 덮어쓰지 말고 기존 상태와 백업을 보존한 채
   복구 방안을 조사하세요. 예를 들어 해당 구형 엔진이 공인 도메인 모드로 설치된
   경우에는 설치된 엔진으로 검증할 때 `validate` 뒤에 `--allow-public-domains`가
   필요할 수 있습니다. 이 옵션을 최신 엔진이나 `publish` 명령에 임의로 추가하지
   마세요.
4. 서버의 저장소에서 현재 변경사항을 확인하고 검증한 커밋을 가져옵니다.
   `--ff-only`가 실패하면 로컬 작업과 양쪽 이력을 조사하고 임의로 강제 초기화하지
   않습니다. 다음 명령은 해당 저장소 디렉터리에서 실행합니다.

   ```sh
   git status --short --branch
   git fetch origin
   git pull --ff-only origin main
   git rev-parse HEAD
   ```

### 업그레이드 실행

다음 명령은 **DNS 서버의 갱신된 저장소**에서 실행합니다.

```sh
# 변경 없이 안내만 표시 (실제 설치 상태를 검사하는 사전 검증은 아님)
python3 infra/edge/system_dns.py upgrade

# 표식이 있는 관리형 설치
sudo python3 infra/edge/system_dns.py upgrade --apply

# 표식이 없는 구버전: 이 테이블의 소유권을 관리자가 직접 확인한 후에만
sudo python3 infra/edge/system_dns.py upgrade --apply --adopt-legacy-table
```

표식이 없는 테이블은 규칙이 정확히 일치해도 소유권을 증명할 수 없습니다.
`--adopt-legacy-table`은 관리자가 소유권을 확인했다는 명시적 입력입니다.
원본 unit·규칙·코드, 적용된 drop-in, 권한과 현재 정책·상태가 지원되는 형태와
일치하지 않으면 진행하지 않습니다. 구버전이 남긴 `root:root 0775` 소스 루트는
알려진 코드와 제한된 권한 조건에서만 허용합니다. 계정 목록·ACL 검사만으로
이미 실행 중인 프로세스나 동적 그룹의 쓰기 권한까지 증명할 수 없으므로 root 그룹을
신뢰하고 해당 경로에 쓸 수 있는 다른 프로세스를 중지한 격리 환경에서 수행하세요.

정책·상태·코드·unit의 내용과 소유자·그룹·모드를 root 전용 아카이브에 보존하고,
기존 상태를 유지한 채 새 서비스가 정책을 수락했는지 확인합니다. 중단되면 자동으로
이전 정책을 덮어쓰지 않으며 진행 기록을 남깁니다.

성공 메시지에 기록된 백업 경로를 보관하고, 두 서비스가 활성 상태인지와
`journalctl -u aleph-dns -n 50 --no-pager`를 확인하세요. 아래의 정책 상태와
허용된 다른 LAN 단말의 UDP/TCP 정상 질의도 확인한 뒤 클라이언트를 다시 전환합니다.
업그레이드의 자체 검사만으로 외부 업스트림 질의 성공이나 모든 차단 규칙의 동작이
증명되지는 않습니다.

```sh
sudo python3 infra/edge/system_dns.py migration-status
```

이 명령은 백업과 현재 상태를 진단하지만 자동 복원하거나 기록을 지우지 않습니다.
중단 시 현재 파일·상태·저널·백업을 모두 보존하고 서비스 및 정책 발행 상태를
조사하세요. 재시작 후 더 새로운 정책이 수락됐을 수 있으므로 백업을 무조건 덮어쓰면
안 됩니다.

## 다른 LAN 클라이언트에서 검증

```sh
sudo systemctl status aleph-dns.service --no-pager
sudo systemctl status aleph-dns-firewall.service --no-pager
sudo nft list table inet aleph_dns
sudo journalctl -u aleph-dns -n 50 --no-pager

# 다른 허용 LAN 단말에서 UDP/TCP
dig @192.168.44.10 example.org A
dig +tcp @192.168.44.10 example.org A
dig @192.168.44.10 account-session-verify.test A
dig @192.168.44.10 sub.account-session-verify.test AAAA
```

`account-session-verify.test`는 **합성 캠페인의 승인된 BLOCK** 예시입니다.
공인 DNS에서 `.test` 자체가 NXDOMAIN일 수 있으므로 이 결과만으로 차단 성공을
판정하지 마세요. 통제된 양성 업스트림 fixture와 정책 적용 전후, 로그·해시를
함께 검증해야 합니다. 정상 이름의 통과 결과도 확인한 다음에만 DHCP/DNS를 전환하세요.

## 정책은 어디에 저장되나요?

- `/etc/aleph-dns/policy.json`: 관리자가 마지막으로 발행한 전체 정책 파일입니다.
  root 소유이고 서비스 그룹이 읽을 수 있습니다. 발행 직후 오류가 나면 이 파일이
  실행 중 상태와 다를 수 있습니다.
- `/var/lib/aleph-dns/state.json`: 에이전트가 수락한 정책과 해시, 적용 시각,
  차단 수 등을 담는 서비스 전용 상태입니다. `pending.json`이 있으면 트랜잭션
  복구 중일 수 있습니다. 이 파일들을 직접 수정하거나 구버전으로 복원하지 마세요.
- 업그레이드·제거 시 `/var/backups/` 아래 root 전용 아카이브에 원본 정책·상태가
  보존됩니다. 실습 모드는 `--state-dir`로 지정한 별도 경로를 사용합니다.

DNS 서버에서 현재 파일과 수락 상태를 확인하려면 다음을 실행합니다.

```sh
sudo env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/aleph-dns/src /usr/bin/python3 -m dns_agent validate /etc/aleph-dns/policy.json
sudo python3 -c 'import json; s=json.load(open("/var/lib/aleph-dns/state.json")); print({k:s.get(k) for k in ("policy_sha256", "applied_at", "blocked_count")})'
sudo journalctl -u aleph-dns -n 50 --no-pager
```

`validate`의 `policy_sha256`은 정규화한 JSON의 해시이며 `state.json`의
`policy_sha256`과 비교합니다. `sha256sum policy.json`은 원본 파일 바이트의
해시이므로 일반적으로 둘과 다릅니다. `expired`는 정책 전체의 만료 여부이고
각 차단 규칙의 만료는 `active_blocks`에 반영됩니다. 구형 공인 도메인 모드의
설치 엔진에는 위의 `validate` 뒤에 `--allow-public-domains`가 필요할 수 있습니다.
설치본을 관리자 권한으로 직접 실행할 때는 위와 같이 `PYTHONDONTWRITEBYTECODE=1`을
지정하세요. 그렇지 않으면 설치 경로에 `__pycache__`가 생성되어 코드 소유권·무결성
검사가 거부할 수 있습니다. 예기치 않은 설치 파일은 임의로 삭제하지 말고 점검합니다.

## 원격 서버와 정책 주고받기

원격 OpenPhish/Google Safe Browsing 후보 수집과 수동 검토, 서명된 HTTPS Pull 및 DNS 로컬 적용은
선택형으로 구현되어 있습니다. **승인 API/DB와 자동 BLOCK 승인은 미구현**입니다.
실제 자동 갱신을 켜려면 서버별 설치·운영 절차를 먼저 수행하세요:
[원격 정책 서버·사설 DNS 설치](../../docs/remote-policy-deployment.md).
아래는 별도의 수동 SSH 전송/검토 예시이며, 서명된 자동 배포를 대체하지 않습니다.
SSH 서버 호스트 키와 파일 출처를 독립적으로 확인하고, 정책에는 민감한 도메인과
검토 정보가 있을 수 있으므로 공개 저장소에 올리지 마세요.

### 관리 PC에서 DNS 서버의 현재 정책 사본 가져오기

일반 SSH 계정은 원본 파일을 직접 읽을 권한이 없을 수 있습니다. 먼저 DNS 서버에
SSH로 로그인해 관리자 비밀번호를 터미널에서 입력하고, 무작위 이름의 0600 임시
사본을 만듭니다. 이 과정은 운영 정책을 수정하지 않습니다.

```sh
# 관리 PC에서; 계정과 IP는 환경에 맞게 변경
ssh USER@192.168.7.69

# 아래는 DNS 서버의 SSH 셸에서 실행
export_file=$(mktemp "$HOME/aleph-policy.XXXXXXXX")
if sudo cat /etc/aleph-dns/policy.json > "$export_file"; then
  sha256sum "$export_file"
  printf '내보낸 경로: %s\n' "$export_file"
else
  rm -f -- "$export_file"
fi
```

출력된 전체 경로를 기록한 후 `exit`로 서버에서 나와 관리 PC에서 복사합니다.
아래 `USER`와 `/home/USER/aleph-policy.XXXXXXXX`는 **실제 계정과 출력된
경로로 바꾸는 자리표시자**입니다.

```sh
umask 077
scp USER@192.168.7.69:/home/USER/aleph-policy.XXXXXXXX ./aleph-policy-copy.json
sha256sum ./aleph-policy-copy.json
```

복사한 파일의 바이트 해시를 서버에서 출력한 값과 비교합니다. 마지막으로 DNS
서버에 다시 로그인해 출력된 정확한 임시 경로를 `rm -- 경로`로 삭제하세요.
같은 이름의 기존 로컬 파일을 덮어쓰지 않도록 복사 목적지를 먼저 확인합니다.

### DNS 서버가 원격의 검토된 정책을 가져와 발행하기

DNS 서버에 SSH로 접속한 뒤, 해당 서버에서 접근 가능한 정책 보관 호스트의 파일을
전용 임시 디렉터리로 가져옵니다. `SOURCE_USER`, `POLICY_HOST`와 경로는 실제
승인된 출처로 바꾸세요. 이 예시는 **DNS 서버의 저장소 디렉터리**에서 실행합니다.

```sh
umask 077
policy_dir=$(mktemp -d)
scp SOURCE_USER@POLICY_HOST:/path/to/reviewed-policy.json "$policy_dir/candidate.json"
sha256sum "$policy_dir/candidate.json"
sudo env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/aleph-dns/src /usr/bin/python3 -m dns_agent validate "$policy_dir/candidate.json"
```

독립적으로 확인한 원본 해시와 비교하고, 전체 규칙·승인 여부·유효기간·기존 정책과의
차이를 검토하세요. `validate` 성공은 출처 인증이나 사용자 영향 승인이 아닙니다.
정책은 **전체 교체**이므로 기존 규칙이 빠지면 그 차단이 철회됩니다. 적용이 승인된
경우에만 다음을 실행하고 응답 및 로그를 확인합니다. 구형 공인 도메인 모드라면
설치된 구형 파서의 검증 옵션과 그 설치에 맞는 구형 관리 명령을 사용해야 합니다.

```sh
sudo python3 infra/edge/system_dns.py publish --policy "$policy_dir/candidate.json"
sudo journalctl -u aleph-dns -n 50 --no-pager
```

실패 시 진단과 감사에 필요한 파일을 보존하세요. 성공 후 임시 사본이 더 이상
필요하지 않으면 `rm -- "$policy_dir/candidate.json"`과 `rmdir -- "$policy_dir"`로
삭제할 수 있습니다. DNS 서버에 정책 보관 호스트 접근 권한이 없다면 관리 PC에서
검토한 파일을 DNS 서버의 사용자 소유 임시 디렉터리로 `scp`한 다음 같은 검증·발행
절차를 따릅니다.

## 정책 발행 및 장애 복구

```sh
python3 scripts/build_campaign_policy.py > /tmp/aleph-next.json
sudo python3 infra/edge/system_dns.py publish --policy /tmp/aleph-next.json
sudo journalctl -u aleph-dns -n 50 --no-pager
```

실제 `publish`는 **실행 중 DNS 서비스·설치 소유권을 확인**, 이전 게시본과
실행 중 정책보다 오래됐거나 같은 시각에 다른 정책을 거부하고,
업데이트 후 **실행 중 DNS 에이전트의 SHA 수락**을 확인해야 성공을 반환합니다.
설치·발행·제거는 `/run/aleph-dns.lock`으로 서로 직렬화하며, 충돌 시 재시도해야 합니다.
이전 버전의 관리 명령은 다른 잠금을 사용하므로 업그레이드 전 이전 버전의 설치·발행·
제거 프로세스를 모두 종료하고, 업그레이드가 끝날 때까지 실행하지 마세요.
수락 확인에 실패하면 오류로 종료하며
관리자는 `journalctl`과 `/var/lib/aleph-dns/state.json`을 확인해야 합니다.
오류 뒤의 정책 파일은 자동으로 구 버전으로 되돌리지 않습니다
(안티 리플레이 검사가 구 정책 재게시를 거부할 수 있기 때문).

DNS 장애 또는 제거 전에는 **DHCP·관리 단말의 DNS를 작동하는 이전 리졸버로 되돌리고**
캐시·리스 갱신을 고려해 실제 질의를 확인하세요.

```sh
# 미리보기
sudo python3 infra/edge/system_dns.py uninstall

# DNS 클라이언트 전환 후 명시적 제거
sudo python3 infra/edge/system_dns.py uninstall --apply

# 표식이 없는 구버전의 소유권을 직접 확인한 경우에만
sudo python3 infra/edge/system_dns.py uninstall --apply --adopt-legacy-table
```

제거는 **설치 식별자·방화벽 규칙·전용 systemd unit·소스 경로/해시**를 확인한 뒤 중지합니다. 백업 아카이브를 만들 수 없으면 서비스를 중단하지 않습니다.
검사한 테이블의 핸들과 커널 규칙셋 세대번호를 사용해 조건부 삭제하므로 검사 후
규칙셋이 바뀌면 실패합니다. 커널이 이 조건을 지원하지 않거나 소유권을 확인할 수
없으면 자동 삭제를 거부하고 수동 점검이 필요합니다. 정책·개인 상태는
`/var/backups/aleph-dns-...` 아래 **0700 아카이브**로 옮기며,
제한된 서비스 계정은 남겨 둡니다. 원격 정책 서버, 외부 방화벽, DHCP는 건드리지 않습니다.
구버전의 표식 없는 테이블은 관리자의 명시적 확인 없이 자동 제거하지 않습니다.
설치 실패 복구도 예상하지 못한 하위 파일이나 서비스 상태를 삭제하지 않고 수동 복구로 전환합니다.

다른 관리자가 동시에 `systemctl` 또는 nftables를 직접 조작하면 이 도구의 잠금으로
직렬화되지 않습니다. 설치·제거 중에는 다른 관리 작업을 중지하고, 실행 중 방화벽을
수정하거나 초기화했다면 적용 상태를 재확인하세요.
커널 기능 확인은 잘못된 세대번호로 임시 테이블의 생성·삭제를 한 트랜잭션에 요청합니다.
일반적으로 커널이 거부하지만, 기능 미지원 또는 동시 변경 시 요청이 실행될 수 있으며
테이블은 남지 않아도 규칙셋 세대번호나 알림에 영향을 줄 수 있습니다.

## 검증 범위

설치기 단위 시험 외에 실제 nftables를 격리 네트워크 네임스페이스에서 실행해
생성·재사용·충돌·변조·조건부 제거를 시험할 수 있습니다. 필수 모드는 네임스페이스
사용이 불가능하면 건너뛰지 않고 실패합니다.

```sh
ALEPH_REQUIRE_NETNS_TESTS=1 PYTHONPATH=apps/dns-agent/src \
  python3 -m unittest discover -s tests/deployment -v
```

격리 시험의 통과는 실제 운영 서버의 방화벽 공존, 물리 LAN 다중 클라이언트·부하·
서비스 중단시간을 입증하지 않습니다. 커널 capability와 cgroup IP 필터도 배포할
서버에서 확인해야 합니다.
이 서비스는 요청 QNAME의 `SUBTREE` 차단만 수행하며
DoH/DoT·VPN·CNAME 응답 체인, IPv6 리졸버·TLS 경고 화면을 강제하지 않습니다.
