/** Rectilinear callout routing in one coordinate system. No term-specific sides. */
export type LeaderPoint = {x:number;y:number};
export type LeaderRect = {left:number;top:number;right:number;bottom:number};
export type LeaderSide = "top"|"bottom"|"left"|"right";
export type TermLeader = {d:string;points:LeaderPoint[];x:number;y:number;side:LeaderSide};

export const LEADER_TEXT_GAP = 4;
export const LEADER_MARKER_RADIUS = 2.5;
const MARKER_OFFSET = LEADER_TEXT_GAP + LEADER_MARKER_RADIUS + 1;
const EXIT_LENGTH = 5;
const EPSILON = .01;
const inflate = (r:LeaderRect,gap:number):LeaderRect => ({left:r.left-gap,top:r.top-gap,right:r.right+gap,bottom:r.bottom+gap});
const clamp = (n:number,low:number,high:number) => Math.max(low,Math.min(high,n));
const inside = (p:LeaderPoint,r:LeaderRect) => p.x>r.left+EPSILON&&p.x<r.right-EPSILON&&p.y>r.top+EPSILON&&p.y<r.bottom-EPSILON;

/** Boundary contact is allowed; obstacles already include stroke/text clearance. */
export function leaderSegmentIntersectsRect(a:LeaderPoint,b:LeaderPoint,r:LeaderRect):boolean {
 if(Math.abs(a.y-b.y)<EPSILON)return a.y>r.top+EPSILON&&a.y<r.bottom-EPSILON&&Math.max(a.x,b.x)>r.left+EPSILON&&Math.min(a.x,b.x)<r.right-EPSILON;
 if(Math.abs(a.x-b.x)<EPSILON)return a.x>r.left+EPSILON&&a.x<r.right-EPSILON&&Math.max(a.y,b.y)>r.top+EPSILON&&Math.min(a.y,b.y)<r.bottom-EPSILON;
 // The router only emits orthogonal segments. Never accept a diagonal shortcut.
 return true;
}

function simplify(points:LeaderPoint[]):LeaderPoint[] {
 const result:LeaderPoint[]=[];
 for(const point of points){
  const last=result.at(-1);
  if(last&&Math.abs(last.x-point.x)<EPSILON&&Math.abs(last.y-point.y)<EPSILON)continue;
  const before=result.at(-2);
  if(before&&last&&((before.x===last.x&&last.x===point.x&&(last.y-before.y)*(point.y-last.y)>=0)||(before.y===last.y&&last.y===point.y&&(last.x-before.x)*(point.x-last.x)>=0)))result.pop();
  result.push(point);
 }
 return result;
}

/**
 * Try every edge of every rendered target line, then choose the shortest clear
 * orthogonal route to the note. Search direct, elbow and obstacle-edge/gutter
 * corridors. Text, controls and the note are hard exclusions, not score penalties.
 * A crowded layout may omit the decorative leader; it must never obscure content.
 */
