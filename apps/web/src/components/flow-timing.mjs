/** Shared pacing for explanatory flows. Scenario selection is deliberately absent. */
import {presentationDuration} from './presentation-motion.mjs';
export const FLOW_STEP_MS = presentationDuration(2200);
export const FLOW_REST_MS = presentationDuration(1000);
export const FLOW_PACKET_MS = presentationDuration(1800);

export function nextFlowFrame(frame, last, loopStart = 0) {
  if (frame.resting) return {step: loopStart, resting: false, cycle: frame.cycle + 1};
  if (frame.step < last) return {...frame, step: frame.step + 1};
  return {...frame, resting: true};
}

export function flowDelay(frame, durations = []) {
  return frame.resting ? FLOW_REST_MS : durations[frame.step] === undefined ? FLOW_STEP_MS : presentationDuration(durations[frame.step]);
}
