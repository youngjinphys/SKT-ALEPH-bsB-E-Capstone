# SKT ALEPH E조 Capstone — Protective DNS

**원격 서버에서 위협정보를 수집·검토·서명하고, 사설 DNS가 HTTPS로 받아 로컬에서 집행**합니다. DNS 질의마다 외부 API를 호출하지 않습니다. 코드·자동 시험과 실제 운영망 인수는 구분합니다.

| 구성 | 역할 |
|---|---|
| `apps/policy-server/` | OpenPhish → Safe Browsing 조회, 태양님 정책의 EXACT 위험 제안, 사람 승인 정책 생성·발행 |
| `apps/policy-sync/` | Ed25519·장치 ID·시퀀스·만료 검증, 비특권 HTTPS Pull과 별도 관리자 적용 |
| `apps/dns-agent/` · `infra/edge/` | 허용된 LAN 클라이언트의 기본 SUBTREE BLOCK → NXDOMAIN, 적용·만료·복구 |
| `apps/warning-portal/` | 독립 안내 화면. 선택형 **평문 HTTP 실습**은 별도 응답 방식이며 HTTPS 해결책이 아님 |

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
