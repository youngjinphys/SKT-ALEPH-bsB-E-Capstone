# DNS 관제·배포 운영 심층 검토 — 2026-11-03

## 검토 범위와 증거 등급

기준: `youngjinphys/SKT-ALEPH-bsB-E-Capstone`의 최신 `main`. 다른 브랜치는 비교 대상으로만 읽고, 코드 변경은 `main`에서 단일 Git 트리로 구성한다.

- 정책 생성기 `intel.build_policy`: 사람이 검증한 최신 증거만 SUBTREE BLOCK 초안으로 생성
- `aleph_policy_sync`: Ed25519 서명, 장치/시퀀스/만료, HTTPS Pull, root DNS apply 및 로컬 attest
- `telemetry.py`: **별도** 장치 키 서명, 로컬 UDP/TCP 검증, 독립 upstream 양성 확인, 비특권 HTTPS 발행
- `nodes.py`: 장치 등록, 고정된 신뢰 공개키, 서명·시각·시퀀스 검증, 수신·로컬 게시 정책 SHA-256 비교
- `console.py`·프런트엔드: 단계별 상태 설명, 승인/초안, 등록 노드, 실패 상태, 인증/Origin/Host
- 운영 설치기·CI·문서: 최초 설치와 기존 설치 구분, 실제 Linux 서버 적용 절차 및 rollback

## 주요 발견과 조치

| 위험/불일치 | 실패 조건 | 보수적 조치 |
|---|---|---|
| 서로 다른 콘솔 프로세스의 쓰기 경쟁 | 동일 장치 등록/폐기/보고가 동시에 저장되어 최근 보고를 덮어씀 | root 정책 변경과 분리된 OS 파일 잠금(`fcntl.flock`), 원자적 JSON 교체 |
| 폐기·재등록 키의 상태 재사용 | 키를 제거한 뒤 같은 Ed25519 키를 재등록하면 기존의 최근 서명 보고가 현재 보고로 오해될 수 있음 | registry format 2에 폐기 키 fingerprint를 영속 기록하고 같은 키의 재등록을 거부; 새 키 필요 |
| 장치 키 회전 직후 잘못된 경보 | 기존 파일의 옛 서명 키가 새 등록 키와 달라 `INVALID_REPORT`가 표시됨 | `REKEY_PENDING`로 격리, 새 키로 검증된 보고 전까지 성공 불가 |
| 전체 관제 개요의 단일 실패 | 검증 자료·노드 registry·미서명 초안 중 하나가 손상돼 모든 상태 조회가 실패 | 세 구역 독립 오류 경계, 미확인=null, 데이터가 없다는 0과 구분 |
| 설치 재실행/업그레이드 충돌 | 신규 설치기의 `--apply`는 기존 /opt 경로를 안전하게 거부 | 별도 role 지정 코드 업그레이드, 사전 owner/file 검사, 서비스 중지 확인, stage 교체, 롤백 백업 |
| 잘못된 차단 성공 판단 | 로컬 DNS NXDOMAIN이 원래 없는 이름이거나 외부 상위 DNS의 차단 결과 | 독립 upstream의 A 양성 응답 확인이 없는 경우 `LOCAL_DNS_VERIFIED`를 주장하지 않음 |
| 보고서 시간·재생 | 서명돼도 오래되거나 미래의 보고가 살아 있는 것처럼 보임 | 유효 기간, 수신 시각, 시퀀스, 서명키·장치 identity 검증 |
| LAN 전체 보호 과장 | DNS 노드에서만 성공했는데 모든 단말 보호로 오인 | 로컬 attestation, 상위 DNS 비교, LAN 별도 관측을 명확히 분리 |

## 브랜치 수렴

