"use client";
import latency from '../../capstone/data/dns-latency.json';
import './pi-network-plan.css';

const armLabels:Record<string,string>={local_upstream:'Pi 첫 조회',no_dns:'공용 DNS 직접'};
const milliseconds=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
export function PiNetworkPlan({paused=false}:{paused?:boolean}){
 // Show one matched-domain comparison. The other experiments remain separate
 // in the source data and report; combining them would change the population.
 const series=latency.series.find(item=>item.id==='warm_paired')!;
 const arms=series.arms.filter(arm=>arm.id==='no_dns'||arm.id==='local_upstream');
 const ceiling=Math.ceil(Math.max(...arms.map(arm=>arm.p95))/50)*50;
 const baseline=arms[0];
 const deltaLabel=(value:number)=>`${value>0?'+':''}${milliseconds.format(value)} ms · ${value>0?'더 느림':value<0?'더 빠름':'동일'}`;
 return <div className="latency-scene">
  <section className="diagram-panel latency-results" aria-label="일반 도메인 40개의 운영 DNS 응답 지연">
   <header><span>2026.11.03 · Pi DNS 실측 · UDP A</span><h2>운영 DNS :53의 응답 지연</h2></header>
   <p className="latency-context">같은 일반 도메인 40개 · 공용 DNS 직접 질의와 Pi 첫 조회 비교</p>
   <p className="latency-context">운영 :53 · 로컬 캐시 꺼짐 · 측정 시 활성 차단 규칙 없음</p>
   <div className="latency-legend"><span><i className="latency-dot p50"/>p50 · 중앙값</span><span><i className="latency-dot p95"/>p95 · 95백분위</span><small>오른쪽일수록 느림</small></div>
   <div id="latency-chart" className="latency-plot" data-series={series.id} data-paused={paused} data-metric="combined" role="group" aria-label={`p50·p95 함께 비교, 일반 도메인 40개, 축 0부터 ${ceiling}밀리초`}>
    <div className="latency-axis" aria-hidden="true"><span>0 ms</span><span>{ceiling/2}</span><span>{ceiling} ms</span></div>
    <ol className="latency-arms">{arms.map((arm,index)=><li className="latency-arm" key={arm.id} data-arm={arm.id}>
     <div className="latency-arm-heading"><strong>{armLabels[arm.id]}</strong><small>n={arm.n}{index===0?' · 비교 기준':''}</small></div>
     <div className="latency-track" aria-hidden="true"><span className="latency-span" style={{left:`${arm.p50/ceiling*100}%`,width:`${(arm.p95-arm.p50)/ceiling*100}%`}}/><i className="latency-dot p50" style={{left:`${arm.p50/ceiling*100}%`}}/><i className="latency-dot p95" style={{left:`${arm.p95/ceiling*100}%`}}/></div>
     <dl className="latency-values">{(['p50','p95'] as const).map(metric=><div key={metric} data-percentile={metric}><dt>{metric}</dt><dd><strong>{milliseconds.format(arm[metric])} ms</strong>{index>0&&<small className="latency-delta">{deltaLabel(arm[metric]-baseline[metric])}</small>}</dd></div>)}</dl>
    </li>)}</ol>
   </div>
  </section>
 </div>;
}
