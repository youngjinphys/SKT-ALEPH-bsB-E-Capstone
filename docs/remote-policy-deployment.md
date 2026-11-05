# 대시보드를 HTTPS 정책 서버로 사용하기

Vercel의 `/dashboard`는 FastAPI 정책 서버의 운영 화면입니다. 상태는 별도 영구 저장소에 CAS 방식으로 저장하며, 서명 봉투는 `/v1/policies/<device-id>/current.json`에서 제공합니다. 브라우저 탭이나 Vercel 프로세스의 임시 파일에 정책을 보관하지 않습니다.

## 초안 → 서명 → 게시

1. 운영자 인증 후 수동 FQDN 또는 검토 승인한 근거로 초안을 만듭니다.
2. **DNS 정책 초안 → 장치별 배포 준비**에서 초안과 실제 장치 ID를 선택합니다. 현재 게시 시퀀스, 다음 시퀀스, 정책 SHA-256, 유효기간과 피드 주소를 확인합니다. 조회는 정책을 변경하지 않습니다. 짧은 유효기간이면 새 근거로 초안을 다시 생성합니다.
3. 초안을 다운로드해 독립 서명자에게 전달합니다. 서명자는 동일한 신뢰 소스 체크아웃에서 아래 환경을 설정하고 화면에 표시한 명령의 파일 경로를 바꿔 실행합니다.

   ```bash
   export PYTHONPATH="$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src"
   python3 -m aleph_policy_sync sign --policy /private/draft.json \
     --private-key /private/signer.pem --device-id edge-69 --sequence 1 \
     --output /private/signed-envelope.json --confirm-replacement
   ```

   전체 교체 영향을 검토하세요. 빈 정책의 모든 차단 철회에는 별도 `--confirm-empty`가 필요합니다. 개인키는 생성·보관 절차가 이미 승인된 서명자의 키를 사용하며 업로드하지 않습니다. 출력 파일은 기존 파일을 덮어쓰지 않습니다.
4. **서명 정책 게시로 이동**을 누르면 선택한 장치와 현재 시퀀스가 게시 폼에 반영됩니다. 독립 채널에서 확인한 서명자의 Ed25519 공개키를 **정책 서명자** 역할로 등록합니다. 장치 상태 보고키와 정책 서명키는 분리합니다.
5. 서명 봉투를 업로드해 서명과 교체 영향을 미리 확인합니다. 철회·유효기간 단축·키 변경이 있으면 각각 확인한 후 `PUBLISH_POLICY`로 게시합니다. 다른 운영자가 먼저 게시하면 409가 발생하므로 다시 조회·검토합니다.
6. 정책 피드의 장치·시퀀스·해시와 노드의 서명된 적용 보고를 비교합니다. 게시 성공 후 조회가 실패하면 결과를 미확인으로 두고 다시 조회하세요. 응답 유실 시 재게시하기 전에 현재 시퀀스와 정책 해시를 확인합니다.

`ALEPH_POLICY_FEED_ORIGIN`은 별도 공개 정책 호스트를 사용하는 경우 설정합니다. 미설정이면 `CAPSTONE_SITE_ORIGIN`, 그마저 없으면 기본 Vercel 도메인을 사용합니다. HTTPS 원점만 허용하며 경로·계정·쿼리는 허용하지 않습니다. 대시보드 인증 원점과 실제 정책 피드 원점은 동일하지 않을 수 있습니다.

## DNS 노드 연결

노드의 **상태 보고 등록**과 **정책 수신 설치**는 별도입니다. 노드 등록만으로 fetch/apply 타이머가 설치되지 않습니다. 신규 DNS 서버에서는 배포 준비 화면의 설치 명령을 사용하되 네트워크·부트스트랩 정책·공개키 경로를 실제 값으로 바꿉니다. 처음에는 `--apply` 없는 미리보기로 검사합니다. 승인된 클라이언트 CIDR과 upstream을 임의로 추정하지 마세요.

기존 설치에는 신규 설치 스크립트를 반복하지 않습니다. [DNS 운영 가이드](../infra/edge/README.md)의 기존 설치 업그레이드 절차를 따르고, 현재 정책과 상태·pending journal의 해시를 보존합니다. [Policy Sync 복구 절차](policy-distribution.md)를 확인하세요.

노드에서 확인할 항목:

```bash
systemctl status aleph-policy-fetch.timer aleph-policy-apply.timer
systemctl cat aleph-policy-fetch.service aleph-policy-apply.service
sudo journalctl -u aleph-policy-fetch -u aleph-policy-apply --since '-10 min'
```

feed URL과 장치 ID가 일치하고, 신뢰 디렉터리에 실제 서명자 공개키가 있어야 합니다. 정책 서버의 공개키 등록은 노드의 신뢰키 설치를 대신하지 않습니다. 서비스 이름이나 명령은 현재 설치 내용을 먼저 확인하세요.

## 실제 적용 검증

게시 파일의 서명 성공은 DNS 적용 성공이 아닙니다. 노드의 적용 시퀀스·정책 해시·로컬 attestation·UDP/TCP 검사 결과를 확인하고, 별도 허가된 LAN 클라이언트에서 정상 응답 → 정책 적용 후 차단 → 승인된 철회 후 회복을 각 프로토콜별로 확인합니다. `.test`의 NXDOMAIN 한 번만으로는 차단 증명이 되지 않습니다. 정책의 유효기간을 늘려 검사를 통과시키지 마세요.

## Vercel 배포

웹/API 코드 배포와 DNS 정책 게시는 서로 다른 작업입니다. Git 연결의 저장소가 이 저장소인지와 production 브랜치가 main인지 확인하세요. 다른 저장소가 연결돼 있으면 push만으로 자동 반영되지 않습니다. 배포의 소스 SHA와 실제 `/dashboard/assets/console.js`를 확인한 후 운영 반영을 판단합니다. 환경 변수의 존재만으로 DB 연결이나 운영자 인증이 검증되는 것은 아닙니다.
