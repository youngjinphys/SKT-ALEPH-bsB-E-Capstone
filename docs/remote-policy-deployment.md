# 원격 정책 서버 → 사설 DNS 설치·운영

원격 수집 계정, 사람 검토자, 비특권 서명자, root 발행자와 DNS 수신/적용 계정을 분리합니다. 수집기는 의심 웹사이트를 방문하지 않고 공개 후보 URL을 Google에 조회합니다. 서명 개인키는 수집 계정·DNS·웹 루트에 배치하지 않습니다.

## 1. 키와 원격 서버

서명 담당자의 일반 사용자 계정에서:

```bash
umask 077
mkdir -p "$HOME/aleph-signing/releases"
chmod 700 "$HOME/aleph-signing" "$HOME/aleph-signing/releases"
openssl genpkey -algorithm Ed25519 -out "$HOME/aleph-signing/signing.pem"
openssl pkey -in "$HOME/aleph-signing/signing.pem" -pubout -out "$HOME/aleph-signing/public.pem"
```

공개키만 신뢰된 관리 채널로 두 서버에 전달하고 fingerprint를 교차 확인합니다. 다음의 `policy.example.org`, 파일 경로, LAN 주소는 실제 값으로 바꿉니다. 원격 서버는 정상 인증서를 갖춘 NGINX HTTPS vhost가 먼저 필요합니다.

```bash
sudo apt-get install -y python3-cryptography nginx
sudo install -o root -g root -m 0600 /private/google-api-key /root/aleph-google.key
sudo install -o root -g root -m 0644 /private/public.pem /root/aleph-publisher.pub
sudo bash scripts/deploy/install-policy-server.sh \
  --server-name policy.example.org --device-id edge-69 \
  --api-key-file /root/aleph-google.key --public-key /root/aleph-publisher.pub \
  --accept-openphish-terms --ack-url-disclosure --ack-noncommercial-use
# 미리보기 확인 후 같은 명령에 --apply 추가
```

설치기는 계정·경로·공개키를 검사하고 root 관리 코드, 비공개 수집 디렉터리, 12시간 갱신 타이머를 준비합니다. 기존 설치·불명확한 서비스 계정·심볼릭 링크를 인수하지 않습니다. 복사 시 `.pyc`, `.pyo`, `__pycache__` 및 비소스 파일을 제외합니다. 실패한 설치를 무조건 덮어쓰거나 삭제하지 마세요. 설치기 전체의 OS 수준 전원 장애 롤백은 보장하지 않습니다.

`/etc/nginx/snippets/aleph-policy-feed.conf`를 해당 **443/TLS vhost 안에만** 포함하고 `sudo nginx -t && sudo systemctl reload nginx`로 검사·적용합니다. 인증서와 접근 제어는 자동 구성되지 않습니다. 서명은 무결성을 보장할 뿐 정책 내용의 비밀성을 보장하지 않으므로 배포 권한을 검토하세요. 공개하는 파일은 장치별 `current.json` 하나뿐이며 숨김 발행 기록·개인키·원본 URL 데이터셋을 웹 루트로 노출하면 안 됩니다.

## 2. 수집·독립 검토·정책 생성

```bash
sudo systemctl start aleph-policy-refresh.service
sudo systemctl status aleph-policy-refresh.timer
sudo journalctl -u aleph-policy-refresh -n 50 --no-pager
sudo cat /var/lib/aleph-policy-server/latest.json
```

결과는 `/var/lib/aleph-policy-server/runs/<실제-run-id>/`의 `collected.json`, `verified.json`, `review-template.json`입니다. 기본 승인값은 false이고, API 장애가 새 정책 발행으로 이어지지 않습니다. 원본 URL은 비공개로 유지하며 데이터 보존·용량은 운영자가 관리해야 합니다.

리뷰 파일은 수집 계정이 수정할 수 있는 위치에 두지 않습니다. 아래는 **일반 검토자 계정**에서 실행하는 예입니다.

```bash
umask 077
mkdir -p "$HOME/aleph-review"
chmod 700 "$HOME/aleph-review"
RUN=/var/lib/aleph-policy-server/runs/REPLACE-WITH-ACTUAL-RUN-ID
sudo install -o "$(id -un)" -g "$(id -gn)" -m 0600 "$RUN/verified.json" "$HOME/aleph-review/verified.json"
sudo install -o "$(id -un)" -g "$(id -gn)" -m 0600 "$RUN/review-template.json" "$HOME/aleph-review/reviews.json"
# reviews.json을 편집: 실제 검토한 항목만 approved/acknowledge_subtree=true,
# reviewer와 구체적 reason(15자 이상)을 기록합니다. 바깥쪽 증거 해시는 수정하지 않습니다.
export PYTHONPATH=/opt/aleph-policy-code/apps/policy-server/src:/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
python3 -B -m policy_server build \
  --verified "$HOME/aleph-review/verified.json" --reviews "$HOME/aleph-review/reviews.json" \
  --output "$HOME/aleph-review/approved-policy.json" \
  --confirm-replacement --acknowledge-user-notice
```

