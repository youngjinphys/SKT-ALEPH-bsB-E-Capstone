# Unified Vercel presentation and DNS dashboard

## One source repository, one existing project

`youngjinphys/SKT-ALEPH-bsB-E-Capstone` is the unified source. `apps/web/` preserves all tracked files from PR-Page main `313164e65314032468d47e5c43273e35e77fba84`, with only the navigation links and allowlisted post-login destination adapted. `/`, `/capstone`, `/fishing`, `/app`, assets and the existing Google callback remain available. The original PR-Page repository is retained, not deleted or force-rewritten.

The existing Vercel project `skt-aleph-capstone` serves:

| Path | Owner |
| --- | --- |
| `/`, `/capstone`, `/fishing`, `/app`, `/api/auth`, `/api/oauth`, `/api/oauth-callback` | `apps/web` / Next.js |
| `/dashboard`, `/dashboard/assets/*` | Python cloud adapter using existing console UI |
| `/api/ops/*` | Operator-authorized Python management API |
| `/v1/nodes/report` | Ed25519-signed device report receiver |
| `/v1/policies/<device>/current.json` | Independently signed and unexpired policy feed |

Vercel Services is currently Beta. Its routing configuration is at the repository root. No local DNS daemon, nftables rules, privileged installer or signing private key runs on Vercel. The original standalone console remains supported by `policy_server.console`.

## Authentication and persistent state

The frontend and backend use the existing `__Host-capstone_at` HttpOnly cookie. Every operator request is verified using Supabase Auth; `CAPSTONE_OPS_ALLOWED_EMAILS` is a separate, explicit deny-by-default operator allowlist. A general Google login does not grant DNS privileges. Write requests additionally require the exact configured Origin. Return destinations after OAuth are restricted to `/app` and `/dashboard`.

Production state is an isolated PostgreSQL JSONB snapshot in `aleph_ops_private` with RLS, no direct anon/authenticated table grants, and narrowly scoped capability-protected read/write RPCs. No service-role key is required. Each request temporarily materializes private files for the existing Python engine, and removes them afterward. A DB revision compare-and-swap, not a temporary-file lock, prevents cross-instance lost updates and replay-counter regression. Stale writes return 409 and must be reloaded. An unavailable DB returns 503; there is no memory-only production fallback.

Snapshot limits: 8 MiB, 512 files, 2 MiB per file. Local audit history is capped at 500 events and is not tamper-proof compliance storage. This bounded control-plane adapter is appropriate for a small capstone deployment, not an unlimited multi-tenant telemetry warehouse. Production state is denied to preview deployments.

## Environment (server-only)

- `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`: existing **Google/OAuth authentication** project; do not point these to the Naver DB.
- `ALEPH_STATE_URL=https://uilpaajbcnxklorjhksc.supabase.co`: Naver-linked **operations DB only**, not an authentication provider.
- `ALEPH_STATE_PUBLISHABLE_KEY`: the Naver project's active publishable API key. Server-only even though publishable, and production-only.
- `ALEPH_STATE_DB_CAPABILITY`: independently generated operations DB capability (48–256 printable ASCII characters), production-only. Only its SHA-256 is saved in the Naver DB.
- `CAPSTONE_SITE_ORIGIN=https://skt-aleph-capstone.vercel.app`.
- `CAPSTONE_OPS_ALLOWED_EMAILS`: explicitly approved operator email addresses.
- `ALEPH_STATE_CAPABILITY`: legacy operations capability for the **previous** database. Preserve it only for a controlled rollback; new production code does not use it. Never commit or expose any capability to the browser.
- `ALEPH_DEFAULT_DEVICE=edge-69`: initial policy-view device; node registrations remain explicit.

Keep both state capabilities and the operator allowlist production-only. The bundled migration creates isolated objects but never embeds a capability or private key. Naver uses the separate DB URL, publishable key and capability. A production deployment missing any of these three **fails closed** rather than falling back to the old authentication tenant. Local development retains explicit legacy compatibility only.

### Naver-account database cutover (2026-11-03)

- Old authentication/state project: `ytvwpdjfrpwxwtucclpe` (authentication retained; historical DB kept read-only for rollback).
- Naver-owned state project: `uilpaajbcnxklorjhksc`. The `aleph_ops_private` tables and `public.aleph_ops_load/save` RPCs were verified present, with schema RLS and only capability-controlled access.
- At cutover inspection both state rows had revision `0` and zero files, therefore **no signed policies, trust keys or DNS node reports were transferred**. The target is a fresh empty control plane; an empty dashboard is not proof of an applied DNS policy.
- The Naver project's *existing* capability hash was different from the legacy project. Rotate only the Naver state's capability to a freshly generated production secret, without modifying the OAuth tenant's settings, users or legacy state.
- Configure new `ALEPH_STATE_*` variables on the **existing** `skt-aleph-capstone` Vercel project and deploy reviewed Capstone `main`. Never add service-role keys. Verify the Naver RPC's read access before promoting; `GET /v1/policies/edge-69/current.json` should return 404 **when the empty store is healthy**, and 503 for unavailable storage. 404 does not prove DNS deployment.
- To roll back, promote the prior tested deployment which continues to use the preserved legacy `ALEPH_STATE_CAPABILITY`; do not copy the Naver capability over the old one. Do not delete the original database until a later verified migration/export decision. Google OAuth remains the previous project, and a disabled provider still requires independent activation.


