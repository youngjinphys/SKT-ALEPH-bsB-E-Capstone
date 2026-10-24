# 독립 HTTPS 경고 포털 — SKT ALEPH E조

> **구현 범위:** 정적 프론트엔드 3개 화면(안내 홈, BLOCK, WARN), 접근성·반응형·오탐 검토 초안 UI, 정적 배포 설정 및 검증 테스트. **DNS/정책 서버·실제 위험도 분석·오탐 접수 API는 아직 연결되지 않았습니다.**

## 원본과 의도

조유정 팀원의 `phishing-block.html`, `phishing-warning-continue.html`을 출발점으로 작업했습니다. 원본은 `originals/`에 **수정 없이 보존**했습니다. 차단(빨강)과 경고(주황), 위험 점수(각각 94/72 **시연 예시**), 권장 안전 행동, 계속 방문의 위험성, 오탐 신고라는 정보 구조를 유지했습니다. 가독성·명암·키보드 조작·모바일 대응을 개선했고, 공통 CSS/JS로 중복을 줄였습니다.

### 페이지

| URL | 설명 |
| --- | --- |
| `/index.html` | 프로젝트 안내 및 BLOCK/WARN/ALLOW의 차이 |
| `/phishing-block.html` | BLOCK 시연 · 안전한 조치/오탐 검토 초안 |
| `/phishing-warning-continue.html` | WARN 시연 · 설명용 계속 방문 선택지(실제 우회 없음) |

**ALLOW**는 정상 DNS 응답으로 진행하므로 별도의 포털 이동 화면이 없습니다. 두 HTML의 파일명은 기존 원본과의 연결성을 고려하여 유지했습니다.

## 기술 선택

**정적 HTML + 공통 CSS/JavaScript**를 채택했습니다. 원본이 HTML이고, DNS 포털이 인증된 서버 API와 연결되기 전이므로 프레임워크·런타임·npm 의존성이 추가되는 Next.js보다 제출·격리 배포·보안 감사에 필요한 구성이 작습니다. 추후 운영자 콘솔/SSR/로그인/동적 사례 조회가 실제로 필요하면 Next.js를 별도로 평가할 수 있습니다.

- 외부 폰트·CDN·서드파티 JavaScript·쿠키·로컬 스토리지·자동 네트워크 요청 없음
- `public/`은 빌드 없이 정적 호스팅 가능, 상대 경로만 사용
- 모바일, 자동 라이트/다크 테마, 줄임 동작, 포커스 표시, 상태 안내/다이얼로그
- `vercel.json`은 해당 폴더를 Vercel 프로젝트 Root Directory로 지정했을 때 적용되는 보안 헤더와 정적 출력 설정

### 로컬 실행

```bash
python3 -m http.server 35173 --directory apps/warning-portal/public
# http://127.0.0.1:35173/
```

위 명령은 **시연 프론트엔드만** 제공합니다. 개발 HTTP의 인증서는 HTTPS 검증 자료가 아닙니다. 실제 외부 배포에는 소유한 도메인의 정상 TLS 인증서가 필요합니다.

### 배포 예시 (Vercel)

Vercel 프로젝트에서 저장소를 연결하고 **Root Directory를 `apps/warning-portal`**, Framework Preset을 `Other`, Output Directory를 `public`으로 지정합니다. `vercel.json`에 `outputDirectory: public`과 경로별 정적 보안 헤더가 선언되어 있으며, 별도 빌드가 필요하지 않습니다. 다른 호스팅 플랫폼은 CSP·보안 헤더를 서버 측에 따로 설정해야 합니다.

## 중요한 보안 경계

1. **DNS는 HTTP 302가 아닙니다.** NXDOMAIN으로 차단된 원래 HTTPS 탭을 이 HTML로 자동 이동시킬 수 없습니다. 포털은 별도의 신뢰할 수 있는 HTTPS 주소에서 방문해야 합니다.
2. URL의 `score`, `url`, `target`, `domain`, `verdict` 쿼리/해시를 판정·위험 점수·원래 목적지로 사용하지 않습니다. 화면의 94/72점과 예시 신호는 실제 분석 결과가 아닙니다.
3. WARN의 ‘위험을 감수하고 방문하기’는 원본 의도를 보존한 **설명 버튼**이며 이동/우회 권한을 부여하지 않습니다. BLOCK에서도 원래 방문 주소로 돌아가지 않습니다.
4. 오탐 신고는 입력값을 **서버에 전송·저장하지 않고**, 사용자 요청으로 **복사할 텍스트 초안만** 만듭니다. 브라우저 자체 클립보드 사용은 사용자의 복사 버튼 클릭 시에만 시도됩니다. 실제 접수·사용자 인증·승인 및 자동 허용은 구현되지 않았습니다.
5. 원격 URL을 가져오거나 DOM에 사용자 내용을 HTML로 삽입하지 않습니다. 브라우저 입력 검증은 UX용이며, 향후 접수 API는 서버에서 FQDN·크기·요청 출처·권한·속도 제한을 다시 검증해야 합니다.

### 추후 정책 연동 권고

정책 서버/로컬 DNS가 발급한 검증된 사례 ID·결정 상태·만료·근거 등을 신뢰 가능한 **서버 경로**로 조회할 수 있는 별도 API/인증 설계가 필요합니다. URL 쿼리만으로 BLOCK/WARN/ALLOW나 ‘계속 방문’ 목적지를 전달하면 상태 위조·오픈 리다이렉트 위험이 발생합니다. 원래 차단 사이트의 HTTPS 트래픽을 TLS MITM으로 가로채는 방법은 채택하지 않습니다. 경고 UI는 독립 포털 또는 관리 단말의 별도 UX를 통해 제공해야 합니다.

## 테스트

```bash
python3 -m unittest discover -s apps/warning-portal/tests -p 'test_*.py' -v
node --check apps/warning-portal/public/portal.js
```

정적 구조·링크·예시 표시·보안 헤더·원본 해시·의도치 않은 외부 통신 코드 여부를 검사합니다. `tests/browser_smoke.py`는 Playwright 사용 가능 환경에서 **정적 HTML을 메모리 DOM에 넣고 CSS/JS를 주입**하여 데스크톱/모바일 상호작용을 검사하는 선택적 테스트입니다. 실제 HTTP 응답·Vercel 헤더·TLS와 DNS 연동을 검사하지는 않습니다. **정적 테스트와 브라우저 테스트는 실제 DNS 차단이나 HTTPS 인증서 실증을 대신하지 않습니다.**

관련: [캡스톤 기술 명세](https://app.notion.com/p/4025db6797f081e18de9cc1a2ca748f2) · [팀 일정 트래커](https://app.notion.com/p/78f284e4c1504c90ab32e8e568c296d6).
