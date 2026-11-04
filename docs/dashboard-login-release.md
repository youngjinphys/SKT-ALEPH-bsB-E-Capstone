# Unified dashboard: release and login

## Existing-domain release handoff

The source audit compared all 131 tracked files at PR-Page `313164e65314032468d47e5c43273e35e77fba84`: none were missing under `apps/web`; 96 were byte-identical and 35 reflected existing integration/presentation changes. The original repository was not rewritten. Tests and patches are committed only to the unified repository's `main`.

The project ID remains `prj_p2R0tXgaSRTnoeML0ujaUAZyLsko`; the public destination remains `https://skt-aleph-capstone.vercel.app/dashboard`. Building another version in this same project is necessary to ship code; no new project or public domain is needed.

A deploy from an explicit Git source does **not** reconnect a project's automatic Git integration. At review time the project still listed PR-Page. The existing project must be connected to `youngjinphys/SKT-ALEPH-bsB-E-Capstone`, production branch `main`, in Settings → Git. Keep framework `services`, root directory empty, and clear manual build/install overrides. A project-level Ignored Build Step should skip any source other than the unified owner/repo until that link is corrected. Do not confuse a successful manual deployment with working automatic main deployments.

## 로그인 운영 안내

1. 소개 페이지의 **관제센터** 또는 `/dashboard`로 접속합니다.
2. **Google로 로그인**을 선택합니다. 이미 로그인했다면 **현재 로그인으로 관제센터 연결**을 사용합니다.
3. Google에서 확인된 이메일이 production의 `CAPSTONE_OPS_ALLOWED_EMAILS`에 정확하게 등록되어 있어야 합니다. 이 설정은 일반 방문자 로그인 허용 목록과 별개이며 비어 있으면 모두 거부합니다. Vercel 계정 이메일과 Google 계정 이메일이 다를 수 있습니다.
4. 비밀번호·로컬 콘솔 Bearer 토큰·서비스 역할 키를 이 화면에 입력하지 않습니다. 로그인 성공은 정책 발행 성공이나 DNS 적용 성공을 뜻하지 않습니다.

### Google 제공자가 disabled인 경우

`/api/oauth?action=status`가 `state: disabled`면 페이지를 배포했어도 새 Google 로그인을 할 수 없습니다. 인증을 해제하거나 임시 비밀번호로 우회하지 마세요.

- Google Cloud의 Web OAuth client에 사이트 origin `https://skt-aleph-capstone.vercel.app`을 등록합니다.
- Google의 redirect URI는 **Supabase 프로젝트의** `https://<project-ref>.supabase.co/auth/v1/callback`입니다.
- Supabase Authentication → Providers → Google에서 해당 client ID/secret을 직접 입력하고 활성화합니다. 비밀값을 Git이나 채팅에 붙이지 마세요.
- Supabase Authentication → URL Configuration의 redirect allowlist에 **애플리케이션의** `https://skt-aleph-capstone.vercel.app/api/oauth-callback`을 추가합니다. Google callback과 앱 callback은 다릅니다.
- 공유 인증 프로젝트를 사용하므로 Claire 등 다른 앱의 기존 Site URL/redirect를 지우거나 덮어쓰지 않습니다. 필요한 주소만 추가합니다.
- OAuth app이 Testing이면 실제 운영자 Google 계정을 Test users에 등록합니다. Google 로그인 이메일을 운영자 목록에 승인한 뒤 재로그인합니다.

외부 인증 설정은 페이지 배포와 별도의 인수 항목입니다. 제공자 활성화 확인과 실제 계정의 OAuth 왕복을 완료하기 전에는 로그인을 검증 완료로 표시하지 않습니다.
