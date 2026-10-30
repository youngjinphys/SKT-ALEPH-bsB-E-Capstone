# 원격 정책 서버

OpenPhish 공개 URL 후보를 Google Safe Browsing v5로 조회해 **비공개 데이터셋과 미승인 검토 템플릿**을 만듭니다. 검토 후 전체 정책을 생성하고, 별도 비특권 서명자가 서명한 결과만 root 발행기가 HTTPS에 게시합니다. 의심 사이트에 직접 접속하지 않습니다.

| 모듈 | 책임 |
|---|---|
| `policy_server.intel` | 후보·API 응답 검증, Google 조회, 검토 템플릿, 승인 정책 컴파일 |
| `policy_server.engine` · `data_adapter` | 태양님 정책 기반 EXACT 위험 점수 제안; DNS 자동 집행 없음 |
| `policy_server.__main__` | 동시 수집 잠금, 비공개 데이터셋 저장, 공통 명령 진입점 |
| `policy_server.promote` | 서명·장치·시퀀스·만료·철회 검사 및 원자적 발행 |

저장소 루트에서:

```bash
export PYTHONPATH="$PWD/apps/policy-server/src:$PWD/apps/dns-agent/src:$PWD/apps/policy-sync/src"
python3 -m policy_server --help
python3 -m policy_server.intel --help
python3 -m unittest discover -s tests/intel -v
python3 -m unittest discover -s tests/policy_server -v
```

운영 순서는 **`refresh` → 사람이 리뷰 파일 편집 → `build` → `aleph_policy_sync sign` → `promote`**입니다. 설치 후 갱신은 `sudo systemctl start aleph-policy-refresh.service`로 실행합니다. 상태는 `/var/lib/aleph-policy-server/latest.json`, 비공개 결과는 `runs/<run-id>/`에 저장됩니다. 전체 입력을 검증한 뒤 API를 호출하며, 수집 중복·손상 입력·API 실패는 새 정책 발행으로 이어지지 않습니다.

[서버별 설치·검토·서명·발행 가이드](../../docs/remote-policy-deployment.md)를 참조하세요. [OpenPhish](https://openphish.com/terms.html)와 [Google Safe Browsing](https://developers.google.com/safe-browsing/terms)의 사용·출처 표시·데이터 처리 조건을 확인해야 합니다. Google에는 공개 후보 URL을 보내며 개인 DNS 질의·방문 기록은 보내지 않습니다.

**제한:** 점수의 source allowlist는 발신자 인증을 대신하지 않습니다. 숫자 점수를 생성하는 모델과 신뢰된 전송 경로는 별도입니다. URL 증거를 도메인 전체 차단으로 자동 승격하거나 운영 정책을 자동 승인·서명하지 않습니다. 원격 검토 API/DB, 운영 TLS 설정, 실제 LAN 배포 검증은 포함하지 않습니다.
