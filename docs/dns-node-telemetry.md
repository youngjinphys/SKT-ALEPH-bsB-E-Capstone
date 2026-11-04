# DNS 노드 → 정책 서버: 서명된 운영 상태 보고

이 문서는 기존 **DNS가 정책 서버 HTTPS 피드를 주기적으로 Pull**하는 구조 위에 추가되는 관제 보고 경로를 설명합니다. 두 채널은 독립적입니다. 상태 보고서가 들어와도 정책 승인·서명·root 적용·방화벽은 변경되지 않습니다.

## 데이터 흐름 및 보안 경계

1. DNS의 root 전용 `aleph-ops-collect`는 root 소유 `applied.json`에서 시퀀스와 해시를 읽고, 수신한 정책 엔벨로프의 **현재 신뢰키 서명·장치 ID·시퀀스·SHA-256·유효기간**과 일치하는지 확인합니다.
2. 일치할 때만 기존 관리형 DNS의 root-only `system_dns.py attest --policy-sha256 ...`를 실행해 실제 live resolver 정책·관리 방화벽 상태를 재검증합니다.
3. 적용된 차단 규칙 중 1개를 서명 검증된 로컬 canary로 사용합니다. 먼저 **별도로 지정한 상위 DNS 서버**가 그 도메인의 A 질의에 대해 UDP와 TCP 모두 실제 양성 레코드(NOERROR 및 A 응답)를 제공하는지 확인합니다. 이후 등록된 사설 DNS IP:53에서 UDP/TCP의 A·AAAA 질의가 모두 NXDOMAIN인지 비교합니다. 상위 DNS가 자체 차단하거나 이름이 원래 존재하지 않으면 로컬 NXDOMAIN만으로 차단 성공을 주장하지 않습니다. DNS 응답은 해당 노드에서 검사하며 LAN 전체 이용을 증명하지 않습니다.
4. root가 별도의 **장치 텔레메트리 Ed25519 개인키**로 `device_id`, `report_sequence`, `reported_at`, 리스닝 IP, 정책 시퀀스·해시, 로컬 attestation, probe를 서명합니다. **정책 서명 개인키와 장치 키는 서로 다른 키**입니다.
5. root는 0640 (root:aleph-ops-sender) 보고서를 outbox에 작성합니다. 비특권 `aleph-ops-sender`만 HTTPS `POST /v1/nodes/report`를 수행합니다. 장치 개인키 파일은 root 전용 0600입니다. 공개 신뢰키와 보고용 CA가 들어 있는 `/etc/aleph-ops` 디렉터리는 송신 계정이 통과할 수 있어야 하며, 개인키 파일 자체는 읽지 못합니다.
6. 정책 서버의 기존 루프백 `policy_server.console`이 별도로 등록된 **장치 키 공개키 지문, 장치 ID, 사설 IP, 시각, 단조 증가 보고 카운터, Ed25519 서명**을 모두 검증한 뒤 0600 로컬 상태로 수신합니다.
7. 관제 대시보드는 신뢰 가능한 수신 시각, DNS 보고 시퀀스, 정책 서버의 **검증된 로컬 게시 정책** 시퀀스와 SHA-256이 일치하는지 비교합니다. 150초 넘게 새 보고가 없으면 STALE입니다. 동일한 보고를 재전송하면 시각을 갱신하지 않습니다.

**확인 수준:** `LOCAL_POLICY_ATTESTED`는 로컬 DNS 런타임과 게시 정책 일치, `LOCAL_DNS_VERIFIED`는 이에 더해 독립 upstream 양성 기준과 로컬 UDP/TCP NXDOMAIN의 차이를 확인했음을 뜻합니다. `LOCAL_DNS_UNCORROBORATED`는 상위 양성 기준이 설정되지 않았거나 구형 format-1 보고이며, `LOCAL_DNS_REFERENCE_UNVERIFIED`는 상위 DNS가 양성 응답을 제공하지 못했음을 뜻합니다. 어느 쪽도 LAN 여러 단말의 실제 DNS 사용, DNS 캐시 우회, DoH/VPN/IPv6/외부 TLS 전송 성공을 보장하지 않습니다.

