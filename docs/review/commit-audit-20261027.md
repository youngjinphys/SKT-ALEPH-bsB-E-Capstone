# DNS 코드·이력 검증 (2026-10-28)

이 문서는 GitHub `main`의 DNS 구현·설치 경계와 테스트 근거를 정리합니다. **자동 시험·격리 VM 관측은 운영망 안전성이나 탐지율의 증명이 아닙니다.**

## 단일 DNS 커밋과 원자료

`Frontend`(`4c60d486bb32246d662c7672ea45325c3aa73205`) 다음의 작업을 하나의 `DNS` 커밋으로 압축했습니다. `main`의 도달 가능한 순서는 `first commit → Baseline → Frontend → DNS`입니다. 압축 대상은 다음 다섯 개의 과거 커밋입니다.

| 이전 SHA | 작업 내용 |
| --- | --- |
| `bd190b802e06d8752800bf091dea9ecf56bc9021` | DNS 격리·LAN 서비스, 합성 정책·기본 실험 |
| `b47d7bbbc651ac446bd4d97d68570725af2504c4` | 재시작/손상 정책 복구와 배포 작업 잠금 |
| `e94665fc1020e8af47afa883fc56caa81f230fc7` | nftables 테이블 식별·검사·조건부 삭제 |
| `f770f365c0c63b556d9f29be25f20217a39cca67` | 코드·저널·서비스의 소유권 및 수명주기 강화 |
| `d986a20fba665a0a05904a8c4cb536dd7e2d8eae` | 레거시 설치 백업 검증·마이그레이션 |

압축 직전 HEAD는 `d986a20fba665a0a05904a8c4cb536dd7e2d8eae`, 최종 코드 트리는 `c47b0cedcefe83f06ad5c15195ef7ae659021732`였습니다. 압축은 **원래 HEAD의 전체 코드·시험·이진 증빙 파일을 보존**하고 이 문서의 과거 커밋 수·이력 보존 문구만 현재 상태에 맞게 수정한 것입니다. 위 다섯 SHA는 역사적 원자료 표지이며 압축 후 `main` 경로에서는 도달하지 않습니다. 협업자의 기존 클론은 이력 재작성 사실을 확인하고 동기화해야 합니다.

## 실제 실행 경계

- 기본 개발 모드: Python 3.11+, Linux, 일반 사용자, `python3 -m dns_agent run`, loopback `127.0.0.1:35353`. 서비스 설정을 수정하지 않습니다.
- 시스템 설치: `infra/edge/system_dns.py install`은 기본 미리보기이며, 실제 변경은 환경 확인 뒤 관리자 권한과 명시적 `--apply`로만 수행합니다. 사설 IPv4 포트 53, 전용 systemd 계정·nftables 리소스를 생성합니다. 원래 DHCP와 호스트 `resolv.conf`는 도구가 바꾸지 않습니다.
- 기존 설치 전환: `upgrade --apply`는 가동 중 서비스 중단·백업·검증이 수반됩니다. 인수되지 않은 운영 장비에 바로 실행하지 않습니다.
- 합성 캠페인·HTTP 302 시연·정적 안내 포털은 별도 기능입니다. 원격 IOC 승인/서명, AI 탐지 모델, 브라우저 HTTPS 자동 안내·신고 접수 API는 아직 연결되지 않았습니다.

명령과 선행 조건은 [루트 README](../../README.md), [DNS 에이전트](../../apps/dns-agent/README.md), [Linux 설치·복구](../../infra/edge/README.md)를 기준으로 삼습니다.

## 실행한 CI와 보존된 VM 증거

- 압축 전 HEAD `d986a20`의 [DNS workflow](https://github.com/youngjinphys/SKT-ALEPH-bsB-E-Capstone/actions/runs/40496118719): DNS 시험 **68개**, 합성 캠페인 **10개**, 설치기 시험 **79개 중 75개 실행·4개 skip**, 별도 root 네트워크 네임스페이스 방화벽 시험 **8개**, 정적 포털 **6개**, HTTP 비교 **9개** 성공.
- 같은 소스에서 [기본 저장소 검사](https://github.com/youngjinphys/SKT-ALEPH-bsB-E-Capstone/actions/runs/40496118907) 성공.
- [nftables 격리 VM 증빙](nft-vm-validation.md)과 [기존 설치 마이그레이션 VM 증빙](legacy-migration-vm-validation.md)은 각 문서에 명시한 파일 SHA-256·환경·시험 조건의 증거입니다. 테스트하지 않은 새로운 버전이나 운영 LAN의 품질을 입증하지 않습니다.
- **압축 후 새 `DNS` SHA의 CI를 별도 확인해야 합니다.** 이전 성공 로그를 새 SHA의 실제 실행 결과로 바꿔 적지 않습니다. 검토 기준은 [Actions](https://github.com/youngjinphys/SKT-ALEPH-bsB-E-Capstone/actions)에서 해당 커밋과 실행 로그의 SHA가 일치하는지 여부입니다.

## 남은 위험과 후속 검증

1. QNAME의 `SUBTREE` 차단은 CNAME·HTTPS/SVCB 응답 체인 전체 보호가 아닙니다. 외부 DoH/DoT·VPN, 직접 IP, 기존 캐시와 IPv6 클라이언트 DNS는 별도입니다.
2. nftables 소유권·규칙셋 세대 검증은 **설치·확인·제거 시점** 기준입니다. 외부 관리자가 실행 중 테이블을 제거할 때 계속 감시해 자동 복구하는 보장은 없습니다.
3. 재시작·전원 손실·정책 갱신 직후의 통신 중단시간, 다른 방화벽·DNS 서비스와의 공존, 물리 LAN 다중 클라이언트는 운영 환경과 동일한 허가된 격리 VM/실습망에서 계측해야 합니다.
4. 과거 마이그레이션 시험에는 초기 설치에 실패해 VM 전용 보정으로 재현한 사례와 SIGKILL 후 DNS 중단 상태가 있습니다. 관련 제한은 증빙 문서에 그대로 남깁니다.
5. `.test`의 기본 NXDOMAIN은 차단 성공의 독립 증거가 아닙니다. **정상 양성 응답을 먼저 제공한 통제 업스트림**과 적용 후 응답을 비교합니다.
6. DNS 정책 집행 시험과 실세계 피싱 분류 정확도·AI 프로젝트 평가 요건은 별개의 검증입니다.

운영 DNS로 전환하기 전에는 소스 SHA, 실제 인터페이스·호스트·업스트림, 백업·복구 수단, 정책 계약과 사람의 인수 상태를 확인하세요.
