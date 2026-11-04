import type {Projection} from './opening-orbit.mjs';
export interface GlobeController {ready:Promise<boolean>;setMotion(on:boolean):void;destroy():void}
export function mountEarthGlobe(host:HTMLElement,options?:{motion?:boolean;anchors?:ReadonlyArray<{id:string;lat:number;lon:number}>;onProjection?:(points:Projection[],width?:number,height?:number)=>void;onFallback?:(points?:Projection[])=>void}):GlobeController;
