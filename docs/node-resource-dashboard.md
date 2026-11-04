# DNS 노드 자원·네트워크 관제 연결

운영 대시보드: `https://skt-aleph-capstone.vercel.app/dashboard`.
웹을 배포해도 로컬 Linux 수집기의 설치 코드는 자동 갱신되지 않습니다.
노드 등록, 보고 수신, 정책 적용, 자원 측정은 서로 다른 상태입니다.

## 1. 읽기 전용 수신 경로 점검

DNS 노드에서 실행합니다. 개인키·토큰·상태 파일을 보내지 않습니다.

```bash
curl --fail --max-time 10 --silent --show-error \
  https://skt-aleph-capstone.vercel.app/v1/nodes/report
```

정상 응답은 `service: aleph-signed-node-receiver`, `metrics_format: 4`,
`enrollment_required: true`, `storage: not_checked`와 서버 시각을 포함합니다.
HTTP 200은 TLS/라우팅 확인일 뿐, 장치 등록이나 DB·DNS 적용 성공이 아닙니다.
HTML 또는 로그인 리다이렉트라면 운영 도메인과 Deployment Protection을 점검하세요.
TLS 검증을 끄거나, 관리 API를 익명 공개하거나, 개인키를 업로드하지 마세요.

## 2. 기존 등록 노드가 format 1/2/3를 보내는 경우

관리 화면은 실제 검증한 보고의 format을 표시합니다. format 2에는 CPU·메모리·NIC 자원이 없습니다.
이 경우 **등록 해제, 개인키 재생성, counter.json 삭제가 필요하지 않습니다.**
기존 신뢰키와 보고 순번을 보존하고 동일한 검토 커밋으로 Linux 런타임을 갱신합니다.

1. 저장소에서 검토한 `main` 커밋을 선택합니다. 로컬 수정은 먼저 별도로 보존하세요.
2. 아래 타이머/서비스를 기록하고 중지합니다. DNS 리졸버 자체는 중지하지 않습니다.
3. 코드 전용 업그레이드를 미리보기한 뒤 적용합니다. 실패 시 기존 백업을 유지하고 원인을 확인하세요.

```bash
sudo systemctl stop aleph-policy-fetch.timer aleph-policy-apply.timer \
  aleph-ops-collect.timer aleph-ops-send.timer
sudo systemctl stop aleph-policy-fetch.service aleph-policy-apply.service \
  aleph-ops-collect.service aleph-ops-send.service
sudo bash scripts/deploy/upgrade-policy-runtime.sh --role dns
sudo bash scripts/deploy/upgrade-policy-runtime.sh --role dns --apply
```

4. 실제 장치 ID/IP/기존 표시 이름을 사용해 연결 도우미를 미리보기하고 적용합니다.

```bash
sudo python3 scripts/deploy/connect-node-dashboard.py \
  --device-id "$DEVICE" --listen-ip "$DNS_IP" --label "$EXISTING_LABEL"
# 미리보기를 확인한 뒤 같은 명령 끝에 --apply 추가
```

`--interface`를 생략하면 해당 IP가 유일하게 할당된 로컬 인터페이스만 선택합니다.
여러 NIC에 같은 IP가 있으면 추측하지 않고 중단하므로 `--interface`를 명시하세요.
기존 `--probe-upstream`은 새 값을 명시하지 않으면 보존합니다.
도우미는 변경 전에 Vercel HTTPS 수신 경로와 60초 이내 시각 일치를 확인합니다.
개인키, 재생 방지 카운터, DNS 정책, DHCP, 방화벽은 초기화하지 않습니다.
기존 장치는 같은 공개키를 재등록할 필요가 없습니다. 새 장치만 출력된 공개
`node-enrollment.json`의 지문을 확인하고 관제 화면에서 승인합니다.

```bash
sudo systemctl start aleph-ops-collect.service
sudo systemctl start aleph-ops-send.service
sudo systemctl start aleph-policy-fetch.timer aleph-policy-apply.timer
sudo journalctl -u aleph-ops-collect -u aleph-ops-send -n 60 --no-pager
```

원래 활성화된 정책 타이머만 다시 켜세요. 위 예시는 두 정책 타이머를 원래 사용하던 장치 기준입니다.
타이머가 누락된 최초 설치는 [기존 설치 안내](production-install-and-validation.md)를 따릅니다.

## 3. 그래프와 측정 의미

- CPU는 동일 부팅·CPU 개수의 tick 증가분입니다. 첫 보고·재부팅·카운터 역전·150초 공백은 변화율을 표시하지 않습니다.
- 메모리는 `MemAvailable`, 디스크는 수집 경로(`/var/lib`) 파일시스템의 사용 가능한 블록 기준입니다.
- RX/TX는 선택한 NIC 전체의 바이트/초입니다. DNS 트래픽만이나 회선 최대 속도를 측정하는 값이 아닙니다.
- NIC 오류·드롭은 커널 카운터 증가율입니다. 인터페이스 교체 중의 혼합 표본은 버립니다.
- 일반 DNS 품질은 `example.org`의 UDP/TCP A 양성 응답 검사입니다. `--quality-probes`로 선택 수집하고 연결 도우미는 이를 활성화합니다.
- DNS 검사 실패율은 실패 횟수/시도 횟수입니다. 회선 패킷 손실률이 아닙니다.
- p50/p95는 성공한 RTT의 nearest-rank 분위수입니다. p95는 최소 2개 표본에서 표시하며 20개 미만에서는 특히 불안정합니다.
- RTT 변동은 동일 부팅의 연속 원본 관측 RTT 차이 절댓값 평균이며 패킷 단위 jitter가 아닙니다.

최근 48건과 시간별 마지막 관측 24건까지 보존합니다. 시간별 점은 평균이 아닙니다.
구간 요약은 원본 표본만 사용하고 압축된 시간별 점은 제외합니다. 빈 값은 0으로 보간하지 않습니다.
15분/1시간/24시간 선택, 로컬/상위 DNS 선택, CSV, 수치 표, 일시정지를 지원합니다.

자원 관측은 정책 만료와 독립적입니다. 만료된 차단 정책은 신규 검증·독립 서명·게시가
필요하며, 자원 그래프를 채우기 위해 정책 수명을 임의 연장하지 않습니다.
