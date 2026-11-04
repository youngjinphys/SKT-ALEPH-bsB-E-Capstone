# ALEPH DNS Operations Console

검증된 위협정보에 대한 검토, **미서명 DNS 정책 생성**, 비집행 EXACT 제안 엔진 설정, 서명된 로컬 게시 파일 확인을 수행하는 운영자 관제 GUI입니다. 기존 `policy_server.intel.build_policy`, `dns_agent.policy.parse_policy`, `policy_server.engine.evaluate_policy`, `aleph_policy_sync.snapshot.verify_envelope`을 재사용합니다. 모의 통계, 자동 승인, 온라인 서명, 자동 root 발행은 구현하지 않습니다.

## 위협 모델과 권한

| 단계 | 콘솔 권한 | 실제 시스템 변경 |
| --- | --- | --- |
| 최신 `verified.json` 읽기 | 0600 파일 또는 제한된 Unix 소켓을 통한 명시적 가져오기 | 원본 조회 결과 변경 없음 |
| GUI 수집 요청 | Unix 소켓으로 고정 OpenPhish/GSB 검증만 요청 | 비특권 수집기만 실행; 승인·서명·배포 불가 |
| 검토자 승인/거절 | 리뷰어 소유 0700 작업 공간의 `reviews.json` | **DNS 미변경** |
| BLOCK 초안 생성 | 실제 엔진이 신선도·SUBTREE 승인·증거 결합을 검증 | 0600 미서명 JSON만 생성 |
| 제안 엔진 목록 수정 | 로컬 `engine-config.json`의 EXACT 제안 평가 | **DNS 미변경** |
| 게시 상태 조회 | 선택한 피드의 `current.json`을 신뢰 공개키로 검증 | 서명된 **로컬 파일 상태만** 표시 |
| 서명·root 발행·DNS 적용 | 콘솔에서는 **실행 불가** | 독립 서명자/발행자/DNS 노드에서 시행 |

브라우저에서 입력하는 **검토자 식별명은 본인 인증을 대체하지 않습니다**. 검토 파일 해시는 증거와 기록의 불일치만 감지합니다. 작업 기록(`audit.jsonl`) 역시 변경 불가능한 감사 증거가 아닙니다.

## 실행 (수동·옵트인)

Linux, Python 3.11+, `python3-cryptography`가 필요합니다. 정책 수집·서명·root 발행과 다른 **전용 비특권 리뷰어 계정**에서, 저장소 밖의 작업 공간을 사용하세요.

```bash
umask 077
install -d -m 0700 "$HOME/aleph-console"
python3 -c 'import secrets, pathlib; pathlib.Path.home().joinpath("aleph-console.token").write_text(secrets.token_urlsafe(48) + "\n")'
chmod 600 "$HOME/aleph-console.token"
# 수집 완료 후 안전하게 전달받은 동일 run의 verified.json 사본
install -m 0600 /trusted-review-copy/verified.json "$HOME/aleph-console/verified.json"

export PYTHONPATH="$PWD/apps/policy-server/src:$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src"
python3 -B -m policy_server.console \
  --workspace "$HOME/aleph-console" \
  --token-file "$HOME/aleph-console.token" \
  --port 8765
```

서비스는 **항상 127.0.0.1에서만** 접속받습니다. 로컬에서 http://127.0.0.1:8765 에 접속해 토큰 파일의 내용을 입력하세요. 다른 장치에서 접속한다면 SSH 터널을 사용합니다.

```bash
ssh -N -L 8765:127.0.0.1:8765 reviewer@policy-server.example.org
```

실제 주소와 계정을 바꾸세요. 원격 TLS 리버스 프록시를 설정한다면 접근통제·인증·rate limit을 별도로 적용하고 콘솔에 `--origin https://admin.example.org`를 전달해야 합니다. 프록시가 올바른 Host/Origin을 전달해야 합니다. 인터넷에 직접 노출하지 마세요.

로컬에서 서명된 게시 파일과 공개키를 읽을 수 있을 때만 다음 옵션을 추가합니다.

```bash
  --feed-root /srv/aleph-policy-feed \
  --device-id edge-69 \
  --trust-dir /etc/aleph-policy-sync/trust
```

다른 서버의 원격 피드는 로컬 `--feed-root` 설정만으로 읽을 수 없습니다. 별도 검증된 읽기 전용 복제 또는 권한 분리된 프로세스가 필요합니다. 콘솔에 root 권한, 개인 서명키, DNS 관리자 실행 권한을 주지 마세요.

## 운영 흐름