export function routeTermLeader({targets,text,controls=[],note,anchor,width,height,bounds:availableBounds}:{targets:LeaderRect[];text:LeaderRect[];controls?:LeaderRect[];note:LeaderRect;anchor:LeaderRect;width:number;height:number;bounds?:LeaderRect}):TermLeader|null {
 if(width<=0||height<=0||!targets.length)return null;
 const obstacles=[...text,...targets].map(r=>inflate(r,LEADER_TEXT_GAP)).concat(controls.map(r=>inflate(r,LEADER_TEXT_GAP)),[note]);
 const markerObstacles=[...text,...targets].map(r=>inflate(r,LEADER_TEXT_GAP+LEADER_MARKER_RADIUS)).concat(controls.map(r=>inflate(r,LEADER_MARKER_RADIUS)),[inflate(note,LEADER_MARKER_RADIUS)]);
 const available=availableBounds??{left:0,top:0,right:width,bottom:height};
 const bounds={left:available.left+LEADER_MARKER_RADIUS,top:available.top+LEADER_MARKER_RADIUS,right:available.right-LEADER_MARKER_RADIUS,bottom:available.bottom-LEADER_MARKER_RADIUS};
 const inBounds=(p:LeaderPoint)=>p.x>=bounds.left&&p.x<=bounds.right&&p.y>=bounds.top&&p.y<=bounds.bottom;
 const clear=(points:LeaderPoint[])=>points.every(inBounds)&&points.slice(1).every((point,index)=>obstacles.every(r=>!leaderSegmentIntersectsRect(points[index],point,r)));
 // Exterior gutters are reserved by CSS. Obstacle edges supply interior lanes
 // when, for example, the selected word sits in the middle of a caption.
 const xs=[bounds.left+3,bounds.right-3,anchor.left-8,anchor.right+8,...obstacles.flatMap(r=>[r.left,r.right])].filter(x=>x>=bounds.left&&x<=bounds.right);
 const ys=[bounds.top+3,bounds.bottom-3,anchor.top-8,anchor.bottom+8,...obstacles.flatMap(r=>[r.top,r.bottom])].filter(y=>y>=bounds.top&&y<=bounds.bottom);
 const xLanes=[...new Set(xs)],yLanes=[...new Set(ys)];
 let best:TermLeader|null=null,bestScore=Infinity;
 for(const target of targets){
  const cx=(target.left+target.right)/2,cy=(target.top+target.bottom)/2;
  const starts:{side:LeaderSide;point:LeaderPoint;normal:LeaderPoint}[]=[
   {side:"top",point:{x:cx,y:target.top-MARKER_OFFSET},normal:{x:0,y:-1}},
   {side:"bottom",point:{x:cx,y:target.bottom+MARKER_OFFSET},normal:{x:0,y:1}},
   {side:"left",point:{x:target.left-MARKER_OFFSET,y:cy},normal:{x:-1,y:0}},
   {side:"right",point:{x:target.right+MARKER_OFFSET,y:cy},normal:{x:1,y:0}},
  ];
  for(const {side,point:start,normal} of starts){
   if(!inBounds(start)||markerObstacles.some(r=>inside(start,r)))continue;
   const exit={x:start.x+normal.x*EXIT_LENGTH,y:start.y+normal.y*EXIT_LENGTH};
   if(!clear([start,exit]))continue;
   const insetX=Math.min(14,(note.right-note.left)/2),insetY=Math.min(14,(note.bottom-note.top)/2);
   const ports:LeaderPoint[]=[];
   for(const x of new Set([clamp(start.x,note.left+insetX,note.right-insetX),note.left+insetX,note.right-insetX]))ports.push({x,y:note.top},{x,y:note.bottom});
   for(const y of new Set([clamp(start.y,note.top+insetY,note.bottom-insetY),note.top+insetY,note.bottom-insetY]))ports.push({x:note.left,y},{x:note.right,y});
   const consider=(raw:LeaderPoint[])=>{
    const points=simplify(raw);
    const length=points.slice(1).reduce((sum,p,i)=>sum+Math.abs(p.x-points[i].x)+Math.abs(p.y-points[i].y),0);
    const score=length+Math.max(0,points.length-2)*12;
    if(score>=bestScore||!clear(points))return;
    bestScore=score;
    best={d:points.map((p,i)=>`${i?'L':'M'} ${p.x} ${p.y}`).join(' '),points,x:start.x,y:start.y,side};
   };
   ports.sort((a,b)=>(Math.abs(exit.x-a.x)+Math.abs(exit.y-a.y))-(Math.abs(exit.x-b.x)+Math.abs(exit.y-b.y)));
   for(const end of ports){
    const minimumLength=EXIT_LENGTH+Math.abs(exit.x-end.x)+Math.abs(exit.y-end.y);
    // The shortest possible Manhattan distance is a lower bound for every
    // detour. Once a direct route wins, skip the entire remaining lane search.
    if(minimumLength>=bestScore)continue;
    consider([start,exit,{x:end.x,y:exit.y},end]);
    consider([start,exit,{x:exit.x,y:end.y},end]);
    if(minimumLength>=bestScore)continue;
    for(const x of xLanes){
     if(EXIT_LENGTH+Math.abs(exit.x-x)+Math.abs(x-end.x)+Math.abs(exit.y-end.y)>=bestScore)continue;
     consider([start,exit,{x,y:exit.y},{x,y:end.y},end]);
    }
    for(const y of yLanes){
     if(EXIT_LENGTH+Math.abs(exit.y-y)+Math.abs(y-end.y)+Math.abs(exit.x-end.x)>=bestScore)continue;
     consider([start,exit,{x:exit.x,y},{x:end.x,y},end]);
    }
   }
  }
 }
 return best;
}

/** All inputs use rendered viewport geometry, never offset/layout dimensions. */
export function relativeLeaderRect(rect:LeaderRect,scene:Pick<LeaderRect,"left"|"top">):LeaderRect {
 return {left:rect.left-scene.left,top:rect.top-scene.top,right:rect.right-scene.left,bottom:rect.bottom-scene.top};
}

/** A real overlay may use only existing empty background. Text/card collisions
 * are hard constraints, never a distance penalty. All units are rendered pixels. */
export function placeTermNote({target,bounds,width,height,obstacles,gap=8,maxDistance=180}:{target:LeaderRect;bounds:LeaderRect;width:number;height:number;obstacles:LeaderRect[];gap?:number;maxDistance?:number}):{rect:LeaderRect;score:number}|null {
 if(width<=0||height<=0||width>bounds.right-bounds.left||height>bounds.bottom-bounds.top)return null;
 const blocked=obstacles.map(rect=>inflate(rect,gap));
 const cx=(target.left+target.right)/2,cy=(target.top+target.bottom)/2;
 const xs=[cx-width/2,target.right+gap,target.left-width-gap,bounds.left,bounds.right-width,...blocked.flatMap(r=>[r.right,r.left-width])];
 const ys=[cy-height/2,target.bottom+gap,target.top-height-gap,bounds.top,bounds.bottom-height,...blocked.flatMap(r=>[r.bottom,r.top-height])];
 const unique=(values:number[],low:number,high:number,center:number,size:number)=>[...new Set(values.map(value=>clamp(value,low,high)))].sort((a,b)=>Math.abs(a+size/2-center)-Math.abs(b+size/2-center)).slice(0,40);
 let best:{rect:LeaderRect;score:number}|null=null;
 for(const left of unique(xs,bounds.left,bounds.right-width,cx,width))for(const top of unique(ys,bounds.top,bounds.bottom-height,cy,height)){
  const rect={left,top,right:left+width,bottom:top+height};
  const dx=Math.max(0,target.left-rect.right,rect.left-target.right),dy=Math.max(0,target.top-rect.bottom,rect.top-target.bottom);
  const distance=Math.hypot(dx,dy);
  if(distance>maxDistance||blocked.some(r=>Math.min(rect.right,r.right)>Math.max(rect.left,r.left)+EPSILON&&Math.min(rect.bottom,r.bottom)>Math.max(rect.top,r.top)+EPSILON))continue;
  const score=distance+Math.hypot(left+width/2-cx,top+height/2-cy)*.1;
  if(!best||score<best.score)best={rect,score};
 }
 return best;
}
