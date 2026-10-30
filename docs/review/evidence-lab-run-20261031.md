# 격리 DNS 정책 실험 감사 — 2026-10-31

## 검증한 코드와 재현 범위

이 저장소의 정책 서명·HTTPS 수신·DNS Agent/dnsmasq를 **비특권 로컬 루프백**에 연결한다. 기준 조상은 `bdb1abf813dcca443074f476bd23b0d3ece91e3d`이며, 결과는 언제나 실행 JSON의 소스 SHA·수정 여부·바이너리 버전과 해당 GitHub Actions 실행 커밋으로 판단한다. 최종 실험기 blob SHA는 `2aa3591`로 시작한다. 만료된 이력의 중간 커밋이나 과거 CI가 현재 `main`의 검증을 대신하지 않는다.

실험에는 각 실행마다 생성한 Ed25519 서명키·로컬 CA와 실제 TLS가 사용되며, 피싱 사이트·외부 위협 API·공용 DNS는 호출하지 않는다. 호스트 DNS, DHCP, nftables, systemd와 운영 장비는 변경하지 않는다.

## 독립 실험의 결과와 판정 경계

- DNS 에이전트 기존 시험 **79개 통과**, 응답 집계·실행 회귀 **9개 통과**. 정책 수신/적용과 root 테스트는 별도 시험이다.
- 3회 × upstream/기준선/차단/서명 철회 4상태 × 5개 합성 이름 × A/AAAA × UDP/TCP = **240개 질의 관측**. 최신 실행에서 **240/240 예상 결과 일치** 및 변조된 서명 스냅샷 수신 거부를 확인했다.
- 응답이 `NOERROR`인지만 보지 않고 기대 주소와 QNAME 또는 QNAME에서 도달 가능한 CNAME 체인의 **응답 소유자**를 확인한다. 무관한 소유자의 동일 주소가 있는 답변은 거부하며, 타임아웃·SERVFAIL은 차단 성공으로 세지 않는다.
- 정상 하위 도메인의 SUBTREE 과차단과 CNAME 별칭을 통한 보호 공백도 **기대대로 재현한 한계**이다. 240/240이 240건의 악성 탐지 성공이라는 뜻은 아니다.
- 응답 지연에는 `dig` 프로세스 생성 시간이 포함된다. 측정값은 성공한 로컬 fixture 질의에 한정하며 실패는 전체 시도 분모에 남긴다.

## 회귀 발견과 수정

1. 자식 Python DNS 프로세스에 소스 경로가 전달되지 않아 초기 실험이 실패했다. 격리 실행자의 `PYTHONPATH`를 명시하고, 외부 작업 디렉터리·환경변수 미설정 회귀시험을 추가했다.
2. 첫 실험 판정기는 기대 IP만 같으면 무관한 DNS 응답 소유자도 수락했다. QNAME/CNAME 소유자 검증과 양성·음성 회귀시험 2개를 추가했다. **이는 판정기 결함이지 실제 dnsmasq가 위조 응답을 보냈다는 증거가 아니다.**
3. 환경별 `/usr/bin/env`의 심볼릭 링크 여부와 사용자 namespace의 **nftables 변경 권한**을 검사하지 않으면 시험이 잘못 실패할 수 있다. root 프로그램은 실제로 신뢰 가능한 정규 파일인지 검사하며, nft 시험은 네임스페이스 내부 테이블 생성·삭제까지 사전 확인한다. 강제 CI 검사에서는 해당 권한 부재를 실패로 보고, 일반 환경에서는 건너뜀으로 명시한다.

## 재현

```bash
python3 -m unittest discover -s tests/evidence -v
python3 scripts/evidence_lab.py --rounds 3 --output /tmp/aleph-evidence.json
```

Linux 비특권 계정, `dnsmasq`·`dig`·Python `cryptography`가 필요하다. 출력 JSON은 기존 파일을 덮어쓰지 않는다. [자동 실험](../../.github/workflows/evidence.yml)은 GitHub의 정확한 커밋에서 반복 실행하고 실패 시에도 생성된 JSON을 출력한다.

**실험이 인증하지 않는 범위:** 운영 root `publish/attest`, 두 실제 서버·재부팅, 실제 LAN의 IPv4/IPv6, DoH·VPN·DNSSEC, 단말 캐시와 철회 지연 SLA, BIND RPZ와의 우위, 실제 오탐률·탐지율·피해 예방률, 인간 이의신청·철회 운영. 실험은 root 서비스를 우회하는 비특권 직접 Agent 어댑터이며, 추가 보호 효과를 주장하려면 [독립 평가 계획](independent-evaluation-20261031.md)의 조건별 비교가 필요하다.
