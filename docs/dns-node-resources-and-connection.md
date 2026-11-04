# Vercel 관제센터: 실제 DNS 노드 연결 및 자원·네트워크 측정

운영 주소는 기존 `https://skt-aleph-capstone.vercel.app/dashboard`를 유지합니다. 이 변경은 DNS 노드를 스캔하거나 원격 root 관리 권한을 만들지 않습니다. 실제 노드가 공개키를 등록한 후 HTTPS로 서명된 관측을 전송하는 구조입니다. 클라우드에 임의의 장치·IP·측정값을 생성하지 않습니다.

## 클라우드에 구현된 것

- `배포 현황 → 노드 연결 파일 등록`: 노드의 **공개** `node-enrollment.json`을 확인하고 공개키 신뢰+장치 등록을 한 DB 트랜잭션으로 수행합니다. 동일 파일을 재등록하면 기존 항목을 보존합니다. 장치 ID/공개키가 다른 등록과 충돌하면 대체하지 않고 거부합니다.
- 등록 파일의 자체 서명은 개인키 보유만 증명합니다. 운영자는 노드 터미널에 표시된 지문을 별도 채널로 대조하고 `ENROLL_NODE`를 입력해야 합니다. 등록 API는 기존 운영자 인증·same-origin·CAS 검사를 그대로 적용합니다.
- `DNS 통계`에 CPU, 메모리/디스크, RX/TX KiB/s, 로컬·상위 UDP/TCP 일반 DNS 응답시간 그래프가 추가됩니다. 텍스트 수치표와 CSV도 제공됩니다.
- 기존 v1/v2/v3 보고는 계속 읽습니다. 새 노드는 v4를 보내며 예전 보고에 없던 수치를 0으로 만들지 않습니다. 옛 compact history v1은 새 v2 필드가 null인 관측으로 읽고 다음 쓰기에서 정규화합니다.
- 공개 상태 보고 경로는 Origin 또는 Authorization을 받지 않습니다. 장치별 Ed25519 서명과 등록된 장치 ID·IP·공개키, 단조 증가 카운터, 보고 시각을 검증합니다. 브라우저 인증 토큰을 장치에 저장하지 마세요.

## 실제 DNS 서버에서 실행할 작업

작업 대상은 Vercel이 아니라 **DNS가 동작하는 Linux 서버**입니다. 실제 IP와 인터페이스는 `ip -br -4 address`로 확인하고 아래 예시를 바꾸세요. `edge-69`가 실제 장치 ID인지도 확인해야 합니다.

### 1. 현재 Git 코드와 설치 런타임 맞추기

저장소의 검토된 `main`을 가져오고 정확한 SHA를 확인합니다. `/opt/aleph-policy-code`가 오래된 경우에는 [코드 전용 업그레이드 절차](production-install-and-validation.md)를 먼저 수행합니다. 설치기는 Git 체크아웃과 설치 런타임이 다르면 중단하며, `git pull`만으로 운영 코드가 변경되지는 않습니다.

```bash
# 저장소 루트. 보존할 로컬 변경이 있다면 덮어쓰지 마세요.
git fetch origin main
git checkout --detach origin/main
git rev-parse HEAD
ip -br -4 address

# 기존 설치를 갱신할 경우 먼저 프리뷰
sudo bash scripts/deploy/upgrade-policy-runtime.sh --role dns
# 프리뷰가 요구하는 관련 타이머/서비스를 명시적으로 정지한 후:
sudo bash scripts/deploy/upgrade-policy-runtime.sh --role dns --apply
```

업그레이드 후에는 원래 활성화했던 fetch/apply 타이머를 다시 시작합니다. 서비스가 없는 신규 서버는 먼저 [DNS 서버 최초 설치](production-install-and-validation.md)를 완료해야 합니다. 이 연결 도구는 dnsmasq나 DHCP 설정을 새로 만들지 않습니다.

### 2. 노드 연결 미리보기 및 적용

```bash
sudo python3 scripts/deploy/connect-node-dashboard.py \
  --device-id edge-69 \
  --listen-ip 192.168.7.69 \
  --interface eth0 \
  --label '실제 DNS 서버'
```

프리뷰가 정확하면 같은 명령 끝에 `--apply`를 추가합니다. 상위 DNS 비교도 필요하면 **로컬 DNS 주소와 다른** 검토된 resolver를 `--probe-upstream <IP>`로 명시합니다. 고정 `example.org` A 질의의 능동 UDP/TCP 검사는 이 연결 도구의 적용에 포함됩니다. 외부 질의를 원하지 않는 환경에서는 기존 `install-dns-telemetry.sh`를 직접 사용하고 `--quality-probes`를 생략하세요.

도구는 다음을 수행합니다.