## Operator flow

1. Visit `/dashboard`, complete existing Google login, and pass operator authorization.
2. Register independently verified **public** Ed25519 keys, separately for policy signers and reporting devices. A key cannot be reused across roles. Private-key PEM is rejected.
3. Register DNS devices with their private IPv4 address, ID and pinned public-key fingerprint.
4. Import the collector's valid `verified.json`, review the evidence, acknowledge SUBTREE scope and generate an unsigned draft using the existing compiler. Import alone never grants approval.
5. Independently sign the draft outside Vercel using the existing CLI. Upload the signed envelope with the expected current sequence. Signature, expiry, device identity, sequence monotonicity, key rotation and withdrawal acknowledgement are revalidated before publication.
6. Configure the local DNS node's policy URL as `https://skt-aleph-capstone.vercel.app/v1/policies/<device>/current.json` and report URL as `https://skt-aleph-capstone.vercel.app/v1/nodes/report`. Devices initiate outbound HTTPS; no DDNS or inbound router ports are required by this topology.

The existing collector bridge uses a Unix socket and systemd; it does not run inside a Vercel function. Automatic OpenPhish/GSB refresh remains explicitly unavailable in the cloud adapter until a separately configured cloud collection job and API credentials are supplied. Verified evidence import remains usable; it does not extend evidence validity or bypass the independent signer. Local collectors and signers can continue to run without exposing a web management port.

## Release and verification

Use only `main`; no separate Git branch or Vercel project is required. Git integration should point the existing project to the unified Capstone repository with framework `services`, root directory unset, and no project-level install/build command override. Stage the existing project's production build with auto-alias assignment disabled, test route ownership and authentication boundaries, then promote to the existing domain. Do not let the retired PR-Page integration overwrite this deployment.

Run `python3 -B -m unittest discover -s tests/cloud -v`, existing policy tests, and `npm ci && npm run check` in `apps/web`. Browser-test the public landing and the actual dashboard login/gated flows. Do not seed production with synthetic health reports or claim an unregistered node is healthy.

## Reviewed operator handoff (2026-11-03)

The shared workbench now obtains `/api/ops/capabilities` on login. The cloud adapter
explicitly identifies its collector as **external** and offers verified-file
preview/import; it does not show a disabled local Unix-socket refresh form or
suggest that adding a secret alone would activate a serverless job. The standalone
console exposes `/api/capabilities` and retains its opt-in collector bridge.

Evidence import is a two-stage operation. `cloud/evidence/preview` validates the
complete evidence, its provider cache expiry, and returns a fingerprint and a
context revision binding **both** the current evidence and reviews. A subsequent
`cloud/evidence` commit requires these values and `IMPORT_VERIFIED`. A changed
context returns 409. Existing records are archived privately; different evidence
starts with all approvals false. Re-importing the same valid pair preserves its
approvals; retrying an explicitly confirmed interrupted pair repairs the mismatch.
Archives are not silently pruned. Account for them in the bounded 8 MiB/512-file
snapshot and establish an administrator-reviewed retention procedure.

Public keys are previewed before trust registration, so the operator can compare
the displayed fingerprint with the independent channel. Signed publication is
previewed before commit, showing additions, withdrawals, expiry shortening and
signer rotation. The commit rechecks signature, expiry, device, sequence, **later
issuance time**, and required acknowledgements. Preview endpoints never save a
new DB revision. Generated drafts are bound to the review-set revision displayed
by the GUI. These confirmations reduce accidental changes but do not replace
operator authorization, independent signing or a tamper-proof approval process.

`nodes/unregister` is the canonical shared UI route; `nodes/remove` is retained as
a compatibility alias. The node table provides local filtering by name/device/IP
and verified versus attention-needed status. Missing/stale observations are not
shown as success. Locking cancels confirmation dialogs and clears selected files
and pending previews. Audit timestamps are labeled as the browser's local time.

### Reproducible UI acceptance

```bash
python3 -m pip install -r requirements.txt httpx==0.28.1 playwright==1.57.0
python3 -m playwright install --with-deps chromium
python3 -B -m unittest discover -s tests/cloud -v
ALEPH_SCREENSHOTS=/tmp/aleph-browser-artifacts python3 -B tests/browser/console_smoke.py
```

