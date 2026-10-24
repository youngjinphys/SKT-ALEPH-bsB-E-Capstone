/* 독립 안내 포털: 외부 요청·쿠키·로컬 저장소·사용자 입력 기반 리다이렉트 없음. */
(() => {
  'use strict';

  // 신뢰하지 않는 URL 쿼리·해시로 verdict/점수/도메인/목적지를 변경하지 않습니다.
  const byId = (id) => document.getElementById(id);
  const notice = byId('action-status');
  const close = byId('close-tab');
  if (close) {
    close.addEventListener('click', () => {
      if (notice) notice.textContent = '브라우저가 스크립트로 연 탭만 닫도록 허용할 수 있습니다. 닫히지 않으면 이 탭을 직접 닫아 주세요.';
      window.close();
    });
  }

  const dialog = byId('continue-dialog');
  const openDialog = byId('continue-button');
  if (dialog && openDialog) {
    openDialog.addEventListener('click', () => {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else if (notice) notice.textContent = '이 시연 페이지에는 위험 사이트로 이동하거나 DNS 정책을 해제하는 기능이 없습니다.';
    });
    dialog.querySelector('[data-close]')?.addEventListener('click', () => dialog.close());
  }

  const form = byId('report-form');
  if (!form) return;

  const draftBox = byId('draft-box');
  const draftText = byId('draft-text');
  const formStatus = byId('form-status');
  const error = byId('form-error');
  const domain = byId('reported-domain');
  const message = byId('reported-reason');
  const copy = byId('copy-draft');
  const submitButton = form.querySelector('button[type=submit]');
  if (submitButton) submitButton.disabled = false;

  const validDomain = (value) => {
    if (!value) return true;
    if (value.length > 253 || /[\s\/@:?#\\]/u.test(value)) return false;
    const labels = value.split('.');
    if (labels.length < 2) return false;
    return labels.every((label) => label.length <= 63 && /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(label));
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault(); // 실제 수집 서버가 없어 전송하지 않습니다.
    if (error) { error.textContent = ''; error.hidden = true; }
    if (formStatus) formStatus.textContent = '';
    if (!domain || !message || !draftText || !draftBox) return;

    const hostname = domain.value.trim();
    const reason = message.value.trim();
    if (!validDomain(hostname)) {
      if (error) { error.hidden = false; error.textContent = '도메인에는 URL이나 경로가 아닌 ASCII 도메인 이름만 입력해 주세요. 예: example.test'; }
      domain.focus();
      draftBox.hidden = true;
      return;
    }
    if (reason.length < 10 || reason.length > 1000) {
      if (error) { error.hidden = false; error.textContent = '신고 사유를 10~1,000자로 작성해 주세요.'; }
      message.focus();
      draftBox.hidden = true;
      return;
    }

    const kind = document.body.dataset.mode === 'warn' ? '경고 표시' : '차단 표시';
    draftText.value = `오탐 검토 요청 (미제출 초안)\n유형: ${kind}\n도메인(본인 입력): ${hostname || '미입력'}\n사유: ${reason}\n\n[주의] 서버로 전송되지 않았습니다. 담당자에게 별도 전달해야 합니다.`;
    draftBox.hidden = false;
    if (formStatus) formStatus.textContent = '신고 초안을 만들었습니다. 실제 접수된 것은 아닙니다. 검토 담당자에게 별도로 전달해 주세요.';
  });

  copy?.addEventListener('click', async () => {
    if (!draftText?.value) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard API unavailable');
      await navigator.clipboard.writeText(draftText.value);
      if (formStatus) formStatus.textContent = '초안을 복사했습니다. 실제 접수된 것은 아닙니다.';
    } catch {
      draftText.focus();
      draftText.select();
      if (formStatus) formStatus.textContent = '자동 복사를 사용할 수 없습니다. 선택된 내용을 직접 복사해 주세요.';
    }
  });
})();
