/** Pure globe mathematics and bounded resource ownership; no renderer/global DOM. */
export function geographicUnit(lat,lon){
 if(!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90)throw new RangeError('Finite latitude in [-90,90] and longitude required');
 const p=(90-lat)*Math.PI/180,a=(((lon+180)%360)+360)%360*Math.PI/180;
 return [-Math.cos(a)*Math.sin(p),Math.cos(p),Math.sin(a)*Math.sin(p)];
}
const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
const scale=(a,k)=>a.map(x=>x*k);
const add=(a,b)=>a.map((x,i)=>x+b[i]);
const unit=a=>{const n=Math.hypot(...a);if(n<1e-12)throw new RangeError('Degenerate direction');return scale(a,1/n);};
export function greatCirclePoints(from,to,count=72){
 if(!Array.isArray(from)||!Array.isArray(to)||from.length!==2||to.length!==2)throw new TypeError('Expected [latitude, longitude] endpoints');
 if(!Number.isInteger(count)||count<2||count>1024)throw new RangeError('Arc segment count must be an integer from 2 to 1024');
 const a=geographicUnit(...from),b=geographicUnit(...to),cos=Math.max(-1,Math.min(1,dot(a,b)));
 const angle=Math.acos(cos),sin=Math.sin(angle);
 // Antipodes have no unique shortest great circle. Choose a deterministic
 // perpendicular instead of normalizing their zero midpoint.
 let tangent;
 if(cos<-.999999){
  const ref=Math.abs(a[0])<.7?[1,0,0]:[0,1,0];
  tangent=unit(add(ref,scale(a,-dot(a,ref))));
 }
 return Array.from({length:count+1},(_,i)=>{
  const t=i/count;let d;
  if(i===0)d=a;else if(i===count)d=b;
  else if(tangent)d=add(scale(a,Math.cos(Math.PI*t)),scale(tangent,Math.sin(Math.PI*t)));
  else if(Math.abs(sin)<1e-7)d=unit(add(scale(a,1-t),scale(b,t)));
  else d=unit(add(scale(a,Math.sin((1-t)*angle)/sin),scale(b,Math.sin(t*angle)/sin)));
  return scale(d,1.046+.125*Math.sin(Math.PI*t));
 });
}
/** The wall clock must never make a returning tab leap around the globe. */
export function boundedFrameDelta(now,previous){
 if(!Number.isFinite(now)||!Number.isFinite(previous)||previous<=0)return 0;
 return Math.min(.07,Math.max(0,(now-previous)/1000));
}
/** Own every texture as soon as it resolves, including late arrivals after timeout. */
export function createTextureBatch(load,{timing=globalThis,timeout=10000}={}){
 const owned=new Set(),pending=new Set();let closed=false;
 function request(url){
  return new Promise((resolve,reject)=>{
   let settled=false,timer;
   const finish=(ok,value)=>{if(settled)return;settled=true;timing.clearTimeout(timer);pending.delete(cancel);ok?resolve(value):reject(value);};
   const cancel=()=>finish(false,new Error('Texture request cancelled'));
   pending.add(cancel);
   timer=timing.setTimeout(()=>finish(false,new Error('Texture request timed out')),timeout);
   if(closed){cancel();return;}
   Promise.resolve().then(()=>load(url)).then(texture=>{
    if(closed||settled){texture.dispose();return;}
    owned.add(texture);finish(true,texture);
   },error=>finish(false,error));
  });
 }
 function destroy(){if(closed)return;closed=true;for(const cancel of [...pending])cancel();for(const texture of owned)texture.dispose();owned.clear();}
 return Object.freeze({request,destroy});
}
