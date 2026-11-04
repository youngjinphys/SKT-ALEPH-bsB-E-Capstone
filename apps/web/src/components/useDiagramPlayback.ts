"use client";
import {useCallback,useEffect,useLayoutEffect,useState,type SetStateAction} from 'react';
import {useDiagramVisibility} from './useDiagramVisibility';
import {flowDelay,nextFlowFrame,type FlowFrame} from './flow-timing.mjs';

const DEFAULT_DURATIONS:readonly number[]=[];
/** Repeat only this flow, with a quiet two-second gap. Never choose another scenario. */
export function useDiagramPlayback({steps,paused,loopStart=0,reducedStep=0,durations=DEFAULT_DURATIONS}:{steps:number;paused:boolean;loopStart?:number;reducedStep?:number;durations?:readonly number[]}){
 const {ref:diagramRef,inView}=useDiagramVisibility();
 const last=Math.max(0,steps-1);
 const [run,setRun]=useState(0);
 const [frame,setFrame]=useState<FlowFrame>({step:0,resting:false,cycle:0});
 const [running,setRunning]=useState(true),[positioned,setPositioned]=useState(false);
 const [reduced,setReduced]=useState(true),[visible,setVisible]=useState(true),[motionReady,setMotionReady]=useState(false);
 useLayoutEffect(()=>{
  const media=window.matchMedia('(prefers-reduced-motion: reduce)');
  const syncMotion=()=>{setReduced(media.matches);setMotionReady(true)};
  const syncVisibility=()=>setVisible(!document.hidden);
  syncMotion();syncVisibility();media.addEventListener('change',syncMotion);document.addEventListener('visibilitychange',syncVisibility);
  return()=>{media.removeEventListener('change',syncMotion);document.removeEventListener('visibilitychange',syncVisibility)};
 },[]);
 const canAnimate=motionReady&&running&&!paused&&!reduced&&visible&&inView;
 useEffect(()=>{
  if(!canAnimate)return;
  const timer=window.setTimeout(()=>{if(!document.hidden)setFrame(current=>nextFlowFrame(current,last,Math.min(last,loopStart)))},flowDelay(frame,durations));
  return()=>window.clearTimeout(timer);
 },[frame,last,loopStart,canAnimate,durations]);
 const restart=useCallback((start=loopStart)=>{
  setRun(value=>value+1);setPositioned(true);setFrame({step:Math.max(0,Math.min(last,start)),resting:false,cycle:0});setRunning(true);
 },[last,loopStart]);
 const setStep=useCallback((value:SetStateAction<number>)=>{
  setPositioned(true);setFrame(current=>({step:Math.max(0,Math.min(last,typeof value==='function'?value(current.step):value)),resting:false,cycle:0}));setRunning(false);
 },[last]);
 const pause=useCallback(()=>setRunning(false),[]);
 const reset=useCallback(()=>{setPositioned(true);setRunning(false);setFrame({step:0,resting:false,cycle:0})},[]);
 const play=useCallback(()=>restart(),[restart]);
 useEffect(()=>{const replay=()=>{if(inView&&!paused&&!reduced&&!document.hidden)restart()};window.addEventListener('capstone:replay',replay);return()=>window.removeEventListener('capstone:replay',replay)},[restart,inView,paused,reduced]);
 return {diagramRef,step:motionReady&&reduced&&!positioned?Math.min(last,reducedStep):Math.min(last,frame.step),setStep,reduced,
  automatic:canAnimate,playing:canAnimate&&!frame.resting,resting:canAnimate&&frame.resting,cycle:frame.cycle,
  hint:canAnimate&&frame.cycle>0,epoch:`${run}:${frame.cycle}`,complete:frame.resting,play,pause,reset,restart};
}
