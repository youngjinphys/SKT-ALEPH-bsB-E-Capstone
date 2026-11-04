# SKT ALEPH E조 · Protective DNS 캡스톤

검토한 위협정보를 승인 가능한 정책으로 만들고 DNS에서 집행·철회하는 흐름을 설명하는 Next.js·TypeScript 발표 사이트입니다. **표지 포함 14장·20분 단일 발표**입니다. 관리형 네트워크를 적용 대상으로 삼고, 기존 브라우저 보호에 더할 효과는 후속 비교 평가로 남깁니다.

[최종 발표 시나리오](docs/presentation/final-20min-scenario.md)에는 화면별 발화·조작·전환 문장과 예상 질문 답변이 있습니다. [콘텐츠 검토 기록](docs/CAPSTONE-CONTENT-REVIEW.md)에서 수정 이유와 근거 범위를 확인할 수 있습니다.

## 실행과 검증

Node.js 24.x 환경에서 통합 저장소의 `apps/web` 디렉터리 기준:

```bash
npm ci
npm run content:check
npm run typecheck
npm run build
```

개발 서버는 `npm run dev`, 프로덕션은 `npm run start`입니다. 기존 CI는 콘텐츠 정합성·타입 검사·프로덕션 빌드를 수행합니다. 콘텐츠 검사는 14장 순서, 1,200초 배분, 발표자 노트와 최종 시나리오의 본문 일치를 검증합니다.

프로덕션 웹 화면 우측 하단의 `Updated at`은 빌드 서버가 `next build`를 시작할 때 기록한 UTC 시각입니다. `next.config.ts`의 production-build 단계에서 한 번 기록하고 컴파일 결과에 고정하므로 새로고침·서버 재시작·방문자의 시간대에 따라 바뀌지 않습니다. 캐시된 빌드를 다시 배포하면 원래 빌드 시각을 유지하며, 실제 배포 완료 시각이나 Python 관제 서비스의 갱신 시각을 뜻하지 않습니다. 개발 모드에는 표시하지 않습니다. 회귀 검사는 저장소 루트에서 `node --test tests/browser/build_timestamp.test.mjs`와 프로덕션 빌드 후 `python3 -B tests/browser/build_timestamp.py`로 실행합니다.

## 페이지와 발표 조작

- `/`: 프로젝트 홈
- `/capstone`: 14장 발표·참조·발표자 노트
- `/capstone/references`: 활성 화면의 전체 출처와 최종 원고의 Q&A를 연결한 별도 참조 페이지. 발표 순서·시간에는 추가하지 않습니다.
- `/fishing`: 개인정보를 수집하지 않는 모의 사이트
- `/app`: 서버에서 접근 권한을 검증하는 연구실
- `/dashboard`: 같은 배포의 Python 클라우드 관제. 구성·권한은 [통합 운영 문서](../../docs/unified-vercel-dashboard.md) 참조

좌우 방향키(`←/→`)·목차·장 선택·터치 스와이프·선택형 박수 제어로 이동합니다. 위아래 방향키와 PageUp/Down·Space·Home/End는 스크롤 등 브라우저 기본 동작을 유지하며, 이전·다음 화살표 버튼과 발표 타이머는 없습니다. 시나리오·단계·측정 조건·요점/도식·HTTP/HTTPS·EDE/SDE는 모두 선택 상태를 알리는 일반 버튼입니다. 클릭 또는 Enter/Space로 내용을 선택한 뒤에도 좌우 방향키로 슬라이드를 이동합니다. 버튼 간 이동은 Tab/Shift+Tab을 사용하며 포커스를 강제로 해제하지 않습니다. 입력란·탭·슬라이더처럼 방향키를 사용하는 위젯에 포커스가 있거나 목차·노트가 열려 있으면 슬라이드를 넘기지 않습니다. `O/N/F/M/R/D`는 목차·노트·전체 화면·모션·재생·사례 선택에 사용합니다.

통합 CI는 기존 Python Playwright 환경에서 `python3 -B tests/browser/presentation_keyboard.py`로 좌우 이동·빠른 연속 입력·처음/끝 경계·히스토리·모달·입력란·모바일 보기 선택의 키보드 회귀를 검사합니다. 저장소 루트에서 실행하며 `apps/web`의 프로덕션 빌드가 먼저 필요합니다. 같은 실행에서 `presentation_controls.py`가 14장 전체의 실제 표시 선택, 클릭 후 좌우 이동, 선택 상태와 포커스, 데스크톱·모바일·전체 보기 조합을 검사합니다.

