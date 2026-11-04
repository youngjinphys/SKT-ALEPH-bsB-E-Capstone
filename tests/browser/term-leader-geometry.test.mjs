import assert from 'node:assert/strict';
import test from 'node:test';
import {LEADER_TEXT_GAP,LEADER_MARKER_RADIUS,leaderSegmentIntersectsRect,relativeLeaderRect,routeTermLeader} from '../../apps/web/src/components/term-leader-geometry.ts';

const rect=(left,top,right,bottom)=>({left,top,right,bottom});
const expand=(r,n)=>rect(r.left-n,r.top-n,r.right+n,r.bottom+n);
function safe(input,expectedSide){
 const line=routeTermLeader(input);
 assert.ok(line,'Expected a clear leader route');
 if(expectedSide)assert.equal(line.side,expectedSide);
 for(const point of line.points){
  assert.ok(point.x>=0&&point.x<=input.width&&point.y>=0&&point.y<=input.height,'Route stays in the scene');
 }
 for(const obstacle of [...input.text,...input.targets,...(input.controls??[])]){
  const exclusion=expand(obstacle,LEADER_TEXT_GAP);
  for(let i=1;i<line.points.length;i++)assert.equal(leaderSegmentIntersectsRect(line.points[i-1],line.points[i],exclusion),false,'Whole text/control exclusion is respected');
  const marker=expand(obstacle,LEADER_TEXT_GAP+LEADER_MARKER_RADIUS-.01);
  assert.ok(!(line.x>marker.left&&line.x<marker.right&&line.y>marker.top&&line.y<marker.bottom),'Marker clears complete text');
 }
 for(let i=1;i<line.points.length;i++)assert.equal(leaderSegmentIntersectsRect(line.points[i-1],line.points[i],input.note),false,'Leader cannot pass through its note');
 assert.deepEqual(routeTermLeader(input),line,'Routing is deterministic');
 return line;
}
const common={width:500,height:800,anchor:rect(16,193,484,760)};

test('dnsmasq in the middle of a caption exits above, not through its suffix',()=>{
 safe({...common,note:rect(30,58,460,169),targets:[rect(294,226,343,240)],text:[rect(234,226,294,240),rect(294,226,343,240),rect(343,226,440,240)]},'top');
});

test('CNAME routes around the preceding ALLOW label and intervening headings',()=>{
 const target=rect(336,414,391,429);
 safe({...common,note:rect(54,41,434,134),anchor:rect(16,158,484,760),targets:[target],text:[target,rect(307,393,388,408),rect(112,284,300,303),rect(35,337,360,354)],controls:[rect(30,273,407,313)]});
});

test('SNI can exit left through the reserved table gutter',()=>{
 safe({...common,note:rect(26,620,440,750),anchor:rect(16,20,484,580),targets:[rect(34,210,64,229)],text:[rect(34,210,64,229),rect(34,234,145,255),rect(180,200,450,265),rect(34,285,450,550)]},'left');
});

test('TTL exits below its last line and FQDN above its first line',()=>{
 safe({...common,note:rect(30,620,430,750),targets:[rect(350,555,380,569)],text:[rect(35,555,380,569)]},'bottom');
 safe({...common,note:rect(60,10,440,125),targets:[rect(200,180,250,194)],text:[rect(45,180,250,194)]},'top');
});

test('wrapped targets route from a real line fragment, never the bounding-box void',()=>{
 const targets=[rect(350,260,460,278),rect(40,282,110,300)];
 const line=safe({...common,note:rect(28,50,470,160),targets,text:[rect(40,260,460,278),rect(40,282,440,300)]});
 assert.ok(targets.some(t=>line.x===(t.left+t.right)/2||line.y===(t.top+t.bottom)/2));
});

test('scroll offsets and fractional rendered zoom share exactly one coordinate system',()=>{
 const scene={left:137.25,top:-421.5};
 const absolute=rect(437.75,-201.25,493.25,-183.75);
 assert.deepEqual(relativeLeaderRect(absolute,scene),rect(300.5,220.25,356,237.75));
 for(const scale of [.65,1,1.25,2]){
  const scaled=r=>Object.fromEntries(Object.entries(r).map(([k,v])=>[k,v*scale]));
  const target=scaled(rect(294,226,343,240));
  safe({width:500*scale,height:800*scale,anchor:scaled(common.anchor),note:scaled(rect(30,58,460,169)),targets:[target],text:[scaled(rect(234,226,440,240))]},'top');
 }
});

test('crowded or hidden layouts omit decoration rather than draw over text',()=>{
 assert.equal(routeTermLeader({...common,note:rect(30,50,460,170),targets:[rect(200,300,250,320)],text:[rect(180,280,270,340)]}),null);
 assert.equal(routeTermLeader({...common,note:rect(30,50,460,170),targets:[],text:[]}),null);
 assert.equal(routeTermLeader({...common,width:0,note:rect(30,50,460,170),targets:[rect(200,300,250,320)],text:[]}),null);
});

test('random responsive arrangements never trade text collisions for a shorter path',()=>{
 let seed=4221;
 const rand=()=>((seed=Math.imul(seed,1664525)+1013904223>>>0)/2**32);
 for(let sample=0;sample<120;sample++){
  const width=320+rand()*1200,height=500+rand()*600;
  const x=40+rand()*(width-160),y=200+rand()*(height-300);
  const target=rect(x,y,x+60,y+18),text=[target];
  for(let i=0;i<16;i++){const left=24+rand()*(width-130),top=150+rand()*(height-180);text.push(rect(left,top,Math.min(width-20,left+20+rand()*180),top+14+rand()*15));}
  const input={width,height,targets:[target],text,note:rect(26,10,width-26,120),anchor:rect(16,140,width-16,height-16)};
  if(routeTermLeader(input))safe(input);
 }
});

test('dense 100/200-fragment layouts stay clear while neighboring nodes move',()=>{
 for(const count of [100,200]){
  const text=Array.from({length:count},(_,i)=>rect(30+(i%5)*120,250+Math.floor(i/5)*24,115+(i%5)*120,266+Math.floor(i/5)*24));
  for(let frame=0;frame<12;frame++){
   const target=rect(630,600,680,616);
   const moving=text.map((r,i)=>i%5===4?{...r,left:r.left+frame,right:r.right+frame}:r);
   safe({width:720,height:1400,targets:[target],text:[target,...moving],note:rect(160,20,680,130),anchor:rect(16,170,704,1350)});
  }
 }
});