## 1. DNS 노드에서 장치 전용 키 생성

DNS 운영 서버의 root 관리 터미널:

```bash
sudo install -d -o root -g root -m 0700 /root/aleph-ops-secrets
sudo openssl genpkey -algorithm Ed25519 -out /root/aleph-ops-secrets/device-status.pem
sudo chmod 0600 /root/aleph-ops-secrets/device-status.pem
sudo openssl pkey -in /root/aleph-ops-secrets/device-status.pem -pubout -out /root/aleph-ops-secrets/device-status.pub
sudo chmod 0644 /root/aleph-ops-secrets/device-status.pub
```

장치 **공개키만** 별도 안전한 관리 채널로 정책 서버에 복사하고 fingerprint를 검증합니다. 정책 서명 개인키는 DNS 노드에 절대 배치하지 않습니다.

## 2. 원격 정책 서버에 관제 서비스 설치

현재 검토된 커밋의 정책 서버 코드가 `/opt/aleph-policy-code`에 설치된 것을 먼저 확인합니다. **git pull만으로 설치된 코드는 갱신되지 않습니다.** 기존 설치가 있다면 [원격 정책 배포 가이드](remote-policy-deployment.md)에 따라 승인된 업그레이드를 수행합니다.

설치기 프리뷰와 적용:

```bash
sudo bash scripts/deploy/install-operations-console.sh --origin https://ops.example.org --device-id edge-69 --admin-cidr 10.10.20.0/24
sudo bash scripts/deploy/install-operations-console.sh --origin https://ops.example.org --device-id edge-69 --admin-cidr 10.10.20.0/24 --apply
```

설치기는 전용 `aleph-ops-console` 계정/0700 workspace/0600 토큰/루프백 systemd 서비스 및 **NGINX include-only snippet**을 생성합니다. NGINX `http` 컨텍스트에 요청 제한 존을 정의하는 `/etc/nginx/conf.d/aleph-ops-limits.conf`도 생성합니다. 사용자 NGINX가 `conf.d/*.conf`를 포함하지 않는 경우, 해당 HTTP-context 설정을 직접 검토·포함한 뒤 TLS vhost 내 snippet을 로드해야 합니다. 서명 보고 엔드포인트에는 IP당 요청률·동시 연결 제한, Python 서버에는 동시 처리 32개 상한을 적용합니다. 실제 TLS 인증서·vhost·방화벽은 설치기가 건드리지 않습니다. 반드시 HTTPS 443 vhost 안에 `/etc/nginx/snippets/aleph-ops-console.conf`을 검토하여 포함하고 `nginx -t` 통과 후 재시작해야 합니다.

보안상 콘솔의 `/`와 일반 API는 기본값으로 **127.0.0.1/32만** 허용합니다. 별도 VPN 관리망에서 접속한다면 `--admin-cidr 10.10.20.0/24`처럼 제한된 관리망(IPv4 /24 또는 더 좁은 범위)을 명시적으로 지정하세요. 사설망 전체(예: 10.0.0.0/8)는 허용하지 않습니다. 외부 관리자는 검증된 HTTPS/VPN 경로를 사용해야 합니다. `--origin https://ops.example.org`로 실행하면 백엔드는 해당 Host·Origin만 허용하므로, 단순 `http://127.0.0.1:8765` SSH 포워딩만으로는 웹 GUI에 접속할 수 없습니다. 실제 HTTPS 도메인과 일치하는 Host·Origin의 접속 경로를 구성하거나, 별도 루프백 전용 CLI 실행을 사용하세요. `/v1/nodes/report`만 서명된 장치 보고용으로 HTTPS POST를 허용합니다. NGINX에서 별도 rate limit, 패킷 크기 제한, 로그인 공격 모니터링을 적용하세요. 강한 SSO 게이트가 없다면 관제 관리 API를 공중 인터넷에 공개하지 마세요.

