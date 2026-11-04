/** Shared pacing for explanatory flows. Scenario selection is deliberately absent. */
export const FLOW_STEP_MS = 2200;
export const FLOW_REST_MS = 1000;
export const FLOW_PACKET_MS = 1800;

export function nextFlowFrame(frame, last, loopStart = 0) {
  if (frame.resting) return {step: loopStart, resting: false, cycle: frame.cycle + 1};
  if (frame.step < last) return {...frame, step: frame.step + 1};
  return {...frame, resting: true};
}

export function flowDelay(frame, durations = []) {
  return frame.resting ? FLOW_REST_MS : durations[frame.step] ?? FLOW_STEP_MS;
}
