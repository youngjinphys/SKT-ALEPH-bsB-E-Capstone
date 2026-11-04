"""Bundled static console shell; intentionally no external assets or inline scripts."""
from .console_style import CSS as BASE_CSS
from .console_theme import THEME
CSS = BASE_CSS + '\n' + THEME
from .console_script import JS

HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>ALEPH | DNS Operations</title>
  <link rel="stylesheet" href="/console.css">
  <script src="/console.js" defer></script>
</head>
<body>
<a class="skip-link" href="#main-content">본문으로 바로가기</a>
<div class="shell">
  <aside class="sidebar" aria-label="관제 탐색">
    <div class="brand"><div><strong>ALEPH<span class="brand-asterisk">✳</span></strong><small>PROTECTIVE DNS</small></div></div>
    <div class="side-caption">WORKSPACE</div>
    <nav class="side-nav" aria-label="주요 메뉴">
      <button class="nav-item active" data-view="overview"><span class="nav-icon">◫</span>운영 개요</button>
      <button class="nav-item" data-view="reviews"><span class="nav-icon">◎</span>위협 검토 <span class="nav-count" id="nav-review-count">–</span></button>
      <button class="nav-item" data-view="engine"><span class="nav-icon">◇</span>위험도 제안</button>
      <button class="nav-item" data-view="drafts"><span class="nav-icon">▤</span>DNS 정책 초안</button>
      <button class="nav-item" data-view="deployment"><span class="nav-icon">⇧</span>배포 현황</button>
      <button class="nav-item" data-view="audit"><span class="nav-icon">≡</span>작업 기록</button>
    </nav>
    <div class="sidebar-bottom"><div class="security-card"><div class="security-icon">◈</div><div><strong>분리된 보안 경계</strong><small>검토·생성 / 서명·배포 분리</small></div></div><div class="sidebar-foot">E TEAM <span>•</span> OPERATOR CONSOLE</div></div>
  </aside>
  <div class="main-column">
    <header class="topbar">
      <div class="topbar-context"><div class="crumb"><span>ALEPH</span><span class="crumb-sep">/</span><span id="crumb-current">Operations</span></div><span class="topbar-subtitle">DNS POLICY CONTROL CENTER</span></div>
      <div class="topbar-actions"><span class="connection-status" role="status"><span class="connection-dot" id="connection-dot" aria-hidden="true"></span><span class="connection" id="connection-text">콘솔 인증 필요</span></span><button class="icon-button" type="button" id="refresh-button" title="데이터 새로고침" aria-label="데이터 새로고침">↻</button><button class="quiet-button" type="button" id="logout-button" hidden>잠금</button></div>
    </header>
    <main class="content" id="main-content" tabindex="-1">
      <section class="login-wrap" id="login-view" aria-labelledby="login-title">
        <div class="login-card"><div class="login-symbol">◈</div><div class="eyebrow">SECURE OPERATOR ACCESS</div><h1 id="login-title">관제 콘솔에 연결</h1><p>서버 로컬 토큰으로 인증합니다. 토큰은 브라우저 메모리에만 유지되며 저장하지 않습니다.</p>
        <form id="login-form"><label for="token">운영자 액세스 토큰</label><input id="token" type="password" autocomplete="off" spellcheck="false" placeholder="32자 이상 발급한 토큰" required><button type="submit" class="button primary wide">안전하게 연결 <span>→</span></button></form>
        <div class="login-note"><span>●</span> 로컬 바인딩 · API 접근 제어 · DNS 무변경</div></div>
      </section>
      <div id="authorized" hidden>
        <div class="hero"><div class="hero-copy"><div class="eyebrow"><span class="eyebrow-line"></span> ALEPH / SECURITY OPERATIONS <span class="hero-date" id="hero-date"></span></div><h1 id="page-title" tabindex="-1">운영 개요</h1><p class="lead" id="page-description">정책 근거, 승인, 서명 게시 상태를 하나의 화면에서 확인합니다.</p><div class="hero-actions"><button type="button" class="button primary hero-primary" data-go="reviews">위협정보 검토 <span aria-hidden="true">↗</span></button><button type="button" class="button outline hero-secondary" data-go="deployment">배포 상태 확인 <span aria-hidden="true">→</span></button></div><div class="hero-trust"><span><i class="signal-mini"></i> 운영 DNS와 격리된 검토 환경</span><span>독립 서명 절차 유지</span></div></div><div class="hero-art" aria-hidden="true"><span class="orbit orbit-outer"></span><span class="orbit orbit-inner"></span><span class="orbital-core"></span><span class="orbit-north">DNS</span><span class="orbit-east">SIGNED</span><span class="orbit-west">REVIEWED</span></div><div class="hero-tools"><span class="environment-label"><i></i> REVIEW / NO DIRECT DNS WRITE</span></div></div>
        <div class="verification-strip" role="status"><span class="strip-indicator" aria-hidden="true"></span><span class="strip-prefix">관제 상태</span><strong id="verification-status">확인 중</strong><span class="strip-break"></span><span class="strip-checked">마지막 조회 <strong id="last-checked">–</strong></span><span class="strip-tail">게시 정책 · 로컬 DNS 검증 · LAN 보호는 서로 다른 상태입니다</span></div>
        <section class="view" data-panel="overview"><p id="overview-read-error" class="read-error" role="alert" hidden></p>
          <div class="evidence-health" id="evidence-health" role="status" hidden><span class="health-mark">!</span><div><strong id="evidence-health-title">위협 증거 확인 필요</strong><p id="evidence-health-note">검증 자료의 만료 여부를 확인하세요.</p></div><button class="text-button" data-go="reviews">증거 검토하기 →</button></div>
          <div class="section-heading section-heading--metrics"><div><div class="overline">EVIDENCE / REVIEW QUEUE</div><h2>정책 근거 현황</h2></div><p>검토 자료의 수치이며 실제 DNS 차단 통계가 아닙니다.</p></div>
          <div class="stats-grid">
            <article class="stat-card"><div class="stat-caption"><span>검토 후보</span><span class="stat-symbol">◎</span></div><div class="stat-value" id="stat-candidates">–</div><p>검증된 위협 URL 기반 후보</p></article>
            <article class="stat-card"><div class="stat-caption"><span>검토 승인 기록</span><span class="stat-symbol accent">✓</span></div><div class="stat-value" id="stat-approved">–</div><p>SUBTREE 범위 수동 승인</p></article>
            <article class="stat-card"><div class="stat-caption"><span>유효한 증거</span><span class="stat-symbol">◷</span></div><div class="stat-value" id="stat-fresh">–</div><p>조회 결과 유효시간 내</p></article>
            <article class="stat-card"><div class="stat-caption"><span>미서명 초안</span><span class="stat-symbol">▤</span></div><div class="stat-value" id="stat-drafts">–</div><p>독립 서명 전 파일 · 배포와 무관</p></article>
          </div>
          <section class="surface fleet-summary" aria-labelledby="fleet-summary-title">
            <div class="section-top fleet-title"><div><div class="overline">SIGNED NODE RECEIPTS / DEPLOYMENT</div><h2 id="fleet-summary-title">DNS 노드 운영 상태</h2><p class="muted-copy">서명된 노드 보고·정책 SHA-256 비교와 독립 upstream 양성 검증 기준. LAN 전체 보호는 별도입니다.</p></div><button class="text-button" data-go="deployment">장치별 자세히 보기 →</button></div>
            <p id="fleet-alert" class="impact-warning" role="alert" hidden></p>
            <div class="fleet-metrics">
              <div data-metric="nodes"><small>등록된 DNS 노드</small><strong id="fleet-registered">–</strong></div>
              <div data-metric="attested"><small>노드 내부 적용 확인</small><strong id="fleet-applied">–</strong></div>
              <div data-metric="correlated"><small>양성 기준 포함 DNS 비교</small><strong id="fleet-correlated">–</strong></div>
              <div data-state="warning" data-metric="pending"><small>추가 검증 필요</small><strong id="fleet-pending">–</strong></div>
            </div>
          </section>
          <div class="dashboard-grid">
            <article class="surface wide-surface"><div class="section-top"><div><div class="overline">POLICY LIFECYCLE</div><h2>정책 처리 파이프라인</h2></div><span class="pill muted">각 단계별 검증 경계 유지</span></div><div class="pipeline">
              <button type="button" class="stage" data-go="reviews" aria-label="1단계 위협 증거 조회"><span class="stage-number">01</span><strong>위협 증거</strong><small>OpenPhish · GSB 검증</small></button><div class="stage-arrow" aria-hidden="true">→</div><button type="button" class="stage" data-go="reviews" aria-label="2단계 위협정보 수동 검토"><span class="stage-number">02</span><strong>사람 검토</strong><small>증거·범위 명시 승인</small></button><div class="stage-arrow" aria-hidden="true">→</div><button type="button" class="stage" data-go="drafts" aria-label="3단계 정책 초안 생성"><span class="stage-number">03</span><strong>정책 초안</strong><small>실제 엔진으로 생성</small></button><div class="stage-arrow" aria-hidden="true">→</div><button type="button" class="stage stage-final" data-go="deployment" aria-label="4단계 서명된 게시 정책 확인"><span class="stage-number">04</span><strong>서명된 게시</strong><small>DNS 적용은 별도 확인</small></button>
            </div><div class="panel-footer"><span>검증 결과 시각</span><strong id="overview-verified">확인 중</strong><button class="text-button" data-go="reviews">검토 목록 →</button></div><div class="pipeline-bottom"><div><small>정책 작성 가능 후보</small><strong id="overview-eligible">–</strong></div><div><small>유효 증거 중 가장 빠른 만료</small><strong id="overview-next-expiry">–</strong></div></div></article>
            <article class="surface"><div class="section-top"><div><div class="overline">PUBLISHER HEALTH</div><h2>게시 정책 상태</h2></div><span class="status-dot" id="overview-deploy-dot"></span></div><div class="deployment-summary"><div class="deployment-status-icon">◈</div><strong id="overview-deploy-state">확인 중</strong><p id="overview-deploy-detail">서명된 파일과 신뢰키를 검사합니다.</p></div><div class="panel-footer"><span>노드 적용 상태</span><strong class="warning-text">장치별 별도 확인</strong><button class="text-button" data-go="deployment">자세히 보기 →</button></div></article>
          </div>
          <div class="info-banner"><span class="info-banner-icon">i</span><div><strong>권한과 신뢰 경계</strong><p>검토 승인·정책 초안·서명된 게시 파일 확인은 각각 별개의 단계입니다. 게시 파일을 확인해도 DNS 노드의 실제 적용 성공을 의미하지 않습니다.</p></div></div>
        </section>
        <section class="view" data-panel="reviews" hidden>
          <div class="section-top outside"><div><div class="overline">THREAT INTELLIGENCE</div><h2>검증 증거 검토</h2><p>실제 조회 데이터의 도메인·위협 유형·만료시간을 확인한 후 승인합니다. 원본 URL은 노출하지 않습니다.</p></div><button class="button outline" id="reset-reviews">검토 기록 초기화</button></div>
          <section class="surface intel-refresh-panel" aria-labelledby="intel-refresh-heading">
            <div class="section-top"><div><div class="overline">THREAT FEEDS / TWO-SOURCE VERIFICATION</div><h3 id="intel-refresh-heading">위협정보 수집 및 재검증</h3><p class="muted-copy">원격 수집 서비스에 갱신을 요청하고, 완료된 최신 증거를 검토 화면으로 명시적으로 가져옵니다. 기존 승인·초안·서명 정책은 자동 변경되지 않습니다.</p></div><button class="text-button" type="button" id="intel-status-reload">수집 상태 조회 ↻</button></div>
            <div class="intel-activity-line" aria-hidden="true"></div><div class="intel-summary"><div><small>수집 상태</small><strong id="intel-state">확인 중</strong></div><div><small>최근 검증 시각</small><strong id="intel-checked">–</strong></div><div><small>검증 URL / 수동 검토 후보</small><strong id="intel-counts">–</strong></div><div><small>수집 Run ID</small><strong id="intel-run" class="mono">–</strong></div></div>
            <p id="intel-note" class="muted-copy" role="status">수집기 연결을 확인합니다.</p>
            <form id="intel-refresh-form" class="intel-refresh-form">
              <label class="check-row"><input type="checkbox" id="intel-terms" required><span>OpenPhish Community Feed 사용 조건을 확인했습니다.</span></label>
              <label class="check-row"><input type="checkbox" id="intel-disclosure" required><span>후보 URL을 Google Safe Browsing 서비스에 조회한다는 점을 확인했습니다.</span></label>
              <label class="check-row"><input type="checkbox" id="intel-noncommercial" required><span>비상업적 사용·데이터 처리 제한을 확인했습니다.</span></label>
              <div class="action-row"><button class="button outline" type="submit" id="intel-refresh">OpenPhish + GSB 새로 검증</button><button class="button primary" type="button" id="intel-import" disabled>최신 검증 자료 가져오기</button></div>
            </form>
            <p class="fine-print">외부 수집 요청에는 쿨다운(클라우드 기본 15분)이 적용됩니다. 성공한 검증 자료도 직접 가져오기 전에는 기존 승인에 영향을 주지 않으며, 가져오면 기존 검토 기록이 비공개 백업 후 미승인 상태로 초기화됩니다. DNS 게시·집행은 실행하지 않습니다.</p>
          </section>
          <div class="split-view"><div class="surface review-list-panel"><div class="list-toolbar"><input id="review-search" type="search" placeholder="도메인 검색" aria-label="도메인 검색"><select id="review-filter" aria-label="검토 필터"><option value="all">전체 후보</option><option value="pending">미승인</option><option value="approved">승인</option><option value="expired">증거 만료</option></select></div><div id="review-list" class="review-list" aria-live="polite"></div></div>
          <div class="surface review-editor" id="review-editor"><div class="overline">MANUAL EVIDENCE REVIEW</div><div id="review-empty"><h2>검토할 항목 선택</h2><p>후보를 선택하면 증거 상태와 승인 양식을 표시합니다.</p></div><form id="review-form" hidden><div class="review-domain-label">DNS BLOCK SCOPE / SUBTREE</div><h2 id="review-domain">–</h2><div class="meta-grid"><div><small>위협 분류</small><strong id="review-threat">–</strong></div><div><small>증거 만료</small><strong id="review-expires">–</strong></div><div><small>증거 참조</small><strong id="review-ref">–</strong></div><div><small>출처</small><strong id="review-source">–</strong></div></div><div class="review-eligibility" id="review-eligibility" role="status">검증 증거 상태를 확인하세요.</div><label for="reviewer">검토자 식별명</label><input id="reviewer" maxlength="80" placeholder="별도로 확인 가능한 검토자"><label for="reason">승인 근거 및 검토 이유</label><textarea id="reason" maxlength="400" rows="4" placeholder="근거, 오탐 가능성 및 SUBTREE 범위 검토 내용 (승인 시 15자 이상)"></textarea><label class="check-row"><input id="approve" type="checkbox"><span>위협정보를 검토하고 해당 도메인 차단을 승인</span></label><label class="check-row"><input id="ack-subtree" type="checkbox"><span>해당 도메인과 모든 하위 도메인 차단 영향을 이해함</span></label><div class="action-row"><button class="button primary" type="submit">검토 기록 저장</button><span class="fine-print">저장만 수행 · 미배포</span></div></form></div></div>
        </section>
        <section class="view" data-panel="engine" hidden>
          <div class="section-top outside"><div><div class="overline">DECISION ENGINE / v0.8</div><h2>EXACT 위험도 제안 엔진</h2><p>EXACT QNAME 정책 제안을 위한 검토자 관리 설정입니다. DNS SUBTREE 차단 정책으로 자동 변환하지 않습니다.</p></div><span class="pill warning">비집행 제안</span></div>
          <div class="dashboard-grid two-equal"><div class="surface"><form id="engine-form"><div class="form-heading"><h3>정책 평가 조건</h3><span class="pill muted" id="engine-configured">미설정</span></div><div class="form-grid"><div><label for="engine-version">버전</label><input id="engine-version" placeholder="v0.8-operator" required></div><div><label for="engine-threshold">경고 임계값 (0–100)</label><input id="engine-threshold" type="number" min="0" max="100" step="1" value="70" required></div></div><label for="engine-admin">관리자 차단 목록 · 줄 단위</label><textarea id="engine-admin" rows="4" placeholder="blocked.example.org"></textarea><label for="engine-approved">승인된 악성 도메인 · 줄 단위</label><textarea id="engine-approved" rows="3"></textarea><label for="engine-official">공식 도메인 · 줄 단위</label><textarea id="engine-official" rows="3"></textarea><label for="engine-sources">신뢰 점수 출처 ID · 줄 단위</label><textarea id="engine-sources" rows="2" placeholder="lab-scanner"></textarea><div class="action-row"><button type="submit" class="button primary">제안 엔진 설정 저장</button></div></form></div>
          <div class="surface"><div class="overline">EXACT DOMAIN LOOKUP</div><h3>EXACT 제안 조회</h3><p class="muted-copy">저장된 정책 엔진 설정에서 대상 도메인의 기본 제안을 계산합니다. 별도 점수 근거나 실시간 DNS 질의를 조회하지 않으며, 입력된 목록만으로 제안을 평가합니다.</p><form id="evaluate-form"><label for="evaluate-domain">조회 대상 도메인</label><div class="inline-input"><input id="evaluate-domain" placeholder="example.org" required><button type="submit" class="button outline">평가</button></div></form><div id="evaluation-result" class="result-card"><div class="empty-symbol">◇</div><strong>평가 결과 없음</strong><p>도메인과 구성 설정을 입력하세요.</p></div><div class="divider"></div><div class="subtle-note"><strong>정책 범위 분리</strong><p>엔진 결과의 BLOCK은 EXACT 제안입니다. DNS가 집행하는 SUBTREE 차단과 동일하지 않으며 수동 검토를 대신하지 않습니다.</p></div></div></div>
        </section>
        <section class="view" data-panel="drafts" hidden>
          <div class="section-top outside"><div><div class="overline">DNS POLICY / UNSIGNED</div><h2>승인된 증거로 DNS 정책 초안 생성</h2><p>엔진이 만료·증거 해시·SUBTREE 승인 상태를 재검증하고 전체 교체용 JSON을 생성합니다.</p></div><span class="pill muted">별도 서명 필요</span></div>
          <div class="dashboard-grid two-equal"><div class="surface"><h3>신규 정책 초안 생성</h3><p class="muted-copy">수동 FQDN 또는 승인된 검증 증거를 미서명 전체 교체 정책으로 생성합니다.</p><div class="builder-flow manual-source-flow"><span>OpenPhish → GSB 검증·수동 승인</span><span>+</span><span>수동 FQDN</span><span>→</span><strong>미서명 정책 JSON</strong></div><p id="build-review-summary" class="form-status" role="status">검토 상태를 확인합니다.</p><form id="build-form"><div id="build-expired-section" hidden><p class="fine-print">다음 만료 승인을 제외하면 기존 차단이 철회될 수 있습니다. 저장된 승인은 변경하지 않습니다.</p><ul id="build-expired-list" class="fine-print"></ul><label class="check-row"><input type="checkbox" id="confirm-expired-exclusion"><span>위 만료 승인 목록을 이번 전체 교체 초안에서 제외하는 영향을 확인</span></label></div><label class="check-row" id="build-empty-section" hidden><input type="checkbox" id="confirm-empty-replacement"><span>모든 차단 철회를 위한 빈 전체 교체 초안 생성에 동의 (유효기간 15분, 별도 서명·게시 필요)</span></label><label class="check-row"><input type="checkbox" id="confirm-replacement" required><span>생성된 정책은 기존 정책 전체를 교체하는 스냅샷임을 확인</span></label><label class="check-row"><input type="checkbox" id="confirm-notice" required><span>사용자 안내·차단 영향 및 적용 범위를 확인</span></label><button type="submit" class="button primary wide">검증 후 정책 초안 생성 <span>→</span></button></form><p class="fine-print">서명·발행·DNS 업데이트는 이 버튼에서 실행되지 않습니다.</p></div><div class="surface"><div class="section-top"><h3>생성된 정책 목록</h3><span class="pill muted" id="draft-count">0</span></div><div id="draft-list" class="draft-list"></div></div></div>
          <section id="draft-impact" class="surface draft-impact-panel" aria-live="polite" aria-label="정책 변경 영향 비교" hidden></section>
        </section>
        <section class="view" data-panel="deployment" hidden>
          <div class="deployment-toolbar" aria-label="게시 정책 조회 대상">
            <div class="deployment-target"><label for="deployment-device-select">게시 정책 조회 대상</label><select id="deployment-device-select"><option value="">기본 게시 대상</option></select><span class="fine-print">조회 대상 변경은 DNS 설정을 변경하지 않습니다.</span></div>
            <div class="deployment-observation"><span class="overline">VERIFIED OBSERVATION</span><strong id="deployment-observed" aria-live="polite">조회 전</strong><span id="fleet-read-summary" class="fine-print">장치 보고 확인 전</span></div><button type="button" class="button outline" id="deployment-refresh">다시 조회 ↻</button>
          </div>
          <p id="publication-read-error" class="read-error" role="alert" hidden></p>

          <div class="dashboard-grid two-equal"><div class="surface"><div class="overline">01 / SIGNED PUBLICATION</div><div class="deployment-big-icon">⇧</div><h3 id="deployment-state">상태 확인 중</h3><p class="muted-copy" id="deployment-message">로컬 게시 파일을 검사합니다.</p><div class="fact-list"><div><span>대상 장치</span><strong id="deployment-device">–</strong></div><div><span>정책 시퀀스</span><strong id="deployment-sequence">–</strong></div><div><span>정책 SHA-256</span><strong class="mono" id="deployment-hash">–</strong></div><div><span>BLOCK 규칙</span><strong id="deployment-blocks">–</strong></div><div><span>만료 시각</span><strong id="deployment-expires">–</strong></div><div><span>서명자 키 ID</span><strong class="mono" id="deployment-key">–</strong></div></div></div><div class="surface"><div class="overline">02 / SELECTED NODE REPORT</div><div class="deployment-big-icon caution">◎</div><h3 id="edge-apply-state">실제 적용 상태: 미확인</h3><p class="muted-copy" id="edge-apply-note">서명된 게시 파일과 DNS 노드의 서명 보고는 별개입니다. 노드가 등록되고 상태 보고가 도착하면 아래에 시퀀스, 해시, 로컬 응답을 표시합니다.</p><div class="selected-node-facts fact-list"><div><span>선택 장치</span><strong id="edge-read-node">–</strong></div><div><span>서명 보고 수신</span><strong id="edge-read-received">–</strong></div><div><span>정책 신원 비교</span><strong id="edge-read-policy">–</strong></div><div><span>응답 비교 기준</span><strong id="edge-read-dns">–</strong></div></div><p class="fine-print">게시 파일 · 노드 로컬 검증 · LAN 단말 보호를 구분합니다.</p></div></div>
          <div class="surface published-list-surface"><div class="section-top published-header"><div><div class="overline">SIGNED BLOCKLIST</div><h2>게시된 DNS 규칙 <span id="published-count" class="inline-count">–</span></h2><p class="muted-copy" id="published-note">서명 검증된 로컬 게시 파일 기준 · DNS 실제 집행 여부 미확인</p></div><input id="published-search" type="search" aria-label="게시 도메인 검색" placeholder="도메인 검색"></div><div class="published-head"><span>도메인 / SUBTREE</span><span>결정</span><span>만료</span></div><div id="published-list" class="published-list"></div></div>
          <section class="surface nodes-panel" aria-labelledby="nodes-title"><p id="nodes-read-error" class="read-error" role="alert" hidden></p>
            <div class="section-top outside"><div><div class="overline">REGISTERED DNS NODES</div>
            <h2 id="nodes-title">DNS 노드 및 적용 증명</h2>
            <p>장치별 사설 IP, 별도 서명키, 보고 시각과 정책 시퀀스 일치를 확인합니다. 상태 보고는 DNS 노드가 원격 서버로 전송합니다.</p></div>
            <button type="button" class="button outline" id="nodes-refresh">상태 다시 조회</button></div>
            <div class="nodes-layout"><div><div class="node-list" id="nodes-list" aria-live="polite"></div></div>
            <details class="node-enrollment"><summary>새 DNS 노드 등록 <span>공개키 지문으로 신뢰 연결</span></summary><form id="node-register-form" class="node-form">
              <div class="overline">OPERATOR ENROLLMENT</div><h3>신규 DNS 노드 등록</h3>
              <p class="muted-copy">DNS 노드에서 생성한 상태 보고 전용 공개키를 먼저 관제 서버 신뢰 디렉터리에 안전하게 등록해야 합니다.</p>
              <label for="node-id">장치 ID</label><input id="node-id" placeholder="edge-69" maxlength="64" required>
              <label for="node-label">노드 식별명</label><input id="node-label" placeholder="Lab DNS / Rack A" maxlength="64" required>
              <label for="node-address">사설 DNS IPv4</label><input id="node-address" placeholder="192.168.7.69" inputmode="decimal" required>
              <label for="node-key">장치 Ed25519 공개키 SHA-256 (64자리)</label><input id="node-key" placeholder="64자리 소문자 16진 지문" pattern="[0-9a-f]{64}" maxlength="64" spellcheck="false" required>
              <button type="submit" class="button primary wide">신뢰키 확인 후 노드 등록 <span>→</span></button>
              <p class="fine-print">이 폼은 DNS 설정·방화벽을 변경하거나 사설 IP로 접속하지 않습니다. 별도 설치된 상태 전송기의 보고만 수신합니다.</p>
            </form></details></div>
            <div class="info-banner node-boundary-note"><span class="info-banner-icon">i</span><div><strong>LAN 적용 여부는 별도 관측 대상</strong><p>정책 해시가 일치하고 노드 로컬 DNS의 UDP/TCP 응답이 확인되어도, 모든 LAN 클라이언트가 해당 DNS 서버를 이용하고 있다는 뜻은 아닙니다.</p></div></div>
          </section>
        </section>
        <section class="view" data-panel="audit" hidden>
          <div class="section-top outside"><div><div class="overline">LOCAL ACTIVITY</div><h2>작업 기록</h2><p>초안 생성·검토 변경·제안 엔진 설정 이력입니다. 이 로그는 변조 방지된 승인 증명이 아닙니다.</p></div></div><div class="surface"><div class="audit-head"><span>UTC 시간</span><span>이벤트</span><span>참조</span></div><div id="audit-list" class="audit-list"></div></div>
        </section>
      </div>
    </main>
    <footer class="bottom-bar"><span>© ALEPH E TEAM · POLICY CONTROL PLANE</span><span>차단 정책 변경은 별도 승인과 서명이 필요합니다</span></footer>
  </div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite" hidden></div>