1. **검토 자료 확보:** 기존 `policy_server refresh`의 특정 run `verified.json`을 안전하게 복사하거나, 별도 설치한 Unix 수집 브리지를 통해 GUI의 **위협 검토 → OpenPhish + GSB 새로 검증 → 최신 검증 자료 가져오기**를 실행합니다. 수집기는 고정 공식 URL만 조회하고 API 키·원본 URL은 브라우저에 전달하지 않습니다. GUI는 상태·도메인·근거 해시만 표시합니다.
2. **위협 검토:** 후보별 위협 유형·유효기간·증거 해시를 확인합니다. 승인 시 구체적인 사유(15자 이상), 검토자 이름, SUBTREE 차단 영향 확인이 필요합니다. 증거가 달라지면 기존 검토 기록을 자동 이전하지 않습니다.
3. **정책 초안 생성:** 전체 교체·사용자 안내 영향을 확인하고 빌드합니다. 기존 `intel.build_policy`가 만료된 근거나 승인 없는 BLOCK을 거부합니다. 결과는 `<workspace>/drafts/`의 0600 파일입니다.
4. **독립 서명·발행:** GUI에서 초안을 다운로드한 뒤 [원격 정책 운영 가이드](../../docs/remote-policy-deployment.md)에 따라 독립 서명자의 `aleph_policy_sync sign`, 발행자의 `policy_server promote`(미리보기 후 `--apply`), DNS 노드의 서명 검증된 fetch/apply를 실행합니다.
5. **DNS 독립 검증:** `aleph-policy-fetch`·`aleph-policy-apply`·live resolver 상태와 실제 LAN UDP/TCP 질의를 확인합니다. 콘솔의 `SIGNED_FILE_VERIFIED`는 **게시 파일의 서명 확인**이며 HTTPS 전달이나 DNS 실제 적용 증명이 아닙니다.

위협 증거의 수명은 짧습니다. 서명·배포 전에 정책이 만료되면 새로 수집하고 검토해야 합니다. 콘솔은 **증거가 신선하더라도 공유 호스팅·고영향 도메인에는 SUBTREE 승인을 허용하지 않으며**, 기존 정책 생성기의 추가 검증을 유지합니다.

## 관제 상태 해석과 화면 디자인

