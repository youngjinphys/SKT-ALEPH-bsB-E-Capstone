"use client";
import {ReferenceSlide} from "./ReferenceSlide";
import {DiagramText} from "./DiagramText";
import {DnsRouteTopology} from "./DnsRouteTopology";
import {PiNetworkPlan} from "./PiNetworkPlan";
import {TermExplanation,TermTarget} from "./TermExplanation";
import {useId,useState,useRef,useLayoutEffect} from "react";
import "./restored-diagrams.css";
import "./dns-flow-motion.css";
import "./policy-presenter.css";
import type {DeckSlide,SourceRegistry} from "@/lib/deck";
import {RestoredScene} from "./RestoredScene";
import {EvidenceTable} from "./EvidenceTable";
import {ProtocolWalkthrough} from "./ProtocolWalkthrough";
import {CnameWalkthrough} from "./CnameWalkthrough";
import {IndependentTrends,AdoptionCompare,DnsEvidenceDashboard,RoadmapVisual,ThanksVisual,IntroArchitecture} from "./EditorialVisual";
import {useStageIntroduction} from "./useStageIntroduction";
import "./stage-introduction.css";
import {useDiagramPlayback} from "./useDiagramPlayback";
import "./flow-playback.css";
import diagrams from "../../capstone/data/diagrams.json";

