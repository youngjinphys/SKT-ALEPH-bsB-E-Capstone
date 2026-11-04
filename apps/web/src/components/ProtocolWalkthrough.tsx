"use client";
import {DiagramText} from './DiagramText';
import {Fragment,useEffect,useState,type ReactNode} from 'react';
import diagrams from '../../capstone/data/diagrams.json';
import {useDiagramPlayback} from './useDiagramPlayback';
import './protocol-walkthrough.css';

// These are presentation display choices, not arrow-owning tab widgets.
const stages=['접속 시작','302 응답 / TLS 검증','새 요청 / 인증 실패 중단'];
export function ProtocolWalkthrough({paused=false,renderIcon}:{paused?:boolean;renderIcon:(name:string)=>ReactNode}){
 const playback=useDiagramPlayback({steps:stages.length,paused});
 const [mobile,setMobile]=useState(false),[protocol,setProtocol]=useState('http');
 useEffect(()=>{const media=matchMedia('(max-width:780px)');const sync=()=>setMobile(media.matches);sync();media.addEventListener('change',sync);return()=>media.removeEventListener('change',sync)},[]);
 const chooseProtocol=(id:string)=>{setProtocol(id);playback.restart()};
 const activeStages=mobile?(protocol==='http'?['HTTP 요청','302 응답','새 요청 · 안내 페이지']:['HTTPS 연결','TLS 신원 검증','인증 실패 · HTTP 이전 중단']):stages;
 const [errorInfo,setErrorInfo]=useState<'ede'|'sde'>('ede');
 return <section tabIndex={0} className="diagram-panel restored-diagram restored-protocol protocol-walkthrough" aria-label={mobile?"HTTP와 HTTPS 처리 경로 선택":"HTTP와 HTTPS의 동시 비교"} data-step={playback.step} data-flow-cycle={playback.cycle} data-flow-resting={playback.resting} data-playback={playback.playing?'running':'paused'}>
  <p className="diagram-caption">HTTP·HTTPS 처리 순서 · 설명용 흐름</p><h2>같은 안내 주소, 서로 다른 신뢰 절차</h2>
  {mobile&&<div className="protocol-path-tabs" role="group" data-flow-cue={playback.hint} aria-label="HTTP와 HTTPS 경로">
   {diagrams.protocolRows.map(row=><button type="button" key={row.id} id={`tab-protocol-${row.id}`} aria-controls={`panel-protocol-${row.id}`} aria-pressed={protocol===row.id} onClick={()=>chooseProtocol(row.id)}>{row.id.toUpperCase()}</button>)}
  </div>}
  {diagrams.protocolRows.map(row=><section className="restored-protocol-row" data-protocol={row.id} key={row.id} hidden={mobile&&protocol!==row.id} role={mobile?"region":undefined} id={`panel-protocol-${row.id}`} aria-labelledby={mobile?`tab-protocol-${row.id}`:undefined} aria-label={mobile?undefined:row.label}>
   <h3>{row.label}</h3><div ref={(mobile?row.id===protocol:row.id===diagrams.protocolRows[0].id)?playback.diagramRef:undefined} className="restored-protocol-path">{row.steps.map((item,i)=><Fragment key={item.title}>
    <article className="restored-node" data-active={playback.step===i} aria-current={playback.step===i?'step':undefined}>{renderIcon(item.icon)}<strong>{item.title}</strong><small>{item.detail}</small></article>
    {i<row.steps.length-1&&<span className="restored-protocol-arrow" data-active={playback.step===i+1} data-blocked={row.id==='https'&&i===1} aria-hidden="true"><b>{row.id==='https'&&i===1?'⊣':'→'}</b>{row.id==='http'&&<i className="protocol-packet"/>}</span>}
   </Fragment>)}</div>
  </section>)}
  <div className="protocol-control-strip"><div className="protocol-stage" aria-live={playback.automatic?"off":"polite"} aria-atomic="true"><span>{playback.step+1} / 3</span><strong><DiagramText value={activeStages[playback.step]} values={activeStages} paused={paused}/></strong></div>
  </div>
  <div className="protocol-standard-panel" aria-label="DNS 오류 표준과 제안">
   <div className="protocol-standard-tabs" role="group" data-flow-cue={playback.hint} aria-label="DNS 오류 전달 표준">
    <button type="button" id="tab-ede" aria-controls="panel-standards"
      aria-pressed={errorInfo==='ede'} onClick={()=>setErrorInfo('ede')}>EDE · RFC 8914</button>
    <button type="button" id="tab-sde" aria-controls="panel-standards"
      aria-pressed={errorInfo==='sde'} onClick={()=>setErrorInfo('sde')}>SDE · IETF 초안</button>
   </div>
   <div id="panel-standards" role="region" tabIndex={0} aria-labelledby={errorInfo==='ede'?'tab-ede':'tab-sde'} className="protocol-standard-explainer" aria-live="polite">
    <strong>{errorInfo==='ede'?'INFO-CODE 15 · Blocked':'Structured Error Data · I-JSON'}</strong>
    <p>{errorInfo==='ede'
      ?'DNS 응답에 차단 사유를 담습니다. 화면 안내에는 클라이언트 지원이 필요합니다.'
      :'EDE 설명을 구조화한 IETF 초안입니다. 리졸버·브라우저가 지원해야 안내에 활용할 수 있습니다.'}</p>
   </div>
  </div>
 </section>;
}
