# SKT ALEPH E조 Capstone — Protective DNS

**원격 정책 서버에서 위협정보를 수집·검토·서명하고, 사설 DNS에서 HTTPS로 받아 로컬 차단**합니다. DNS 질의마다 Google/OpenPhish API를 호출하지 않습니다.

| 구성 | 역할 |
|---|---|
| `apps/policy-server/` | OpenPhish → Safe Browsing v5 조회, 태양님 v0.8 기반 위험 제안, 승인 정책 생성·발행 |
| `apps/policy-sync/` | Ed25519 서명·장치 ID·시퀀스·만료 검증, HTTPS Pull |
| `apps/dns-agent/` · `infra/edge/` | 허가된 LAN 클라이언트의 BLOCK SUBTREE → NXDOMAIN, 만료·복구 |
| `apps/warning-portal/` | 독립 안내 화면과 선택형 평문 HTTP 실습 |

## 설치·사용

Linux/systemd와 Python 3.11+가 필요합니다. DNS 서버에는 `dnsmasq-base dnsutils nftables iproute2 python3-cryptography`, 원격 서버에는 `python3-cryptography nginx`를 설치합니다. 두 서버는 같은 검토된 커밋을 사용합니다.

```bash
# 저장소 루트에서 실행. 설치기는 기본 미리보기, --apply 지정 시에만 변경합니다.
bash scripts/deploy/install-policy-server.sh --help
bash scripts/deploy/install-dns-server.sh --help
export PYTHONPATH="$PWD/apps/policy-server/src:$PWD/apps/policy-sync/src:$PWD/apps/dns-agent/src"
python3 -m policy_server --help
python3 -m policy_server.intel --help
```

운영 순서: **`refresh` → 별도 리뷰 사본 검토 → `build` → `aleph_policy_sync sign` → `promote --apply` → DNS fetch/apply**. API 키·서명키 준비와 실제 서버별 명령은 [설치·운영 가이드](docs/remote-policy-deployment.md)에 있습니다. DHCP·호스트 기본 DNS·TLS 인증서는 자동 변경하지 않습니다.

승인 템플릿 **format 2**는 전체 증거·만료·위협 유형·출처·SUBTREE 범위를 묶습니다. 이전 미결합 템플릿은 **재생성 후 재검토**해야 합니다. 해시는 승인자 인증을 대신하지 않으므로 리뷰 파일은 수집 계정과 분리해 보관하고, 별도 서명자가 최종 권한을 통제합니다.

발행 중 중단되면 원본 서명 파일로 동일한 `promote --apply`를 재실행합니다. 완료된 동일 파일은 읽기 전용 성공이며, 변경된 동일 시퀀스는 거부합니다. 활성 차단 삭제·유효기간 단축은 `--ack-withdrawals`, 서명키 변경은 `--ack-key-rotation`이 필요합니다. 복구 기록을 임의 삭제하지 마세요.

## 검증

```bash
python3 -m unittest discover -s tests/intel -v
python3 -m unittest discover -s tests/policy_server -v
python3 -m unittest discover -s tests/policy_sync -v
REQUIRE_DNSMASQ=1 python3 -m unittest discover -s apps/dns-agent/tests -v
```

root 발행 시험과 비특권 수집 시험은 권한을 나누어 실행하며, CI에서 두 경로를 검사합니다. 실제 Google 계정·HTTPS·LAN 종단 간 검증과 운영 설치 중 장애 복구는 별도 실증 대상입니다.

**제한:** 자동 승인·자동 서명·AI 점수 산출·원격 승인 API/DB는 없습니다. URL 위협을 도메인 전체 악성으로 자동 승격하지 않습니다. DNS 차단은 HTTPS 리디렉션이 아니며, DoH·VPN·IPv6·기존 캐시 우회는 별도 검증 대상입니다. 12시간 후보 수집과 최대 15분 GSB 기반 BLOCK만으로 상시 보호를 보장하지 않습니다.

[아키텍처](docs/architecture.md) · [DNS/업그레이드](infra/edge/README.md) · [검토 결과](docs/review/remote-policy-audit-20261030.md) · [위협 모델](docs/threat-model.md)
