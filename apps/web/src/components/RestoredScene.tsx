"use client";
import {useEffect,useRef} from "react";
import {PRESENTATION_MOTION_RATE} from "./presentation-motion.mjs";
import type {GlobeController} from "./restored/earth-globe.mjs";
import type {MascotController} from "./restored/mascot-surface.mjs";
import "./restored-scene.css";
import {CARD_LOCATIONS,createOpeningOrbit,type OpeningOrbit} from "./restored/opening-orbit.mjs";

/** React owns mounting; historical renderers own and dispose their GPU resources.
 * The Earth and packet paths are decorative, never real threat observations. */
export function RestoredMascot({paused=false,motionRate=1}:{paused?:boolean;motionRate?:number}){
 const host=useRef<HTMLDivElement>(null);
 const fallback=useRef<HTMLImageElement>(null);
 const controller=useRef<MascotController|null>(null);
 const pausedRef=useRef(paused);pausedRef.current=paused;
 useEffect(()=>{
  let cancelled=false;
  void import("./restored/mascot-surface.mjs").then(({mountMascotSurface})=>{
   if(cancelled||!host.current||!fallback.current)return;
   controller.current=mountMascotSurface(host.current,{fallback:fallback.current,motion:!pausedRef.current,motionRate});
  }).catch(()=>{if(!cancelled&&host.current){host.current.dataset.rig='fallback';host.current.dataset.rigFallbackReason='module-load-failed';}});
  return()=>{cancelled=true;controller.current?.destroy();controller.current=null;};
 },[motionRate]);
 useEffect(()=>{controller.current?.setMotion(!paused);},[paused]);
 return <div ref={host} className="restored-mascot" data-restored-mascot="true">
  <img ref={fallback} src="/assets/guardian/guardian-smile-open.webp" width="1024" height="1024" alt="피라냥 안내 캐릭터" decoding="async"/>
 </div>;
}

export function RestoredScene({paused=false}:{paused?:boolean}){
 const host=useRef<HTMLDivElement>(null);
 const scene=useRef<HTMLElement>(null);
 const orbit=useRef<OpeningOrbit|null>(null);
 const controller=useRef<GlobeController|null>(null);
 const pausedRef=useRef(paused);pausedRef.current=paused;
 useEffect(()=>{
  let cancelled=false;
  if(scene.current)orbit.current=createOpeningOrbit(scene.current,{motion:!pausedRef.current,motionRate:PRESENTATION_MOTION_RATE});
  void import("./restored/earth-globe.mjs").then(({mountEarthGlobe})=>{
   if(cancelled||!host.current)return;
   controller.current=mountEarthGlobe(host.current,{motion:!pausedRef.current,motionRate:PRESENTATION_MOTION_RATE,anchors:CARD_LOCATIONS,onProjection:orbit.current?.updateProjection,onFallback:orbit.current?.setFallback});
  }).catch(()=>{if(!cancelled&&host.current){host.current.dataset.earthState="fallback";host.current.dataset.earthFallbackReason="module-load-failed";orbit.current?.setFallback();}});
  return()=>{cancelled=true;controller.current?.destroy();controller.current=null;orbit.current?.destroy();orbit.current=null;};
 },[]);
 useEffect(()=>{controller.current?.setMotion(!paused);orbit.current?.setMotion(!paused);},[paused]);
 return <figure ref={scene} className="restored-scene" aria-label="회전하는 지구와 피라냥: 교육용 역할 배치와 연결 도식">
  <div className="restored-globe-orbit" aria-hidden="true"/>
  <div ref={host} className="restored-globe" data-earth-state="loading">
   <img className="restored-earth-fallback" src="/capstone/assets/earth-fallback.webp" width="1536" height="1536" alt="지구를 형상화한 설명용 이미지"/>
  </div>
  <div className="cyber-space-infos" data-orbit-layout="loading" aria-hidden="true">{CARD_LOCATIONS.map(card=><div className={`cyber-space-panel cyber-info-${card.id}`} data-geo-id={card.id} title={`${card.originalTitle} · ${card.detail} (시연용)`} key={card.id}><svg className="globe-role-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={card.id==='government'?'M3 9h18L12 3 3 9 M5 10v9 M10 10v9 M14 10v9 M19 10v9 M3 21h18':card.id==='isp'?'M3 6c0-5 18-5 18 0s-18 5-18 0v12c0 5 18 5 18 0V6 M3 12c0 5 18 5 18 0':card.id==='users'?'M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M2 21v-2a7 7 0 0 1 14 0v2 M17 4a4 4 0 0 1 0 8 M22 21v-2a7 7 0 0 0-3-6':'M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6z M12 7v6 M12 17h.01'}/></svg><div className="cyber-info-copy"><strong>{card.title}</strong><span>{card.subtitle}</span><small className="cyber-geo-location">{card.detail}</small></div></div>)}</div>
  <div className="restored-scene-mascot"><RestoredMascot paused={paused} motionRate={PRESENTATION_MOTION_RATE}/></div>
 </figure>;
}