**호환성 변경:** format 2 승인 템플릿은 전체 검증 아티팩트의 출처·위협 유형·상태·조회 시각·만료·URL 해시와 SUBTREE 범위에 결합됩니다. 구형 템플릿이나 증거가 바뀐 템플릿은 재생성·재검토가 필요합니다. 여러 승인 URL을 한 호스트로 합칠 때 전체 승인 근거·검토자·사유를 감사 해시에 묶고 가장 짧은 만료를 유지합니다.

이는 파일 바꿔치기/실수 탐지이며 **발신자나 사람의 인증이 아닙니다**. 증거와 승인 파일 모두를 바꿀 권한이 있는 공격자는 해시를 다시 만들 수 있습니다. 별도 파일 권한과 서명자 검토를 유지하세요.

OpenPhish Community 갱신은 약 12시간이며 GSB 위협정보는 최신 30분 이내 및 응답 `cacheDuration` 안에서만 사용합니다. 생성하는 BLOCK은 추가로 최대 15분입니다. 만료된 자료는 다시 조회·검토해야 하며, 시각을 고쳐 연장하면 안 됩니다. 이 수동 파이프라인만으로 24시간 보호가 이어지는 것은 아닙니다.

## 3. 서명·발행·중단 복구

승인 정책을 별도 서명 계정의 0700 디렉터리에 전달하고 소유권을 확인한 뒤:

```bash
export PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
python3 -B -m aleph_policy_sync sign \
  --policy /private/approved-policy.json --private-key "$HOME/aleph-signing/signing.pem" \
  --device-id edge-69 --sequence 1 --confirm-replacement \
  --output "$HOME/aleph-signing/releases/edge-69-1.json"
# 서명 결과만 관리 채널로 원격 발행 서버에 전달
```

원격 발행 서버에서:

```bash
sudo env PYTHONPATH=/opt/aleph-policy-code/apps/policy-server/src:/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src \
  /usr/bin/python3 -B -m policy_server promote --device-id edge-69 --release /private/edge-69-1.json
# 추가/철회/만료 단축을 검토한 후 같은 명령에 --apply 추가
```

새 정책은 완전 교체이며, 시퀀스를 올리고 새로운 발행 시각과 신선한 증거를 사용합니다. 활성 차단을 삭제하거나 만료를 앞당길 때는 `--ack-withdrawals`, 서명자를 바꿀 때는 `--ack-key-rotation`이 필요합니다. 빈 정책은 서명 시 `--confirm-empty`도 필요합니다.

발행자는 공개 파일을 쓰기 **전에** root 전용 `.pending-publication.json`을 동기화해 저장하고, 공개 파일과 `.publication.json` 검증 기록을 완성한 뒤 journal을 제거합니다.

- 중단 시 **원래 서명 파일로 동일한 `promote --apply`**를 재실행합니다. 다른 파일로 진행 중인 트랜잭션을 덮어쓸 수 없습니다. 미리보기는 `recovery_pending`만 알리고 변경하지 않습니다.
- 공개 전 만료된 준비 기록은 폐기하고 이전 정책·검증 기록을 보존합니다. 이미 공개된 파일이 만료됐다면 검증 기록만 복구하고 TTL을 늘리지 않습니다.
- 완료된 동일 서명 파일의 재시도는 `already_published=true`, `published=false`이며 파일을 다시 쓰지 않습니다. 같은 시퀀스의 다른 내용이나 이전 시퀀스는 거부합니다.
- format 2 발행 기록은 이전에 검증한 전체 서명 파일을 묶으므로 이전 공개키를 회수한 뒤에도 **현재 신뢰된 새 키**와 명시적 동의로 교체할 수 있습니다. 구형 2필드 기록은 이전 키가 아직 검증 가능할 때 다음 정상 발행으로 이전하세요. DNS 노드에도 새 공개키를 먼저 배포해야 합니다.
- 기록이 가리키는 공개 파일이 사라지거나 해시가 다르면 임의 초기화하지 않습니다. 원본과 백업을 조사하고 정확한 파일을 복원하세요. watermark/journal 삭제로 오류를 우회하지 마세요.

