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

## 정책 기반 HTTP 302 경고·차단 실습

기존 **고정 302 비교 파일은 중복되어 제거**했습니다. 이제 실제 DNS 에이전트가
수락한 정책과 활성 dnsmasq 설정이 서로 일치할 때에만,
`BLOCK` / `WARN`의 요청 HTTP `Host`를 분리하여 기존 포털로
고정된 `302`를 반환합니다. `ALLOW`나 미승인·만료된 이름은 전달하지 않습니다.

**기본 NXDOMAIN은 그대로 유지**합니다. 별도 실습 모드는
`--http-sink-ip` / `--ack-http-sinkhole`을 명시적으로 선택해야
승인된 BLOCK/WARN의 A 응답을 안내 IP로 바꿉니다.
기본 브라우저 사용 시 별도 DNS:53과 HTTP:80이 필요하며,
고포트 루프백 시험은 실제 LAN 연계 완료를 뜻하지 않습니다.

[실행 명령·허용 범위·요청 검증·HTTPS 한계](http-notice.md) ·
[단위 및 로컬 HTTP 통합 테스트](../tests/e2e/test_http_policy_notice.py)

### 발표에서 정확히 말할 문장

> “DNS의 이름 해석과 HTTP의 302 응답은 서로 다른 계층입니다.
> 선택형 실습에서는 정책에 해당하는 DNS A 응답을 로컬 안내 IP로
> 돌려 평문 HTTP에 대해 302 화면 전환을 시연합니다.
> HTTPS/HSTS에서는 원래 호스트 인증서를 확보하지 못하므로
> 자동 안내가 아니라 연결 오류가 발생할 수 있습니다.”

## 다음 시연의 완료 조건

[조건별 검증표](validation-matrix.md)를 기준으로 실험 환경·소스 SHA·원문 응답·미측정 항목을 기록합니다.
발표에서는 DNS 정상·차단·철회와 선택형 HTTP 안내를 독립 증빙으로 구분하고,
DoH·VPN·실제 LAN은 측정 증거가 없으면 한계와 다음 실험으로 설명합니다.