비교 대상은 `audit/console-ops-hardening`, `feat/dns-operations-console`, `feat/dns-report-reference-verification`, `feat/dns-signed-status-reporting`, `refactor/dns-ops-audit-theme`이다. 모두 `main`에 없는 고유 파일이 없고, 마지막 수렴 단계의 보안/관제 기능은 최신 `main` 트리에 포함됐다. 기존 브랜치가 깔끔하게 main의 조상이 아닌 이유는 이전 변경이 squash/이력 재작성으로 단일 커밋에 정리됐기 때문이다. 2026-11-03 최종 검증에서 5개 브랜치는 모두 main에 없는 고유 파일이 없고, 기존 구현은 main의 후속 수정에 흡수됐음을 확인했다. GitHub Actions의 일회성 SHA-pinned cleanup job이 `audit/console-ops-hardening`, `feat/dns-operations-console`, `feat/dns-report-reference-verification`, `feat/dns-signed-status-reporting`, `refactor/dns-ops-audit-theme`를 삭제했고, GitHub REST 브랜치 재조회 결과 **`main`만 남았다**. 같은 job이 재사용되지 않도록 임시 워크플로를 뒤이어 제거한다.

## 반드시 남겨 둘 안전 경계

1. 웹 콘솔과 위협 수집기는 서명 개인키 및 DNS root 명령에 접근할 수 없다. 상태 보고자의 별도 개인키도 로컬 DNS 노드 root 소유다.
2. 서명된 상태 영수증은 키가 유출된 악성 노드 또는 전체 운영 체제 침해를 탐지하는 TPM/원격 무결성 attestation이 아니다.
3. 정책 서버의 서명 게시물은 DNS 노드 적용 증거가 아니다. 노드 적용 기록과 실제 resolver 검증 후 별도의 표시가 필요하다.
4. 로컬 DNS의 독립 upstream 양성 비교도 **LAN 여러 클라이언트가 해당 DNS를 사용한다는 증거가 아니다**. 별도 LAN 관측, router/DHCP/IPv6, DNS 캐시/DoH/VPN 검증은 현장 인수 과제다.
5. GSB 증거와 발행 정책의 짧은 TTL, 수동 검토·별도 서명 때문에 지속적인 자동 차단을 보장하지 않는다.
6. 인증용 브라우저 단일 토큰·로컬 JSON 작업 이력은 개인별 RBAC/SSO 및 변조 방지 감사 로그를 대체하지 않는다.
7. 코드 검증과 CI 성공은 실제 Ubuntu 서버 설치, NGINX TLS 인증서, VLAN·방화벽, 외부 DNS 응답 및 장애 복구를 보증하지 않는다.

## 검증과 설치

`tests/policy_server/test_nodes.py`에서 장치 서명·회전·폐기 키·수신 순서·파일 잠금·stale clock·reference 검사 경계를 확인한다. `tests/policy_server/test_console.py`에서 비공개 증거 손상, 노드 상태 손상, 초안 오류 시 개요가 다른 정보를 보존하는지 점검한다. `tests/policy_server/test_installers.py`와 GitHub Actions에서 최초 설치기의 드라이런 및 업그레이드 스크립트의 구문과 보호 장치를 점검한다.

실제 최초 설치·기존 코드 업그레이드·정책 키·장치 보고 키·NGINX/vhost·systemd 서비스·LAN 질의 검증 절차는 [운영 설치 및 인수](../production-install-and-validation.md)에 정리했다. 실운영 장치에서 root 유지보수 및 장애 복구 검증을 수행하기 전에는 본 작업을 현장 배포 완료로 기록해서는 안 된다.

## 배포 런타임 일치성 개선

관제/노드 telemetry 신규 설치기의 기존 설치 버전 판단은 파일 존재 검사만으로 불충분하다. 설치 시점에 현재 체크아웃과 `/opt/aleph-policy-code`의 각 Python/JSON 런타임 파일을 SHA-256으로 대조하고, 여분 코드·심볼릭 링크·쓰기 가능한 디렉터리·다중 하드링크를 거부하도록 했다. `upgrade-policy-runtime.sh`도 스테이징 트리를 활성화하기 전에 동일성 확인을 수행한다. 관련 비특권/격리 root CI 경로를 검증한다.

**판단 경계:** 런타임 내용 일치가 서명된 Git 커밋 출처를 증명하지는 않는다. 신규 설치뿐 아니라 기존 설치의 실제 서비스 중지·재부팅·DNS 53 응답·NGINX TLS·방화벽·키 회수 동작은 현장 검증이 필요하다.
