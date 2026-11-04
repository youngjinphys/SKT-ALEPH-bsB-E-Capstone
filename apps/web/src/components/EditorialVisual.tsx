"use client";
import {useEffect,useState,type CSSProperties} from "react";
import {useStageIntroduction} from "./useStageIntroduction";
import "./stage-introduction.css";
import {useDiagramVisibility} from "./useDiagramVisibility";
import type {DeckSlide,SourceRegistry} from "@/lib/deck";
import {TermExplanation} from "./TermExplanation";
import {CnameWalkthrough} from "./CnameWalkthrough";
import {ServerDnsObservation} from "./ServerDnsObservation";
import "./server-dns-observation.css";
import "./editorial-visual.css";
import diagrams from "../../capstone/data/diagrams.json";

type Trend=Extract<NonNullable<DeckSlide["visual"]>,{type:"independent-trends"}>;
type Chain=Extract<NonNullable<DeckSlide["visual"]>,{type:"cname-chain"}>;

/** Separate baselines, units and citations: no overlaid series or shared scale. */
export function IndependentTrends({visual,sources,paused=false}:{visual:Trend;sources:SourceRegistry;paused?:boolean}){
 const {ref,inView}=useDiagramVisibility();
 const [motion,setMotion]=useState<"pending"|"reveal"|"done">("pending");
 const [ready,setReady]=useState(false),[reduced,setReduced]=useState(true);
 useEffect(()=>{const media=matchMedia('(prefers-reduced-motion: reduce)');const sync=()=>{setReduced(media.matches);setReady(true)};sync();media.addEventListener('change',sync);return()=>media.removeEventListener('change',sync)},[]);
 useEffect(()=>{if(!ready)return;if(paused||reduced){setMotion('done');return}if(!inView){setMotion(value=>value==='reveal'?'done':value);return}if(inView)setMotion(value=>value==='pending'?'reveal':value)},[ready,paused,reduced,inView]);
 useEffect(()=>{if(motion!=='reveal')return;const finish=()=>setMotion('done');const hidden=()=>{if(document.hidden)finish()};document.addEventListener('visibilitychange',hidden);const timer=setTimeout(finish,1800);return()=>{clearTimeout(timer);document.removeEventListener('visibilitychange',hidden)}},[motion]);
 const format=(value:number,unit:string)=>unit==="%"?`${value}%`:`${value.toLocaleString("ko-KR")} ${unit}`;
 return <figure className="diagram-panel chart-card independent-trends" aria-label={visual.title}>
  <figcaption><p className="diagram-caption">TWO OBSERVATIONS · SEPARATE MEASURES</p><h2>{visual.title}</h2></figcaption>
  <div className="independent-panels">{[visual.left,visual.right].map((series,index)=><section className="independent-series" data-series={index===0?"ai":"smishing"} aria-label={series.context!==undefined?series.title:`${series.title}, 단위 ${series.unit}`} key={series.sourceKey}>
   <div className="series-heading"><h3>{series.title}</h3>{series.context===undefined&&<span>단위 {series.unit}</span>}</div>
   {series.context!==undefined?<p className="series-context">{series.context}</p>:<div className="series-column-chart" data-motion={!ready?'pending':paused||reduced?'done':motion} data-count={series.values.length} style={{'--series-count':series.values.length} as CSSProperties}>
    <div className="series-y-axis" aria-hidden="true">{[series.max,series.max/2,0].map(value=><span key={value}>{value.toLocaleString('ko-KR')}</span>)}</div>
    <ol ref={ref} className="series-observations" aria-hidden="true">{series.values.map((value,i)=><li key={series.periods[i]}>
     <div className="series-track" aria-hidden="true"><span style={{height:`${Math.max(0, value/series.max*100)}%`,'--reveal-delay':`${i*50}ms`} as CSSProperties}/></div>
     <span className="series-period">{series.periods[i]}</span>
    </li>)}</ol>
    <dl className="series-exact-values">{series.values.map((value,i)=><div key={series.periods[i]}><dt>{series.periods[i]}</dt><dd className="series-value">{format(value,series.unit)}</dd></div>)}</dl>
   </div>}

   <div className="series-footer">{series.context===undefined&&<span>막대 범위 0–{format(series.max,series.unit)}</span>}{[series.sourceKey,...(series.additionalSourceKeys||[])].map(key=><a key={key} href={sources[key].url} rel="noopener noreferrer" target="_blank">{sources[key].label} ↗</a>)}</div>
  </section>)}</div>
  <p className="trend-warning">{visual.caveat}</p>
 </figure>;
}
export function AdoptionCompare({paused=false}:{paused?:boolean}){
 const [active,setActive]=useState("dns");
 const lanes=diagrams.protectionRoles;
 const selected=lanes.find(l=>l.id===active)!;
 return <TermExplanation term="fqdn" paused={paused}><section className="diagram-panel editorial-adoption" aria-label="브라우저, 추가 보안 앱, 보호 DNS의 보완 역할">
  <p className="diagram-caption fqdn-caption">조회 이름 · <span data-term-target="fqdn">FQDN</span></p><h2>기존 보호에 DNS 방어를 더합니다</h2>
  <div className="adoption-lanes" role="group" aria-label="보호 역할 선택">{lanes.map((l,i)=><button type="button" className={"adoption-lane adoption-"+l.id} key={l.id} aria-pressed={active===l.id} aria-controls="adoption-role-detail" onClick={()=>setActive(l.id)}>
   <span className="adoption-role"><span aria-hidden="true">0{i+1}</span><span><small>{l.kicker}</small><strong>{l.title}</strong></span></span>
   <span className="adoption-target">{l.target}</span>
  </button>)}</div>
  {selected.condition&&<div className="adoption-role-detail" id="adoption-role-detail" role="status" aria-live="polite"><small>{selected.title} · 적용 조건</small><strong>{selected.condition}</strong><p>{selected.detail}</p></div>}
 </section></TermExplanation>;
}
export function DnsEvidenceDashboard({visual,paused=false}:{visual:Chain;paused?:boolean}){
 const [mode,setMode]=useState<"server"|"fixture">("server");
 const [caseName,setCaseName]=useState<"cname"|"subtree">("cname");
 return <TermExplanation term={mode==="fixture"&&caseName==="cname"?"cname":undefined} paused={paused}><section className="diagram-panel dns-evidence-dashboard" aria-label="실제 DNS 관측과 격리 실험">
  <div className="dns-observation-modes" role="group" aria-label="검증 자료 선택">
   <button type="button" data-scenario-step="true" data-evidence-mode="server" aria-pressed={mode==="server"} onClick={()=>setMode("server")}>실제 server 질의</button>
   <button type="button" data-scenario-step="true" data-evidence-mode="fixture" aria-pressed={mode==="fixture"} onClick={()=>setMode("fixture")}>격리 fixture</button>
  </div>
  {mode==="server"?<ServerDnsObservation/>:<>
   <div className="dns-evidence-top"><strong>240<span>/240</span></strong><div><b>11월 4일 · 합성 DNS 기대 응답 일치</b><small>3회 × 4상태 × 5이름 × A/AAAA × UDP/TCP</small><small>루프백 fixture · 실제 탐지율 아님 · 두 반례 포함</small></div></div>
   <div className="dns-evidence-tabs" role="group" aria-label="반례 전환" data-flow-alternatives="true">
    <button type="button" data-scenario-step="true" aria-pressed={caseName==="cname"} onClick={()=>setCaseName("cname")}>CNAME 보호 공백</button>
    <button type="button" data-scenario-step="true" aria-pressed={caseName==="subtree"} onClick={()=>setCaseName("subtree")}>SUBTREE 과차단</button>
   </div>
   {caseName==="cname"?<CnameWalkthrough visual={visual} paused={paused}/>:<SubtreeIntroduction paused={paused}/>}
  </>}
 </section></TermExplanation>;
}

