# 정책 기반 평문 HTTP 안내 실습

## 지원과 미지원

이 기능은 기존의 **고정 302 시연**과 달리, DNS 에이전트가 마지막으로 수락·검증한 `state.json`/`active.conf`를 읽어 요청 HTTP `Host`가 실제 활성 `BLOCK`인지 `WARN`인지 판정합니다.

| 정책 | 기본 DNS | HTTP 안내 실습 DNS A | HTTP 80 응답 |
| --- | --- | --- | --- |
| 승인된 `BLOCK` | NXDOMAIN | 안내 서버 IPv4 | `302 → /phishing-block.html` |
| 승인된 `WARN` | 비차단 | 안내 서버 IPv4 | `302 → /phishing-warning-continue.html` |
| `ALLOW`, 미승인·만료 | 비차단 | 원래 DNS 응답 | 이 서비스로 라우팅하지 않음 |

이름은 `SUBTREE`로 판정하며 정확히 한 호스트만 매칭하는 `EXACT`는 지원하지 않습니다. 안내 IP는 DNS 리스너와 같아야 하며, `address=/.../IPv4`와 `local=/.../`를 함께 생성하여 dnsmasq의 IPv6 AAAA/HTTPS/SVCB 쿼리가 업스트림으로 그대로 전달되지 않도록 합니다. 서비스는 평문 HTTP `GET`/`HEAD`만 지원하고 쿠키·URL·요청 경로를 로그로 저장하거나 리다이렉트 주소에 포함하지 않습니다. `POST`, 임의 HTTP 프록시 목적지, 알 수 없는 Host는 전달하지 않습니다.

**HTTPS, 브라우저 HTTPS-First, HSTS는 차단 안내로 전환되지 않습니다.** DNS A를 변경하면 HTTPS 인증서 검증 전에 연결이 실패하거나 오류 페이지가 나타납니다. HTTPS를 우회하거나 임의 CA를 배포하지 마세요. WARN의 기본 비차단 의미도 이 실습에서만 바뀌므로 실제 사용자 트래픽에 기본 적용하지 마세요.

## 로컬 동작 확인 (관리자 권한 불필요)

저장소 루트에서 `PYTHONPATH`를 설정한 뒤 [루트 README](../README.md)의 두 개 명령을 **별도 터미널**에서 실행합니다. `--http-sink-ip`/`--ack-http-sinkhole` 및 안내 서버의 `--ack-plaintext-only`는 생략할 수 없습니다.

```sh
export PYTHONPATH="$PWD/apps/dns-agent/src"
python3 -m dns_agent example > /tmp/aleph-policy.json
# A 터미널: --http-sink-ip 127.0.0.1 --ack-http-sinkhole 로 dns_agent 실행
# B 터미널: --http-port 38080 --portal-port 35173 로 dns_agent.http_notice 실행
# C 터미널:
dig @127.0.0.1 -p 35353 blocked.test A
dig @127.0.0.1 -p 35353 blocked.test AAAA
curl --noproxy '*' -I --resolve blocked.test:38080:127.0.0.1 \
  http://blocked.test:38080/some/path?secret=not-copied
curl --noproxy '*' -I --resolve warn.test:38080:127.0.0.1 \
  http://warn.test:38080/
curl --noproxy '*' -I http://127.0.0.1:35173/phishing-block.html
```

기대값: `BLOCK/WARN A=127.0.0.1`, `AAAA`는 외부 주소 없이 응답, `BLOCK` HTTP는 고정 차단 페이지로 `302`, `WARN`은 경고 페이지로 `302`, 정적 포털은 `200`. 정상·비대상 도메인은 정책 승인 없이 바뀌지 않습니다. `curl --resolve`는 HTTP 경로를 테스트하기 위한 수단으로 **클라이언트 기본 DNS 설정 증명은 아닙니다**. 실행 중 정책 만료·철회 후에는 수락 상태를 다시 확인해야 합니다.

## 192.168.7.69 / LAN 80번으로 확장할 때

**기존 관리형 `aleph-dns.service`에 이 실험 기능은 자동 설치되지 않습니다.** DNS 주소만 바꾼 클라이언트가 자동 HTTP 안내를 보려면 호스트의 UDP/TCP 53번 DNS가 안내 IP를 응답해야 하고, 동일 호스트의 TCP 80번에 HTTP 안내 서비스가 있어야 합니다. 정적 포털은 별도 TCP 포트(예: 35173)로 접근 가능해야 합니다.

격리된 Linux VM에서 관리자가 다음을 확인해야 합니다.

1. DNS 서비스와 HTTP 서비스가 **같은 검증된 정책 상태**를 사용하고, DNS가 실제 안내 모드로 실행되는지
2. 정책이 승인된 랩 도메인만 포함하고 실제 HTTPS 사용자의 접속을 방해하지 않는지
3. 서버 `192.168.7.69`에 `53/udp`, `53/tcp`, `80/tcp`, 포털 TCP 포트를 받을 수 있는지, 다른 서비스와 포트 충돌은 없는지
4. HTTP 서비스는 root로 직접 실행하지 않으며, 필요하면 systemd `AmbientCapabilities=CAP_NET_BIND_SERVICE`로 포트 80 바인딩 권한만 부여하는지
5. HTTP 서비스의 `--listen-ip 192.168.7.69 --client-cidr 192.168.7.0/24 --http-port 80`와 DNS 에이전트의 `--listen-address 192.168.7.69 --system-dns --port 53 --http-sink-ip 192.168.7.69 --ack-http-sinkhole`를 일치시키는지
6. 기존 관리형 systemd·nftables·방화벽 규칙을 수동으로 덮어쓰지 않고 별도 허가된 VM에서 먼저 시험하는지

이 저장소의 기존 `infra/edge/system_dns.py install`은 기본 NXDOMAIN 시스템 DNS 설치기입니다. **그 설치기를 실행하는 것만으로 HTTP 실습 모드가 켜지지 않습니다.** 실제 LAN용 부가 서비스 설치·자동 복구·방화벽 통합은 별도 운영 검증이 필요합니다. 포트 80의 권한을 얻기 위해 Python 실행파일 전체에 `setcap`을 부여하지 마세요.

## 진단과 한계

- DNS는 정상인데 HTTP 안내가 없으면 `Host` 요청과 포트 80·포털 포트, 수락된 정책 해시 및 DNS 주소 반환을 분리해서 확인합니다.
- DNS 재시작 중이나 상태 파일의 내용·해시가 불일치하면 안내 서비스는 **503으로 거부**합니다. `ALLOW`·미승인·비대상 Host는 임의 사이트로 프록시하지 않고 404입니다.
- HTTPS에서는 접속 오류가 발생할 수 있으며, 정적 안내 페이지의 94·72점은 실측 점수가 아닙니다.
- HTTP 요청에는 원래 목적지의 쿠키·인증 헤더가 실려 들어올 수 있습니다. 로그를 남기지 않아도 평문 HTTP 수신 자체는 민감정보 취급 행위이므로 허가된 랩에서만 사용합니다.
- 사용자별 정책·승인 예외·실제 신고 접수·TLS 인증서 처리는 미구현입니다. 시험 결과를 운영망에서 피해를 방지한 증거로 해석하지 마세요.

[기능 검증표](validation-matrix.md) · [코드: HTTP 서버](../apps/dns-agent/src/dns_agent/http_notice.py)
