# SKT ALEPH E조 Capstone — Protective DNS

**원격 서버에서 위협정보를 수집·검토·서명하고, 사설 DNS가 HTTPS로 받아 로컬에서 집행**합니다. DNS 질의마다 외부 API를 호출하지 않습니다. 코드·자동 시험과 실제 운영망 인수는 구분합니다.

| 구성 | 역할 |
|---|---|
| `apps/policy-server/` | OpenPhish → Safe Browsing 조회, 태양님 정책의 EXACT 위험 제안, 사람 승인 정책 생성·발행 |
| `apps/policy-sync/` | Ed25519·장치 ID·시퀀스·만료 검증, 비특권 HTTPS Pull과 별도 관리자 적용 |
| `apps/dns-agent/` · `infra/edge/` | 허용된 LAN 클라이언트의 기본 SUBTREE BLOCK → NXDOMAIN, 적용·만료·복구 |
| `apps/warning-portal/` | 독립 안내 화면. 선택형 **평문 HTTP 실습**은 별도 응답 방식이며 HTTPS 해결책이 아님 |


## 설치·운영 인수

원격 정책 서버, 사설 DNS 노드, 독립 서명자의 역할·최초 설치·기존 설치 코드 업그레이드·오프라인 서명/발행·실제 LAN 인수 검사 절차는 [운영 설치 및 인수 가이드](docs/production-install-and-validation.md)에 정리했습니다. 별도 장치 키와 분리된 보고 경로는 기존 서명 정책을 변경하지 않습니다.

## 노드 관제 상태 보고

사설 DNS는 기존 서명 정책을 HTTPS로 가져오는 Pull 방식을 유지하며, 루트 로컬 attestation 결과를 별도 **장치 서명키로 서명해 비특권 HTTPS Push**하는 선택형 상태 보고 경로를 추가합니다. 관제 페이지에 사설 DNS IP와 장치 키 지문을 등록하고, 게시 시퀀스 및 정책 SHA-256과 실제 DNS 노드의 적용 기록·로컬 UDP/TCP 응답을 비교합니다. 자동 승인·서명·원격 DNS 관리자 호출은 없습니다. [설계·설치·운영 가이드](docs/dns-node-telemetry.md).

- **노드 상태 보고**: 장치별 별도 Ed25519 서명, 비특권 HTTPS 송신, 보고 시각·재생 공격 방지. 독립 상위 DNS에서 양성 A 응답이 확인되지 않은 NXDOMAIN은 차단 성공으로 판정하지 않으며 LAN 실제 적용은 별도 인수 대상입니다.

## 운영자 관제 GUI

`policy_server.console`은 로컬 전용 인증형 대시보드입니다. 검증 후보 검토, 블랙리스트 정책 초안 생성, EXACT 제안 엔진 설정, 서명된 게시 정책 조회 및 감사 기록을 제공합니다. 실제 정책 생성기와 서명 검증기를 재사용하며 **서명·발행·DNS 적용은 분리**합니다. [설치 및 제한 사항](apps/policy-server/CONSOLE.md)을 참고하세요.

## 설치·사용

Linux/systemd와 Python 3.11+가 필요합니다. DNS 서버에는 `dnsmasq-base dnsutils nftables iproute2 python3-cryptography`, 원격 서버에는 `python3-cryptography nginx`를 준비합니다. 두 서버는 **같은 검토된 커밋**을 사용하세요.

```bash
# 저장소 루트. 설치기는 기본 미리보기이며 --apply가 있어야 시스템을 변경합니다.
bash scripts/deploy/install-policy-server.sh --help
bash scripts/deploy/install-dns-server.sh --help
export PYTHONPATH="$PWD/apps/policy-server/src:$PWD/apps/policy-sync/src:$PWD/apps/dns-agent/src"
python3 -m policy_server --help
python3 -m policy_server.intel --help
```

**`refresh` → 분리된 리뷰 사본 검토 → `build` → 서명 → `promote --apply` → DNS fetch/apply** 순서입니다. 키·TLS·서버별 명령과 변경 인수는 [설치·운영 가이드](docs/remote-policy-deployment.md)를 따릅니다. DHCP·호스트 기본 DNS·TLS 인증서를 자동 변경하지 않습니다.

