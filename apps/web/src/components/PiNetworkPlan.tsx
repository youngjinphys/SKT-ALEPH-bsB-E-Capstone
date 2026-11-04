"use client";
import {useState} from 'react';
import latency from '../../capstone/data/dns-latency.json';
import './pi-network-plan.css';

const armLabels:Record<string,string>={local_upstream:'Pi DNS :53',local_repeat:'Pi 재조회',no_dns:'공용 DNS 직접',instrument_miss:'임시 캐시 미스',instrument_hit:'임시 캐시 히트'};
const milliseconds=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
export function PiNetworkPlan({paused=false}:{paused?:boolean}){
 const [seriesId,setSeriesId]=useState('warm_paired');
 const series=latency.series.find(item=>item.id===seriesId)!;
 const instrument=seriesId==='instrument_warm';
 const temporary=latency.environment.temporaryDns;
 const ceiling=Math.ceil(Math.max(...series.arms.map(arm=>arm.p95))/50)*50;
 const baseline=series.arms[0];
 const deltaLabel=(value:number)=>`${value>0?'+':''}${milliseconds.format(value)} ms · ${value>0?'더 느림':value<0?'더 빠름':'동일'}`;
 return <div className="latency-scene">
  <section className="diagram-panel latency-results" aria-label="Pi DNS 실측 로그의 조건별 요약">
   <header><span>2026.11.03 · Pi DNS 실측 · UDP A</span><h2>{instrument?'임시 캐시의 미스·히트 지연':'운영 DNS :53의 응답 지연'}</h2></header>
   <fieldset className="latency-series-select"><legend>측정 조건</legend>
    <div className="latency-series-choices">{latency.series.map(item=><button type="button" key={item.id} aria-pressed={seriesId===item.id} aria-controls="latency-chart" onClick={()=>setSeriesId(item.id)}>{item.label}</button>)}</div>
   </fieldset>
   <p className="latency-context">{instrument?`임시 :55353 · 캐시 ${temporary.cacheSize.toLocaleString('en-US')}개 · 최소 TTL ${temporary.minCacheTtlSeconds}초 · 미스→히트 순서`:'운영 :53 · 로컬 캐시 꺼짐 · 측정 시 활성 차단 규칙 없음'}</p>
   <div className="latency-legend"><span><i className="latency-dot p50"/>p50 · 중앙값</span><span><i className="latency-dot p95"/>p95 · 95백분위</span><small>오른쪽일수록 느림</small></div>
   <div id="latency-chart" className="latency-plot" data-paused={paused} data-metric="combined" role="group" aria-label={`p50·p95 함께 비교, 축 0부터 ${ceiling}밀리초`}>
    <div className="latency-axis" aria-hidden="true"><span>0 ms</span><span>{ceiling/2}</span><span>{ceiling} ms</span></div>
    <ol className="latency-arms">{series.arms.map((arm,index)=><li className="latency-arm" key={`${seriesId}-${arm.id}`} data-arm={arm.id}>
     <div className="latency-arm-heading"><strong>{armLabels[arm.id]}</strong><small>n={arm.n}{index===0?' · 비교 기준':''}</small></div>
     <div className="latency-track" aria-hidden="true"><span className="latency-span" style={{left:`${arm.p50/ceiling*100}%`,width:`${(arm.p95-arm.p50)/ceiling*100}%`}}/><i className="latency-dot p50" style={{left:`${arm.p50/ceiling*100}%`}}/><i className="latency-dot p95" style={{left:`${arm.p95/ceiling*100}%`}}/></div>
     <dl className="latency-values">{(['p50','p95'] as const).map(metric=><div key={metric} data-percentile={metric}><dt>{metric}</dt><dd><strong>{milliseconds.format(arm[metric])} ms</strong>{index>0&&<small className="latency-delta">{deltaLabel(arm[metric]-baseline[metric])}</small>}</dd></div>)}</dl>
    </li>)}</ol>
   </div>
   <p className="latency-difference-note">선은 p50–p95 범위이며 오차막대·신뢰구간이 아닙니다. ±는 {armLabels[baseline.id]}의 같은 백분위 대비 차이로, 짝별 차이·정책 비용을 뜻하지 않습니다.</p>
   <div className="latency-quality"><span><b>440 / 440</b> 분석 구간 응답 성공</span><span><b>6건 제외</b> 준비·자가시험, 타임아웃 2건 포함</span></div>
   <p className="latency-source">출처: <a href={latency.source.rawCsvUrl} target="_blank" rel="noopener noreferrer">원시 CSV</a> · <a href={latency.source.reportUrl} target="_blank" rel="noopener noreferrer">실행 조건</a> · p50/p95 선형보간 · 준비 구간 제외</p>
  </section>
 </div>;
}
