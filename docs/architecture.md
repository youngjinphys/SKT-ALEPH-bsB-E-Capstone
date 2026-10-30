# 아키텍처

## 원격 생성과 로컬 집행

```text
OpenPhish → policy_server.intel → Google Safe Browsing v5
                  ↓
비공개 후보·검증 데이터셋 → 사람이 검토 → policy_server build
                  ↓
별도 비특권 서명자 → Ed25519 서명 → root promote → HTTPS current.json
                  ↓
DNS 비특권 fetch → root 재검증·apply → dnsmasq → BLOCK=NXDOMAIN
```

`refresh`는 프로세스 간 잠금 안에서 후보 전체를 검증하고 API를 호출합니다. 입력 검증·API 호출 실패는 이전 성공 데이터셋을 덮어쓰지 않습니다. 승인 데이터는 도메인·URL 해시·검증 시각에 결합됩니다. 위협 조회의 부정 결과는 안전 인증이 아니며, UNKNOWN은 승인 정책으로 자동 변환하지 않습니다.

| 경계 | 책임 |
|---|---|
| `apps/policy-server/` | 공개 후보 수집·Google 조회, 태양님 정책 기반 위험 제안, 수동 검토 정책 컴파일·발행 |
| `apps/policy-sync/` | 공개키·장치·시퀀스·만료 검증, 비특권 HTTPS 수신과 root 적용 분리 |
| `apps/dns-agent/` | SUBTREE 계약 검사, dnsmasq 설정, 잠금·반영·만료·복구 |
| `packages/policy-contract/` | DNS 정책 JSON 스키마·예제·테스트 벡터 |
| `scripts/deploy/` | 두 서버의 별도 설치·systemd 서비스 및 HTTPS 배포 설정 생성 |
| `infra/edge/policy-sync/` | DNS fetch/apply 타이머 |
| `apps/warning-portal/` | 독립 안내 및 미제출 신고 초안; 정책 변경 권한 없음 |

수집기는 서명키를 가지지 않고, DNS는 Google/OpenPhish에 질의를 보내지 않습니다. `engine.py`의 EXACT 점수 제안은 SUBTREE로 자동 확대하지 않습니다. 서명은 발행자·전송 무결성을 검증할 뿐 위협 판정의 정확성을 보증하지 않습니다. 출처 목록과 데이터 스키마 역시 인증이나 오탐 검토를 대체하지 않습니다.

## LAN DNS

`install-dns-server.sh --apply`는 기존 `system_dns.py install`을 사용해 root 관리 코드·전용 계정·systemd·nftables ACL을 설치합니다. 지정된 RFC1918 IPv4:53의 UDP/TCP를 처리하고 허용 클라이언트는 명시된 `/24` 또는 더 작은 IPv4 대역으로 제한합니다. 다른 DNS 서비스, 서버 기본 리졸버, DHCP는 자동 변경하지 않습니다.

정책 수신과 적용은 별도 타이머이며 적용 전 서명·장치 ID·시퀀스·만료를 다시 확인합니다. 같은 서명 시퀀스를 다시 받아도 `system_dns.py attest`로 설치 정책·에이전트 상태·DNS 응답·방화벽 상태를 재확인합니다. 운영 정책은 전체 교체이며 활성 차단 규칙의 제거에는 명시적인 철회 승인이 필요합니다. 기존 DNS 설치기의 실패 복구·업그레이드·제거 절차는 [LAN 가이드](../infra/edge/README.md)를 따릅니다. 설치 스크립트 제공과 실제 systemd/nftables/LAN 배포 실증은 별개입니다.

## 선택형 HTTP 실습과 한계

기본 모드에서 BLOCK은 NXDOMAIN이고 WARN/ALLOW는 비차단입니다. 격리된 HTTP 실습에서는 수락된 DNS 정책·설정 해시를 확인한 뒤 A 레코드를 안내 IP로 보내고 HTTP Host별 고정 302로 정적 포털에 연결합니다. URL·헤더를 리디렉션 목적지에 삽입하지 않습니다.

이 기능은 관리형 LAN 설치에 자동으로 켜지지 않으며 임의 HTTPS 사이트의 인증서·HSTS 제약을 해결하지 않습니다. [HTTP 실습 가이드](http-notice.md)를 참조하세요. 원격 승인 API/DB, 사용자별 경고 예외·오탐 신고 접수, AI 탐지 모델은 미구현입니다. 실제 TLS·LAN·IPv6·재부팅·우회 검증은 운영 환경에서 별도로 필요합니다.

현재 엔진은 dnsmasq입니다. 정확한 QNAME 집행, CNAME 응답 검사, DNSSEC 요구가 달라지면 백엔드 선택을 재검토해야 합니다. 이는 팀의 최종 운영 엔진 결정과 구분합니다.

[배포 절차](remote-policy-deployment.md) · [위협 모델](threat-model.md) · [검증표](validation-matrix.md)
