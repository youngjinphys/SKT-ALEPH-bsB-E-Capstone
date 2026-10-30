# 아키텍처

## 확인된 구현

```text
검토된 JSON → DNS 에이전트 → 기본 모드: BLOCK=NXDOMAIN, WARN/ALLOW=비차단
                                     └→ 실습 명시 동의: BLOCK/WARN A=안내 IP
DNS가 수락한 상태·활성 설정 → HTTP 안내 서버 → 302 → 기존 정적 BLOCK/WARN 포털
                                    (고포트 격리 실습, HTTPS 미지원)
```

| 경계 | 책임 |
| --- | --- |
| `apps/dns-agent/` | 데이터 검사, 명시적 SUBTREE 규칙, 잠금·반영·만료·복구 |
| `apps/warning-portal/` | 안내와 미제출 신고 초안. 실제 정책 변경 권한 없음 |
| `packages/policy-contract/` | 현행 구현의 입력 형식. 검토되지 않은 과거 예시와 구분 |
| `dns_agent.http_notice` | 수락된 DNS 정책·설정의 해시 검사 후 평문 HTTP Host별 BLOCK/WARN 고정 302. URL/헤더를 목적지에 반영하지 않음 |
| `apps/policy-server/` | 오프라인 OpenPhish·GSB 수집·검토 초안 생성; 원격 DB·승인 API는 미구현 |
| `apps/policy-sync/` | 서명된 전체 정책 스냅샷의 HTTPS 수신, 공개키·버전·만료 검증, 별도 root 적용기 |
| `infra/edge/policy-sync/` | root 관리 HTTPS 정적 서버 및 fetch/apply용 systemd 구성 예시 |

## 구현 선택과 팀 결정의 구분

한 저장소·독립 배포는 사용자 요청입니다. dnsmasq 선택은 제출 코드와 검증 가능성을 고려한
이번 구현 선택입니다. **팀이 이를 운영 엔진으로 확정했다는 뜻은 아닙니다.**
Unbound/BIND 전환은 정확한 QNAME 규칙·CNAME 응답 검사·DNSSEC 요구가 확정된 뒤 비교합니다.
미검토 문서의 특정 엔진·점수 임계치·주말 일정·DB 필수 도입은 요구사항으로 승격하지 않습니다.

## 실제 LAN DNS 배포 모드

`infra/edge/system_dns.py install --apply`는 검토된 정책 파일과 dns_agent 모듈을 루트 관리 경로에 복사하고, 전용 비특권 계정·systemd·nftables ACL을 구성해 **지정된 RFC1918 IPv4:53에만** 서비스를 띄웁니다. UDP·TCP 53번을 모두 처리하며, 다른 DNS 서비스·서버의 기본 리졸버·DHCP를 자동 변경하지 않습니다. 허용 LAN 클라이언트는 명시된 `/24` 또는 더 작은 IPv4 대역으로 제한합니다. 설치 이전 검증과 설치 후 실제 클라이언트 시험은 별개입니다.

신규 설치 시 실패하면 이번 설치가 생성한 전용 리소스를 복구하며, 관리자 승인 아래 제거할 때는 정책·상태를 별도 보관합니다. 정책 게시자는 기존 게시 파일과 실행 중 정책의 발행 시각을 비교하고 에이전트의 수락을 확인합니다. **systemd·nftables 전체 동작은 실제 서버에서 별도 실증해야 합니다.**

[설치와 원복 절차](../infra/edge/README.md) · [서명·Pull·발행 절차](policy-distribution.md)

## 아직 연결되지 않은 부분

서명된 HTTPS 파일 Pull·인증 검증은 선택형 도구로 구현했지만 기본 관리형 LAN DNS에 아직 설치되지 않았습니다. 원격 승인 API/DB, 사용자별 차단 사유 식별, 경고 후 예외 승인, 오탐 신고 접수,
정상 HTTPS 배포, **실제 운영 LAN 배포·재부팅 검증**, AI 탐지 모델은 별도 작업입니다.
DNS 오류만으로 임의 HTTPS 탭을 안내 페이지로 바꿀 수 없습니다.
기본 DNS 차단은 계속 NXDOMAIN입니다. 격리 실습의 `--http-sink-ip` 모드를
명시적으로 설정하면 DNS A 주소와 정책 기반 HTTP 302가 연결되지만, 해당
기능은 **기존 관리형 LAN 설치기에 자동 통합되지 않았습니다**.
기존 설치를 임의로 수정해 활성화하지 마세요.
실습 중 HTTPS/HSTS 접속은 인증서/연결 오류가 발생할 수 있고 실제 신고도 접수하지 않습니다.
[HTTP 실습과 제한](http-notice.md)을 참조하세요.

[위협 모델](threat-model.md) · [DNS 검토](review/dns-audit.md)
