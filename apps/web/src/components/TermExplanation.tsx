"use client";
import {createContext,useContext,useId,useLayoutEffect,useRef,useState,type ReactNode} from "react";
import {createPortal} from "react-dom";
import terms from "../../capstone/data/term-explanations.json";
import {LEADER_MARKER_RADIUS,relativeLeaderRect,routeTermLeader,placeTermNote,type LeaderRect,type TermLeader} from "./term-leader-geometry";
import "./term-explanation.css";

export type ExplainedTerm=keyof typeof terms;
type LeaderLayout=TermLeader&{width:number;height:number};
const TermContext=createContext<{term?:ExplainedTerm;id:string;open:()=>void}|null>(null);

/** The highlighted word keeps the same inline footprint and exposes the complete
 * definition on demand, including when no safe automatic overlay fits. */
export function TermTarget({term,children,className}:{term:ExplainedTerm;children:ReactNode;className?:string}){
 const context=useContext(TermContext);
 if(context?.term!==term)return <span className={className}>{children}</span>;
 return <button type="button" className={["term-target",className].filter(Boolean).join(" ")} data-term-target={term}
  aria-label={`${term} 용어 설명`} aria-describedby={`${context.id}-description`} aria-haspopup="dialog"
  aria-controls={`${context.id}-dialog`} onClick={context.open}>{children}</button>;
}

/** Measure complete text fragments, including siblings after the selected word. */
function textRects(element:HTMLElement,scene:DOMRect):LeaderRect[]{
 const walker=document.createTreeWalker(element,NodeFilter.SHOW_TEXT);
 const rects:LeaderRect[]=[];
 const range=document.createRange();
 let node:Node|null;
 while((node=walker.nextNode())){
  if(!node.textContent?.trim())continue;
  const parent=node.parentElement;
  if(!parent)continue;
  const css=getComputedStyle(parent);
  if(css.visibility==='hidden'||css.visibility==='collapse'||parent.closest('[hidden],.sr-only,.term-note,svg,script,style'))continue;
  // Opacity-only text handoffs keep both variants as exclusions. A label becoming
  // visible must not suddenly be under a leader chosen for the previous variant.
  range.selectNodeContents(node);
  for(const rect of range.getClientRects())if(rect.width>0&&rect.height>0)rects.push(relativeLeaderRect(rect,scene));
 }
 return rects;
}