const milestones=[
 ["01","추가 보호·정상 영향","독립 정답셋 · 동일 브라우저 설정에서 추가 차단과 오탐을 함께 비교","효과 평가"],
 ["02","실단말 적용·복구","게시→수신→적용 시간과 양성·음성 캐시, 재질의까지 확인","운영 평가"],
 ["03","정책 비용·부하","동일 Pi의 정책 전후 지연 · 완료 QPS · CPU/RAM 비교","성능 평가"],
 ["04","확대에 필요한 책임","DNS 운영·사유 표시·위협정보 갱신·이의신청 주체 합의","운영 제안"]
];
export function RoadmapVisual(){
 return <section className="diagram-panel editorial-roadmap" aria-label="추가 보호 효과와 운영 품질의 다음 검증">

  <ol>{milestones.map(m=><li key={m[0]}><span>{m[0]}</span><div><small>{m[3]}</small><h3>{m[1]}</h3><p>{m[2]}</p></div></li>)}</ol>
  <p className="visual-caveat">KISA·NCSC 선례를 참고한 제안 · 가입자 선택·운영 책임·구제 절차 검토</p>
 </section>;
}
export function ThanksVisual(){
 return <div className="editorial-thanks" role="img" aria-label="감사합니다. 질문과 토론을 환영합니다.">
  <span className="thanks-ring" aria-hidden="true"/><span className="thanks-symbol" aria-hidden="true">◇</span>
  <strong>THANK YOU</strong><p>검증 가능한 정책, 신뢰할 수 있는 기본 보호</p><span className="thanks-invite">Q & A · SKT ALEPH E조</span>
 </div>;
}


