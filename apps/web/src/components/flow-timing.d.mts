export type FlowFrame = {step: number; resting: boolean; cycle: number};
export const FLOW_STEP_MS: number;
export const FLOW_REST_MS: number;
export const FLOW_PACKET_MS: number;
export function nextFlowFrame(frame: FlowFrame, last: number, loopStart?: number): FlowFrame;
export function flowDelay(frame: FlowFrame, durations?: readonly number[]): number;