두 참고 저장소의 코드를 확인해 디자인 언어를 적용했습니다. [SKT-ALEPH-PR-Page](https://github.com/youngjinphys/SKT-ALEPH-PR-Page)의 네이비·시안 기반 글래스 표면과 [Claire](https://github.com/youngjinphys/Claire)의 Observatory 스타일·정보 밀도·궤도형 시각 요소를 사용합니다. 외부 디자인 라이브러리나 CDN은 추가하지 않았습니다. 애니메이션 감소·투명도 감소·강제 색상 설정을 고려합니다.

- **관제 상태:** 연결된 콘솔이 응답했는지, 로컬 증거가 현재 유효한지를 표시합니다. 녹색·시안 시각 신호가 운영 DNS의 차단 성공을 뜻하지 않습니다.
- **검토 후보/승인 기록:** 위협 URL 기반 검토 항목과 과거 수동 승인 이력입니다. *현재 차단된 DNS 도메인 수* 또는 *차단 성공 횟수*가 아닙니다.
- **신선한 증거:** 실제 백엔드 시각 기준 조회 유효기간 안의 결과입니다. **작성 가능 후보**는 보호된 공유 호스팅 도메인 등을 제외한 값입니다.
- **정책 초안:** 비특권 리뷰어가 생성한 미서명 JSON입니다. 서명이나 배포 성공으로 계산하지 않습니다.
- **서명된 게시 정책:** 지정된 로컬 `current.json`의 Ed25519 서명·정책 유효기간·장치 ID 등을 검사한 결과입니다. 서명이 유효하고 유효기간 안이면 `SIGNED_FILE_VERIFIED`, 서명은 맞지만 유효기간이 지났으면 `PUBLICATION_EXPIRED`, 서명·형식·시각이 깨졌으면 `VERIFICATION_FAILED`입니다. 어느 상태도 게시자의 완료 영수증, 외부 HTTPS 도달성, DNS 노드의 적용 영수증을 대신하지 않습니다.

로그인 토큰은 메모리에만 유지하며 **15분간 조작이 없으면 브라우저에서 잠금 처리**합니다. 상태 화면만 60초 간격으로 재조회하고, 편집 중인 검토/엔진 설정/정책 작성 폼을 자동 새로고침하지 않습니다. 서버는 느린 요청을 10초 이후 중단할 수 있습니다. 이 브라우저 잠금은 SSO·서버 세션 폐기·다중 사용자 RBAC의 대안이 아닙니다.

### 실패/경고 상태

서명 확인에 실패하거나 증거가 만료된 경우에는 UI에서 명시적으로 알리고, **UNKNOWN / 미확인 / 미설정 / 서명 검증 실패 / 게시 유효기간 만료**를 구분합니다. 만료된 서명 파일을 서명 손상으로 표시하지 않습니다. 네트워크 장애나 취소된 조회 결과를 성공으로 보정하지 않습니다. 로컬 작업 로그는 마지막 100건을 제한된 메모리로 읽지만 변조 방지된 감사 체계나 독립 감사자 확인을 제공하지 않습니다.

## 보안 및 기술 제한

- 외부 Node/npm 서버, DB, CDN, 분석 스크립트, 의심 사이트 요청이 없는 Python 표준 라이브러리 HTTP 서비스와 번들 HTML/CSS/JS를 사용합니다.
- 소유자 전용 0600 액세스 토큰(32~256자)을 Authorization Bearer 헤더로 확인합니다. 토큰은 브라우저 메모리에만 남고, 새로고침/로그아웃 시 사라집니다. API는 Host/Origin·크기 제한을 적용합니다.
- 운영 토큰, `verified.json`, `reviews.json`, 미서명 초안, 설정, 감사 기록은 GitHub·공개 디렉터리·웹 루트에 저장하면 안 됩니다.
- 장치 서명 DNS 텔레메트리 및 노드 로컬 적용 상태 비교는 제공하지만, **LAN 전체 실제 이용 증빙**, 사용자별 RBAC/SSO, 서명자 승인 DB 및 root 배포 자동화는 제공하지 않습니다. 악성 URL의 진위에 대한 암호학적 발신자 인증도 콘솔 자체는 수행하지 않으며, 신뢰되는 수집/전달 절차 및 독립 서명 검토가 필수입니다.

## 테스트

```bash
export PYTHONPATH="$PWD/apps/policy-server/src:$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src"
python3 -B -m unittest discover -s tests/policy_server -p 'test_console.py' -v
```

테스트는 합성 위협정보를 사용하며 외부 API를 호출하지 않습니다.


## 검토 동시성 및 전체 교체 영향 미리보기

- 각각의 검토 항목은 현재 리뷰 JSON에 결합된 `revision`으로 저장합니다. 다른 탭 또는 운영자가 먼저 변경한 뒤 오래된 화면에서 덮어쓰면 API는 HTTP **409 Conflict**를 반환합니다. 변경을 재확인한 뒤 후보를 다시 선택해야 합니다.
- 같은 검증 증거를 다른 순서로 저장해도 URL 해시·조회 시각·도메인 일치와 전체 fingerprint가 동일한 경우 리뷰를 유효하게 인정합니다. 중복된 리뷰나 다른 근거가 섞인 리뷰는 거부합니다.
- 신규 증거를 전달받아 기존 리뷰가 무효화된 경우에는 `검토 기록 초기화`의 읽기 전용 재설정 문맥을 확인합니다. 초기화는 *현재 증거 fingerprint*와 *디스크의 현재 리뷰 전체 revision* 양쪽에 결합되므로, 초기화 직전 발생한 다른 변경을 무시하고 실행할 수 없습니다.
- 초안 목록의 `변경 영향 확인`은 `/api/drafts/<이름>/impact`를 통해 서명 검증된 **로컬 게시 기준선**과 신규 정책의 유효한 BLOCK 차단 집합을 비교합니다. 추가·철회·만료 단축 수와 첫 20개 도메인 샘플을 보여줍니다. 게시 기준선이 미설정·만료·서명 검증 실패라면 **영향을 계산할 수 없음**으로 명확히 알립니다.
- 철회나 만료 단축이 예상된다면 발행자가 `promote --ack-withdrawals`로 별도 확인하도록 안내합니다. 미리보기는 root 게시, DNS fetch/apply, 온라인 DNS 적용을 **실행하지 않습니다**.
- 화면의 15분 비활동 잠금은 클릭 후 활동 시간이 갱신되기 **전에** 확인하며, 같은 브라우저에서 재인증하거나 탭을 전환했을 때 이전 비동기 응답이 새로운 세션의 내용을 덮어쓰지 않도록 세션·뷰별 요청 버전을 확인합니다.


## DNS 노드 등록 및 서명된 적용 상태

관제 화면의 **배포 현황 → DNS 노드 및 적용 증명**에서 장치 ID, 사설 DNS IPv4, 표시 이름, 독립 장치 키 SHA-256을 입력합니다. 먼저 별도의 운영자 채널을 통해 해당 Ed25519 **공개키만** 원격 관제 서버 root 관리 신뢰 디렉터리에 설치해야 하며, GUI는 인증 키를 새로 신뢰하거나 임의 IP로 접속하지 않습니다. DNS 서버의 root 수집기가 실제 `applied.json`/서명된 Inbox/로컬 `attest`/UDP/TCP 응답을 검사해 서명한 보고만 받습니다. DNS 노드의 비특권 프로세스가 고정 HTTPS 엔드포인트 `POST /v1/nodes/report`로 전송하며, 카운터와 시각을 재검증합니다. 단순 게재 정책 확인, 로컬 DNS 적용 확인, LAN 클라이언트 정상 이용은 **서로 다른 검증 단계**입니다. 자세한 키 등록·시스템 서비스·NGINX TLS 프록시와 상태 해석은 [상태 보고 운영 가이드](../../docs/dns-node-telemetry.md)를 따릅니다.


### DNS 노드의 차단 성공 판정 조건

노드 telemetry format 2는 차단 canary 도메인에 대한 `probe.baseline`을 추가합니다. 별도 상위 DNS의 UDP/TCP A 응답에 실제 A 레코드가 있을 때만 양성 비교가 성립합니다. 로컬 서버의 UDP/TCP A·AAAA가 모두 NXDOMAIN이고 기존 root attest 및 게시 정책 SHA-256·시퀀스가 일치할 때만 `LOCAL_DNS_VERIFIED`라고 표현합니다. 구형 format 1 보고와 상위 비교 기준 누락은 `LOCAL_DNS_UNCORROBORATED`, 상위 DNS 양성 기준 실패는 `LOCAL_DNS_REFERENCE_UNVERIFIED`로 구분합니다. 이 판정은 노드 내부 관측이며 LAN 단말 전체 보호와는 별개입니다.


### 부분 장애와 장치 키 교체 상태

관제 개요의 검토 근거, 장치 등록정보 및 미서명 초안 저장소는 서로 독립적으로 실패할 수 있습니다. 데이터가 손상되거나 읽기 권한이 부적절하면 해당 통계는 0으로 대체하지 않고 **미확인(—)**으로 표시합니다. DNS 장치를 명시적으로 등록 해제하고 새 장치 공개키로 재등록한 직후 기존 서명 보고는 **REKEY_PENDING**으로 표시하며, 새 장치 키로 유효한 보고가 도착하기 전에는 성공으로 처리하지 않습니다. 교차 프로세스 등록 및 보고 수락은 OS 파일 잠금으로 직렬화합니다. 최초·기존 설치 절차는 [운영 가이드](../../docs/production-install-and-validation.md)를 참고하세요.

**장치 키 재등록:** 노드를 등록 해제하면 해당 장치 상태 보고 공개키 지문은 신뢰 기록(format 2)의 retired-key 목록에 원자적으로 보관됩니다. 같은 개인키/공개키로 재등록하는 것은 거부됩니다. 노드 재등록에는 *새로운* 장치 전용 Ed25519 키 쌍 생성, 새 공개키의 별도 검증 및 신뢰 등록이 필요합니다. 등록된 새 키로 유효한 보고가 들어오기 전에는 `REKEY_PENDING`으로 처리하고 이전 보고를 운영 정상으로 인정하지 않습니다.

## GUI에서 OpenPhish / Google Safe Browsing 갱신

기존 원격 정책 서버에는 `policy_server refresh`(OpenPhish Community feed → Google Safe Browsing v5 검증)와 12시간 timer가 있습니다. GUI 직접 갱신은 선택형 **`install-intel-refresh-bridge.sh`** 설치가 필요합니다. 수집/웹 계정 사이에는 인증된 로컬 Unix 소켓(`/run/aleph-intel-refresh.sock`, 0660, group `aleph-ops-console`)만 노출됩니다. 커널 SO_PEERCRED로 실제 콘솔 사용자 UID를 확인합니다. 키 파일 `/var/lib/aleph-policy-server/google-api-key`는 `aleph-policy-server`만 읽습니다.

1. 원격 정책 서버의 현재 검토된 checkout을 `/opt/aleph-policy-code`에 먼저 적용합니다. 초기 정책 서버·관제 콘솔 설치 완료 후 `sudo bash scripts/deploy/install-intel-refresh-bridge.sh` 미리보기를 검토하고 `--apply`로 활성화합니다. 기존 설치용 업그레이드 스크립트는 활성 bridge service/socket을 중지한 상태에서 실행해야 합니다.
2. 관제의 **위협 검토** 화면에서 세 가지 사용 조건을 확인하고 `OpenPhish + GSB 새로 검증`을 누릅니다. 버튼은 비특권 collector thread를 요청할 뿐, 의심 사이트에 방문하거나 DNS 서버를 변경하지 않습니다. 수동 요청은 최대 5분마다 한 번만 수락되고, 12시간 자동 timer와 같은 `.refresh.lock`을 사용하므로 병렬 외부 호출을 차단합니다.
3. 상태가 `SUCCESS`이고 현재 `Run ID`·시각·검토 후보가 확인되면 **최신 검증 자료 가져오기**로 반영합니다. 별도 `IMPORT_VERIFIED` 입력을 요구하며, 기존 검토 자료는 0700 `evidence-archive/`에 0600 파일로 백업합니다. **이전 승인 결과를 새 증거로 복사하지 않습니다.** 검토 항목은 모두 미승인으로 시작합니다. 백업 디렉터리에는 원본 검증 URL이 포함될 수 있으므로 외부에 공개하지 마세요.
4. 새 근거를 검토하고 초안을 만든 뒤 기존 독립 서명자·root 발행자·DNS 적용기를 그대로 사용합니다. **자동 서명, 자동 게시, 자동 DNS 차단은 GUI에 없습니다.** 기존 발행 정책과 과거 초안은 새 증거를 가져오는 작업으로 수정되지 않습니다.

수집 실패, API 키·네트워크 장애, 만료, source 약관 문제는 기존 자료를 보존하고 GUI에서 실패/미확인을 나타냅니다. 수집 상세 원인은 `journalctl -u aleph-intel-refresh.service -u aleph-policy-refresh.service`로 확인하세요. `/api/intel`은 브라우저에 원본 위협 URL을 반환하지 않으며, 비공개 run별 검증 JSON을 복제하는 데는 별도 운영 승인과 기존 권한 분리가 필요합니다. 최초/기존 설치에서 운영 중단·복구와 신뢰 공개키 관리도 별도로 확인해야 합니다.

## 게시 대상별 조회와 동시 변경 보호

**배포 현황** 상단에서 등록 장치를 선택하면 해당 장치의 서명된 게시 정책과 규칙을 조회합니다. `/api/deployment/<device_id>`는 읽기 전용이며, 선택을 바꾸어도 기본 DNS 주소나 게시 정책을 수정하지 않습니다. `/dashboard`에서는 동일 기능을 `/api/ops/deployment/<device_id>`로 제공합니다. 전체 노드의 검증 수와 선택 노드의 결과를 구분합니다.

게시 정책과 노드 상태 조회는 독립적으로 실패할 수 있습니다. 실패한 구역은 이전 정상 값을 남겨 두지 않고 **미확인**으로 바꾸며, 성공한 다른 구역은 유지합니다. 느린 이전 대상의 응답은 현재 선택을 덮어쓸 수 없습니다. 노드 등록 양식은 **새 DNS 노드 등록**을 펼쳐 사용합니다.

로컬 수집 자료를 가져올 때는 `/api/intel`의 `context_revision`과 `review_revision`을 모두 확인 요청에 보냅니다. 근거 파일만 바뀌어도 이전 확인은 거부됩니다. 장치 등록 해제는 표시된 장치의 `expected_key_id`가 필요합니다. 대화상자가 열린 동안 장치 키가 교체되면 409로 거부되고 새 장치는 보존됩니다. 기존 직접 API 호출 스크립트도 이 전제조건을 추가해야 합니다. 화면과 서버를 같은 커밋으로 갱신하고 이전 탭은 새로고침하세요.

### FQDN 수동 블랙리스트와 OpenPhish·GSB

DNS 정책 초안 메뉴에서 FQDN, 검토자, 근거, 만료시간 및 SUBTREE
범위를 명시적으로 검토·등록·해제할 수 있습니다. 기존 EXACT 제안
엔진과 별개이며, 등록만으로 DNS에 적용되지 않습니다.
승인된 GSB 증거와 수동 FQDN은 새 **미서명 전체 교체 정책 초안**에
함께 반영됩니다. 실제 적용은 외부 서명과 게시, 노드 서명 상태 확인을
별도로 거쳐야 합니다.

로컬 서버의 비특권 위협정보 수집 브리지는 유지합니다.
Vercel에서는 합법적으로 허가된 사용을 전제로 Production 환경에
`SAFE_BROWSING_API_KEY`, `ALEPH_OPENPHISH_SOURCE_ALLOWED=true`
둘 다 있을 때만 직접 갱신을 활성화합니다. 자세한 절차는
`docs/manual-fqdn-and-feed-workflow.md`에 있습니다.