토큰은 서버에서 `sudo cat /var/lib/aleph-ops-console/token`으로 확인합니다. UI 또는 bearer 토큰을 공개 URL에 포함시키지 마세요.

## 3. 장치 공개키 신뢰 및 GUI 등록

정책 서버에서 장치 공개키의 fingerprint를 먼저 별도로 검증하고 설치합니다.

```bash
PUB=/private/edge-69-status.pub
KEY_ID="$(PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src python3 -B -m aleph_policy_sync key-id --public-key "$PUB")"
sudo install -o root -g root -m 0644 "$PUB" "/etc/aleph-ops-nodes/trust/$KEY_ID.pem"
```

운영자 관제 페이지의 **DNS 노드 등록** 양식에서 `edge-69`, 사설 리스닝 IP `192.168.7.69`, 표시 이름, `KEY_ID`를 입력합니다. GUI가 새 공개키를 신뢰하거나 업로드하지는 않습니다. 해당 장치는 사전에 허가된 공개키가 설치된 경우에만 등록됩니다.

## 4. DNS 서버의 보고 서비스 설치

동일한 검토 커밋의 현재 코드가 DNS 노드 `/opt/aleph-policy-code`에 설치되어 있어야 합니다. 정책 다운로드·적용 타이머와 별개로 다음 설치기를 실행합니다.

```bash
sudo bash scripts/deploy/install-dns-telemetry.sh \
  --device-id edge-69 --listen-ip 192.168.7.69 \
  --probe-upstream 9.9.9.9 \
  --report-url https://ops.example.org/v1/nodes/report \
  --private-key /root/aleph-ops-secrets/device-status.pem \
  --public-key /root/aleph-ops-secrets/device-status.pub
# 프리뷰를 검토하고 똑같은 명령 끝에 --apply 추가
```

여기서 `--probe-upstream`은 실제 운영용으로 검토된 **별도** DNS resolver 주소로 바꾸세요. 로컬 DNS 리스닝 주소와 동일하게 설정할 수 없습니다. 상위 DNS가 자체 악성 도메인 필터를 사용하거나 양성 A 레코드가 없으면 결과는 `REFERENCE_UNVERIFIED`이며, 차단 성공으로 표시하지 않습니다. `--probe-upstream`을 생략하면 형식 2 보고에도 baseline이 없다는 사실이 기록되며 `UNCORROBORATED` 상태로 표시됩니다. 개별 기업/내부 CA를 이용한다면 `--ca-file /path/to/ca.pem`을 명시할 수 있습니다. `--apply`는 root local attestation timer와 비특권 HTTPS sender timer를 설치하며 60초 수준으로 주기적으로 실행합니다.

```bash
sudo systemctl status aleph-ops-collect.timer aleph-ops-send.timer
sudo systemctl start aleph-ops-collect.service
sudo systemctl start aleph-ops-send.service
sudo journalctl -u aleph-ops-collect -u aleph-ops-send -n 50 --no-pager
```

설치기는 기존 DNS resolver·DHCP·기본 DNS·방화벽·서명 정책 적용기를 수정하지 않습니다. 원격 서버가 내부 DNS IP로 직접 접근하는 구조도 필요하지 않습니다. DNS 주소를 등록하는 이유는 노드 인스턴스의 고정 식별과 로컬 UDP/TCP probe 대상 설정을 일치시키기 위해서입니다.

## 상태 해석과 장애 복구