/** Introduction: an implementation overview, with measured scope next to the result. */
export function IntroArchitecture({paused=false}:{paused?:boolean}){
 const stages=diagrams.introductionStages;
 const playback=useStageIntroduction(stages.length,paused);
 return <section ref={playback.ref} data-step={playback.step} data-playing={playback.playing} data-complete={playback.complete} className="diagram-panel intro-architecture stage-introduction" aria-label="수집·검토, 정책 서버, 보호 DNS의 세 단계">
  <p className="diagram-caption">PROTOTYPE · SIGNED POLICY FLOW</p>
  <h2>위협 신호에서 로컬 DNS 응답까지</h2>
  <ol className="intro-stages">{stages.map((stage,i)=><li key={stage.title}>
   <article className="intro-stage" data-stage-state={playback.reduced?"done":playback.step===i?"active":i<playback.step?"done":"pending"} aria-current={!playback.reduced&&playback.step===i?"step":undefined}>
    <span className="intro-stage-number" aria-hidden="true">{String(i+1).padStart(2,"0")}</span>
    <div><h3>{stage.title}</h3>{stage.system&&<strong>{stage.system}</strong>}{stage.detail&&<p>{stage.detail}</p>}</div>
   </article>
   {i<stages.length-1&&<span className="intro-stage-connector stage-connector" data-stage-state={playback.reduced||i<playback.step?"done":i===playback.step?"active":"pending"} aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3v17m-5-5 5 5 5-5"/></svg></span>}
  </li>)}</ol>
 </section>;
}


/** The counterexample has three causal stages, unlike static comparison cards. */
function SubtreeIntroduction({paused}:{paused:boolean}){
 const playback=useStageIntroduction(3,paused);
 const state=(index:number)=>playback.reduced?'done':playback.step===index?'active':index<playback.step?'done':'pending';
 return <div ref={playback.ref} className="subtree-case stage-introduction" data-flow-cycle={playback.cycle} data-step={playback.step} data-playing={playback.playing} data-complete={playback.complete} role="img" aria-label="부모 blocked.test를 SUBTREE 차단하면 정상 자식 child.blocked.test도 NXDOMAIN이 되는 반례">
  <small>정책 대상: BLOCK · SUBTREE</small><strong data-stage-state={state(0)}>blocked.test</strong><b className="stage-connector" data-stage-state={state(1)} aria-hidden="true">↓ 자식 이름에 적용 ↓</b><strong className="subtree-affected" data-stage-state={state(2)}>child.blocked.test · NXDOMAIN</strong><p>정상 하위 서비스까지 영향을 받는 과차단</p>
 </div>;
}
