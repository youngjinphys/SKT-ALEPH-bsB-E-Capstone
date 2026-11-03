"""Bundled static console shell; intentionally no external assets or inline scripts."""
from .console_style import CSS
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
<div class="shell">
  <aside class="sidebar" aria-label="관제 탐색">
    <div class="brand"><div class="brand-mark"><span class="brand-orbit"></span><span class="brand-core"></span></div><div><strong>ALEPH<span class="brand-asterisk">✳</span></strong><small>PROTECTIVE DNS</small></div></div>
    <div class="side-caption">WORKSPACE</div>
    <nav class="side-nav" aria-label="주요 메뉴">
      <button class="nav-item active" data-view="overview"><span class="nav-icon">◫</span>운영 개요</button>
      <button class="nav-item" data-view="reviews"><span class="nav-icon">◎</span>위협 검토 <span class="nav-count" id="nav-review-count">–</span></button>
      <button class="nav-item" data-view="engine"><span class="nav-icon">◇</span>정책 제안 엔진</button>
      <button class="nav-item" data-view="drafts"><span class="nav-icon">▤</span>정책 초안</button>
      <button class="nav-item" data-view="deployment"><span class="nav-icon">⇧</span>배포 현황</button>
      <button class="nav-item" data-view="audit"><span class="nav-icon">≡</span>작업 기록</button>
    </nav>
    <div class="sidebar-bottom"><div class="security-card"><div class="security-icon">◈</div><div><strong>분리된 보안 경계</strong><small>검토·생성 / 서명·배포 분리</small></div></div><div class="sidebar-foot">E TEAM <span>•</span> OPERATOR CONSOLE</div></div>
  </aside>
  <div class="main-column">
    <header class="topbar">
      <div class="crumb"><span>ALEPH</span><span class="crumb-sep">/</span><span id="crumb-current">Operations</span></div>
      <div class="topbar-actions"><span class="connection-dot" id="connection-dot"></span><span class="connection" id="connection-text">인증 필요</span><button class="icon-button" type="button" id="refresh-button" title="데이터 새로고침" aria-label="데이터 새로고침">↻</button><button class="quiet-button" type="button" id="logout-button" hidden>잠금</button></div>
    </header>
    <main class="content" id="main-content">
      <section class="login-wrap" id="login-view" aria-labelledby="login-title">
        <div class="login-card"><div class="login-symbol">◈</div><div class="eyebrow">SECURE OPERATOR ACCESS</div><h1 id="login-title">관제 콘솔에 연결</h1><p>서버 로컬 토큰으로 인증합니다. 토큰은 브라우저 메모리에만 유지되며 저장하지 않습니다.</p>
        <form id="login-form"><label for="token">운영자 액세스 토큰</label><input id="token" type="password" autocomplete="off" spellcheck="false" placeholder="32자 이상 발급한 토큰" required><button type="submit" class="button primary wide">안전하게 연결 <span>→</span></button></form>
        <div class="login-note"><span>●</span> 로컬 바인딩 · API 접근 제어 · DNS 무변경</div></div>
      </section>
      <div id="authorized" hidden>
        <div class="hero"><div><div class="eyebrow"><span class="eyebrow-line"></span> SECURITY OPERATIONS CENTER <span class="hero-date" id="hero-date"></span></div><h1 id="page-title">운영 개요</h1><p class="lead" id="page-description">정책 근거, 승인, 서명 게시 상태를 하나의 화면에서 확인합니다.</p></div><div class="hero-tools"><span class="environment-label"><i></i> LOCAL CONTROL PLANE</span></div></div>
        <section class="view" data-panel="overview">
          <div class="stats-grid">
            <article class="stat-card"><div class="stat-caption"><span>검토 후보</span><span class="stat-symbol">◎</span></div><div class="stat-value" id="stat-candidates">–</div><p>검증된 위협 URL 기반 후보</p></article>
            <article class="stat-card"><div class="stat-caption"><span>승인 검토</span><span class="stat-symbol accent">✓</span></div><div class="stat-value" id="stat-approved">–</div><p>SUBTREE 범위 수동 승인</p></article>
            <article class="stat-card"><div class="stat-caption"><span>유효 증거</span><span class="stat-symbol">◷</span></div><div class="stat-value" id="stat-fresh">–</div><p>조회 결과 유효시간 내</p></article>
            <article class="stat-card"><div class="stat-caption"><span>미서명 초안</span><span class="stat-symbol">▤</span></div><div class="stat-value" id="stat-drafts">–</div><p>서명·배포 대기 중인 산출물</p></article>
          </div>
          <div class="dashboard-grid">
            <article class="surface wide-surface"><div class="section-top"><div><div class="overline">POLICY LIFECYCLE</div><h2>정책 처리 파이프라인</h2></div><span class="pill muted">승인 절차 분리</span></div><div class="pipeline">
              <div class="stage"><div class="stage-number">01</div><strong>위협 증거</strong><small>OpenPhish · GSB 검증</small></div><div class="stage-arrow">→</div><div class="stage"><div class="stage-number">02</div><strong>사람 검토</strong><small>증거·범위 명시 승인</small></div><div class="stage-arrow">→</div><div class="stage"><div class="stage-number">03</div><strong>정책 초안</strong><small>실제 엔진으로 생성</small></div><div class="stage-arrow">→</div><div class="stage stage-final"><div class="stage-number">04</div><strong>서명·배포</strong><small>별도 권한으로 발행</small></div>
            </div><div class="panel-footer"><span>최근 검증 데이터</span><strong id="overview-verified">확인 중</strong><button class="text-button" data-go="reviews">검토 목록 보기 →</button></div></article>
            <article class="surface"><div class="section-top"><div><div class="overline">PUBLISHER HEALTH</div><h2>게시 정책 상태</h2></div><span class="status-dot"></span></div><div class="deployment-summary"><div class="deployment-status-icon">◈</div><strong id="overview-deploy-state">확인 중</strong><p id="overview-deploy-detail">서명된 파일과 신뢰키를 검사합니다.</p></div><div class="panel-footer"><span>DNS 적용 검증</span><strong class="warning-text">미확인</strong><button class="text-button" data-go="deployment">자세히 보기 →</button></div></article>
          </div>
          <div class="info-banner"><span class="info-banner-icon">i</span><div><strong>검토자가 최종 승인자가 되는 구조를 피합니다.</strong><p>이 콘솔은 검토 기록과 미서명 정책을 생성합니다. 운영 배포에는 별도 서명자의 확인과 root 발행이 필요합니다.</p></div></div>
        </section>
        <section class="view" data-panel="reviews" hidden>
          <div class="section-top outside"><div><div class="overline">THREAT INTELLIGENCE</div><h2>검증 증거 검토</h2><p>실제 조회 데이터의 도메인·위협 유형·만료시간을 확인한 후 승인합니다. 원본 URL은 노출하지 않습니다.</p></div><button class="button outline" id="reset-reviews">검토 기록 초기화</button></div>
          <div class="split-view"><div class="surface review-list-panel"><div class="list-toolbar"><input id="review-search" type="search" placeholder="도메인 검색" aria-label="도메인 검색"><select id="review-filter" aria-label="검토 필터"><option value="all">전체 후보</option><option value="pending">미승인</option><option value="approved">승인</option><option value="expired">증거 만료</option></select></div><div id="review-list" class="review-list" aria-live="polite"></div></div>
          <div class="surface review-editor" id="review-editor"><div class="overline">MANUAL REVIEW</div><div id="review-empty"><h2>검토할 항목 선택</h2><p>후보를 선택하면 증거 상태와 승인 양식을 표시합니다.</p></div><form id="review-form" hidden><div class="review-domain-label">DOMAIN / SUBTREE</div><h2 id="review-domain">–</h2><div class="meta-grid"><div><small>위협 분류</small><strong id="review-threat">–</strong></div><div><small>증거 만료</small><strong id="review-expires">–</strong></div><div><small>증거 참조</small><strong id="review-ref">–</strong></div><div><small>출처</small><strong id="review-source">–</strong></div></div><label for="reviewer">검토자 식별명</label><input id="reviewer" maxlength="80" placeholder="별도로 확인 가능한 검토자"><label for="reason">승인 근거 및 검토 이유</label><textarea id="reason" maxlength="400" rows="4" placeholder="근거, 오탐 가능성 및 SUBTREE 범위 검토 내용 (승인 시 15자 이상)"></textarea><label class="check-row"><input id="approve" type="checkbox"><span>위협정보를 검토하고 해당 도메인 차단을 승인</span></label><label class="check-row"><input id="ack-subtree" type="checkbox"><span>해당 도메인과 모든 하위 도메인 차단 영향을 이해함</span></label><div class="action-row"><button class="button primary" type="submit">검토 기록 저장</button><span class="fine-print">저장만 수행 · 미배포</span></div></form></div></div>
        </section>
        <section class="view" data-panel="engine" hidden>
          <div class="section-top outside"><div><div class="overline">DECISION ENGINE / v0.8</div><h2>제안 엔진 설정</h2><p>EXACT QNAME 정책 제안을 위한 검토자 관리 설정입니다. DNS SUBTREE 차단 정책으로 자동 변환하지 않습니다.</p></div><span class="pill warning">비집행 제안</span></div>
          <div class="dashboard-grid two-equal"><div class="surface"><form id="engine-form"><div class="form-heading"><h3>정책 평가 조건</h3><span class="pill muted" id="engine-configured">미설정</span></div><div class="form-grid"><div><label for="engine-version">버전</label><input id="engine-version" placeholder="v0.8-operator" required></div><div><label for="engine-threshold">경고 임계값 (0–100)</label><input id="engine-threshold" type="number" min="0" max="100" step="1" value="70" required></div></div><label for="engine-admin">관리자 차단 목록 · 줄 단위</label><textarea id="engine-admin" rows="4" placeholder="blocked.example.org"></textarea><label for="engine-approved">승인된 악성 도메인 · 줄 단위</label><textarea id="engine-approved" rows="3"></textarea><label for="engine-official">공식 도메인 · 줄 단위</label><textarea id="engine-official" rows="3"></textarea><label for="engine-sources">신뢰 점수 출처 ID · 줄 단위</label><textarea id="engine-sources" rows="2" placeholder="lab-scanner"></textarea><div class="action-row"><button type="submit" class="button primary">제안 엔진 설정 저장</button></div></form></div>
          <div class="surface"><div class="overline">EXACT DOMAIN LOOKUP</div><h3>정책 제안 시뮬레이터</h3><p class="muted-copy">저장된 정책 엔진 설정에서 대상 도메인의 기본 제안을 계산합니다. 실제 점수 근거나 실시간 DNS 질의를 조회하지 않습니다.</p><form id="evaluate-form"><label for="evaluate-domain">조회 대상 도메인</label><div class="inline-input"><input id="evaluate-domain" placeholder="example.org" required><button type="submit" class="button outline">평가</button></div></form><div id="evaluation-result" class="result-card"><div class="empty-symbol">◇</div><strong>평가 결과 없음</strong><p>도메인과 구성 설정을 입력하세요.</p></div><div class="divider"></div><div class="subtle-note"><strong>정책 범위 분리</strong><p>엔진 결과의 BLOCK은 EXACT 제안입니다. DNS가 집행하는 SUBTREE 차단과 동일하지 않으며 수동 검토를 대신하지 않습니다.</p></div></div></div>
        </section>
        <section class="view" data-panel="drafts" hidden>
          <div class="section-top outside"><div><div class="overline">POLICY BUILDER</div><h2>승인 증거에서 정책 생성</h2><p>엔진이 만료·증거 해시·SUBTREE 승인 상태를 재검증하고 전체 교체용 JSON을 생성합니다.</p></div><span class="pill muted">서명 전 검토</span></div>
          <div class="dashboard-grid two-equal"><div class="surface"><h3>신규 정책 초안 생성</h3><p class="muted-copy">기존 승인 검토 기록을 사용합니다. 승인 증거가 만료되면 빌드가 거부됩니다.</p><div class="builder-flow"><span>Verified intel</span><span>→</span><span>Human review</span><span>→</span><strong>Unsigned JSON</strong></div><form id="build-form"><label class="check-row"><input type="checkbox" id="confirm-replacement" required><span>생성된 정책은 기존 정책 전체를 교체하는 스냅샷임을 확인</span></label><label class="check-row"><input type="checkbox" id="confirm-notice" required><span>사용자 안내·차단 영향 및 적용 범위를 확인</span></label><button type="submit" class="button primary wide">검증 후 정책 초안 생성 <span>→</span></button></form><p class="fine-print">서명·발행·DNS 업데이트는 이 버튼에서 실행되지 않습니다.</p></div><div class="surface"><div class="section-top"><h3>생성된 정책 목록</h3><span class="pill muted" id="draft-count">0</span></div><div id="draft-list" class="draft-list"></div></div></div>
        </section>
        <section class="view" data-panel="deployment" hidden>
          <div class="section-top outside"><div><div class="overline">SIGNED DISTRIBUTION</div><h2>배포 상태 검증</h2><p>게시 파일 서명·시퀀스·유효기간을 확인합니다. DNS 실제 반영은 별도 노드 검증이 필요합니다.</p></div><button class="button outline" id="deployment-refresh">상태 다시 조회</button></div>
          <div class="dashboard-grid two-equal"><div class="surface"><div class="overline">PUBLISHER</div><div class="deployment-big-icon">⇧</div><h3 id="deployment-state">상태 확인 중</h3><p class="muted-copy" id="deployment-message">로컬 게시 파일을 검사합니다.</p><div class="fact-list"><div><span>대상 장치</span><strong id="deployment-device">–</strong></div><div><span>정책 시퀀스</span><strong id="deployment-sequence">–</strong></div><div><span>서명 파일의 정책 해시</span><strong class="mono" id="deployment-hash">–</strong></div><div><span>BLOCK 규칙</span><strong id="deployment-blocks">–</strong></div><div><span>만료 시각</span><strong id="deployment-expires">–</strong></div></div></div><div class="surface"><div class="overline">EDGE DNS</div><div class="deployment-big-icon caution">◎</div><h3>실제 적용 상태: 미확인</h3><p class="muted-copy">서명된 정책 파일이 존재하는 것과 LAN의 DNS가 해당 정책을 적용했다는 것은 별개의 사건입니다. 현재 콘솔은 DNS의 root 전용 적용 영수증이나 실시간 질의 검증을 수신하지 않습니다.</p><div class="subtle-note"><strong>배포 절차</strong><div class="check-timeline"><div><span>1</span>정책 초안 다운로드 및 독립 검토</div><div><span>2</span>분리된 서명자 계정에서 Ed25519 서명</div><div><span>3</span>root 발행자의 promote 미리보기·적용</div><div><span>4</span>DNS fetch / apply와 실 단말 검증</div></div></div></div></div>
          <div class="surface published-list-surface"><div class="section-top published-header"><div><div class="overline">SIGNED BLOCKLIST</div><h2>게시된 DNS 규칙</h2><p class="muted-copy">서명 검증된 로컬 게시 파일 기준 · DNS 집행 여부 별도 확인</p></div><input id="published-search" type="search" aria-label="게시 도메인 검색" placeholder="도메인 검색"></div><div class="published-head"><span>도메인 / SUBTREE</span><span>결정</span><span>만료</span></div><div id="published-list" class="published-list"></div></div>
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
