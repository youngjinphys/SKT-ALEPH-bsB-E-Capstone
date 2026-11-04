# 기존 도메인의 DNS 관제 로그인

운영 경로는 `https://skt-aleph-capstone.vercel.app/dashboard`이며, 소개 페이지의 **관제센터**가 같은 경로로 연결됩니다. `apps/web`은 PR-Page의 파일·에셋을 보존한 프론트엔드이고, 기존 main에서 진행된 발표/발표자 노트 수정도 유지합니다. `cloud`는 동일 Vercel 프로젝트의 FastAPI 서비스로 실제 정책 엔진과 영속 DB를 연결합니다. 새 프로젝트나 별도 도메인을 만들 필요가 없습니다.

## 로그인 방법

1. `/dashboard`에서 **Google로 로그인**을 선택합니다. Vercel 관제에서는 별도 암호나 로컬 콘솔 Bearer 토큰을 입력하지 않습니다.
2. Google/Supabase가 확인한 이메일이 production의 `CAPSTONE_OPS_ALLOWED_EMAILS`에 포함된 계정만 운영자로 인증됩니다. 일반 사이트 로그인과 DNS 운영자 권한은 별개입니다. 승인되지 않은 계정은 HTTP 403입니다.
3. OAuth가 완료되면 `/dashboard`로 돌아오고, `/api/ops/session`이 실제 운영자 권한을 확인합니다. 헤더에 로그인한 이메일이 표시됩니다. 이 인증 확인은 정책 DB를 읽거나 변경하지 않으므로, 정책 데이터 오류를 로그인 실패로 혼동하지 않습니다.
4. **잠금**은 화면과 진행 중 요청을 무효화합니다. **계정 로그아웃**은 공통 사이트 로그아웃 API도 호출합니다. 늦게 도착한 인증 응답이 잠금/로그아웃을 취소할 수 없습니다.

다른 운영자를 승인하려면 프로젝트 관리자가 Vercel 환경 변수 `CAPSTONE_OPS_ALLOWED_EMAILS`의 production 값을 명시적으로 승인한 이메일 목록으로 변경하고 **동일 프로젝트**를 재배포합니다. 실제 Google 계정이 다른 이메일을 반환하면 허용 목록도 그 주소와 일치해야 합니다. Gmail이 아닌 주소로 만든 Google 계정도 가능하지만 이메일 소유 확인이 필수입니다.

## Google 제공자가 비활성화된 경우

`/api/oauth?action=status`가 실제 제공자 상태를 알려줍니다. `disabled`이면 관제 화면은 실행 불가능한 로그인 링크 대신 설정 필요 메시지를 표시합니다. 코드에 로그인 버튼이 있다고 OAuth 클라이언트까지 자동 생성되지는 않습니다.

- Supabase **Authentication → Sign In / Providers → Google**에서 Google Web application OAuth Client ID와 Client Secret을 설정하고 활성화합니다.
- Google의 Authorized redirect URIs에는 **해당 Supabase 프로젝트**의 `https://<project-ref>.supabase.co/auth/v1/callback`을 등록합니다.
- Supabase URL Configuration의 Site URL은 `https://skt-aleph-capstone.vercel.app`, 허용 Redirect URL은 `https://skt-aleph-capstone.vercel.app/api/oauth-callback`로 설정합니다.
- 비밀키는 공급자 관리 화면에만 입력하고, Git 저장소·브라우저 코드·채팅에는 넣지 않습니다. 공급자 활성화 후 새로고침하면 됩니다. 허용 목록이나 쿠키 검증을 제거해 설정 누락을 우회하지 않습니다.

## 저장소와 배포 소스

소개 페이지·발표·관제의 기준 소스는 `youngjinphys/SKT-ALEPH-bsB-E-Capstone/main`입니다. Vercel 프로젝트의 Settings → Git에서 연결 저장소도 이 저장소로 설정해야 향후 main push가 자동 배포됩니다. 원본 `SKT-ALEPH-PR-Page`를 삭제하거나 그 저장소의 오래된 빌드로 통합 사이트를 덮어쓰면 안 됩니다. 기존 프로젝트에 명시적인 Capstone Git source로 배포하는 것과 영구 Git 연결 변경은 별개입니다.

노드 상태 보고는 운영자의 Google 세션이 아닌 장치별 Ed25519 서명을 사용합니다. 실제 DNS 노드·신뢰 공개키·서명 정책이 등록되기 전까지 운영 상태를 성공으로 표시하지 않습니다.
