"use client";
import {useDiagramPlayback} from './useDiagramPlayback';

/** Causal stages repeat slowly; selecting a detail still holds it for inspection. */
export function useStageIntroduction(steps:number,paused=false){
 const playback=useDiagramPlayback({steps,paused,reducedStep:Math.max(0,steps-1)});
 return {ref:playback.diagramRef,step:playback.step,playing:playback.playing,reduced:playback.reduced,
  restart:playback.restart,select:playback.setStep,complete:playback.complete,
  cycle:playback.cycle,hint:playback.hint,resting:playback.resting};
}
