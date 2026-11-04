import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {PRESENTATION_MOTION_SCALE,PRESENTATION_MOTION_RATE,presentationDuration,SLIDE_TRANSITION_MS} from '../../apps/web/src/components/presentation-motion.mjs';
import {FLOW_STEP_MS,FLOW_REST_MS,FLOW_PACKET_MS,flowDelay,nextFlowFrame} from '../../apps/web/src/components/flow-timing.mjs';
const read=path=>readFileSync(new URL('../../apps/web/src/'+path,import.meta.url),'utf8');

test('presentation clocks use precisely half speed and double duration',()=>{
 assert.equal(PRESENTATION_MOTION_SCALE,2);
 assert.equal(PRESENTATION_MOTION_RATE,.5);
 assert.equal(presentationDuration(650),1300);
 assert.equal(SLIDE_TRANSITION_MS,760);
 assert.equal(FLOW_STEP_MS,4400);
 assert.equal(FLOW_REST_MS,2000);
 assert.equal(FLOW_PACKET_MS,3600);
 assert.ok(FLOW_PACKET_MS<FLOW_STEP_MS);
});
test('custom intro steps and rests scale once while replay keeps its original state machine',()=>{
 const first={step:0,resting:false,cycle:0};
 assert.equal(flowDelay(first),4400);
 assert.equal(flowDelay(first,[650]),1300);
 assert.equal(flowDelay(first,[0]),0);
 const last={step:2,resting:false,cycle:0};
 const rest=nextFlowFrame(last,2,1);
 assert.deepEqual(rest,{step:2,resting:true,cycle:0});
 assert.equal(flowDelay(rest,[650]),2000);
 assert.deepEqual(nextFlowFrame(rest,2,1),{step:1,resting:false,cycle:1});
});
test('CSS times inherit the deck scale, including stagger and pseudo-elements',()=>{
 for(const folder of ['app','components'])for(const file of readdirSync(new URL('../../apps/web/src/'+folder+'/',import.meta.url))){
  if(!file.endsWith('.css'))continue;
  const css=read(folder+'/'+file);
  for(const declaration of css.matchAll(/\b(?:animation|transition)(?:-(?:duration|delay))?\s*:[^;{}]+/g)){
   const unscaled=declaration[0].replace(/calc\((?:\d*\.)?\d+(?:ms|s) \* var\(--presentation-motion-scale, 1\)\)/g,'').replace(/\.01ms/g,'');
   assert.doesNotMatch(unscaled,/(?<![\w.-])(?:\d*\.)?\d+(?:ms|s)\b/,`${file}: ${declaration[0]}`);
  }
 }
 assert.match(read('components/editorial-visual.css'),/calc\(var\(--reveal-delay\) \* var\(--presentation-motion-scale, 1\)\)/);
 assert.match(read('components/SlideDeck.tsx'),/"--presentation-motion-scale":PRESENTATION_MOTION_SCALE/);
 assert.match(read('components/SlideDeck.tsx'),/},SLIDE_TRANSITION_MS\)/);
});
test('shared renderers retain full-speed defaults; presentation opts in without delaying controls or IO',()=>{
 const scene=read('components/RestoredScene.tsx');
 for(const renderer of ['earth-globe','mascot-surface','opening-orbit'])assert.match(read('components/restored/'+renderer+'.mjs'),/motionRate=1/);
 assert.match(scene,/<RestoredMascot paused=\{paused\} motionRate=\{PRESENTATION_MOTION_RATE\}/);
 assert.match(read('components/Landing.tsx'),/<RestoredMascot paused=\{paused\}\//);
 assert.match(read('components/restored/earth-globe.mjs'),/boundedFrameDelta\(time,lastTime\)\*motionRate/);
 assert.match(read('components/restored/mascot-surface.mjs'),/time\+=Math.min\(.08,Math.max\(0,\(now-last\)\/1000\)\)\*motionRate/);
 assert.match(read('components/restored/opening-orbit.mjs'),/85\*frameDelta\*motionRate/);
 assert.match(read('components/SlideDeck.tsx'),/navigationBurstUntil.current=now\+180/);
 assert.match(read('components/EditorialVisual.tsx'),/setTimeout\(finish,presentationDuration\(1800\)\)/);
 assert.match(read('components/restored/mascot-surface.mjs'),/Mascot image deadline'\)\),8000/);
});
