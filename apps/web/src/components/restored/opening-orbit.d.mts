export interface Projection {id:string;x:number;y:number;visible:boolean;alpha?:number;frontScore?:number}
export interface OpeningOrbit {setMotion(on:boolean):void;updateProjection(points:Projection[],width?:number,height?:number):void;setFallback(points?:Projection[]):void;destroy():void}
export const CARD_LOCATIONS:ReadonlyArray<{id:string;lat:number;lon:number;title:string;originalTitle:string;subtitle:string;detail:string;direction:number[]}>;
export function createOpeningOrbit(host:HTMLElement,options?:{motion?:boolean;motionRate?:number}):OpeningOrbit;

export function leaderToCardEdge(pin:{x:number;y:number},rect:{left:number;top:number;width:number;height:number},gap?:number):{angle:number;length:number};

export interface CardRect {left:number;top:number;width:number;height:number}
export function advanceFloatingCard(rect:CardRect,target:{x:number;y:number},obstacles:CardRect[],bounds:{width:number;height:number},maxStep?:number,gap?:number,blend?:number):CardRect;

export function segmentIntersectsRect(a:{x:number;y:number},b:{x:number;y:number},rect:CardRect,padding?:number):boolean;

export function initialFloatingCard(rect:CardRect,target:{x:number;y:number},obstacles:CardRect[],bounds:{width:number;height:number},gap?:number):CardRect|null;

export function geographicCardVisible(point:{visible:boolean;frontScore?:number;alpha?:number}|undefined,wasVisible?:boolean):boolean;
