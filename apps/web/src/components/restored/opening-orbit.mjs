/** Geographic labels share the Earth mesh's yaw, tilt and camera.
 * All locations, including Attacker, are illustrative—not attribution.
 * The projection source owns the clock; no independent orbit is animated.
 */
export const CARD_LOCATIONS=Object.freeze([
 Object.freeze({id:'government',lat:37.5665,lon:126.9780,title:'정부',subtitle:'정책 공급',originalTitle:'Government',detail:'서울 · 시연용',direction:[-1,-1]}),
 Object.freeze({id:'isp',lat:1.3521,lon:103.8198,title:'ISP',subtitle:'DNS 집행',originalTitle:'ISP',detail:'싱가포르 · 시연용',direction:[1,1]}),
 Object.freeze({id:'users',lat:51.5074,lon:-0.1278,title:'이용자',subtitle:'보호 DNS 사용',originalTitle:'Users',detail:'런던 · 시연용',direction:[1,1]}),
 Object.freeze({id:'attacker',lat:-9.0,lon:-175.0,title:'가상 공격자',subtitle:'시연용 발신',originalTitle:'Attacker',detail:'태평양의 가상 위치',direction:[1,-1]}),
]);
/** Neutral, non-directional leader stops before the card rectangle. */
export function leaderToCardEdge(pin,rect,gap=3){
 const centerX=rect.left+rect.width/2,centerY=rect.top+rect.height/2;
 const dx=centerX-pin.x,dy=centerY-pin.y,distance=Math.hypot(dx,dy);
 const edgeFraction=Math.min(dx!==0?rect.width/2/Math.abs(dx):Infinity,dy!==0?rect.height/2/Math.abs(dy):Infinity);
 return {angle:Math.atan2(dy,dx),length:Math.max(0,distance*(1-Math.min(1,edgeFraction))-Math.max(0,gap))};
}
const clamp=(n,min,max)=>Math.min(max,Math.max(min,n));
/** Bounded incremental movement: shorten an obstructed step without changing its direction. */
export function advanceFloatingCard(rect,target,obstacles,bounds,maxStep=4,gap=8,blend=.16){
 const tx=clamp(target.x-rect.width/2,gap,Math.max(gap,bounds.width-rect.width-gap));
 const ty=clamp(target.y-rect.height/2,gap,Math.max(gap,bounds.height-rect.height-gap));
 const dx=tx-rect.left,dy=ty-rect.top,d=Math.hypot(dx,dy),scale=d?Math.min(Math.max(0,Math.min(1,blend)),Math.max(0,maxStep)/d):0;
 const sx=dx*scale,sy=dy*scale;
 const fits=(left,top)=>left>=gap&&top>=gap&&left+rect.width<=bounds.width-gap&&top+rect.height<=bounds.height-gap&&obstacles.every(o=>left+rect.width+gap<=o.left||left>=o.left+o.width+gap||top+rect.height+gap<=o.top||top>=o.top+o.height+gap);
 for(const [x,y] of [[sx,sy],[sx*.5,sy*.5],[sx*.25,sy*.25]])if((x||y)&&fits(rect.left+x,rect.top+y))return {...rect,left:rect.left+x,top:rect.top+y};
 return rect;
}
/** Start close to the first projected anchor, without an animated trip from a corner. */
export function initialFloatingCard(rect,target,obstacles,bounds,gap=8){
 const fits=r=>obstacles.every(o=>r.left+r.width+gap<=o.left||r.left>=o.left+o.width+gap||r.top+r.height+gap<=o.top||r.top>=o.top+o.height+gap);
 const offsets=[[0,0],[0,-rect.height-gap],[0,rect.height+gap],[-rect.width-gap,0],[rect.width+gap,0],[-rect.width-gap,-rect.height-gap],[rect.width+gap,-rect.height-gap],[-rect.width-gap,rect.height+gap],[rect.width+gap,rect.height+gap]];
 // Real obstacle dimensions can exceed the card-sized ring (e.g. mascot).
 // Include positions immediately outside their edges, still nearest the anchor.
 for(const o of obstacles){
  const xs=[o.left-gap-rect.width/2,o.left+o.width+gap+rect.width/2],ys=[o.top-gap-rect.height/2,o.top+o.height+gap+rect.height/2];
  for(const x of xs)offsets.push([x-target.x,0]);for(const y of ys)offsets.push([0,y-target.y]);
  for(const x of xs)for(const y of ys)offsets.push([x-target.x,y-target.y]);
 }
 offsets.sort((a,b)=>Math.hypot(...a)-Math.hypot(...b));
 for(const [ox,oy] of offsets){
  const candidate={...rect,left:clamp(target.x-rect.width/2+ox,gap,Math.max(gap,bounds.width-rect.width-gap)),top:clamp(target.y-rect.height/2+oy,gap,Math.max(gap,bounds.height-rect.height-gap))};
  if(fits(candidate))return candidate;
 }
 return null;
}
/** Closed segment vs expanded box, used to suppress misleading crossing leaders. */
export function segmentIntersectsRect(a,b,rect,padding=2){
 let lo=0,hi=1;
 for(const [start,delta,min,max] of [[a.x,b.x-a.x,rect.left-padding,rect.left+rect.width+padding],[a.y,b.y-a.y,rect.top-padding,rect.top+rect.height+padding]]){
  if(Math.abs(delta)<1e-9){if(start<min||start>max)return false;continue;}
  const t1=(min-start)/delta,t2=(max-start)/delta;lo=Math.max(lo,Math.min(t1,t2));hi=Math.min(hi,Math.max(t1,t2));if(lo>hi)return false;
 }
 return true;
}
/** Limb hysteresis avoids repeated show/hide while the projected anchor grazes Earth. */
export function geographicCardVisible(point,wasVisible=false){
 return Boolean(point?.visible)&&Number.isFinite(point.frontScore)&&point.frontScore>(wasVisible?.025:.08)&&Number(point.alpha??1)>.001;
}
const none=()=>({setMotion(){},updateProjection(){},setFallback(){},destroy(){}});
const px=n=>n.toFixed(3)+'px';
const cq=(n,total)=>((n/total)*100).toFixed(4);
const translated=(x,y,w,h)=>'translate3d('+cq(x,w)+'cqw,'+cq(y,h)+'cqh,0) translate(-50%,-50%)';
export function createOpeningOrbit(visual,{motion=true,motionRate=1}={}){
 const globe=visual?.querySelector?.('.restored-globe');
 const layer=visual?.querySelector?.('.cyber-space-infos');
 if(!visual||!globe||!layer)return none();
 const doc=visual.ownerDocument,media=window.matchMedia('(prefers-reduced-motion: reduce)');
 const abort=new AbortController(),roles=new Map();
 let destroyed=false,requested=Boolean(motion),fallback=false,lastFrame=null,geometryDirty=true;
 let mascotBounds=null,lastProjectionTime=0,frameDelta=1/30;
 let geometry={width:0,height:0,globeLeft:0,globeTop:0,globeWidth:0,globeHeight:0};
 const enabled=()=>requested&&!media.matches&&!doc.hidden&&!destroyed;
 const syncMotion=()=>{
  if(destroyed)return;
  const value=enabled()?'on':'off';
  if(visual.dataset.orbitMotion!==value)visual.dataset.orbitMotion=value;
 };
 const visible=(role,show,alpha=0)=>{
  role.card.style.visibility=geometry.mobile?'visible':show?'visible':'hidden';
  role.card.style.opacity=geometry.mobile?'1':show?String(alpha):'0';
  role.card.dataset.surfaceVisible=geometry.mobile?'legend':String(show);
  if(role.visible!==show){
   role.visible=show;
   for(const element of (geometry.mobile?[role.pin,role.leader]:[role.card,role.pin,role.leader])){
    element.style.visibility=show?'visible':'hidden';
    element.dataset.surfaceVisible=String(show);
   }
  }
  if(show&&(role.alpha===undefined||Math.abs(alpha-role.alpha)>0.005)){
   role.alpha=alpha;
   for(const element of (geometry.mobile?[role.pin,role.leader]:[role.card,role.pin,role.leader]))element.style.opacity=String(alpha);
  }else if(!show&&role.alpha!==0){
   role.alpha=0;
   for(const element of (geometry.mobile?[role.pin,role.leader]:[role.card,role.pin,role.leader]))element.style.opacity='0';
  }
 };
 const writeTransform=(role,element,key,value)=>{
  if(role[key]!==value){element.style.transform=value;role[key]=value;}
 };
 for(const entry of CARD_LOCATIONS){
  const card=layer.querySelector('.cyber-space-panel[data-geo-id="'+entry.id+'"]');
  if(!card)continue;
  const pin=doc.createElement('span');
  pin.className='cyber-surface-pin cyber-surface-pin--'+entry.id;
  pin.dataset.geoId=entry.id;pin.setAttribute('aria-hidden','true');
  const leader=doc.createElement('span');
  leader.className='cyber-surface-leader cyber-surface-leader--'+entry.id;
  leader.dataset.geoId=entry.id;leader.setAttribute('aria-hidden','true');
  layer.prepend(pin,leader);
  card.dataset.geoLat=String(entry.lat);card.dataset.geoLon=String(entry.lon);
  const role={entry,card,pin,leader,visible:null,alpha:undefined,size:{width:108,height:48}};
  visible(role,false);
  roles.set(entry.id,role);
 }
 if(roles.size!==CARD_LOCATIONS.length){
  for(const {pin,leader} of roles.values()){pin.remove();leader.remove();}
  return none();
 }
 visual.dataset.orbitAnchor='geographic-surface';
 visual.dataset.orbitLayout='loading';
 layer.dataset.orbitLayout='loading';
 syncMotion();
 // Offset geometry is read only when the viewport/card dimensions change.
 function measure(){
  const next={width:visual.offsetWidth,height:visual.offsetHeight,
    globeLeft:globe.offsetLeft,globeTop:globe.offsetTop,
    globeWidth:globe.offsetWidth,globeHeight:globe.offsetHeight};
  const changed=Object.keys(next).some(key=>next[key]!==geometry[key]);
  geometry={...geometry,...next};
  for(const role of roles.values()){
   const size={width:role.card.offsetWidth||108,height:role.card.offsetHeight||48,left:role.card.offsetLeft,top:role.card.offsetTop};
   if(changed||Object.keys(size).some(key=>size[key]!==role.size[key])){
    role.rect=role.rect?{...role.rect,width:size.width,height:size.height}:{...size};
    role.size=size;role.needsReflow=true;
   }
  }
  const mascot=visual.querySelector('.restored-scene-mascot');
  mascotBounds=mascot?{left:mascot.offsetLeft,top:mascot.offsetTop,width:mascot.offsetWidth,height:mascot.offsetHeight}:null;
  geometry.mobile=window.matchMedia('(max-width: 780px)').matches;
  geometryDirty=false;
 }
 function position(role,point){
  if(!point){role.depthShown=false;visible(role,false);return;}
  const {width,height,globeLeft,globeTop}=geometry;
  const x=globeLeft+point.x,y=globeTop+point.y;
  if(![x,y,width,height].every(Number.isFinite)||width<=0||height<=0
    ||x<0||y<0||x>width||y>height){visible(role,false);return;}
  const wasShown=role.wasShown===true;
  role.card.dataset.depth=Number(point.frontScore??0).toFixed(3);
  if(geometry.mobile){role.card.style.visibility='visible';role.card.style.opacity='1';role.card.dataset.surfaceVisible='legend';}
  // Follow the rotating projected point with a bounded, collision-safe offset.
  if(!geometry.mobile){
   const obstacles=[...roles.values()].filter(other=>other!==role&&other.depthShown===true&&other.initialized).map(other=>other.rect);
   if(mascotBounds)obstacles.push(mascotBounds);
   const target={x:x+role.entry.direction[0]*(role.size.width/2+14),y:y+role.entry.direction[1]*(role.size.height/2+14)};
   if(!role.initialized||!wasShown||role.needsReflow){
    const aim=role.needsReflow&&role.initialized&&wasShown?{x:role.rect.left+role.rect.width/2,y:role.rect.top+role.rect.height/2}:target;
    const initial=initialFloatingCard(role.rect,aim,obstacles,{width,height:height-28});
    if(!initial){role.initialized=false;role.card.dataset.placement='pending';visible(role,false);return;}
    role.rect=initial;role.initialized=true;role.needsReflow=false;role.card.dataset.placement='ready';
   }
   else if(role.depthShown&&enabled())role.rect=advanceFloatingCard(role.rect,target,obstacles,{width,height:height-28},85*frameDelta*motionRate,8,1-Math.exp(-frameDelta*motionRate/.16));
   writeTransform(role,role.card,'cardTransform','translate3d('+px(role.rect.left-role.size.left)+','+px(role.rect.top-role.size.top)+',0)');
   role.card.dataset.cardX=role.rect.left.toFixed(3);role.card.dataset.cardY=role.rect.top.toFixed(3);
  }
  if(!role.depthShown){visible(role,false);return;}
  const cw=role.size.width,ch=role.size.height;
  const segment=leaderToCardEdge({x,y},{left:role.rect.left,top:role.rect.top,width:cw,height:ch});
  writeTransform(role,role.pin,'pinTransform',translated(x,y,width,height));
  const leader='translate3d('+px(x)+','+px(y)+',0) rotate('+segment.angle.toFixed(6)+'rad) scaleX('+segment.length.toFixed(3)+')';
  writeTransform(role,role.leader,'leaderTransform',leader);
  visible(role,true,clamp(point.alpha??1,0,1));
  const endpoint={x:x+Math.cos(segment.angle)*segment.length,y:y+Math.sin(segment.angle)*segment.length};
  const blocked=[...roles.values()].filter(other=>other!==role&&other.depthShown===true&&other.initialized).map(other=>other.rect);
  if(mascotBounds)blocked.push(mascotBounds);
  const occluded=blocked.some(rect=>segmentIntersectsRect({x,y},endpoint,rect));
  // Do not draw a straight connector through unrelated roles; the pin/card remain.
  role.leader.style.visibility='visible';role.leader.style.opacity=occluded?'0':String(clamp(point.alpha??1,0,1));role.leader.dataset.occluded=String(occluded);
  // Diagnostic coordinates only update at meaningful position changes.
  if(!role.reported||Math.hypot(x-role.reported.x,y-role.reported.y)>=0.24){
   role.reported={x,y};
   role.card.dataset.pinX=x.toFixed(3);
   role.card.dataset.pinY=y.toFixed(3);
   role.card.dataset.depth=Number(point.frontScore??0).toFixed(3);
  }
 }
 function updateProjection(projected,globeWidth,globeHeight){
  if(destroyed||fallback||!Array.isArray(projected))return;
  const now=performance.now();frameDelta=lastProjectionTime?Math.min(.05,Math.max(.001,(now-lastProjectionTime)/1000)):1/30;lastProjectionTime=now;
  lastFrame=projected;
  if(geometryDirty||(globeWidth&&globeWidth!==geometry.globeWidth)||(globeHeight&&globeHeight!==geometry.globeHeight))measure();
  if(visual.dataset.orbitLayout!=='surface')visual.dataset.orbitLayout='surface';
  if(layer.dataset.orbitLayout!=='surface')layer.dataset.orbitLayout='surface';
  const byId=new Map(projected.map(p=>[p.id,p]));
  // Decide visibility for the whole frame before collision placement. CSS seed
  // boxes and rear-facing roles must not divert the first visible card.
  for(const [id,role] of roles){role.wasShown=role.depthShown===true;role.depthShown=geographicCardVisible(byId.get(id),role.wasShown);}
  for(const [id,role] of roles)position(role,byId.get(id));
  syncMotion();
 }
 function setFallback(projected){
  if(destroyed)return;
  fallback=true;
  // Without GPU, keep all four illustrative roles visible in reserved peripheral slots.
  visual.dataset.orbitLayout='fallback';layer.dataset.orbitLayout='fallback';
  for(const role of roles.values()){
   role.pin.style.visibility='hidden';role.leader.style.visibility='hidden';
   role.card.style.visibility='visible';role.card.style.opacity='1';
   role.card.style.removeProperty('transform');
   role.visible=true;role.alpha=1;role.card.dataset.surfaceVisible='fallback';
  }
  syncMotion();
 }
 const onResize=()=>{
  geometryDirty=true;
  if(lastFrame&&!fallback)updateProjection(lastFrame);
 };
 const resize=typeof ResizeObserver==='function'?new ResizeObserver(onResize):null;
 resize?.observe(visual);resize?.observe(globe);
 for(const role of roles.values())resize?.observe(role.card);
 window.addEventListener('resize',onResize,{signal:abort.signal});
 media.addEventListener?.('change',syncMotion,{signal:abort.signal});
 doc.addEventListener('visibilitychange',syncMotion,{signal:abort.signal});
 return{
  updateProjection,setFallback,
  setMotion(value){requested=Boolean(value);lastProjectionTime=0;syncMotion();},
  destroy(){
   if(destroyed)return;
   destroyed=true;abort.abort();resize?.disconnect();
   for(const role of roles.values()){
    role.pin.remove();role.leader.remove();
    for(const key of ['transform','visibility','opacity'])role.card.style.removeProperty(key);
    for(const key of ['surfaceVisible','pinX','pinY','depth','cardX','cardY','placement'])delete role.card.dataset[key];
   }
   for(const key of ['orbitMotion','orbitAnchor','orbitLayout'])delete visual.dataset[key];
   delete layer.dataset.orbitLayout;
  },
 };
}