</body>
</html>"""

from .console_workbench import CONTEXT_HTML, ATTENTION_HTML, DIALOG_HTML, NODE_FILTER_HTML, REVIEW_SUMMARY_HTML, CSS as WORKBENCH_CSS
HTML = HTML.replace('<div class="verification-strip"', CONTEXT_HTML + '<div class="verification-strip"', 1)
HTML = HTML.replace('<section class="view" data-panel="overview">', '<section class="view" data-panel="overview">' + ATTENTION_HTML, 1)
HTML = HTML.replace('<div class="list-toolbar">', REVIEW_SUMMARY_HTML + '<div class="list-toolbar">', 1)
HTML = HTML.replace('<div class="node-list" id="nodes-list"', NODE_FILTER_HTML + '<div class="node-list" id="nodes-list"', 1)
HTML = HTML.replace('<div class="toast"', DIALOG_HTML + '<div class="toast"', 1)
HTML = HTML.replace('<span>UTC 시간</span>', '<span>현지 시각</span>')
CSS += '\n' + WORKBENCH_CSS

from .console_deployment import CSS as DEPLOYMENT_CSS
CSS += "\n" + DEPLOYMENT_CSS

from .console_observability import HTML as OBS_HTML, CSS as OBS_CSS
HTML = HTML.replace('<section class="surface fleet-summary"', OBS_HTML + '<section class="surface fleet-summary"', 1)
CSS += '\n' + OBS_CSS

from .console_manual import HTML as MANUAL_HTML, CSS as MANUAL_CSS
HTML = HTML.replace('<div class="dashboard-grid two-equal"><div class="surface"><h3>신규 정책 초안 생성</h3>', MANUAL_HTML + '<div class="dashboard-grid two-equal"><div class="surface"><h3>신규 정책 초안 생성</h3>', 1)
CSS += '\n' + MANUAL_CSS

from .console_palette import CSS as PALETTE_CSS
CSS += '\n' + PALETTE_CSS