승인은 전체 증거·만료·위협 유형·출처·SUBTREE 범위에 결합됩니다. 구형 리뷰는 재생성·재검토해야 하며, 해시는 승인자 인증을 대신하지 않습니다. 수집 계정과 리뷰·서명 권한을 분리하세요.

## 갱신·복구의 안전 경계

- 서명키 교체는 운영자가 신뢰 공개키를 배포한 뒤 수행합니다. 이전 키가 폐기된 캐시는 새 다운로드를 막지 않지만, **새 파일은 현재 신뢰 키로 다시 검증**합니다. 시퀀스 기록은 지우지 않습니다.
- HTTP 캐시 메타데이터가 없거나 형식이 손상되면 조건부 요청 없이 다시 받습니다. 그때도 **현재 검증 가능한 서명 정책의 시퀀스는 유지**합니다. 파일 소유권·심볼릭 링크 등 안전성 오류는 자동 복구하지 않습니다.
- HTTP `304 Not Modified`도 서명·만료를 다시 검사합니다. HTTP 캐시가 정책 유효기간이나 신뢰를 연장하지 않습니다.
- 원격 게시파일과 root 완료 영수증이 모두 일치하면, 옛 서명키가 폐기된 뒤에도 남은 **정리 작업만** 재시도할 수 있습니다. 파일 재게시·서명 신뢰 복구·만료 연장은 하지 않습니다. 완료 영수증이 없다면 현행 서명 검증이 필요합니다.
- 발행·적용 저널은 확인 가능한 상태에서만 정리합니다. 미완료 DNS 정책과 직전 정책이 모두 만료돼 실제 상태를 확인할 수 없으면 자동 진행하지 않습니다. **복구 기록을 지우거나 만료를 연장해 우회하지 마세요.**
- 활성 차단 제거·만료 단축은 `--ack-withdrawals`, 서명자 변경은 `--ack-key-rotation`이 필요합니다.

## 검증

```bash
python3 -m unittest discover -s tests/intel -v
python3 -m unittest discover -s tests/policy_server -v
python3 -m unittest discover -s tests/policy_sync -v
REQUIRE_DNSMASQ=1 python3 -m unittest discover -s apps/dns-agent/tests -v
```

root 발행 시험과 비특권 다운로드 시험은 서로 다른 계정에서 실행해야 합니다. CI가 양쪽 경로를 검사하며, 건너뛴 시험을 통과로 세지 않습니다. 실제 Google 자격증명·HTTPS·LAN 전체 배포와 패키지 설치 중 장애 복구는 별도 인수 대상입니다.

**제한:** 자동 승인·자동 서명·AI 점수 산출·원격 승인 API/DB는 없습니다. URL 위협을 도메인 전체 악성으로 자동 승격하지 않습니다. CNAME 응답 체인·DoH·VPN·IPv6·기존 캐시는 별도 검증 대상입니다. 후보 수집 주기와 짧은 정책 수명 때문에 수동 검토·서명만으로 상시 보호를 보장하지 않습니다.

[아키텍처](docs/architecture.md) · [DNS 설치/업그레이드](infra/edge/README.md) · [검토 결과](docs/review/remote-policy-audit-20261030.md) · [복구 경계 재검토](docs/review/recovery-boundaries-20261030.md) · [위협 모델](docs/threat-model.md)

### GUI 위협정보 갱신 (선택 설치)

기존 OpenPhish Community → Google Safe Browsing v5 수집 엔진을 전용 비특권 Unix 소켓으로 GUI 위협 검토 메뉴에 연결합니다. 웹 콘솔에는 API 키를 제공하지 않습니다. GUI 갱신 요청은 OpenPhish·GSB 사용 조건 확인과 5분 요청 간격 제한을 거치며, 성공한 새 증거는 별도 확인을 거쳐 기존 검토 기록을 비공개 백업하고 **모두 미승인**으로 가져옵니다. 독립 서명·root 발행·DNS 적용 단계는 자동화하지 않습니다. 원격 정책 서버에서 `scripts/deploy/install-intel-refresh-bridge.sh`를 사용하세요. 상세한 권한·설치는 [콘솔 운영 문서](apps/policy-server/CONSOLE.md)를 참조하세요.
