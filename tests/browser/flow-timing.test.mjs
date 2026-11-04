import test from 'node:test';
import assert from 'node:assert/strict';
import {nextFlowFrame,flowDelay,FLOW_STEP_MS,FLOW_REST_MS,FLOW_PACKET_MS} from '../../apps/web/src/components/flow-timing.mjs';

test('selected flow repeats forever after one second without selecting a scenario',()=>{
 let frame={step:0,resting:false,cycle:0};
 for(let cycle=0;cycle<100;cycle++){
  for(let step=0;step<6;step++){
   assert.deepEqual(frame,{step,resting:false,cycle});
   assert.equal(flowDelay(frame),FLOW_STEP_MS);
   frame=nextFlowFrame(frame,5);
  }
  assert.deepEqual(frame,{step:5,resting:true,cycle});
  assert.equal(flowDelay(frame),1000);
  frame=nextFlowFrame(frame,5);
 }
 assert.equal(frame.cycle,100);
 assert.ok(FLOW_PACKET_MS<FLOW_STEP_MS);
});
test('entry explanation plays once, subsequent loops start at the selected flow',()=>{
 let frame={step:0,resting:false,cycle:0};
 for(let i=0;i<18;i++)frame=nextFlowFrame(frame,16,11);
 assert.deepEqual(frame,{step:11,resting:false,cycle:1});
 assert.equal(flowDelay({step:2,resting:false,cycle:0},[2000,2100,700]),700);
 assert.equal(flowDelay({step:2,resting:true,cycle:0},[2000,2100,700]),FLOW_REST_MS);
});
test('single-state illustrations still pause and replay without changing selection',()=>{
 const rest=nextFlowFrame({step:0,resting:false,cycle:0},0);
 assert.deepEqual(rest,{step:0,resting:true,cycle:0});
 assert.deepEqual(nextFlowFrame(rest,0),{step:0,resting:false,cycle:1});
});
