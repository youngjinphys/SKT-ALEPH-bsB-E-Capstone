"use client";
import {DiagramText} from './DiagramText';
import {useId,useState} from 'react';
import {useDiagramPlayback} from './useDiagramPlayback';
import './dns-route-topology.css';

const explanations=[
 '공공 주체가 검토·서명한 정책을 ISP 보호 DNS에 사전 배포하는 운영 구상입니다. 개별 질의는 공공 주체를 거치지 않습니다.',
 '사용자가 보호 DNS를 선택한 조회에서만 로컬 정책을 대조합니다. 질의와 응답은 사용자와 보호 DNS 사이를 오갑니다.',
 '사용자가 다른 리졸버나 VPN의 DNS 경로를 선택하면 이 보호 DNS를 거치지 않습니다. 해당 경로에는 이 정책의 집행을 보장할 수 없습니다.'
];
function RouteArrows({id,label,epoch}:{id:string;label:string;epoch:string}){
 return <div className="dns-route-arrows" role="img" aria-label={label}>
  <span>질의 →</span>
  <svg key={epoch} viewBox="0 0 100 38" preserveAspectRatio="none" aria-hidden="true"><defs><marker id={`${id}-query`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="m1 1 5 2.5L1 6" fill="none" stroke="#9beaff" strokeWidth="1.4"/></marker><marker id={`${id}-answer`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="m1 1 5 2.5L1 6" fill="none" stroke="#77f0c7" strokeWidth="1.4"/></marker></defs><path className="dns-route-query" d="M3 10H94" markerEnd={`url(#${id}-query)`}/><path className="dns-route-answer" d="M97 28H6" markerEnd={`url(#${id}-answer)`}/></svg>
  <span>← 응답</span>
 </div>;
}
/** Proposed control-plane distribution and two distinct client DNS routes. */
export function DnsRouteTopology({paused=false}:{paused?:boolean}){
 const [selected,setSelected]=useState(0);
 const playback=useDiagramPlayback({steps:selected===0?1:2,paused});
 const id=useId().replaceAll(':','');
 return <section ref={playback.diagramRef} className="diagram-panel dns-route-topology" data-stage={selected} data-flow-step={playback.step} data-flow-cycle={playback.cycle} data-playing={playback.playing} aria-label="공공·ISP 운영 제안과 보호 DNS 우회 경로">
  <p className="diagram-caption">PROPOSED OPERATION · NOT DEPLOYED</p>
  <h2>보호 범위는 선택한 DNS 경로까지</h2>
  <div className="dns-route-stages" role="group" data-flow-cue={playback.hint} aria-label="설명할 경로 선택">
   {['정책 사전 배포','보호 DNS 선택','다른 DNS 경로'].map((label,index)=><button key={label} type="button" data-scenario-step="true" aria-pressed={selected===index} onClick={()=>{setSelected(index);playback.restart(0)}}>{label}</button>)}
  </div>
  <div className="dns-route-map">
   <div className="dns-route-policy">
    <article><small>공공 주체 · 제안</small><strong>정책 검토 · 서명</strong></article>
    <div className="dns-route-policy-line" role="img" aria-label="공공 주체에서 ISP 보호 DNS로 서명 정책 사전 배포"><span><span>서명 정책</span>{' '}<span>사전 배포</span></span><svg key={playback.epoch} viewBox="0 0 20 28" aria-hidden="true"><path d="M10 3v21m-6-7 6 7 6-7"/></svg></div>
   </div>
   <article className="dns-route-client dns-route-node"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 4h18v12H3zM8 20h8M12 16v4"/></svg><strong>사용자</strong><small>기기 · 브라우저의<br/>DNS 경로 선택</small></article>
   <div className="dns-route-protected-line"><RouteArrows epoch={playback.epoch} id={`${id}-protected`} label="사용자에서 ISP 보호 DNS로 질의, 보호 DNS에서 사용자로 응답"/></div>
   <article className="dns-route-protected dns-route-node"><small>보호 경로 · 제안</small><strong>ISP 보호 DNS</strong><span>로컬 정책 대조</span></article>
   <div className="dns-route-bypass-line"><RouteArrows epoch={playback.epoch} id={`${id}-bypass`} label="사용자에서 대체 리졸버 또는 VPN DNS로 별도 질의, 해당 경로에서 사용자로 응답. 보호 DNS를 거치지 않음"/></div>
   <article className="dns-route-bypass dns-route-node"><small>우회 경로</small><strong>대체 리졸버<br/>또는 VPN DNS</strong><span>이 보호 DNS를 거치지 않음</span></article>
  </div>
  <p className="dns-route-explanation" role="status" aria-live="polite" aria-atomic="true"><DiagramText value={explanations[selected]} values={explanations} paused={paused}/></p>
  <p className="visual-caveat">공공·ISP 운영 구상 · 도입 전 협약·이용자 동의·운영 검증 필요.</p>
 </section>;
}
