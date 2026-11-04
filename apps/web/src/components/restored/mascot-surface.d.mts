export interface MascotController {ready:Promise<boolean>;setMotion(on:boolean):void;greet():boolean;destroy():void}
export function mountMascotSurface(host:HTMLElement,options:{fallback:HTMLImageElement;motion?:boolean;motionRate?:number}):MascotController;
export function motionAt(time:number,greetingAge?:number):{angles:number[];blink:number};
export function warpPoint(point:number[],angles:number[]):number[];