/** Shared, collision-aware callouts for every slide using an explained term. */
export function TermExplanation({term,children,paused=false}:{term?:ExplainedTerm;children:ReactNode;paused?:boolean}){
 const id=useId(),scene=useRef<HTMLDivElement>(null),dialog=useRef<HTMLDialogElement>(null);
 const [portal,setPortal]=useState<HTMLElement|null>(null);
 useLayoutEffect(()=>setPortal(document.body),[]);
 const [line,setLine]=useState<LeaderLayout|null>(null);
 useLayoutEffect(()=>{
  const root=scene.current;
  if(!root||!term){setLine(null);return;}
  const note=root.querySelector<HTMLElement>('.term-note');
  const anchor=root.querySelector<HTMLElement>('.term-anchor');
  if(!note||!anchor)return;
  const surface=root.closest<HTMLElement>('.deck-slide')??root;
  let frame=0,disposed=false,target:HTMLElement|null=null;
  const measure=()=>{
   if(disposed)return;
   const next=anchor.querySelector<HTMLElement>(`[data-term-target="${term}"]`);
   if(next!==target){if(target)observer.unobserve(target);target=next;if(target)observer.observe(target);}
   const r=root.getBoundingClientRect();
   if(!target||r.width<=0||r.height<=0){note.style.visibility="hidden";root.dataset.termLayout="on-demand";setLine(null);return;}
   const scale=r.width/root.offsetWidth || 1;
   // Intersect actual clipping ancestors and viewport; an off-screen gap is not
   // available background. Never make a new row or stretch a connector to fit.
   const viewport=window.visualViewport;
   const viewLeft=viewport?.offsetLeft??0,viewTop=viewport?.offsetTop??0;
   const surfaceBox=relativeLeaderRect(surface.getBoundingClientRect(),r);
   const bounds={left:Math.max(surfaceBox.left,viewLeft-r.left),top:Math.max(surfaceBox.top,viewTop-r.top),right:Math.min(surfaceBox.right,viewLeft+(viewport?.width??innerWidth)-r.left),bottom:Math.min(surfaceBox.bottom,viewTop+(viewport?.height??innerHeight)-r.top)};
   for(let parent=root.parentElement;parent;parent=parent.parentElement){
    const css=getComputedStyle(parent),box=relativeLeaderRect(parent.getBoundingClientRect(),r);
    if(/hidden|clip|auto|scroll/.test(css.overflowX)){bounds.left=Math.max(bounds.left,box.left);bounds.right=Math.min(bounds.right,box.right);}
    if(/hidden|clip|auto|scroll/.test(css.overflowY)){bounds.top=Math.max(bounds.top,box.top);bounds.bottom=Math.min(bounds.bottom,box.bottom);}
   }
   bounds.left+=4*scale;bounds.right-=4*scale;bounds.top+=4*scale;bounds.bottom-=4*scale;
   const text=textRects(surface,r);
   const controls=Array.from(surface.querySelectorAll<HTMLElement>('button,a,input,select,textarea,[role="button"],[role="tab"],.restored-node,.restored-lane,.bidirectional-lane,.chain-step,.cname-arrow,.adoption-lane,.policy-timeline-result,.server-dns-observation,.slide-point,svg:not(.term-leader)')).filter(el=>el.getClientRects().length>0).map(el=>relativeLeaderRect(el.getBoundingClientRect(),r));
   let placement:ReturnType<typeof placeTermNote>=null,chosenWidth=360;
   for(const width of [360,320,280]){
    note.style.width=`${width}px`;
    const box=note.getBoundingClientRect();
    const candidate=placeTermNote({target:relativeLeaderRect(target.getBoundingClientRect(),r),bounds,width:box.width,height:box.height,obstacles:[...text,...controls],gap:8*scale,maxDistance:180*scale});
    if(candidate&&(!placement||candidate.score<placement.score)){placement=candidate;chosenWidth=width;}
   }
   note.style.width=`${chosenWidth}px`;
   note.style.visibility=placement?'visible':'hidden';
   root.dataset.termLayout=placement?'overlay':'on-demand';
   if(placement){note.style.left=`${placement.rect.left/scale}px`;note.style.top=`${placement.rect.top/scale}px`;}
   // The same rendered coordinate system is used for note, line and obstacles.
   const route=placement?routeTermLeader({targets:textRects(target,r),text,controls,
    note:placement.rect,anchor:relativeLeaderRect(anchor.getBoundingClientRect(),r),width:r.width,height:r.height,bounds}):null;
   const nextLine=route?{...route,width:r.width,height:r.height}:null;
   setLine(previous=>previous?.d===nextLine?.d&&previous?.width===nextLine?.width&&previous?.height===nextLine?.height?previous:nextLine);
   // Follow finite layout/transform transitions, not infinite decorative packets.
   // ResizeObserver alone cannot see a transform or repositioned sibling.
   const moving=root.getAnimations({subtree:true}).some(animation=>animation.playState==='running'&&animation.effect?.getTiming().iterations!==Infinity&&animation.effect instanceof KeyframeEffect&&animation.effect.getKeyframes().some(keyframe=>Object.keys(keyframe).some(key=>/^(transform|translate|scale|width|height|top|left|right|bottom|margin|padding)/.test(key))));
   if(moving)frame=requestAnimationFrame(measure);
  };
  const schedule=()=>{if(disposed)return;cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);};
  const observer=new ResizeObserver(schedule);
  [root,note,anchor,surface].forEach(el=>observer.observe(el));
  const mutations=new MutationObserver(schedule);
  mutations.observe(anchor,{subtree:true,childList:true,characterData:true,attributes:true});
  window.addEventListener('resize',schedule);
  window.addEventListener('scroll',schedule,true);
  window.visualViewport?.addEventListener('resize',schedule);
  window.visualViewport?.addEventListener('scroll',schedule);
  root.addEventListener('transitionrun',schedule);
  root.addEventListener('transitionend',schedule);
  root.addEventListener('transitioncancel',schedule);
  root.addEventListener('animationstart',schedule);
  root.addEventListener('animationend',schedule);
  root.addEventListener('animationcancel',schedule);
  document.fonts.addEventListener('loadingdone',schedule);
  void document.fonts.ready.then(schedule);
  measure();
  return()=>{
   disposed=true;observer.disconnect();mutations.disconnect();cancelAnimationFrame(frame);
   window.removeEventListener('resize',schedule);window.removeEventListener('scroll',schedule,true);
   window.visualViewport?.removeEventListener('resize',schedule);window.visualViewport?.removeEventListener('scroll',schedule);
   root.removeEventListener('transitionrun',schedule);root.removeEventListener('transitionend',schedule);root.removeEventListener('transitioncancel',schedule);
   root.removeEventListener('animationstart',schedule);root.removeEventListener('animationend',schedule);root.removeEventListener('animationcancel',schedule);
   document.fonts.removeEventListener('loadingdone',schedule);
  };
 },[term,id]);
 const entry=term?terms[term]:null;
 return <TermContext.Provider value={{term,id,open:()=>dialog.current?.showModal()}}><div ref={scene} className="term-scene" data-term={term} data-motion={paused?'paused':'enter'}>
  <div className="term-anchor">{children}</div>
  {entry&&<><span className="sr-only" id={`${id}-description`}>{entry.title}. {entry.body}</span>
   <aside className="term-note" aria-hidden="true"><strong>{entry.title}</strong><p>{entry.body}</p></aside></>}
  {term&&line&&<svg className="term-leader" viewBox={`0 0 ${line.width} ${line.height}`} preserveAspectRatio="none" data-term-side={line.side} aria-hidden="true"><path d={line.d}/><circle cx={line.x} cy={line.y} r={LEADER_MARKER_RADIUS}/></svg>}
  {entry&&portal&&createPortal(<dialog ref={dialog} className="term-definition-dialog" id={`${id}-dialog`} aria-labelledby={`${id}-title`}
   onKeyDown={event=>event.stopPropagation()} onClick={event=>{if(event.target===dialog.current)dialog.current.close();}}>
   <h2 id={`${id}-title`}>{entry.title}</h2><p>{entry.body}</p><button type="button" autoFocus onClick={()=>dialog.current?.close()}>닫기</button>
  </dialog>,portal)}
 </div></TermContext.Provider>;
}