1. 지정한 IPv4가 지정한 NIC에 실제 할당되어 있는지 확인합니다.
2. 기존 상태 보고 개인키와 카운터를 보존합니다. 기존 장치 ID/IP가 다르면 조용히 변경하지 않습니다. 새 설치에만 노드 안에서 장치 키를 생성합니다.
3. 상태 보고 URL을 `https://skt-aleph-capstone.vercel.app/v1/nodes/report`로 구성합니다. 기존 설치에는 검토 가능한 systemd drop-in을 씁니다.
4. 공개 등록 파일 `/root/aleph-ops-secrets/node-enrollment.json`을 생성하고 키 지문을 출력합니다. **이 JSON만** 관제 브라우저로 옮깁니다. `status.pem`, `device-status.pem` 등 개인키를 보내지 마세요.

도구는 DNS 정책·방화벽·DHCP·현재 upstream resolver·보고 카운터를 재설정하지 않습니다. 로컬 서비스 관리 권한이 필요하며 원격에서 대신 실행되는 것은 아닙니다.

### 3. 관제 승인 및 상태 송신

관제센터의 `배포 현황 → 노드 연결 파일 등록`을 열어 JSON을 선택하고 실제 노드 지문과 대조한 뒤 승인합니다. 등록 직후 `NO_REPORT`가 정상이며, 유효 보고가 들어오기 전에는 보호 중으로 표시하지 않습니다.

```bash
sudo systemctl start aleph-ops-collect.service
sudo systemctl start aleph-ops-send.service
sudo systemctl status aleph-ops-collect.timer aleph-ops-send.timer --no-pager
sudo journalctl -u aleph-ops-collect -u aleph-ops-send -n 60 --no-pager
```

보고가 수락되면 `DNS 통계`에서 장치를 선택합니다. CPU·트래픽 변화율은 같은 부팅·NIC에서 두 개의 연속 관측이 들어와야 계산됩니다. 측정치가 있어도 게시·적용 정책이 없으면 정책 상태는 `NO_POLICY`로 남습니다. DNS 정책 다운로드 URL은 이 도구가 변경하지 않습니다.

## 지표 해석과 한계

| 지표 | 측정·계산 방법 | 의미의 한계 |
|---|---|---|
| CPU % | `/proc/stat`의 guest 중복을 제외한 합계 tick 차분, idle+iowait 제외 | load average와 다름. iowait 감소·재부팅·긴 공백은 결측 처리 |
| 메모리 % | MemTotal 및 MemAvailable | 프로세스별 메모리나 Vercel 리소스가 아님 |
| 디스크 % | 로컬 수집기가 보는 파일시스템 사용률 | 디스크 I/O 지연·전체 마운트 목록이 아님 |
| RX/TX KiB/s | 명시한 NIC의 누적 byte 차분 / uptime 차분 | DNS 전용 트래픽, 속도 테스트, 회선 최대 대역폭이 아님 |
| NIC 오류/드롭 | RX/TX 커널 counter 증가율 | 종단 간 패킷 손실률이 아님 |
| 일반 DNS 품질 | 고정 `example.org` A 양성 응답을 로컬/선택 upstream에서 UDP·TCP 측정 | 왕복 처리시간이며 캐시, 서버, 경로 영향 포함. 제어된 피싱 차단 검증과 별개 |
| DNS 검사 실패 % | 각 보고의 실패 수 / 2개 또는 4개 검사 표본 | 표본 수가 작음. 실제 사용자 실패율이나 회선 손실률이 아님 |

네트워크 필터가 검사 도메인을 차단하거나 A 레코드 양성 응답이 없으면 실패로 기록합니다. 실패한 지연은 `null`이며 0ms로 바꾸지 않습니다. 첫 관측, 재부팅, NIC/index 교체, 누적 counter 감소, 150초 넘는 공백에서는 변화율을 만들지 않습니다. 개인 호스트명·프로세스 목록·클라이언트 주소·브라우징 이력·패킷 내용은 수집하지 않습니다.

최근 최대 48개 보고와 최근 24시간의 시간당 마지막 관측 최대 24개를 보존합니다. 성긴 구간은 시간당 평균이 아니며 그래프를 연결해서 채우지 않습니다. CPU/트래픽 변화율은 수신 시점의 원래 인접 관측으로 계산한 값을 보존합니다. 클라우드 공간 제한·동시 쓰기 충돌 검사는 계속 적용됩니다.

## 검증 구분

테스트는 임시 MemoryStore/루프백 서버/합성 키에 한정합니다. 합성 보고·장치를 운영 DB에 삽입하지 않습니다. 브라우저 수치·누락·모바일·세션 검증과 실제 DNS 서버의 systemd/권한/인터페이스/UDP/TCP 인수는 다른 검증입니다. 실제 노드 파일·키·명령 실행 결과 없이는 실장비 연결 완료를 주장할 수 없습니다.
