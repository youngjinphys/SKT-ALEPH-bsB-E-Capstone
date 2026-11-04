/** Public extract: the private endpoint and local stub values are redacted. */
export function ServerDnsObservation(){
 return <section className="server-dns-observation" aria-label="server 실제 DNS 질의 결과">
  <div className="server-dns-heading"><strong>실제 server 질의</strong><span>2026.11.04 · 02:42 UTC</span></div>
  <p>google.com · example.com A × 기본 / 사설 DNS × UDP / TCP</p>
  <p className="server-dns-result"><b>8건 모두 NOERROR · 주소 반환</b><br/>사설 DNS의 google.com 차단 응답은 관측되지 않음</p>
  <div className="server-dns-commands" aria-label="TCP 질의와 응답">
   <div><code>dig google.com A +time=2 +tries=1 +tcp</code><small>기본 로컬 stub · NOERROR · A 1개</small></div>
   <div><code>{'dig @${PRIVATE_DNS} google.com A +time=2 +tries=1 +tcp'}</code><small>사설 DNS · NOERROR · A 6개</small></div>
  </div>
  <p className="server-dns-note">PRIVATE_DNS는 실제 사설 주소를 가린 변수입니다.<br/>stub 후단·캐시와 현재 정책 상태는 미확인</p>
  <a href="/capstone/evidence/dns-query-20261104.txt" target="_blank" rel="noopener noreferrer">공개 발췌: 질의·응답과 원본 해시 ↗</a>
 </section>;
}
