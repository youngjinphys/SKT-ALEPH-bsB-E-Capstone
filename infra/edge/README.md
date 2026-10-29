# Linux DNS 서버 배포 · UDP/TCP 53

이 디렉터리는 **별도 Linux DNS 서버에 실제 LAN 질의를 받는 서비스**를 설치합니다.
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

## 실습 정책과 실제 도메인 정책 구분

기본 설치는 검증된 **`.test` 실습 도메인만** 허용합니다. 이 설정은 실제 악성 도메인의
보호 정책이 아니라 안전한 DNS 설치·차단·철회 검증용입니다. 공용 도메인 정책을
적용할 필요가 있다면 사람의 IOC 출처·과차단 영향 검토 후, 초기 설치 시
`--allow-public-domains`를 **명시적으로** 지정해야 합니다. 단순히 이 옵션을 추가하거나
JSON의 `approved=true`를 설정해도 발행자의 신원이 인증되는 것은 아닙니다.
실제 원격 IOC 수집·검토·승인·서명 API는 아직 없습니다.

정책 게시 과정은 **설치된 DNS 에이전트의 파서**를 사용합니다. Git 저장소의 DNS 코드만
업데이트해도 운영 프로세스는 자동 업그레이드되지 않습니다.

## 기존 설치 업그레이드

기존 DNS 클라이언트를 다른 정상 리졸버로 전환하고 백업 공간과 복구 접속 수단을
확보한 뒤 검증된 새 저장소에서 실행합니다. 업그레이드 중 DNS 서비스가 중단됩니다.
다른 버전의 설치·발행·제거 명령과 별도의 `systemctl`·nftables 관리 작업을 모두
중지하세요. 구버전의 잠금은 모든 관리 명령을 직렬화하지 않습니다.

```sh
# 변경 없이 안내만 표시
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