The browser fixture uses synthetic evidence, an isolated test-only MemoryStore,
and actual loopback HTTP API handlers. Browser requests are bridged to loopback
HTTP in the test harness so managed Chromium network policy is not weakened.
Screenshots test rendered assets, confirmation/cancel, file import, filters,
responsive layouts and page errors. They do **not** certify production OAuth,
Supabase availability, HTTP routing, TLS, CSP enforcement, real GSB requests or
LAN DNS behavior. The existing project still requires its normal deployment and
live acceptance checks; no new Vercel project is introduced.

### 장치별 관제 읽기와 변경 확인

게시 대상 선택은 `GET /api/ops/deployment/<device_id>`로 해당 장치의 서명 정책을 읽습니다. 기본 `/deployment` 경로는 유지되며 조회는 durable state의 revision을 증가시키지 않습니다. 노드 보고 API 또는 게시 읽기 API 중 하나가 실패하면 해당 근거만 미확인으로 처리합니다.

`POST /api/ops/nodes/unregister`(및 `/nodes/remove`)에는 `device_id`, `confirm: UNREGISTER_NODE`, **`expected_key_id`**가 필요합니다. 표시한 키와 현재 등록 키가 다르면 409로 거부하며 데이터와 감사 로그를 commit하지 않습니다. 새 UI가 이 값을 전송하므로 웹/ASGI 코드를 동일 버전으로 갱신하고 열린 탭을 다시 읽어야 합니다. 추가 환경 변수나 데이터베이스 마이그레이션은 없습니다.

## Aggregate DNS observations

The overview includes authenticated `/api/ops/analytics`, bounded node histories, diagnostic latency/cache/host charts and 10-second read-only polling. Node reporting stays at its 60-second default. Production data remains in the Naver operations DB. [Collection semantics, privacy, retention and node upgrade](dns-observability.md) must be read before enabling optional cache counters.

## 실제 노드 자원 관측과 연결

[v4 노드 연결·CPU/메모리/NIC/일반 DNS 품질 가이드](dns-node-resources-and-connection.md)를 참고하세요. `/api/ops/cloud/enroll/preview`와 `/api/ops/cloud/enroll`은 운영자 승인을 받아 공개 장치 키와 등록정보만 원자적으로 저장합니다. 기존 수집기 v1–v3도 읽으며 수치가 없는 경우 결측으로 표시합니다.


## 대시보드 사용방법 HUD

`/dashboard` 우측 하단 **사용방법**에서 운영 개요, 위협 검토, 위험도 제안, 정책 초안, 배포 현황, 작업 기록을 순서대로 안내합니다. 안내는 직접 열 때만 나타납니다. 이전·다음은 설명만 바꾸며, **해당 화면 보기**를 눌렀을 때만 기존 메뉴로 이동하고 HUD를 접습니다. 닫기·Esc는 현재 화면을 유지하며, 닫기 전 단계는 같은 페이지에서 다시 열 때 유지됩니다. 가이드 완료 또는 세션 잠금 후에는 첫 단계로 돌아갑니다.

로그인 전에도 설명을 읽을 수 있지만 운영 메뉴 이동은 비활성화됩니다. 승인·가져오기·신뢰키/장치 등록·정책 게시·DNS 변경은 가이드가 수행하지 않습니다. 개인키를 업로드하도록 안내하지 않으며, 노드 내부 검증과 LAN 전체 보호를 구분합니다. 로그인·권한 확인은 기존 흐름 그대로입니다.

대시보드 왼쪽 위 **ALEPH✳ PROTECTIVE DNS**는 같은 사이트 루트 `/` 소개 페이지로 이동하는 기본 링크입니다. 로컬 토큰 콘솔에는 이 링크나 튜토리얼을 추가하지 않습니다.

검증 명령:

```bash
python3 -B -m unittest discover -s tests/cloud -p test_tutorial.py -v
node --test tests/cloud/dashboard-tutorial.test.mjs
python3 -B tests/browser/dashboard_tutorial.py
```

브라우저 검증은 기존 Playwright 설치를 사용하며 외부 요청을 모두 가로챕니다. 실제 조립된 HTML/CSS와 가이드 JS를 검사하고, 인증 및 읽기 전용 메뉴 이동은 합성 UI 상태로 제공합니다. 320px 모바일부터 데스크톱·가로 화면까지 70개 단계/크기 조합, 키보드 열기·닫기·초점 복귀·비모달 Tab 이동·세션 잠금·루트 이동/뒤로 가기를 확인합니다. 운영 서버 인증이나 DNS 적용 검증을 대신하지 않습니다.
