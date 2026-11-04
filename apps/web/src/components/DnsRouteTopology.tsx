"use client";
import {useState} from 'react';
import {useDiagramPlayback} from './useDiagramPlayback';
import './dns-route-topology.css';

function RouteArrows({label,epoch,policy=false}:{label:string;epoch:string;policy?:boolean}){
 return <div className={`dns-route-arrows${policy?' dns-route-policy-line':''}`} role="img" aria-label={label}>
  <span className="dns-route-query-label">{policy?<><span>서명 정책</span>{' '}<span>사전 배포</span></>:'질의'}</span>
  <div className="dns-route-lines" aria-hidden="true">
   <svg key={`h:${epoch}`} className="dns-route-rails dns-route-horizontal" viewBox="0 0 100 38" preserveAspectRatio="none"><path className="dns-route-query" d={policy?"M3 19H94":"M3 10H94"} vectorEffect="non-scaling-stroke"/>{!policy&&<path className="dns-route-answer" d="M97 28H6" vectorEffect="non-scaling-stroke"/>}</svg>
   <svg key={`v:${epoch}`} className="dns-route-rails dns-route-vertical" viewBox="0 0 38 100" preserveAspectRatio="none"><path className="dns-route-query" d={policy?"M19 3V94":"M10 3V94"} vectorEffect="non-scaling-stroke"/>{!policy&&<path className="dns-route-answer" d="M28 97V6" vectorEffect="non-scaling-stroke"/>}</svg>
   <svg className="dns-route-head dns-route-horizontal dns-route-head-query" data-direction="right" viewBox="0 0 12 12"><path d="M2 1l8 5-8 5"/></svg>
   {!policy&&<svg className="dns-route-head dns-route-horizontal dns-route-head-answer" data-direction="left" viewBox="0 0 12 12"><path d="M10 1L2 6l8 5"/></svg>}
   <svg className="dns-route-head dns-route-vertical dns-route-head-query" data-direction="down" viewBox="0 0 12 12"><path d="M1 2l5 8 5-8"/></svg>
   {!policy&&<svg className="dns-route-head dns-route-vertical dns-route-head-answer" data-direction="up" viewBox="0 0 12 12"><path d="M1 10l5-8 5 8"/></svg>}
  </div>
  {!policy&&<span className="dns-route-answer-label">응답</span>}
 </div>;
}
export function DnsRouteTopology({paused=false}:{paused?:boolean}){
 const [selected,setSelected]=useState(0);
 const playback=useDiagramPlayback({steps:selected===0?1:2,paused});
 const external=selected===2, resolver=external?'external':'protected';
 return <section ref={playback.diagramRef} className="diagram-panel dns-route-topology" data-stage={selected} data-resolver={resolver} data-flow-step={playback.step} data-flow-cycle={playback.cycle} data-playing={playback.playing} aria-label="공공·ISP 운영 제안과 선택한 하나의 DNS 경로">
  <p className="diagram-caption">PROPOSED OPERATION</p>
  <h2>보호 범위는 선택한 DNS 경로까지</h2>
  <div className="dns-route-stages" role="group" data-flow-cue={playback.hint} aria-label="설명할 경로 선택">
   {['정책 사전 배포','보호 DNS 선택','다른 DNS 경로'].map((label,index)=><button key={label} type="button" data-scenario-step="true" aria-pressed={selected===index} onClick={()=>{setSelected(index);playback.restart(0)}}>{label}</button>)}
  </div>
  <div className="dns-route-map">
   {selected===0?<article className="dns-route-source dns-route-policy dns-route-node"><small>공공 주체 · 제안</small><strong>정책 검토 · 서명</strong><span>사용자 질의 전에 배포</span></article>:<article className="dns-route-source dns-route-client dns-route-node"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 4h18v12H3zM8 20h8M12 16v4"/></svg><strong>사용자</strong><small>기기 · 브라우저가<br/>선택한 경로</small></article>}
   <div className="dns-route-transfer"><RouteArrows epoch={playback.epoch} policy={selected===0} label={selected===0?'공공 주체에서 ISP 보호 DNS로 서명 정책 사전 배포':external?'사용자에서 대체 리졸버 또는 VPN DNS로 질의, 해당 DNS에서 사용자로 응답. ISP 보호 정책 적용 범위 밖':'사용자에서 ISP 보호 DNS로 질의, 보호 DNS에서 사용자로 응답'}/></div>
   <article key={resolver} className={`dns-route-resolver dns-route-node ${external?'dns-route-bypass':'dns-route-protected'}`} data-resolver={resolver}>
    <small>{selected===0?'정책 수신 DNS · 제안':external?'다른 DNS로 변경':'선택한 DNS · 제안'}</small>
    <strong>{external?<>대체 리졸버<br/>또는 VPN DNS</>:'ISP 보호 DNS'}</strong>
    <span>{selected===0?'서명 정책을 미리 받음':external?'ISP 보호 정책 적용 범위 밖':'받아 둔 정책을 로컬 대조'}</span>
   </article>
  </div>
 </section>;
}