function ComparisonBars({visual,sources}:{visual:Extract<NonNullable<DeckSlide["visual"]>,{type:"comparison-bars"}>;sources:SourceRegistry}){
 const peak=Math.max(1,...visual.measurements.map(m=>m.value));
 return <figure className="chart-card" aria-label={visual.title}>
  <figcaption><span>OBSERVED DATA</span><h2>{visual.title}</h2></figcaption>
  <div className="bar-chart">{visual.measurements.map((m,i)=><div key={m.label} className="bar-row"><div className="bar-info"><span>{m.label}</span><strong>{m.value.toLocaleString("ko-KR")} <small>{visual.unit}</small></strong></div><div className="bar-track"><span className={i===visual.measurements.length-1?"bar-fill bar-accent":"bar-fill"} style={{width:`${Math.max(1,m.value/peak*100)}%`}}/></div></div>)}</div>
  <p className="visual-caveat">{visual.caveat}</p>
  {sources[visual.sourceKey]&&<a href={sources[visual.sourceKey].url} target="_blank" rel="noreferrer noopener">집계 출처 ↗</a>}
 </figure>;
}
/** The policy server prepares a signed snapshot; DNS answers are local to the resolver. */
function PolicyPipeline({paused=false}:{paused?:boolean}){
 const [mode,setMode]=useState<"lab"|"proposal">("lab");
 const stages=diagrams.policyPipeline[mode];
 const playback=useStageIntroduction(stages.length,paused);
 const active=playback.step,selected=stages[active];
 return <section ref={playback.ref} data-step={active} data-playing={playback.playing} data-complete={playback.complete} className="diagram-panel policy-flow-panel stage-introduction" aria-label="검증·승인·서명·DNS 집행 파이프라인">
  <p className="diagram-caption">POLICY TRUST BOUNDARIES · FOUR STAGES</p>
  <div className="policy-flow-modes" role="group" data-flow-cue={playback.hint} aria-label="구현 경로와 확대 제안">
   <button type="button" data-scenario-step="true" aria-pressed={mode==="lab"} onClick={()=>{setMode("lab");playback.restart()}}>현재 코드</button>
   <button type="button" data-scenario-step="true" aria-pressed={mode==="proposal"} onClick={()=>{setMode("proposal");playback.restart()}}>공공·ISP 제안</button>
  </div>
  <ol className="policy-flow-steps">
   {stages.map((stage,i)=><li key={stage.label}>
    <button type="button" className="policy-flow-stage" aria-current={active===i?"step":undefined}
     data-stage-state={playback.reduced?"done":active===i?"active":i<active?"done":"pending"} onClick={()=>playback.select(i)} aria-label={`${i+1}단계, ${stage.label}, 상세 표시`}>
      <small>{String(i+1).padStart(2,"0")} · {stage.label}</small>
      <strong>{stage.owner}</strong>
      <span>{stage.detail}</span>
    </button>
    {i<stages.length-1&&<span className="policy-flow-connector stage-connector" data-stage-state={playback.reduced||i<active?"done":i===active?"active":"pending"} aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3v17m-5-5 5 5 5-5"/></svg></span>}
   </li>)}
  </ol>
  <div className="policy-flow-detail" aria-live={playback.playing||playback.resting?"off":"polite"}>
   <span>{mode==="lab"?"검토된 로컬 실행 경계":"운영 모델 · 도입 전 검토"}</span>
   <strong><DiagramText value={selected.artifact} values={stages.map(stage=>stage.artifact)} paused={paused}/></strong>
   <p><DiagramText value={selected.detail} values={stages.map(stage=>stage.detail)} paused={paused}/></p>
  </div>
 </section>;
}
function IntelEvidence(){
 const [selected,setSelected]=useState(0);
 const facts=diagrams.feedSnapshot;
 return <section className="diagram-panel intel-evidence" aria-label="외부 후보 정규화의 팀 기록">
   <p className="diagram-caption">OCT 30 · REVIEWED INPUTS</p>
   <div className="intel-metrics" role="group" aria-label="OpenPhish와 Safe Browsing 팀 실행 기록">
    {facts.map((fact,i)=><button key={fact.label} type="button" aria-pressed={selected===i}
      onClick={()=>setSelected(i)} className="intel-metric">
      <strong>{fact.value}</strong><span>{fact.label}</span>
    </button>)}
   </div>
   <div className="intel-detail" role="status" aria-live="polite">
     <span>검증 범위 · {facts[selected].label}</span><p>{facts[selected].note}</p>
   </div>
   <div className="intel-review-boundary">
    <span>수집 JSON</span><b aria-hidden="true">→</b>
    <strong>별도 검증 결과</strong><b aria-hidden="true">→</b>
    <span>검토 파일 (approved: false)</span>
   </div>
   <p className="visual-caveat">10월 30일 팀 기록 · 원본 API 응답·해시·요청 시각 인수 필요.</p>
  </section>;
}
function PolicyVerdicts(){
 const [active,setActive]=useState(1);
 const verdicts=diagrams.policyVerdicts,selected=verdicts[active];
 return <section className="diagram-panel verdict-matrix" aria-label="정책의 네 가지 판단 상태">
  <p className="diagram-caption">POLICY VERDICTS · DNS RESPONSE</p>
  <div className="verdict-grid" role="group" aria-label="정책 판단 선택">
   {verdicts.map((v,i)=><button type="button" key={v.code}
    data-verdict={v.code.toLowerCase()} data-scenario-step="true"
    aria-pressed={active===i} onClick={()=>setActive(i)}>{v.code}</button>)}
  </div>
  <table className="verdict-mapping" aria-label="네 정책 판정의 DNS 응답 매핑">
   <thead><tr><th scope="col">판정</th><th scope="col">DNS 동작</th><th scope="col">조건</th></tr></thead>
   <tbody>{verdicts.map(v=><tr key={v.code} data-selected={v.code===selected.code}><th scope="row">{v.code}</th><td>{v.answer}</td><td>{v.condition}</td></tr>)}</tbody>
  </table>
  <div className="verdict-detail" role="status" aria-live="polite">
   <small>{selected.code} · 조건</small><h2>{selected.condition}</h2>
   <span>DNS 응답</span><strong>{selected.answer}</strong>
   <p>{selected.detail}</p>
  </div>
  <p className="visual-caveat">후속: 근거 인증·자동 공급·가중치 보정.</p>
 </section>;
}

function DiagramIcon({name}:{name:string}){
 const paths:Record<string,string>={client:'M3 4h18v12H3z M8 20h8 M12 16v4',server:'M3 3h18v7H3z M3 14h18v7H3z M6 6h1 M6 17h1',document:'M6 2h9l4 4v16H6z M14 2v6h5 M9 12h7 M9 16h7',globe:'M2 12h20 M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M12 2c-6 5-6 15 0 20 6-5 6-15 0-20',lock:'M5 10h14v12H5z M8 10V6a4 4 0 0 1 8 0v4',stop:'M5 5l14 14 M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20',shield:'M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6z M8 12l3 3 5-6'};
 return <svg className="restored-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name]||paths.document}/></svg>;
}
/** Two equal spans share endpoints; labels never compete with the arrow shafts. */
function BidirectionalLane({className,reverse=false,verticalOnMobile=false,unused=false,blocked=false,label,activeFlow='none'}:{activeFlow?:'none'|'query'|'response';className:string;reverse?:boolean;verticalOnMobile?:boolean;unused?:boolean;blocked?:boolean;label:string}){
 const id=useId().replaceAll(':','');
 const marker=(suffix:string,color:string)=><marker id={`${id}-${suffix}`} markerWidth="12" markerHeight="12" refX="11" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M1 1L11 6 1 11" fill="none" stroke={color} strokeWidth="2.2"/></marker>;
 return <div className={`restored-bidirectional ${className}`} data-reverse={reverse} data-mobile-vertical={verticalOnMobile} data-unused={unused} data-blocked={blocked} data-active-flow={activeFlow} role="img" aria-label={label}>
  <span className="lane-query-label">{blocked?"조회 생략":<><span className="lane-label-prefix">DNS </span>질의</>}</span>
  <svg className="lane-horizontal" aria-hidden="true"><defs>{marker('hq','#9beaff')}{marker('hr','#77f0c7')}</defs><line className="lane-shaft" data-direction={reverse?'left':'right'} data-flow="query" x1={reverse?'97%':'3%'} x2={reverse?'3%':'97%'} y1="25%" y2="25%" markerEnd={`url(#${id}-hq)`}/><line className="lane-shaft" data-direction={reverse?'right':'left'} data-flow="response" x1={reverse?'3%':'97%'} x2={reverse?'97%':'3%'} y1="75%" y2="75%" markerEnd={`url(#${id}-hr)`}/><circle className="lane-packet" data-flow="query" data-direction={reverse?'left':'right'} cx="3%" cy="25%" r="3"/><circle className="lane-packet" data-flow="response" data-direction={reverse?'right':'left'} cx="3%" cy="75%" r="3"/></svg>
  <svg className="lane-vertical" aria-hidden="true"><defs>{marker('vq','#9beaff')}{marker('vr','#77f0c7')}</defs><line className="lane-shaft" data-direction={reverse?'up':'down'} data-flow="query" y1={reverse?'97%':'3%'} y2={reverse?'3%':'97%'} x1="25%" x2="25%" markerEnd={`url(#${id}-vq)`}/><line className="lane-shaft" data-direction={reverse?'down':'up'} data-flow="response" y1={reverse?'3%':'97%'} y2={reverse?'97%':'3%'} x1="75%" x2="75%" markerEnd={`url(#${id}-vr)`}/><circle className="lane-packet" data-flow="query" data-direction={reverse?'up':'down'} cx="25%" cy="3%" r="3"/><circle className="lane-packet" data-flow="response" data-direction={reverse?'down':'up'} cx="75%" cy="3%" r="3"/></svg>
  <span className="lane-response-label"><span className="lane-label-prefix">DNS </span>응답</span>
  {blocked&&<span className="dns-block-gate" aria-hidden="true"><svg className="dns-block-gate-icon" width="24" height="28" viewBox="0 0 24 28" fill="none" focusable="false"><defs><linearGradient id={`${id}-shield-glass`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffe3bf" stopOpacity=".42"/><stop offset=".48" stopColor="#71401f" stopOpacity=".68"/><stop offset="1" stopColor="#ffad63" stopOpacity=".24"/></linearGradient></defs><path fill={`url(#${id}-shield-glass)`} d="M12 2 22 6v7c0 6-4 10-10 13C6 23 2 19 2 13V6Z"/></svg></span>}
 </div>;
}
/** Separate vertical control/web lanes cannot be mistaken for DNS proxy traffic. */
function DirectLane({disabled=false,packet=false}:{disabled?:boolean;packet?:boolean}){
 const id=useId().replaceAll(':','');
 return <svg className="direct-flow-line" width="20" height="30" aria-hidden="true"><defs><marker id={`${id}-direct`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M1 1L7 4 1 7" fill="none" stroke="currentColor" strokeWidth="1.7"/></marker></defs><line x1="10" x2="10" y1="3" y2="27" markerEnd={disabled?undefined:`url(#${id}-direct)`}/>{packet&&!disabled&&<circle className="direct-flow-packet" cx="10" cy="3" r="3"/>}</svg>;
}

const DNS_INTRO_DURATIONS=[2200,2200,800,650,2000,700,1400,700,1300,1200,800];
function DnsLab({paused=false}:{paused?:boolean}){
 const [scenario,setScenario]=useState<keyof typeof diagrams.dnsFlow>('allow');
 const current=diagrams.dnsFlow[scenario];
 const playback=useDiagramPlayback({steps:11+current.steps.length,paused,loopStart:11,reducedStep:11,durations:DNS_INTRO_DURATIONS});
 const {diagramRef,reduced,complete}=playback;
 const introStep=Math.min(11,playback.step),step=Math.max(0,playback.step-11);
 const playbackEpoch=playback.epoch;
 const mapRef=useRef<HTMLDivElement>(null);
 const introducing=introStep<11;
 const introLabels=['일반 DNS에 정상 질의','일반 DNS가 원래 주소 응답','일반 DNS 조회 완료','기존 질의 연결을 정리','일반 DNS를 업스트림 자리로 이동','기존 DNS가 업스트림 자리에 안착','기존 자리에 보호 DNS 등장','보호 DNS가 질의 경로에 안착','서명 정책을 보호 DNS에 연결','보호 DNS와 업스트림 경로 연결','보호 경로 준비 완료 · 새 질의 시작','보호 경로에서 사례 확인'];
 const introStates=['query','response','complete','prepare','move','upstream-settle','reveal','resolver-settle','policy','connect','ready','protected'];
 useLayoutEffect(()=>{
  const map=mapRef.current;if(!map)return;
  const measure=()=>{
   const resolver=map.querySelector<HTMLElement>('.dns-resolver');
   const upstream=map.querySelector<HTMLElement>('.dns-upstream');
   if(!resolver||!upstream)return;
   map.style.setProperty('--dns-intro-x',`${resolver.offsetLeft-upstream.offsetLeft}px`);
   map.style.setProperty('--dns-intro-y',`${resolver.offsetTop-upstream.offsetTop}px`);
  };
  measure();const observer=new ResizeObserver(measure);observer.observe(map);
  return()=>observer.disconnect();
 },[]);
 const status=reduced?`${current.label} · 전체 순서는 아래 설명에서 확인`:introducing?introLabels[introStep]:`${current.label} · ${step+1}/${current.steps.length} ${current.steps[step]}`;
 const statuses=[...introLabels,...Object.values(diagrams.dnsFlow).flatMap(flow=>flow.steps.map((text,index)=>`${flow.label} · ${index+1}/${flow.steps.length} ${text}`))];
 const textPaused=paused||!playback.playing;
 const queryFlow=introducing?(introStep===0?'query':introStep===1?'response':'none'):step===0?'query':step===(scenario==='allow'?4:2)?'response':'none';
 const upstreamFlow=!introducing&&scenario==='allow'?(step===2?'query':step===3?'response':'none'):'none';
 const webFlow=!introducing&&scenario==='allow'&&step===5?'request':'none';
 const flowRunning=playback.playing;
 const activeRoles=step===0?['client','resolver']:step===1?['resolver']:
  scenario==='allow'?(step===2||step===3?['resolver','upstream']:step===4?['resolver','client']:['client','web']):
  step===2?['resolver','client']:['client'];
 const webLabel=scenario==='block'?'이번 새 이름 조회에 의존한 웹 연결 중단':'클라이언트에서 웹 서버로 직접 연결';
 const choose=(key:keyof typeof diagrams.dnsFlow)=>{setScenario(key);playback.restart(11)};
 return <TermExplanation term="dnsmasq" paused={paused}><section tabIndex={0} className="diagram-panel restored-diagram restored-dns" data-scenario={scenario} data-intro-step={introStep} data-intro-state={introStates[introStep]} data-complete={complete} data-flow-cycle={playback.cycle} data-flow-resting={playback.resting} data-playback={flowRunning?'running':'paused'} data-step={step} data-playback-epoch={playbackEpoch} aria-label="일반 DNS 조회에서 보호 DNS 계층을 추가하는 과정과 두 가지 DNS 응답 사례">
  <p className="diagram-caption dns-implementation-caption">동작 설명 · <TermTarget term="dnsmasq">dnsmasq</TermTarget> · 실시간 질의 아님</p>
  <div className="restored-controls" role="group" data-flow-cue={playback.hint} aria-label="DNS 시나리오 선택">{(Object.keys(diagrams.dnsFlow) as (keyof typeof diagrams.dnsFlow)[]).map(key=><button type="button" key={key} data-scenario-step="true" aria-pressed={scenario===key} onClick={()=>choose(key)}>{diagrams.dnsFlow[key].label}</button>)}</div>
  <p className="dns-intro-status" aria-live={playback.automatic?"off":"polite"} aria-atomic="true"><DiagramText value={status} values={statuses} paused={textPaused}/></p>
  <div className="restored-dns-map" ref={mapRef}>
   <article className="restored-node dns-policy" aria-hidden={introStep<8}><DiagramIcon name="document"/><strong>정책 서버</strong><small>후보 검토 · 서명 · 사전 배포</small></article>
   <div className="restored-lane dns-policy-link" aria-hidden={introStep<8}><span>서명 정책</span><DirectLane/></div>
   <article ref={diagramRef} className="restored-node dns-client" data-active={!reduced&&(introducing?introStep<2:activeRoles.includes('client'))}><DiagramIcon name="client"/><strong>클라이언트</strong><small><DiagramText value={`${current.domain} · A 조회`} values={Object.values(diagrams.dnsFlow).map(flow=>`${flow.domain} · A 조회`)} paused={textPaused}/></small></article>
   <BidirectionalLane key={`query-${playbackEpoch}`} className="dns-query-link" activeFlow={reduced?'none':queryFlow} label={introStep<6?"클라이언트에서 일반 DNS로 질의, 일반 DNS에서 클라이언트로 응답":"클라이언트에서 보호 DNS로 질의, 보호 DNS에서 클라이언트로 응답"}/>
   <article aria-hidden={introStep<6} className="restored-node dns-resolver" data-active={!introducing&&!reduced&&activeRoles.includes('resolver')}><DiagramIcon name="shield"/><strong>보호 DNS</strong><small>로컬 정책 대조</small></article>
   <div className="dns-intro-upstream-lane" aria-hidden={introStep<9}><BidirectionalLane key={`upstream-${playbackEpoch}`} className="dns-upstream-link" activeFlow={reduced?'none':upstreamFlow} verticalOnMobile unused={scenario!=='allow'} blocked={scenario==='block'&&(reduced||step>=1)} label={scenario==='block'&&(reduced||step>=1)?'차단 정책 일치 · 업스트림 조회 생략':'보호 DNS에서 업스트림 DNS로 질의, 업스트림 DNS에서 보호 DNS로 응답'}/></div>
   <article className="restored-node dns-upstream" data-active={!reduced&&(introducing?introStep<2:activeRoles.includes('upstream'))} data-unused={scenario!=='allow'}><DiagramIcon name="server"/><strong><DiagramText value={introStep<5?'일반 DNS':'업스트림 DNS'} values={['일반 DNS','업스트림 DNS']} paused={textPaused}/></strong><small className="dns-upstream-condition" aria-hidden={scenario!=='allow'}>시험용 .test</small></article>
   <div className="restored-lane dns-web-link" data-active-flow={reduced?'none':webFlow} data-unused={scenario==='block'} role="img" aria-label={webLabel}><span className="dns-web-blocked-label" data-visible={scenario==='block'} aria-hidden="true">새 연결 없음</span><DirectLane key={`${playbackEpoch}-${scenario}-${step}`} packet disabled={scenario==='block'}/></div>
   <article className="restored-node dns-web" data-active={!reduced&&activeRoles.includes('web')} data-unused={scenario==='block'}><DiagramIcon name="globe"/><strong>목적지 웹 서버</strong><small>클라이언트와 직접 HTTP / TLS</small></article>
  </div>
  <div className="dns-accessible-flow sr-only">
   <p className="dns-current-status">{introducing?introLabels[introStep]:current.label} · {introducing?'선택한 DNS 경로의 보호 계층 도입':reduced?'모션 줄이기: 전체 순서 제공':`${complete?'완료 · ':paused?'모션 정지 · ':''}단계 ${step+1} / ${current.steps.length}: ${current.steps[step]}`}</p>
   <ol aria-label={`${current.label} 전체 순서`}>{current.steps.map((text,i)=><li key={text} aria-current={!reduced&&step===i?'step':undefined}>{text}</li>)}</ol>
  </div>

 </section></TermExplanation>;
}
const policyTimeline=diagrams.policyTimeline;
function PolicyLifecycle({paused=false}:{paused?:boolean}){
 const [active,setActive]=useState(0);
 const playback=useDiagramPlayback({steps:1,paused});
 const current=policyTimeline[active];
 return <TermExplanation term="ttl" paused={paused}><div tabIndex={0} role="region" aria-label="정책 적용과 철회 설명용 시뮬레이션" className="diagram-panel policy-lifecycle" data-step={active} data-playback={playback.playing?'running':'paused'}><p className="diagram-caption">정책 응답 변화 · 설명용 재현</p><h2>정상 → 차단 → 철회: 같은 이름의 응답 변화</h2>
  <div className="policy-review-gates" role="list" aria-label="후보 검토·승인·만료의 생애주기">{["URL 발견","approved: false","검토·서명 승인","만료 또는 철회"].map((x,i)=><span role="listitem" key={x}>{x}{i<3&&<b aria-hidden="true">→</b>}</span>)}</div>
  <div ref={playback.diagramRef} className="policy-timeline" data-flow-cue={playback.hint} role="group" aria-label="정상 차단 철회 상태 선택">
   {policyTimeline.map((state,i)=><div className="policy-timeline-stage" key={state.phase}>
    <button type="button" data-scenario-step="true" aria-pressed={active===i} onClick={()=>{setActive(i);playback.restart()}}><span>0{i+1} / {state.phase}</span><strong>{state.response}</strong><small>blocked.test · A</small></button>
    {i<policyTimeline.length-1&&<span className="policy-timeline-arrow" aria-hidden="true"><svg viewBox="0 0 28 20"><path d="M3 10h21m-7-7 7 7-7 7"/></svg></span>}
   </div>)}
  </div>
  <div className="policy-timeline-result" aria-live="polite" aria-atomic="true"><span><DiagramText value={`선택한 시점 · ${current.phase}`} values={policyTimeline.map(state=>`선택한 시점 · ${state.phase}`)} paused={paused}/></span><strong><DiagramText value={current.response} values={policyTimeline.map(state=>state.response)} paused={paused}/></strong><p><DiagramText value={current.note} values={policyTimeline.map(state=>state.note)} paused={paused}/></p></div>
  <p className="visual-caveat">서버 응답 복원과 단말의 양성·음성 캐시를 구분 · <TermTarget term="ttl">TTL</TermTarget></p>
 </div></TermExplanation>;
}
function Topology({publicMode:initialPublic,comparison=true}:{publicMode:boolean;comparison?:boolean}){
 const [publicMode,setPublicMode]=useState(initialPublic);
 const nodes=publicMode?diagrams.topology.proposal:diagrams.topology.lab;
 return <div tabIndex={0} role="region" aria-label="운영 주체 및 DNS 토폴로지" className="diagram-panel topology-panel restored-diagram restored-topology"><p className="diagram-caption">{publicMode?"PROPOSED OPERATION · NOT DEPLOYED":"LAB IMPLEMENTATION · NOT A PRODUCTION PILOT"}</p><h2>{publicMode?"운영 주체가 달라져도 검증 책임은 남습니다":"정책 공급과 이름 조회를 분리합니다"}</h2>
  {comparison&&<div className="restored-controls" role="group" aria-label="토폴로지 운영 주체 선택"><button type="button" data-scenario-step="true" aria-pressed={!publicMode} onClick={()=>setPublicMode(false)}>실험실</button><button type="button" data-scenario-step="true" aria-pressed={publicMode} onClick={()=>setPublicMode(true)}>공공 · ISP 제안</button></div>}
  <div className="topology-flow" aria-live="polite">
   <div className="topology-step"><DiagramIcon name="document"/><span>01</span><strong>{nodes[0].name}</strong><small>{nodes[0].desc}</small></div>
   <div className="topology-lane topology-policy-lane" role="img" aria-label="검토·서명된 정책이 보호 DNS로 전달됩니다"><span>서명 정책</span><b aria-hidden="true">→</b></div>
   <div className="topology-step topology-step-dns"><DiagramIcon name="server"/><span>02</span><strong>{nodes[1].name}</strong><small>{nodes[1].desc}</small></div>
   <BidirectionalLane className="topology-dns-lane" reverse verticalOnMobile label="클라이언트에서 보호 DNS로 질의, 보호 DNS에서 클라이언트로 응답"/>
   <div className="topology-step topology-step-client"><DiagramIcon name="client"/><span>03</span><strong>{nodes[2].name}</strong><small>{nodes[2].desc}</small></div>
  </div>
  <p className="visual-caveat">{publicMode?"공공·ISP 운영 구상 · 도입 조건: 협약·이용자 동의·운영 검증":"정책 공급과 DNS 조회를 분리합니다. 다음 검증은 실제 LAN 장비입니다."}</p>
 </div>;
}
function GovernanceReview(){
 const steps=diagrams.governance;
 return <div className="evidence-stack">
  <div className="evidence-header"><span>PROPOSED APPEAL & ROLLBACK · NOT DEPLOYED</span><h2>이의신청에서 복구 확인까지</h2></div>
  {steps.map((step,i)=><article className="evidence-row" key={step.title}><span>0{i+1}</span><div><strong>{step.title}</strong><p>{step.detail}</p></div></article>)}
  <p className="visual-caveat">심사 권한·처리 기한·복구 SLA는 운영 주체 간 합의와 실증이 필요합니다.</p>
 </div>;
}
function EvidenceVisual({slide}:{slide:DeckSlide}){
 const entries=slide.reading?.rows||slide.points.map(p=>[p.title,p.body]);
 return <div className="evidence-stack">
  <div className="evidence-header"><span>EVIDENCE & LIMITS</span><h2>{slide.reading?.title||"실험과 검증 범위"}</h2></div>
  {entries.slice(0,4).map((row,i)=><article key={i} className="evidence-row"><span>0{i+1}</span><div><strong>{row[0]}</strong><p>{row.slice(1).join(" · ")}</p></div></article>)}
  {slide.reading&&<a className="visual-source" href={slide.reading.source} target="_blank" rel="noopener noreferrer">{(slide.reading.sourceLabel||"검증 출처").replace(/(?:\s*↗)+\s*$/,"")} ↗</a>}
 </div>;
}
export function SlideVisual({slide,sources,motionPaused=false}:{slide:DeckSlide;sources:SourceRegistry;motionPaused?:boolean}){
 if(slide.id==="topology-public")return <DnsRouteTopology paused={motionPaused}/>;
 if(slide.id==="pi-network-plan")return <PiNetworkPlan paused={motionPaused}/>;
 if(slide.id==="introduction")return <IntroArchitecture paused={motionPaused}/>;
 if(slide.visual?.type==="independent-trends")return <IndependentTrends visual={slide.visual} sources={sources} paused={motionPaused}/>;
 if(slide.visual?.type==="comparison-bars")return <ComparisonBars visual={slide.visual} sources={sources}/>;
 if(slide.id==="bypass"&&slide.visual?.type==="cname-chain")return <DnsEvidenceDashboard visual={slide.visual} paused={motionPaused}/>;
 if(slide.visual?.type==="cname-chain")return <CnameWalkthrough visual={slide.visual} paused={motionPaused}/>;
 if(slide.kind==="policy-pipeline")return <PolicyPipeline paused={motionPaused}/>;
 if(slide.kind==="intel")return <IntelEvidence/>;
 if(slide.kind==="verdicts")return <PolicyVerdicts/>;
 if(slide.kind==="hero"||slide.kind==="conclusion")return <RestoredScene paused={motionPaused}/>;
 if(slide.kind==="adoption")return <AdoptionCompare paused={motionPaused}/>;
 if(slide.kind==="roadmap")return <RoadmapVisual/>;
 if(slide.kind==="thanks")return <ThanksVisual/>;
 if(slide.kind==="dns")return <DnsLab paused={motionPaused}/>;
 if(slide.kind==="dns-demo")return <PolicyLifecycle paused={motionPaused}/>;
 if(slide.kind==="http-demo")return <ProtocolWalkthrough paused={motionPaused} renderIcon={name=><DiagramIcon name={name}/>}/>;
 if(slide.kind==="topology")return <Topology comparison={slide.id!=="architecture"} publicMode={slide.visual?.type==="topology" && slide.visual.mode==="proposal"}/>;
 if(slide.kind==="governance")return <GovernanceReview/>;
 if(["metrics","evidence"].includes(slide.kind))return <EvidenceTable slide={slide} paused={motionPaused}/>;
 if(slide.kind==="repro")return <EvidenceVisual slide={slide}/>;
 if(slide.kind==="sources")return <ReferenceSlide slide={slide} sources={sources}/>;
 return <div className="diagram-panel abstract-panel"><span className="abstract-icon" aria-hidden="true">◇</span><h2>{slide.headline?.focus||slide.title.replaceAll("\n"," ")}</h2><p>확인된 조건, 경계와 책임을 분리합니다.</p><div className="abstract-trace"><i/><i/><i/><i/></div></div>;
}


