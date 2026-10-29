# 시연 순서

1. 격리 VM의 Linux/Python/dnsmasq, 소스 SHA와 테스트 명령을 기록합니다.
2. 통합 시험의 로컬 업스트림이 `blocked.test`와 정상 이름에 A/AAAA를 주는지 확인합니다.
3. 정책 적용 후 `blocked.test`와 그 하위 이름은 NXDOMAIN, 정상·WARN 이름은 원래 응답인지 UDP/TCP로 비교합니다.
4. 잘못된 JSON은 거부하고 이전 정책을 유지하는지, 유효한 새 빈 정책은 차단을 철회하는지 봅니다.
5. 소스 파일 손상 중에도 만료가 처리되는지, 기동 실패 시 복원/복구 실패 시 중단이 분명한지 확인합니다.
6. 포털은 **별도 주소로 직접 열어** 안내합니다. 미제출 신고 초안과 시연 점수를 실제 접수·탐지 결과로 설명하지 않습니다.

## 합격 증거

명령, 원문 출력, DNS 패킷의 RCODE/질의 종류, 정책·설정 해시, 적용·철회 시각,
시험 환경, 실패/복구 결과를 보관합니다. 외부 사이트나 기관을 실제로 피싱이라고 오인시키는 시연은 하지 않습니다.

## 잘못된 증거

`.test`의 NXDOMAIN만 관측한 결과, 서로 다른 캐시/시각/재귀 서버의 A 집합이 항상 같아야 한다는 가정,
`systemctl restart` 성공 코드만으로 정상 판정, blocked 질의 수를 피해 예방 건수로 환산한 수치는 사용하지 않습니다.

[실행 명령](../apps/dns-agent/README.md) · [남은 위험](threat-model.md)

## 가상 캠페인 정책 시연 (DNS 차단과 별도 분류를 구분)

`packages/policy-contract/campaigns/catalog.json`은 가상의 계정·청구서·배송·지원센터 사칭 캠페인 4개로 구성됩니다. 실제 악성 도메인이나 실시간 위협정보가 아닙니다. 파일 생성은 DNS 실행/변경을 일으키지 않습니다.

```sh
python3 scripts/build_campaign_policy.py --list
python3 scripts/build_campaign_policy.py --campaign credential-impersonation > /tmp/aleph-credential-policy.json
export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -m dns_agent validate /tmp/aleph-credential-policy.json
python3 -m dns_agent render /tmp/aleph-credential-policy.json --upstream 127.0.0.1 --upstream-port 35453
```

실습에서는 승인된 BLOCK만 `address=/.../`로 렌더링됩니다. WARN/ALLOW 및 미승인 BLOCK은 로컬 DNS 차단 규칙이 **아닙니다**. 정책이 만료되므로 실행 시 생성하고, 실제 질의 비교에는 정상 응답을 제공하는 통제 업스트림이 필요합니다. [카탈로그 설명](../packages/policy-contract/campaigns/README.md)을 따릅니다.

## HTTP 302 비교 시연

발표에서 **평문 HTTP에서는 302 안내가 가능하다**는 것을 직접 확인하는 독립 실험입니다.
현재 NXDOMAIN DNS 동작을 리다이렉트로 바꾸는 기능이나 HTTPS 해결책이 아닙니다.
운영 DNS·공유기·방화벽·hosts 파일은 변경하지 않습니다.

저장소 루트에서 Python 3.11 이상으로 실행합니다. `sudo`는 필요 없습니다.

```sh
python3 scripts/http_redirect_demo.py
```

두 리스너를 함께 시작하며 Ctrl+C로 함께 종료합니다.

| 주소 | 역할 |
| --- | --- |
| `http://127.0.0.1:38080/` | 모든 GET/HEAD에 고정 `Location`을 가진 302 응답 |
| `http://127.0.0.1:35173/phishing-block.html` | 기존 정적 차단 안내 화면. 실제 신고·정책 변경 권한 없음 |

다른 터미널에서 네트워크 프록시를 경유하지 않고 확인합니다.

```sh
curl --noproxy '*' --head http://127.0.0.1:38080/
curl --noproxy '*' --location --max-redirs 1 --dump-header - \
  http://127.0.0.1:38080/ --output /tmp/aleph-http-demo.html
```

첫 명령은 `302`와 `Location: http://127.0.0.1:35173/phishing-block.html`, 두 번째는 `302` 이후 `200`을 보여야 합니다.
브라우저에서도 첫 주소를 직접 열어 화면 전환을 볼 수 있습니다. HTTPS 우선 모드 등으로 동작이 다르면 설정을 낮추지 말고 curl 결과를 사용합니다.
35173번 포털이 이미 실행 중이면 먼저 그 시연을 종료하거나 `--portal-port 35174`를 사용합니다.

```sh
python3 scripts/http_redirect_demo.py --redirect-port 38081 --portal-port 35174
python3 -m unittest discover -s tests/e2e -p 'test_*.py' -v
```

검증 범위는 실제 로컬 302→포털 연결, GET/HEAD, POST 거부, 정적 파일 허용 목록,
보안 헤더, 임의 Host·쿼리·원래 URL의 목적지 반영 방지, 부분 기동 실패 시 소켓 정리입니다.
요청 경로·쿠키·전체 URL을 수집하거나 다른 서버로 전달하지 않습니다.
이 서버에 `https://`로 접속해 생기는 오류는 **TLS를 제공하지 않는 실험 서버의 오류**입니다.
그 결과를 원래 도메인의 인증서 신원 검증 실패 실험과 혼동하지 않습니다.

### 발표에서 정확히 말할 문장

> “이 비교 실험은 HTTP 응답이 이미 가능한 단계에서 302가 동작함을 보여줍니다.
> HTTPS에서는 그 전에 브라우저가 원래 도메인의 인증서를 검증합니다.
> DNS나 라우팅의 도착지를 바꾸어도 그 인증서 조건은 바뀌지 않습니다.”

## 다음 시연의 완료 조건

[조건별 검증표](validation-matrix.md)를 기준으로 실험 환경·소스 SHA·원문 응답·미측정 항목을 기록합니다.
25분 발표에서는 DNS 정상/차단 대조, 철회, HTTP 비교까지 약 3분으로 제한하고,
DoH·VPN·실제 LAN은 측정 증거가 없으면 한계와 다음 실험으로 설명합니다.
