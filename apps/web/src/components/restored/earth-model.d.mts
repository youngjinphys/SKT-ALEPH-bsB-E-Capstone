export function geographicUnit(lat:number,lon:number):[number,number,number];
export function greatCirclePoints(from:{lat:number;lon:number},to:{lat:number;lon:number},count?:number):[number,number,number][];
export function boundedFrameDelta(now:number,previous:number):number;
