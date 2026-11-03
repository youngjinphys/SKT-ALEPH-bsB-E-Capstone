# ALEPH DNS Operations Console

검증된 위협정보에 대한 검토, **미서명 DNS 정책 생성**, 비집행 EXACT 제안 엔진 설정, 서명된 로컬 게시 파일 확인을 수행하는 운영자 관제 GUI입니다. 기존 `policy_server.intel.build_policy`, `dns_agent.policy.parse_policy`, `policy_server.engine.evaluate_policy`, `aleph_policy_sync.snapshot.verify_envelope`을 재사용합니다. 모의 통계, 자동 승인, 온라인 서명, 자동 root 발행은 구현하지 않습니다.

## 위협 모델과 권한

| 단계 | 콘솔 권한 | 실제 시스템 변경 |
| --- | --- | --- |
| 최신 `verified.json` 읽기 | 0600 파일 | 원본 조회 결과 변경 없음 |
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

1. **검토 자료 확보:** 기존 `policy_server refresh`로 생성된 특정 run의 `verified.json`을 수집자가 변경할 수 없는 리뷰어 작업 공간에 복사합니다. 원본 URL은 브라우저에 제공하지 않습니다.
2. **위협 검토:** 후보별 위협 유형·유효기간·증거 해시를 확인합니다. 승인 시 구체적인 사유(15자 이상), 검토자 이름, SUBTREE 차단 영향 확인이 필요합니다. 증거가 달라지면 기존 검토 기록을 자동 이전하지 않습니다.
3. **정책 초안 생성:** 전체 교체·사용자 안내 영향을 확인하고 빌드합니다. 기존 `intel.build_policy`가 만료된 근거나 승인 없는 BLOCK을 거부합니다. 결과는 `<workspace>/drafts/`의 0600 파일입니다.
4. **독립 서명·발행:** GUI에서 초안을 다운로드한 뒤 [원격 정책 운영 가이드](../../docs/remote-policy-deployment.md)에 따라 독립 서명자의 `aleph_policy_sync sign`, 발행자의 `policy_server promote`(미리보기 후 `--apply`), DNS 노드의 서명 검증된 fetch/apply를 실행합니다.
5. **DNS 독립 검증:** `aleph-policy-fetch`·`aleph-policy-apply`·live resolver 상태와 실제 LAN UDP/TCP 질의를 확인합니다. 콘솔의 `SIGNED_FILE_VERIFIED`는 **게시 파일의 서명 확인**이며 HTTPS 전달이나 DNS 실제 적용 증명이 아닙니다.

위협 증거의 수명은 짧습니다. 서명·배포 전에 정책이 만료되면 새로 수집하고 검토해야 합니다.

## 보안 및 기술 제한

- 외부 Node/npm 서버, DB, CDN, 분석 스크립트, 의심 사이트 요청이 없는 Python 표준 라이브러리 HTTP 서비스와 번들 HTML/CSS/JS를 사용합니다.
- 소유자 전용 0600 액세스 토큰(32~256자)을 Authorization Bearer 헤더로 확인합니다. 토큰은 브라우저 메모리에만 남고, 새로고침/로그아웃 시 사라집니다. API는 Host/Origin·크기 제한을 적용합니다.
- 운영 토큰, `verified.json`, `reviews.json`, 미서명 초안, 설정, 감사 기록은 GitHub·공개 디렉터리·웹 루트에 저장하면 안 됩니다.
- DNS 원격 텔레메트리, 실제 적용 증빙, 사용자별 RBAC/SSO, 서명자 승인 DB 및 root 배포 자동화는 제공하지 않습니다.

## 테스트

```bash
export PYTHONPATH="$PWD/apps/policy-server/src:$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src"
python3 -B -m unittest discover -s tests/policy_server -p 'test_console.py' -v
```

테스트는 합성 위협정보를 사용하며 외부 API를 호출하지 않습니다.
