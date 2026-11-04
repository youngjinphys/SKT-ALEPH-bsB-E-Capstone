"use client";
import {Fragment} from "react";
import {DiagramText} from "./DiagramText";
import type {DeckSlide} from "@/lib/deck";
import {useDiagramPlayback} from "./useDiagramPlayback";
import "./cname-walkthrough.css";

type CnameVisual=Extract<NonNullable<DeckSlide["visual"]>,{type:"cname-chain"}>;
export function CnameWalkthrough({visual,paused=false}:{visual:CnameVisual;paused?:boolean}){
 const {diagramRef,step,reduced,playing,cycle,automatic,epoch}=useDiagramPlayback({steps:visual.nodes.length,paused});
 const suffix=reduced?" · 모션 줄이기: 전체 경로 표시":paused?" · 전체 모션 일시정지":"";
 const labels=visual.nodes.map((node,index)=>`단계 ${index+1} / ${visual.nodes.length} · ${node.label}${suffix}`);
 return <section className="diagram-panel cname-walkthrough" data-step={step} data-flow-cycle={cycle} data-playing={playing&&!paused&&!reduced} aria-label="CNAME 보호 공백 단계별 설명">
  <p className="diagram-caption">RESPONSE CHAIN · KNOWN GAP</p>
  <h2>{visual.title}</h2>
  <div className="chain-nodes">{visual.nodes.map((node,i)=><Fragment key={i}><div ref={i===0?diagramRef:undefined} className="chain-step" data-active={step===i} aria-current={step===i?"step":undefined}>
   <span>{node.label}</span><strong>{node.value}</strong>
   <b data-state={node.state}>{["ALLOW","BLOCK"].includes(node.state)?`정책 ${node.state}`:node.state==="A"?"A 레코드":node.state}</b>
  </div>
   {i<visual.links.length&&<div className="cname-link" data-active={step===i}><span className="cname-arrow" aria-hidden="true"><i key={epoch} className="cname-packet"/>↓</span><span className="cname-link-label" data-term-target={visual.links[i]==="CNAME"?"cname":undefined}>{visual.links[i]}</span></div>}
  </Fragment>)}</div>
  <p className="cname-progress" aria-live={automatic?"off":"polite"} aria-atomic="true">
   {/* Reserve the tallest authored phase at this width. Hidden copies affect
       layout only; assistive technology receives exactly one current status. */}
   {visual.nodes.map((node,i)=><span className="cname-progress-reserve" aria-hidden="true" key={i}>단계 {i+1} / {visual.nodes.length} · {node.label} · 모션 줄이기: 전체 경로 표시</span>)}
   <span className="cname-progress-current"><DiagramText value={labels[step]} values={labels} paused={paused}/></span>
  </p>
  <p className="visual-caveat">{visual.caveat}</p>
 </section>;
}