## 4. 사설 DNS 서버

```bash
sudo apt-get install -y python3-cryptography dnsmasq-base dnsutils nftables iproute2
export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -B -m dns_agent example > /tmp/aleph-bootstrap.json
sudo install -o root -g root -m 0644 /private/public.pem /root/aleph-publisher.pub
sudo bash scripts/deploy/install-dns-server.sh \
  --listen-ip 192.168.7.69 --interface eth0 --client-cidr 192.168.7.0/24 \
  --upstream 9.9.9.9 --bootstrap-policy /tmp/aleph-bootstrap.json \
  --public-key /root/aleph-publisher.pub --device-id edge-69 \
  --policy-url https://policy.example.org/v1/policies/edge-69/current.json
# 주소·방화벽·복구 접속 수단을 확인한 뒤 같은 명령에 --apply 추가
```

설치기는 기존 관리형 DNS 설치기와 별도 비특권 fetch/root apply를 연결합니다. DNS는 OpenPhish/GSB를 조회하지 않습니다. 기본 집행은 BLOCK SUBTREE→NXDOMAIN, WARN/ALLOW→비차단입니다. EXACT 제안을 SUBTREE로 자동 확대하거나 공식 도메인 ALLOW를 상위 BLOCK 예외로 취급하지 않습니다.

```bash
sudo systemctl status aleph-dns aleph-policy-fetch.timer aleph-policy-apply.timer
sudo systemctl start aleph-policy-fetch.service
sudo systemctl start aleph-policy-apply.service
sudo journalctl -u aleph-policy-fetch -u aleph-policy-apply -n 60 --no-pager
# 허가된 다른 LAN 단말에서 UDP와 TCP를 각각 확인
# .test는 원래 NXDOMAIN일 수 있으므로 차단 성공은 통제 upstream 양성 응답과 비교
dig @192.168.7.69 example.org A
dig +tcp @192.168.7.69 example.org AAAA
```

`git pull`은 설치본을 갱신하지 않습니다. DNS 업그레이드는 [관리형 업그레이드](../infra/edge/README.md), 원격 코드 갱신은 승인된 유지보수 절차를 사용합니다. 기존 설치 경로를 새 설치기로 덮어쓰지 않습니다. 실패 시 원래 만료기한을 존중하며 무기한 차단하지 않습니다.

**DNS apply 장애와 복구:** 루트 적용기는 정책 게시 전에 상태 디렉터리에
`pending-apply.json`을 기록합니다. 이 파일은 미완료 의도이지 성공한 정책의
증빙은 아닙니다. DNS가 수락한 뒤 `applied.json`을 갱신하며, 중간 실패 시
같은 서명 정책으로 복구할 수 있습니다. 다운로더가 이미 더 새로운 서명 파일을
받은 경우에는 미완료 정책 또는 직전 기록 정책의 **실제 DNS 적용 상태와
전용 방화벽을 검증한 경우에만** 새 정책으로 진행합니다. 둘 다 확인 불가이면
실행을 중단하고 파일·로그를 보존합니다. 서명 만료·키 회수·디스크 손상으로
자동 복구할 수 없는 경우가 있으며, 관리자가 사유를 확인하기 전에는 저널과
재전송 방지 기록을 임의 삭제하지 마세요. 정책의 기존 만료시간은 연장되지 않습니다.
관리자가 긴급히 차단을 해제하거나 DNS 설정을 수정할 때는 먼저 자동 fetch/apply
타이머를 정지하고, 수동 변경과 서명 정책의 재적용 순서를 검토해야 합니다.
더 최신의 정식 서명 정책은 평상시 자동 적용 대상입니다.

**별도 검증:** 실제 API 자격증명·운영 TLS·LAN·재부팅·CNAME/DNSSEC·DoH/VPN·IPv6·캐시·실행 중 연결. NXDOMAIN은 HTTPS 리디렉션이 아닙니다. 점수 기반 `evaluate`는 신뢰 출처/모델/시간이 붙은 EXACT 제안이고 실제 점수 계산이나 자동 승인을 하지 않습니다.

출처·사용 조건: [OpenPhish](https://openphish.com/terms.html), [Community 주기](https://openphish.com/phishing_feeds.html), [GSB v5](https://developers.google.com/safe-browsing/reference/rest/v5/urls/search), [GSB 약관](https://developers.google.com/safe-browsing/terms). 두 서비스의 비상업적 사용·표시·데이터 처리 조건과 내부 재배포 권한을 확인하세요.
