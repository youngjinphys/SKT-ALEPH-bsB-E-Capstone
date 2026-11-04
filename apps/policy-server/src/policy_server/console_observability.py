"""Accessible aggregate telemetry workspace; shared local/cloud shell."""
HTML = r'''<section class="observatory surface" id="observatory" aria-labelledby="obs-title" data-status="waiting">
  <div class="obs-heading"><div><div class="overline">DNS TELEMETRY / LIVE OBSERVATIONS</div><h2 id="obs-title">네트워크의 현재를, 근거로.</h2><p>서명된 노드 보고에서 읽은 상태와 변화입니다.</p></div><div class="obs-live-tools"><span id="obs-live" class="obs-live" role="status" aria-live="polite">인증 후 조회</span><button type="button" class="button outline" id="obs-pause" aria-pressed="false">자동 갱신 일시정지</button></div></div>
  <div class="obs-toolbar"><label>DNS 노드<select id="obs-device" aria-label="관측 DNS 노드"><option value="">등록된 노드 없음</option></select></label><label>관측 구간<select id="obs-window" aria-label="관측 구간"><option value="15">최근 15분</option><option value="60" selected>최근 1시간</option><option value="1440">최근 24시간</option></select></label><div class="obs-time"><strong id="obs-age">수집 보고 대기</strong><small id="obs-cadence">화면 10초 · 노드 기본 60초 간격</small></div><button type="button" class="text-button" id="obs-export" disabled>집계 CSV ↓</button></div>
  <p id="obs-alert" class="obs-alert" role="status">DNS 노드가 보낸 실제 관측을 기다리고 있습니다. 예시 데이터를 표시하지 않습니다.</p>
  <div class="obs-kpis">
    <div><span>UDP 검사 지연</span><strong id="obs-udp">—</strong><small>평균 왕복시간 · ms</small></div>
    <div><span>TCP 검사 지연</span><strong id="obs-tcp">—</strong><small>평균 왕복시간 · ms</small></div>
    <div><span>캐시 적중 비율</span><strong id="obs-hit">—</strong><small>인접 관측의 증가분 · %</small></div>
    <div><span>캐시 조회율</span><strong id="obs-rate">—</strong><small>hits + misses 증가분 / s</small></div>
  </div>
  <div class="obs-chart-grid"><figure class="obs-chart-card"><figcaption><div><h3>DNS 응답 지연 추이</h3><span>승인된 차단 canary · 사용자 전체 트래픽 아님</span></div><div class="obs-legend"><span class="obs-key udp">UDP</span><span class="obs-key tcp">TCP</span></div></figcaption><div id="obs-latency-chart" class="obs-chart" aria-live="off"></div></figure>
    <figure class="obs-chart-card"><figcaption><div><h3>운영 상태 추이</h3><span id="obs-metric-description">MemAvailable 기반 메모리 사용률</span></div><select id="obs-metric" aria-label="운영 상태 그래프 지표"><option value="cache_lookups_per_s">캐시 조회 / s</option><option value="cache_hit_pct">캐시 적중 %</option><option value="cpu_used_pct">CPU 사용률 %</option><option value="dns_failure_pct">능동 DNS 검사 실패 %</option><option value="nic_drops_per_s">NIC 드롭 / s</option><option value="memory_used_pct" selected>메모리 %</option><option value="load_1m">1분 load</option><option value="report_delay_s">전송 시차 s</option></select></figcaption><div id="obs-metric-chart" class="obs-chart" aria-live="off"></div></figure></div>
  <div class="obs-resource-heading"><div><div class="overline">HOST RESOURCES / NETWORK QUALITY</div><h3>DNS 서버 자원과 연결 품질</h3><p id="obs-resource-note">v4 수집기의 실제 관측을 기다립니다. 비어 있는 값은 0이 아닙니다.</p></div><span id="obs-interface" class="pill muted">NIC 미선택</span></div>
  <div class="obs-kpis obs-resource-kpis"><div><span>CPU 사용률</span><strong id="obs-cpu">—</strong><small>동일 부팅의 인접 CPU tick 차분</small></div><div><span>수신 / 송신</span><strong class="obs-compact-value" id="obs-traffic">—</strong><small>선택한 NIC 전체 · KiB/s</small></div><div><span>DNS 검사 실패</span><strong id="obs-quality-fail">—</strong><small id="obs-quality-count">능동 검사 표본 · 회선 손실률 아님</small></div><div><span>NIC 오류 / 드롭</span><strong class="obs-compact-value" id="obs-link-errors">—</strong><small>커널 카운터 증가율 / s</small></div></div>
  <div class="obs-chart-grid obs-resources-grid">
    <figure class="obs-chart-card"><figcaption><div><h3>CPU 사용률</h3><span>0–100% · iowait 포함 유휴 제외 · 재부팅/공백 구간 미연결</span></div></figcaption><div id="obs-cpu-chart" class="obs-chart"></div></figure>
    <figure class="obs-chart-card"><figcaption><div><h3>메모리·디스크 사용률</h3><span>MemAvailable 기반 / 수집 경로의 파일시스템</span></div><div class="obs-legend"><span class="obs-key udp">메모리</span><span class="obs-key tcp">디스크</span></div></figcaption><div id="obs-host-chart" class="obs-chart"></div></figure>
    <figure class="obs-chart-card"><figcaption><div><h3>인터페이스 송수신량</h3><span>DNS 전용 트래픽이나 회선 최대속도가 아닌 NIC 전체 관측</span></div><div class="obs-legend"><span class="obs-key udp">RX</span><span class="obs-key tcp">TX</span></div></figcaption><div id="obs-traffic-chart" class="obs-chart"></div></figure>
    <figure class="obs-chart-card"><figcaption><div><h3>일반 DNS 응답 품질</h3><span>example.org A 양성 응답 · --quality-probes 선택 수집</span></div><select id="obs-quality-target" aria-label="DNS 품질 측정 대상"><option value="local">로컬 DNS</option><option value="upstream">상위 DNS</option></select></figcaption><div id="obs-quality-chart" class="obs-chart"></div></figure>
  </div>
  <details class="obs-table-wrap"><summary>자원·네트워크 관측 수치</summary><p>첫 보고에서는 CPU 및 트래픽 변화율을 계산하지 않습니다. NIC 교체·재부팅·150초 초과 공백 뒤의 차분은 표시하지 않습니다. 드롭 카운터는 종단 간 패킷 손실률이 아닙니다. 일반 DNS 검사는 정책 적용 여부와 별개이며, 검사 도메인이 차단되면 실패로 집계될 수 있습니다.</p><div class="obs-table-scroll"><table><caption>선택된 노드의 자원 및 DNS 품질 표본</caption><thead><tr><th>시각</th><th>CPU %</th><th>RX KiB/s</th><th>TX KiB/s</th><th>로컬 UDP ms</th><th>로컬 TCP ms</th><th>상위 UDP ms</th><th>검사 실패/전체</th></tr></thead><tbody id="obs-resource-table"></tbody></table></div></details>
  <div class="obs-details"><div><span>메모리 사용</span><meter id="obs-memory-meter" min="0" max="100" value="0" hidden aria-label="메모리 사용률"></meter><strong id="obs-memory">—</strong></div><div><span>저장 영역 사용</span><meter id="obs-disk-meter" min="0" max="100" value="0" hidden aria-label="저장 영역 사용률"></meter><strong id="obs-disk">—</strong></div><div><span>가동 시간</span><strong id="obs-uptime">—</strong></div><div><span>정책 유효기간</span><strong id="obs-policy-ttl">—</strong></div></div>
  <div class="obs-footer"><span id="obs-samples">관측 0건</span><span>개인별 질의·방문 도메인 수집 안 함</span><span>공백은 보간하지 않습니다</span></div>
  <details class="obs-table-wrap"><summary>관측 수치 및 수집 범위</summary><p>최신 48건과 시간별 마지막 관측 최대 24건을 보관합니다. 시간별 점은 평균이 아니며, 과거에 보고가 없던 구간은 비어 있습니다. 캐시 통계는 선택 수집이며 검사 질의도 포함할 수 있습니다. 서명 확인은 노드의 보고 출처 확인이지 LAN 전체 보호의 증명이 아닙니다.</p><div class="obs-table-scroll"><table><caption>선택된 노드와 시간 구간의 집계 관측</caption><thead><tr><th>보고 시각</th><th>UDP ms</th><th>TCP ms</th><th>캐시 /s</th><th>적중 %</th><th>메모리 %</th><th>검사 오류</th></tr></thead><tbody id="obs-table"></tbody></table></div></details>
</section>'''
CSS = r'''
.observatory{--obs-cyan:#72e1e3;--obs-violet:#b3a8fa;padding:28px;margin:0 0 22px;background:linear-gradient(125deg,rgba(17,43,62,.97),rgba(10,23,41,.98));border:1px solid rgba(107,180,206,.32);position:relative;overflow:hidden}
.obs-resource-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;border-top:1px solid #294457;padding-top:25px;margin-top:26px}.obs-resource-heading h3{margin:8px 0;font-size:20px}.obs-resource-heading p{font-size:11px;color:#94b5c8;margin:0;line-height:1.7}.obs-resource-kpis .obs-compact-value{font-size:23px;line-height:1.7}.obs-resources-grid{grid-template-columns:1fr 1fr}.obs-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}.obs-heading h2{font-size:25px;letter-spacing:-.045em;margin:10px 0 8px}.obs-heading p{font-size:12px;color:#9bb8cc;margin:0}.obs-live-tools{display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:flex-end}.obs-live{font-size:10px;color:#93cbd3;white-space:nowrap;border:1px solid #315565;border-radius:30px;padding:7px 12px;background:#13313e}.obs-live::before{content:'';display:inline-block;width:6px;height:6px;margin-right:7px;border-radius:50%;background:currentColor}.obs-live[data-state=error],.obs-live[data-state=offline]{color:#efb588;border-color:#785c40}.obs-live[data-state=paused]{color:#acbdcb}.obs-live[data-state=fetching]::before{animation:obs-fetch .8s ease-in-out infinite alternate}.obs-toolbar{display:flex;align-items:end;gap:14px;border-block:1px solid rgba(104,157,186,.2);margin-top:23px;padding:15px 0}.obs-toolbar label{width:190px;margin:0;font-size:11px;display:grid;gap:7px}.obs-toolbar label:nth-child(2){width:135px}.obs-toolbar select{min-height:37px}.obs-time{margin-left:auto;text-align:right;padding-bottom:3px}.obs-time strong{font-size:11px;color:#c5dce5;display:block}.obs-time small{font-size:10px;color:#809eb3;display:block;margin-top:6px}.obs-toolbar .text-button{margin:0;padding-bottom:12px}.obs-alert{font-size:11px;line-height:1.6;color:#a8c5d3;border-left:2px solid #527d93;padding:10px 13px;margin:16px 0;background:rgba(3,18,32,.35)}.obs-alert[data-state=warning]{border-color:#e7ba76;color:#f0d1a6;background:rgba(106,69,24,.15)}.obs-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:23px 0 25px;gap:18px}.obs-kpis>div{border-right:1px solid #294457;padding:0 12px 0 0}.obs-kpis>div:last-child{border:0}.obs-kpis span{font-size:11px;color:#a0bdcf;display:block}.obs-kpis strong{font-size:34px;letter-spacing:-.04em;font-variant-numeric:tabular-nums;display:block;margin:11px 0 5px;color:#effbff}.obs-kpis small{font-size:9px;color:#809fb2;line-height:1.5;display:block}.obs-kpis .obs-changed{animation:obs-change .5s ease-out}.obs-chart-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:16px}.obs-chart-card{margin:0;background:rgba(5,18,32,.5);border:1px solid rgba(111,160,187,.23);border-radius:12px;overflow:hidden;min-width:0}.obs-chart-card figcaption{padding:18px 18px 6px;display:flex;justify-content:space-between;gap:12px;align-items:start}.obs-chart-card h3{font-size:14px;margin:0 0 7px}.obs-chart-card figcaption span{font-size:9px;color:#859fb4;line-height:1.5}.obs-chart-card select{width:130px;min-height:32px;padding:7px 9px;font-size:10px}.obs-legend{display:flex;gap:12px;white-space:nowrap}.obs-chart-card .obs-key{color:#b7cfdb;display:flex;align-items:center;gap:5px}.obs-key:before{content:'';display:inline-block;width:10px;height:2px;background:var(--obs-cyan)}.obs-key.tcp:before{background:var(--obs-violet)}.obs-chart{min-height:220px;padding:0 7px 8px}.obs-chart svg{width:100%;height:auto;display:block;overflow:visible}.obs-axis{stroke:#284052;stroke-width:1}.obs-gridline{stroke:#223649;stroke-width:1;stroke-dasharray:3 5}.obs-svg-text{fill:#93adbd;font-family:inherit;font-size:11px}.obs-line{fill:none;stroke-width:2;vector-effect:non-scaling-stroke;stroke-linejoin:round;stroke-linecap:round}.obs-line.udp{stroke:var(--obs-cyan)}.obs-line.tcp{stroke:var(--obs-violet);stroke-dasharray:5 3}.obs-point{stroke-width:1;stroke:#0b1c2c;fill:var(--obs-cyan)}.obs-point.tcp{fill:var(--obs-violet)}.obs-point:focus{outline:none;stroke:#fff;stroke-width:3}.obs-empty{min-height:200px;display:flex;align-items:center;justify-content:center;color:#88a5b7;font-size:12px;text-align:center;padding:25px;line-height:1.8}.obs-details{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;padding-top:21px}.obs-details>div{min-width:0;display:flex;gap:9px;align-items:center;flex-wrap:wrap}.obs-details span{font-size:10px;color:#91b0c2}.obs-details strong{font-size:11px;color:#cbe1e9;font-variant-numeric:tabular-nums}.obs-details meter{width:65px;height:9px;accent-color:var(--obs-cyan)}.obs-footer{display:flex;gap:15px;flex-wrap:wrap;justify-content:space-between;margin-top:20px;padding-top:15px;border-top:1px solid #263f52;color:#7fa1b7;font-size:9px}.obs-table-wrap{margin-top:16px;font-size:11px;color:#9bbacd}.obs-table-wrap summary{cursor:pointer;min-height:32px}.obs-table-wrap p{font-size:11px;line-height:1.8;margin-top:10px}.obs-table-scroll{overflow:auto}.obs-table-wrap table{width:100%;border-collapse:collapse;font-size:11px}.obs-table-wrap caption{text-align:left;padding:9px 0;color:#c1d8e4}.obs-table-wrap th,.obs-table-wrap td{padding:10px 8px;border-bottom:1px solid #284152;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.obs-table-wrap th:first-child,.obs-table-wrap td:first-child{text-align:left}.obs-table-wrap th{color:#adcadb;font-weight:600}.observatory[data-status=stale] .obs-kpis strong{color:#c6cbd1}
@keyframes obs-change{0%{color:#83eddf;transform:translateY(2px)}100%{transform:none}}@keyframes obs-fetch{from{opacity:.4}to{opacity:1}}
@media(max-width:1100px){.obs-chart-grid{grid-template-columns:1fr}.obs-heading{flex-wrap:wrap}.obs-live-tools{justify-content:flex-start}.obs-kpis{gap:12px}.obs-details{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.obs-resources-grid{grid-template-columns:1fr}.obs-resource-heading{align-items:flex-start;flex-wrap:wrap}.obs-resource-kpis .obs-compact-value{font-size:22px}.observatory{padding:18px}.obs-heading h2{font-size:22px}.obs-toolbar{flex-wrap:wrap;gap:10px}.obs-toolbar label{width:calc(60% - 5px)}.obs-toolbar label:nth-child(2){width:calc(40% - 5px)}.obs-time{margin:0 auto 0 0;text-align:left}.obs-kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.obs-kpis strong{font-size:30px}.obs-kpis>div:nth-child(2){border:0}.obs-chart-card figcaption{padding:14px 12px 5px;gap:8px}.obs-chart-card select{width:115px}.obs-chart-card figcaption span{font-size:10px}.obs-chart{min-height:180px}.obs-footer{font-size:10px}.obs-live-tools .button{font-size:11px;min-height:35px}.obs-table-wrap summary{font-size:12px}}
@media(prefers-reduced-motion:reduce){.observatory *{animation:none!important;transition:none!important}}
@media(forced-colors:active){.observatory,.obs-chart-card,.obs-alert{background:Canvas;color:CanvasText;border-color:CanvasText}.obs-line{stroke:CanvasText!important}.obs-point{fill:CanvasText!important}.obs-svg-text{fill:CanvasText}.obs-live{color:CanvasText;border-color:CanvasText}}
'''
JS = r'''
let obsData=null,obsRequest=0,obsLastRender='',obsPaused=false,obsLastFetch=0;
const obsWindowMs=()=>Number($('obs-window').value)*60000;
const obsFinite=x=>typeof x==='number'&&Number.isFinite(x);
const obsValue=(x,digits=1)=>obsFinite(x)?x.toLocaleString('ko-KR',{maximumFractionDigits:digits}):'—';
function obsSelected(){return obsData?.nodes.find(x=>x.device_id===$('obs-device').value);}
function obsPoints(){const now=obsData?Date.parse(obsData.observed_at):Date.now();return (obsSelected()?.points||[]).filter(p=>p.received_at>=now-obsWindowMs());}
function obsSet(id,value){const e=$(id);if(e.textContent!==value){e.textContent=value;e.classList.remove('obs-changed');if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches){void e.offsetWidth;e.classList.add('obs-changed');}}}
function obsSvg(tag,attrs={},text){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
function obsSegments(points,key){const groups=[];let current=[];for(const p of points){if(!obsFinite(p[key])||p.gap||p.hourly_sample){if(current.length)groups.push(current);current=[];}if(obsFinite(p[key])){current.push(p);if(p.hourly_sample){groups.push(current);current=[];}}}if(current.length)groups.push(current);return groups;}
function obsEmpty(series){
  const selected=obsSelected();
  if(!selected)return '등록한 DNS 노드의 보고가 도착하면 그래프가 표시됩니다.';
  const keys=series.map(s=>s.key);
  const only=names=>keys.length>0&&keys.every(key=>names.includes(key));
  if(!selected.metrics)return '이 구간에 측정된 값이 없습니다.\n확장 지표가 없는 보고입니다. 없는 값을 0으로 표시하지 않습니다.';
  if(only(['udp_ms','tcp_ms']))return '차단 canary는 서명된 정책이 유효할 때만 측정합니다.\n이번 구간에는 측정값이 없으며 0으로 채우지 않습니다.';
  if(only(['cache_lookups_per_s','cache_hit_pct']))return '캐시 통계는 선택 수집입니다.\n이번 보고에는 캐시 카운터가 없으며 0으로 채우지 않습니다.';
  return '이 구간에 측정된 값이 없습니다.\n공백은 연결하거나 0으로 채우지 않습니다.';
}
function obsChart(id,points,series,unit,ceiling){
  const root=$(id);root.replaceChildren();const values=points.flatMap(p=>series.map(s=>p[s.key])).filter(obsFinite);
  if(!values.length){root.append(node('div','obs-empty',obsEmpty(series)));return;}
  const W=560,H=230,L=55,R=15,T=22,B=37,end=Date.parse(obsData.observed_at),start=end-obsWindowMs();
  const ymin=Math.min(0,...values),ymax=ceiling||Math.max(1,...values)*1.12,x=t=>L+(t-start)/(end-start)*(W-L-R),y=v=>H-B-(Math.min(ymax,Math.max(ymin,v))-ymin)/(ymax-ymin)*(H-T-B);
  const svg=obsSvg('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':unit+' 시계열. 누락 구간은 연결하지 않습니다. 상세 값은 아래 관측 표에 있습니다.'});
  svg.append(obsSvg('title',{},unit+' · '+points.length+'개 관측'),obsSvg('desc',{},'실제 수신한 관측만 표시합니다. 시간별 점은 마지막 표본이며 평균이 아닙니다.'));
  for(let i=0;i<=3;i++){const v=ymin+(ymax-ymin)*i/3,yy=y(v);svg.append(obsSvg('line',{x1:L,y1:yy,x2:W-R,y2:yy,class:'obs-gridline'}),obsSvg('text',{x:L-9,y:yy+4,'text-anchor':'end',class:'obs-svg-text'},obsValue(v,v<10?1:0)));}
  for(let i=0;i<3;i++){const t=start+(end-start)*i/2;svg.append(obsSvg('text',{x:x(t),y:H-12,'text-anchor':i===0?'start':i===2?'end':'middle',class:'obs-svg-text'},new Date(t).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})));}
  svg.append(obsSvg('text',{x:L,y:12,class:'obs-svg-text'},unit));
  for(const s of series){
    for(const group of obsSegments(points,s.key))if(group.length>1){const path=group.map((p,i)=>(i?'L':'M')+x(p.received_at).toFixed(2)+','+y(p[s.key]).toFixed(2)).join(' ');svg.append(obsSvg('path',{d:path,class:'obs-line '+s.kind}));}
    for(const p of points){if(!obsFinite(p[s.key]))continue;const dot=obsSvg('circle',{cx:x(p.received_at).toFixed(2),cy:y(p[s.key]).toFixed(2),r:p.hourly_sample?3.4:2.6,class:'obs-point '+s.kind,tabindex:0,'aria-label':new Date(p.at).toLocaleString('ko-KR')+' '+s.label+' '+obsValue(p[s.key],3)+' '+unit});dot.append(obsSvg('title',{},new Date(p.at).toLocaleString('ko-KR')+' · '+s.label+' '+obsValue(p[s.key],3)+' '+unit+(p.hourly_sample?' · 시간별 마지막 표본':'')));svg.append(dot);}
  }
  root.append(svg);
}
function renderAnalytics(){
  const selected=obsSelected(),points=obsPoints(),last=selected?.points.at(-1);
  const metrics=selected?.metrics,host=metrics?.host,now=obsData?Date.parse(obsData.observed_at):Date.now();
  const stale=selected?.report_at?now-Date.parse(selected.report_at)>150000:true;
  $('observatory').dataset.status=stale?'stale':'fresh';
  obsSet('obs-udp',obsValue(last?.udp_ms));obsSet('obs-tcp',obsValue(last?.tcp_ms));
  obsSet('obs-hit',obsValue(last?.cache_hit_pct));obsSet('obs-rate',obsValue(last?.cache_lookups_per_s,2));
  const alert=$('obs-alert');alert.dataset.state=selected&&(stale||selected.history_error||selected.state!=='LOCAL_DNS_VERIFIED')?'warning':'normal';
  alert.textContent=!selected?'등록된 DNS 노드가 없습니다. 배포 현황에서 장치와 공개키를 등록하세요.':selected.history_error?'관측 이력을 읽을 수 없습니다. 정상 또는 빈 상태로 판단하지 않습니다.':!metrics?'이 노드는 확장 지표를 보고하지 않습니다. v3 수집기로 업데이트하면 지연·자원·캐시 통계를 볼 수 있습니다.':stale?'마지막 보고가 150초 이상 지났습니다. 아래 수치는 현재가 아닌 마지막 관측값입니다.':(nodeStates[selected.state]?.[0]||selected.state)+' · 능동검사와 노드 자원 관측이며 LAN 전체의 실제 사용을 증명하지 않습니다.';
  obsChart('obs-latency-chart',points,[{key:'udp_ms',label:'UDP',kind:'udp'},{key:'tcp_ms',label:'TCP',kind:'tcp'}],'ms');
  const key=$('obs-metric').value;
  const labels={cpu_used_pct:['%','동일 부팅의 CPU tick 차분 · load와 별개'],dns_failure_pct:['%','현재 표본의 실패/검사 수 · 회선 손실률 아님'],nic_drops_per_s:['건/s','선택한 NIC의 RX+TX 커널 드롭 증가율'],cache_lookups_per_s:['캐시 조회 / s','캐시 조회 증가율 · 재시작/공백 구간 제외'],cache_hit_pct:['%','캐시 hits / (hits + misses) 증가분'],memory_used_pct:['%','MemAvailable 기반 메모리 사용률'],load_1m:['load','1분 평균 실행 대기 작업 수 · CPU 사용률 아님'],report_delay_s:['s','노드 보고 시각과 수신 시각 차이 · 시계 오차 포함']};
  const label=labels[key];showText('obs-metric-description',label[1]);
  obsChart('obs-metric-chart',points,[{key,label:label[0],kind:'udp'}],label[0],key.endsWith('_pct')?100:undefined);
  for(const [name,value] of [['memory',host?.memory_used_pct],['disk',host?.disk_used_pct]]){showText('obs-'+name,obsFinite(value)?obsValue(value)+'%':'미측정');$('obs-'+name+'-meter').hidden=!obsFinite(value);if(obsFinite(value))$('obs-'+name+'-meter').value=value;}
  showText('obs-uptime',obsFinite(host?.uptime_s)?obsValue(host.uptime_s/3600,1)+'시간':'미측정');
  const expiry=metrics?.policy?.valid_until;const remaining=expiry?(Date.parse(expiry)-now)/60000:null;
  showText('obs-policy-ttl',obsFinite(remaining)?remaining<=0?'만료':obsValue(remaining,1)+'분 남음':'미확인');
  showText('obs-samples',points.length+'건 · 시간별 표본 '+points.filter(x=>x.hourly_sample).length+'건');
  const body=$('obs-table');body.replaceChildren();for(const point of points.slice().reverse()){const row=node('tr','');for(const value of [new Date(point.at).toLocaleString('ko-KR'),obsValue(point.udp_ms),obsValue(point.tcp_ms),obsValue(point.cache_lookups_per_s,3),obsValue(point.cache_hit_pct),obsValue(point.memory_used_pct),point.probe_count?point.probe_errors+' / '+point.probe_count:'미실시'])row.append(node('td','',value));body.append(row);}
  renderResourceMetrics(points, selected);
  $('obs-export').disabled=!points.length;obsTick();
}
function renderResourceMetrics(points, selected){
  const last=selected?.points.at(-1),system=selected?.metrics?.system;
  showText('obs-resource-note',!selected?'장치를 등록한 뒤 노드의 서명 보고를 연결하세요.':!system?'v4 수집기로 갱신하면 CPU·인터페이스·일반 DNS 검사 그래프가 채워집니다.':selected.history_error?'관측 이력 검증 실패 · 최근 수치를 추측하지 않습니다.':'현재 표시는 해당 노드의 실제 관측입니다. 회선 전체·LAN 클라이언트 전체를 측정한 결과는 아닙니다.');
  showText('obs-interface',system?.interface?system.interface+' · ifindex '+(system.ifindex??'미확인'):'NIC 미선택');
  obsSet('obs-cpu',obsFinite(last?.cpu_used_pct)?obsValue(last.cpu_used_pct)+'%':'—');
  obsSet('obs-traffic',obsFinite(last?.rx_bytes_per_s)&&obsFinite(last?.tx_bytes_per_s)?obsValue(last.rx_bytes_per_s/1024)+' / '+obsValue(last.tx_bytes_per_s/1024):'—');
  obsSet('obs-quality-fail',obsFinite(last?.dns_failure_pct)?obsValue(last.dns_failure_pct)+'%':'—');
  showText('obs-quality-count',last?.dns_attempts?last.dns_failures+' / '+last.dns_attempts+'회 · 회선 손실률 아님':'검사 미실시 · --quality-probes 선택 필요');
  obsSet('obs-link-errors',obsFinite(last?.nic_errors_per_s)&&obsFinite(last?.nic_drops_per_s)?obsValue(last.nic_errors_per_s,3)+' / '+obsValue(last.nic_drops_per_s,3):'—');
  obsChart('obs-cpu-chart',points,[{key:'cpu_used_pct',label:'CPU',kind:'udp'}],'%',100);
  obsChart('obs-host-chart',points,[{key:'memory_used_pct',label:'메모리',kind:'udp'},{key:'disk_used_pct',label:'디스크',kind:'tcp'}],'%',100);
  const traffic=points.map(p=>({...p,rx_kib_s:obsFinite(p.rx_bytes_per_s)?p.rx_bytes_per_s/1024:null,tx_kib_s:obsFinite(p.tx_bytes_per_s)?p.tx_bytes_per_s/1024:null}));
  obsChart('obs-traffic-chart',traffic,[{key:'rx_kib_s',label:'RX',kind:'udp'},{key:'tx_kib_s',label:'TX',kind:'tcp'}],'KiB/s');
  const target=$('obs-quality-target').value;
  obsChart('obs-quality-chart',points,[{key:target+'_dns_udp_ms',label:'UDP',kind:'udp'},{key:target+'_dns_tcp_ms',label:'TCP',kind:'tcp'}],'ms');
  const body=$('obs-resource-table');body.replaceChildren();
  for(const p of points.slice().reverse()){
    const row=node('tr','');
    const values=[new Date(p.at).toLocaleString('ko-KR'),obsValue(p.cpu_used_pct),obsValue(obsFinite(p.rx_bytes_per_s)?p.rx_bytes_per_s/1024:null),obsValue(obsFinite(p.tx_bytes_per_s)?p.tx_bytes_per_s/1024:null),obsValue(p.local_dns_udp_ms),obsValue(p.local_dns_tcp_ms),obsValue(p.upstream_dns_udp_ms),p.dns_attempts?p.dns_failures+' / '+p.dns_attempts:'미실시'];
    for(const v of values)row.append(node('td','',v));body.append(row);
  }
}
$('obs-quality-target').addEventListener('change',()=>{if(token)renderResourceMetrics(obsPoints(),obsSelected());});
async function loadAnalytics(){
  const epoch=sessionEpoch,view=viewEpoch,request=++obsRequest;
  try{
    const data=await api('/api/analytics');
    if(!token||epoch!==sessionEpoch||view!==viewEpoch||request!==obsRequest)return;
    obsLastFetch=Date.now();const old=$('obs-device').value;obsData=data;
    const options=data.nodes.map(x=>x.device_id+'\0'+x.label).join('|');
    if($('obs-device').dataset.options!==options){$('obs-device').replaceChildren();for(const n of data.nodes){const opt=node('option','',n.label+' · '+n.device_id);opt.value=n.device_id;$('obs-device').append(opt);}if(!data.nodes.length)$('obs-device').append(node('option','','등록된 노드 없음'));$('obs-device').dataset.options=options;}
    if(data.nodes.some(x=>x.device_id===old))$('obs-device').value=old;
    const revision=JSON.stringify([data.nodes,$('obs-device').value,$('obs-window').value,$('obs-metric').value]);
    if(revision!==obsLastRender){obsLastRender=revision;renderAnalytics();}else obsTick();
  }catch(error){if(token&&epoch===sessionEpoch&&view===viewEpoch&&request===obsRequest&&!error.stale){$('obs-live').dataset.state='error';showText('obs-live','연결 지연 · 마지막 관측 유지');}throw error;}
}
function obsTick(){
  if(!token)return;const selected=obsSelected(),at=selected?.report_at;
  if(at&&Date.now()-Date.parse(at)>150000){$('observatory').dataset.status='stale';$('obs-alert').dataset.state='warning';showText('obs-alert','보고가 150초 이상 갱신되지 않았습니다. 그래프는 마지막 관측값이며 현재 상태가 아닙니다.');}
  const expiry=selected?.metrics?.policy?.valid_until;if(expiry){const m=(Date.parse(expiry)-Date.now())/60000;showText('obs-policy-ttl',m<=0?'만료':obsValue(m,1)+'분 남음');}
  showText('obs-age',at?'최근 보고 '+Math.max(0,Math.floor((Date.now()-Date.parse(at))/1000))+'초 전':'수집 보고 대기');
}
$('obs-device').addEventListener('change',()=>{obsLastRender='';renderAnalytics();});
$('obs-window').addEventListener('change',()=>{obsLastRender='';renderAnalytics();});
$('obs-metric').addEventListener('change',()=>{obsLastRender='';renderAnalytics();});
$('obs-export').addEventListener('click',()=>{
  const points=obsPoints();if(!points.length||!token)return;
  const keys=['udp_ms','tcp_ms','cache_lookups_per_s','cache_hit_pct','memory_used_pct','disk_used_pct','load_1m','report_delay_s','probe_count','probe_errors','cpu_used_pct','rx_bytes_per_s','tx_bytes_per_s','nic_errors_per_s','nic_drops_per_s','local_dns_udp_ms','local_dns_tcp_ms','upstream_dns_udp_ms','upstream_dns_tcp_ms','dns_attempts','dns_failures'];
  const rows=[['reported_at',...keys,'hourly_sample'].join(',')];for(const p of points)rows.push([new Date(p.at).toISOString(),...keys.map(k=>obsFinite(p[k])?p[k]:''),p.hourly_sample?'true':'false'].join(','));
  const link=document.createElement('a'),url=URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv;charset=utf-8'}));link.href=url;link.download='aleph-aggregate-observations.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
});
document.addEventListener('ops:locked',()=>{obsRequest++;obsData=null;obsLastRender='';obsLastFetch=0;$('obs-device').replaceChildren(node('option','','인증 후 조회'));delete $('obs-device').dataset.options;renderAnalytics();showText('obs-live','인증 후 조회');showText('obs-age','인증 후 조회');});
'''
