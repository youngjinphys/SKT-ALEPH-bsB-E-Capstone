/** Illustrative packet choreography, not measured or live threat telemetry. */
export const TRAIL_COUNT=10;
export const TRAIL_SPACING=.007;
export function packetPhase(progress,lag=0){if(!Number.isFinite(progress)||!Number.isFinite(lag))return 0;return ((progress-lag)%1+1)%1;}
export function routeSample(points,progress,target){const p=packetPhase(progress)*(points.length-1),i=Math.floor(p);return target.copy(points[i]).lerp(points[Math.min(i+1,points.length-1)],p-i);}
export function trailScale(index,count=TRAIL_COUNT){return .2+.8*(1-Math.max(0,Math.min(index,count-1))/Math.max(1,count-1))**1.5;}