| 상태 | 의미와 조치 |
| --- | --- |
| NO_REPORT | 등록 후 유효한 장치 서명 보고가 도착하지 않음; 수집/전송 서비스와 TLS 확인 |
| STALE | 마지막 유효 보고로부터 150초 이상 경과; 정상으로 판단하지 않음 |
| CLOCK_SKEW | 수신 기록 또는 보고 시각이 현재 원격 서버 시각보다 60초 이상 미래; NTP 확인 |
| INVALID_REPORT | 저장된 보고 또는 공개키 신뢰가 손상·회수됨 |
| NO_POLICY | root가 유효한 서명 적용 기록을 확인하지 못함 |
| DNS_ATTESTATION_FAILED | 적용 기록·현재 수신 서명 정책·DNS 관리자가 일치하는지 재검토 |
| POLICY_EXPIRED | 노드가 보고한 정책 시퀀스·SHA-256이 서명 검증된 게시 파일과 일치하지만, 그 파일은 `valid_until`을 지났음. 현재 차단 적용으로 표시하지 않음. 구형 수집기는 만료 inbox를 `FAILED`로 보내며, 게시 파일과 신원이 같으면 콘솔이 이 상태로 해석함 |
| LOCAL_DNS_PROBE_FAILED | 로컬 DNS에서 차단 canary UDP/TCP 응답 불일치 |
| LOCAL_DNS_UNCORROBORATED | 로컬 NXDOMAIN은 관측했지만 상위 DNS 양성 비교 기준이 없거나 구형 보고 |
| LOCAL_DNS_REFERENCE_UNVERIFIED | 독립 상위 DNS에서 같은 도메인의 A 레코드 양성 확인 실패 |
| POLICY_MISMATCH | DNS 측 적용 시퀀스/해시와 원격 게시 정책의 버전이 다름 |
| PUBLISHER_UNVERIFIED | 원격 서버의 현재 서명 게시 파일을 검증하지 못함 |
| LOCAL_POLICY_ATTESTED | 게시 정책과 DNS의 로컬 attestation이 일치, DNS query probe 미실시 |
| LOCAL_DNS_VERIFIED | 위 결과에 더해 독립 상위 DNS 양성 기준과 노드의 UDP/TCP NXDOMAIN 차이를 확인 |

**관리 한계:** 등록된 주소로 원격 서버가 DNS/SSH/HTTP를 임의 검사하거나 관리 명령을 실행하지 않습니다. 읽기 가능한 상태 서명만으로 LAN 전체 정상 이용을 입증할 수 없습니다. 별도의 LAN 관측 프로브·정상 상위 DNS 양성 응답 검증·DNS 캐시/DoH·VPN·IPv6 시험 및 실망 인수는 별도 수행해야 합니다.

## 오프라인 검증

```bash
export PYTHONPATH="$PWD/apps/policy-server/src:$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src"
python3 -B -m unittest discover -s tests/policy_server -p test_nodes.py -v
```


## 관제 부분 장애 및 키 회전

장치 보고 파일과 장치 등록정보는 운영자 소유 0700 디렉터리에 별도로 보관합니다. 서로 다른 콘솔 프로세스가 동시에 장치 등록/해제 또는 서명 보고 수락을 실행하더라도 파일 잠금으로 순서를 정합니다. 장치 공개키 교체 후 이전 보고를 임의로 현재 키의 인증 실패라고 표시하지 않고 **REKEY_PENDING**으로 표현합니다. 등록정보나 위협 검토 파일이 읽기 실패하더라도 관제 개요의 다른 독립 항목은 별도로 읽으며, 손상된 통계는 **0이 아닌 null/미확인**으로 표시합니다.

최초 설치와 이미 운영 중인 코드의 업그레이드는 구분해야 합니다. [운영 설치·검증·코드 업그레이드](production-install-and-validation.md)를 참고하세요.

**장치 키 재등록:** 노드를 등록 해제하면 해당 장치 상태 보고 공개키 지문은 신뢰 기록(format 2)의 retired-key 목록에 원자적으로 보관됩니다. 같은 개인키/공개키로 재등록하는 것은 거부됩니다. 노드 재등록에는 *새로운* 장치 전용 Ed25519 키 쌍 생성, 새 공개키의 별도 검증 및 신뢰 등록이 필요합니다. 등록된 새 키로 유효한 보고가 들어오기 전에는 `REKEY_PENDING`으로 처리하고 이전 보고를 운영 정상으로 인정하지 않습니다.