OAuth/보안 설정은 `.env.example`과 [보안 문서](docs/CAPSTONE-SECURITY.md)를 따릅니다.

## 콘텐츠의 정본

| 위치 | 역할 |
| --- | --- |
| `capstone/data/slides/*.json` | 23개 저작 기록 중 14개 발표·9개 아카이브. `notes`가 화면별 대본의 정본 |
| `capstone/data/sequence.json` | 14장 순서와 20분 시간 배분 |
| `docs/presentation/final-20min-scenario.md` | 같은 노트를 포함한 최종 원고·리허설 계획·Q&A |
| `capstone/data/diagrams.json` | 승인·집행·철회와 DNS·HTTP의 설명용 시각화 |
| `capstone/data/dns-latency.json` | 원시 CSV에서 재계산한 분위수와 측정 조건 |
| `capstone/data/sources.json` | 공식 출처, 현재 코드와 과거 실험의 고정 참조 |
| `src/lib/deck.server.ts` | 서버 전용 JSON 결합·검증 |
| `src/components/SlideDeck.tsx` | 목차·노트·터치·박수 제어 |

화면 주소는 `/capstone#0`부터 `#13`이며, `#dns`, `#bypass` 같은 안정적인 ID 해시도 지원합니다. 아카이브 ID는 공개 발표에 포함하지 않습니다.

## 근거의 범위

- **외부 배경:** APWG의 보고 기반 피싱 사이트 관측과 Okta의 AI 웹 빌더 악용 사례를 사용합니다. 전화금융사기 전체 피해액은 DNS가 다루는 웹 피싱의 분모와 달라 본편에서 제외했습니다.
- **현재 코드:** 캡스톤 `6bf8ccac`에서 운영자 관제, 갱신·검토·초안, 독립 서명·게시, DNS 수신·적용·노드 보고를 확인했습니다. 수동 위험점수와 자동 집행을 구분합니다. 통합 HEAD `9e84275`에서 코어가 동일함을 확인했고, 클라우드 검증 자료 가져오기·외부 서명 정책 게시 경로도 반영했습니다. 클라우드 자동 수집은 미구성입니다.
- **기능 기록:** `397df3f4`의 2026-10-31 합성 DNS **240/240 기대 응답 일치**입니다. CNAME 공백·SUBTREE 과차단 재현을 포함한 과거 기능 실험이며, 실위협 탐지율이나 현재 HEAD의 재실행 결과가 아닙니다.
- **Pi 기록:** 2026-11-03 CSV의 446행 중 준비·자가시험 6행을 제외한 440행입니다. 제품 :53은 로컬 캐시가 꺼져 있고 측정 당시 활성 차단 줄이 없었습니다. 임시 :55353 캐시 실험을 별도로 표시합니다. p50/p95는 선형보간입니다.
- **DNS 계약:** 현재 집행은 SUBTREE이며 EXACT 입력을 자동 확대하지 않습니다. 만료된 BLOCK을 정리하는 동작과 잘못된 갱신을 거부하는 동작을 구분합니다.
- **후속 검증:** 독립 정답셋의 추가 차단·정상 서비스 영향, 정책 게시부터 실단말 복구까지의 시간, 같은 Pi에서 정책 적용 전후·부하별 성능을 비교합니다.

화면 애니메이션은 설명용입니다. HTTPS의 새 이름 조회를 차단하는 것과 제3자 안내 페이지로 전환하는 것은 다릅니다. EDE 사유 전달과 클라이언트 표시, 참여 ISP 운영은 별도 구현·협력 과제입니다.

### Diagram text handoffs

Changing DNS labels and stage captions use `DiagramText`: authored variants share
one grid cell and crossfade for 320 ms, keeping the largest wrapped label's space.
Only the current variant is exposed to assistive technology. Replay/rapid selection
reverse the CSS transition without delayed state or extra timers. OS reduced motion,
the deck's motion toggle, and paused slide content disable the fade immediately.
`tests/browser/presentation_motion.py` runs with the existing presentation browser
check and covers the timed DNS rename, scenario reversals, stable geometry, stage
captions, and reduced-motion/mobile behavior.
