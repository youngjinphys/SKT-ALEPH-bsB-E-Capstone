"""Sample-qualified aggregate DNS quality; no private host or query data."""
JS = r'''
function qualitySummary(points,target='local'){
  if(!['local','upstream'].includes(target))throw Error('Unknown quality target');
  const finite=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
  const valid=p=>[2,4].includes(p.dns_attempts)&&Number.isInteger(p.dns_failures)&&p.dns_failures>=0&&p.dns_failures<=p.dns_attempts;
  const samples=points.filter(p=>!p.hourly_sample&&valid(p));
  const output={observations:samples.length,excludedHourly:points.filter(p=>p.hourly_sample).length,
    attempts:samples.reduce((n,p)=>n+p.dns_attempts,0),failures:samples.reduce((n,p)=>n+p.dns_failures,0)};
  output.failurePct=output.attempts?100*output.failures/output.attempts:null;
  for(const transport of ['udp','tcp']){
    const key=target+'_dns_'+transport+'_ms',values=[],differences=[];
    let before=null;
    for(const p of points){
      if(p.hourly_sample||!valid(p)||!finite(p[key])){before=null;continue;}
      values.push(p[key]);
      if(before&&!p.gap&&p.boot_id&&p.boot_id===before.boot_id
        &&p.at>before.at&&p.at-before.at<=150000
        &&p.received_at>before.received_at&&p.received_at-before.received_at<=150000)
        differences.push(Math.abs(p[key]-before[key]));
      before=p;
    }
    values.sort((a,b)=>a-b);
    const quantile=q=>values.length?values[Math.max(0,Math.ceil(values.length*q)-1)]:null;
    output[transport]={n:values.length,p50:quantile(.5),p95:values.length>=2?quantile(.95):null,
      variationMs:differences.length?differences.reduce((a,b)=>a+b,0)/differences.length:null,pairs:differences.length};
  }
  return output;
}
function renderQualitySummary(points,selected){
  const target=$('obs-quality-target').value, summary=qualitySummary(points,target);
  showText('obs-collector-version',selected?.report_format?'수집기 format '+selected.report_format:'수집기 미확인');
  showText('obs-quality-scope',(target==='local'?'로컬 DNS':'상위 DNS')+' RTT · 원본 '+summary.observations+'건 · 요약 제외 시간별 표본 '+summary.excludedHourly+'건. 보존 한도 내 관측이며 전체 트래픽 통계가 아닙니다.');
  for(const kind of ['udp','tcp']){
    const result=summary[kind];
    showText('obs-quality-'+kind+'-quantiles',obsValue(result.p50)+' / '+obsValue(result.p95));
    showText('obs-quality-'+kind+'-count','성공 '+result.n+'개 · 연속 쌍 '+result.pairs+'개 · ms'+(result.n<20?' · 적은 표본':''));
  }
  showText('obs-quality-variation',obsValue(summary.udp.variationMs)+' / '+obsValue(summary.tcp.variationMs));
  showText('obs-quality-window-fail',obsFinite(summary.failurePct)?obsValue(summary.failurePct)+'%':'—');
  showText('obs-quality-window-count',summary.attempts?summary.failures+' / '+summary.attempts+'회 · 로컬+상위 검사 전체':'능동 검사 원본 없음 · 품질 미확인');
  obsChart('obs-failures-chart',points,[{key:'dns_failure_pct',label:'검사 실패',kind:'udp'}],'%',100);
  obsChart('obs-nic-health-chart',points,[{key:'nic_errors_per_s',label:'오류',kind:'udp'},{key:'nic_drops_per_s',label:'드롭',kind:'tcp'}],'건/s');
}
'''
HTML = r'''<section class="obs-quality-summary" aria-labelledby="quality-summary-title">
<div class="obs-resource-heading"><div><div class="overline">NETWORK QUALITY / SAMPLED EVIDENCE</div><h3 id="quality-summary-title">구간별 응답 품질</h3><p id="obs-quality-scope">원본 관측이 없으면 품질을 판단하지 않습니다.</p></div><span id="obs-collector-version" class="pill muted">수집기 미확인</span></div>
<div class="quality-kpis">
<div><span>UDP p50 / p95</span><strong id="obs-quality-udp-quantiles">—</strong><small id="obs-quality-udp-count">성공한 표본 · ms</small></div>
<div><span>TCP p50 / p95</span><strong id="obs-quality-tcp-quantiles">—</strong><small id="obs-quality-tcp-count">성공한 표본 · ms</small></div>
<div><span>인접 RTT 변동 · UDP / TCP</span><strong id="obs-quality-variation">—</strong><small>연속 관측 RTT 차이의 절댓값 평균 · ms</small></div>
<div><span>보관된 원본 검사 실패율</span><strong id="obs-quality-window-fail">—</strong><small id="obs-quality-window-count">실패 수 / 검사 수 · 회선 패킷 손실률 아님</small></div>
</div>
<div class="obs-chart-grid">
<figure class="obs-chart-card"><figcaption><div><h3>DNS 검사 실패 비율</h3><span>각 보고의 실패/시도 · 2회 또는 4회 검사 · 일반 DNS 진단</span></div></figcaption><div id="obs-failures-chart" class="obs-chart"></div></figure>
<figure class="obs-chart-card"><figcaption><div><h3>인터페이스 오류·드롭 추이</h3><span>NIC 커널 카운터의 변화율 · 회선 손실률 아님</span></div><div class="obs-legend"><span class="obs-key udp">오류</span><span class="obs-key tcp">드롭</span></div></figcaption><div id="obs-nic-health-chart" class="obs-chart"></div></figure>
</div>
<details class="obs-quality-method"><summary>표본·통계 해석</summary><p>선택 구간에 남아 있는 원본 관측만 요약합니다. 시간별 마지막 표본은 과거 추세를 보기 위한 점이며 구간 평균이나 전체 요청 통계가 아니므로 요약에서 제외합니다. p50/p95는 성공한 RTT의 nearest-rank 분위수입니다. p95는 성공 표본 2개 이상에서만 표시하며, 20개 미만이면 특히 불안정합니다. 변동 값은 동일 부팅의 연속된 원본 관측 쌍에서만 계산하고, 실패·재시작·150초 초과 공백을 연결하지 않습니다. 이는 패킷 단위 jitter가 아닙니다.</p></details>
</section>'''
CSS = r'''
.quality-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}
.quality-kpis>div{min-width:0;border:1px solid rgba(108,180,205,.24);background:rgba(5,23,38,.46);border-radius:10px;padding:16px}
.quality-kpis span{font-size:11px;color:#b3cfde;display:block;line-height:1.6}
.quality-kpis strong{display:block;font-size:23px;color:#f0faff;font-variant-numeric:tabular-nums;margin:10px 0;overflow-wrap:anywhere;line-height:1.5}
.quality-kpis small{display:block;font-size:10px;color:#99b6c8;line-height:1.7}
.obs-quality-method{margin:15px 0 22px;color:#a4c0d1;font-size:11px;line-height:1.8}
.obs-quality-method summary{cursor:pointer;padding:8px 0;min-height:32px}.obs-quality-method p{max-width:105ch}
.obs-line.tcp{stroke-dasharray:6 4}.obs-point:focus{stroke:#fff;stroke-width:2;outline:2px solid #fff;outline-offset:2px}
@media(max-width:1000px){.quality-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:520px){.quality-kpis{gap:8px}.quality-kpis>div{padding:12px}.quality-kpis strong{font-size:18px}.obs-quality-method{font-size:12px}}
@media(forced-colors:active){.quality-kpis>div{background:Canvas;border-color:CanvasText}.quality-kpis span,.quality-kpis strong,.quality-kpis small{color:CanvasText}.obs-point:focus{stroke:Highlight;outline-color:Highlight}}
'''
