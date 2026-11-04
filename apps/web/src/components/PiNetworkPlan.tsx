"use client";
import {useState} from 'react';
import {useDiagramVisibility} from './useDiagramVisibility';
import latency from '../../capstone/data/dns-latency.json';
import './pi-network-plan.css';

const armLabels:Record<string,string>={local_upstream:'Pi DNS :53',local_repeat:'Pi 재조회',no_dns:'공용 DNS 직접',instrument_miss:'임시 캐시 미스',instrument_hit:'임시 캐시 히트'};
const milliseconds=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
export function PiNetworkPlan({paused=false}:{paused?:boolean}){
 const chartVisibility=useDiagramVisibility();
 const [seriesId,setSeriesId]=useState('warm_paired');
 const [metric,setMetric]=useState<'p50'|'p95'>('p50');
 const series=latency.series.find(item=>item.id===seriesId)!;
 const instrument=seriesId==='instrument_warm';
 const temporary=latency.environment.temporaryDns;
 const ceiling=Math.ceil(Math.max(...series.arms.map(arm=>arm[metric]))/50)*50;
 const baseline=series.arms[0];
 return <div className="latency-scene">
  <section className="diagram-panel latency-results" aria-label="Pi DNS 실측 로그의 조건별 요약">
   <header><span>2026.11.03 · Pi DNS 실측 · UDP A</span><h2>{instrument?'임시 캐시의 미스·히트 지연':'운영 DNS :53의 응답 지연'}</h2></header>
   <fieldset className="latency-series-select"><legend>측정 조건</legend>
    <div className="latency-series-choices">{latency.series.map(item=><button type="button" key={item.id} aria-pressed={seriesId===item.id} aria-controls="latency-chart" onClick={()=>setSeriesId(item.id)}>{item.label}</button>)}</div>
   </fieldset>
   <p className="latency-context">{instrument?`임시 :55353 · 캐시 ${temporary.cacheSize.toLocaleString('en-US')}개 · 최소 TTL ${temporary.minCacheTtlSeconds}초 · 미스→히트 순서`:'운영 :53 · 로컬 캐시 꺼짐 · 측정 시 활성 차단 규칙 없음'}</p>
   <div className="latency-metric-row"><div className="latency-metric-tabs" role="group" aria-label="비교할 지연 통계"><button aria-pressed={metric==='p50'} onClick={()=>setMetric('p50')}>p50 · 중앙값</button><button aria-pressed={metric==='p95'} onClick={()=>setMetric('p95')}>p95 · 상위 지연</button></div><small>0–{ceiling} ms · 낮을수록 짧음</small></div>
   <div ref={chartVisibility.ref} id="latency-chart" className="latency-plot" data-in-view={chartVisibility.inView} data-paused={paused} data-metric={metric} role="img" aria-label={`${metric} 비교, 축 0부터 ${ceiling}밀리초. `+series.arms.map(arm=>`${armLabels[arm.id]} ${arm.n}건, ${milliseconds.format(arm[metric])}밀리초`).join('; ')}>
    <div className="latency-axis"><span>{ceiling}</span><span>{ceiling/2}</span><span>0</span></div>
    <div className="latency-bars" style={{gridTemplateColumns:`repeat(${series.arms.length},minmax(0,1fr))`}}>{series.arms.map((arm,index)=>{const delta=arm[metric]-baseline[metric];return <div className="latency-arm" key={`${seriesId}-${metric}-${arm.id}`}><div className="latency-track"><div className="latency-bar" style={{height:`${arm[metric]/ceiling*100}%`,animationDelay:`${index*90}ms`}}/><span className="latency-bar-label" style={{bottom:`${arm[metric]/ceiling*100}%`,animationDelay:`${index*90}ms`}}>{milliseconds.format(arm[metric])}</span></div><strong>{armLabels[arm.id]}</strong><span className="latency-delta">{index===0?'비교 기준':`${delta>0?'+':''}${milliseconds.format(delta)} ms`}</span><small>n={arm.n}</small></div>})}</div>
   </div>
   <p className="latency-difference-note">기준 대비 요약 {metric} 차이 · 짝별 차이·정책 비용으로 해석하지 않습니다.</p>
   <div className="latency-quality"><span><b>440 / 440</b> 분석 구간 응답 성공</span><span><b>6건 제외</b> 준비·자가시험, 타임아웃 2건 포함</span></div>
   <p className="latency-source">출처: <a href={latency.source.rawCsvUrl} target="_blank" rel="noopener noreferrer">원시 CSV</a> · <a href={latency.source.reportUrl} target="_blank" rel="noopener noreferrer">실행 조건</a> · p50/p95 선형보간 · 준비 구간 제외</p>
  </section>
 </div>;
}
