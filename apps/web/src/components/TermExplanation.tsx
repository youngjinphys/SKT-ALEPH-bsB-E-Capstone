"use client";
import {createContext,useContext,useId,useLayoutEffect,useRef,useState,type ReactNode} from "react";
import terms from "../../capstone/data/term-explanations.json";
import {LEADER_MARKER_RADIUS,relativeLeaderRect,routeTermLeader,nearestTermNoteOffset,type LeaderRect,type TermLeader} from "./term-leader-geometry";
import "./term-explanation.css";

export type ExplainedTerm=keyof typeof terms;
type LeaderLayout=TermLeader&{width:number;height:number};
const TermContext=createContext<{term?:ExplainedTerm;id:string}|null>(null);

/** Reserve real layout space next to the word, never float over the diagram. */
export function TermDefinition({term}:{term:ExplainedTerm}){
 const context=useContext(TermContext);
 if(context?.term!==term)return null;
 const entry=terms[term];
 return <div className="term-dock" data-term-definition={term}>
  <aside className="term-note" role="note" id={context.id} aria-label={entry.title}>
   <strong>{entry.title}</strong><p>{entry.body}</p>
  </aside>
 </div>;
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
  if(css.visibility==='hidden'||css.visibility==='collapse'||parent.closest('[hidden],svg,script,style'))continue;
  // Opacity-only text handoffs keep both variants as exclusions. A label becoming
  // visible must not suddenly be under a leader chosen for the previous variant.
  range.selectNodeContents(node);
  for(const rect of range.getClientRects())if(rect.width>0&&rect.height>0)rects.push(relativeLeaderRect(rect,scene));
 }
 return rects;
}

/** Shared, collision-aware callouts for every slide using an explained term. */
export function TermExplanation({term,children,paused=false}:{term?:ExplainedTerm;children:ReactNode;paused?:boolean}){
 const id=useId(),scene=useRef<HTMLDivElement>(null);
 const [line,setLine]=useState<LeaderLayout|null>(null);
 useLayoutEffect(()=>{
  const root=scene.current;
  if(!root||!term){setLine(null);return;}
  const note=root.querySelector<HTMLElement>('.term-note');
  const dock=root.querySelector<HTMLElement>('.term-dock');
  const anchor=root.querySelector<HTMLElement>('.term-anchor');
  if(!note||!dock||!anchor)return;
  let frame=0,disposed=false,target:HTMLElement|null=null;
  const descriptions=new Map<HTMLElement,string|null>();
  const describe=(next:HTMLElement)=>{
   if(descriptions.has(next))return;
   const previous=next.getAttribute('aria-describedby');
   descriptions.set(next,previous);
   next.setAttribute('aria-describedby',[...new Set([...(previous?.split(/\s+/).filter(Boolean)??[]),id])].join(' '));
  };
  const measure=()=>{
   if(disposed)return;
   const next=anchor.querySelector<HTMLElement>(`[data-term-target="${term}"]`);
   if(next!==target){if(target){observer.unobserve(target);const previous=descriptions.get(target);if(previous==null)target.removeAttribute('aria-describedby');else target.setAttribute('aria-describedby',previous);descriptions.delete(target);}target=next;if(target){describe(target);observer.observe(target);}}
   const r=root.getBoundingClientRect();
   if(!target||r.width<=0||r.height<=0){setLine(null);return;}
   // The authored slot is directly after the marked caption/link. Center within
   // that reserved row as closely as its edges permit; never place over content.
   const dockRect=dock.getBoundingClientRect(),noteRect=note.getBoundingClientRect();
   const scale=dock.offsetWidth>0?dockRect.width/dock.offsetWidth:1;
   const offset=nearestTermNoteOffset(target.getBoundingClientRect(),dockRect,noteRect.width)/scale;
   const offsetValue=`${Math.round(offset*100)/100}px`;
   if(note.style.getPropertyValue('--term-note-offset')!==offsetValue)note.style.setProperty('--term-note-offset',offsetValue);
   // Use rendered rectangles for target, obstacles AND note. Mixing offsetLeft
   // with getBoundingClientRect caused the old line to drift at zoom/scale.
   const route=routeTermLeader({targets:textRects(target,r),text:textRects(anchor,r),
    controls:Array.from(anchor.querySelectorAll<HTMLElement>('button,input,select,textarea,[role="button"],[role="tab"]')).filter(el=>el.getClientRects().length>0).map(el=>relativeLeaderRect(el.getBoundingClientRect(),r)),
    note:relativeLeaderRect(note.getBoundingClientRect(),r),anchor:relativeLeaderRect(anchor.getBoundingClientRect(),r),width:r.width,height:r.height});
   const nextLine=route?{...route,width:r.width,height:r.height}:null;
   setLine(previous=>previous?.d===nextLine?.d&&previous?.width===nextLine?.width&&previous?.height===nextLine?.height?previous:nextLine);
   // Follow finite layout/transform transitions, not infinite decorative packets.
   // ResizeObserver alone cannot see a transform or repositioned sibling.
   const moving=root.getAnimations({subtree:true}).some(animation=>animation.playState==='running'&&animation.effect?.getTiming().iterations!==Infinity&&animation.effect instanceof KeyframeEffect&&animation.effect.getKeyframes().some(keyframe=>Object.keys(keyframe).some(key=>/^(transform|translate|scale|width|height|top|left|right|bottom|margin|padding)/.test(key))));
   if(moving)frame=requestAnimationFrame(measure);
  };
  const schedule=()=>{if(disposed)return;cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);};
  const observer=new ResizeObserver(schedule);
  [root,note,dock,anchor].forEach(el=>observer.observe(el));
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
   for(const [element,previous] of descriptions){if(previous===null)element.removeAttribute('aria-describedby');else element.setAttribute('aria-describedby',previous);}
  };
 },[term,id]);
 return <TermContext.Provider value={{term,id}}><div ref={scene} className="term-scene" data-term={term} data-motion={paused?'paused':'enter'}>
  <div className="term-anchor">{children}</div>
  {term&&line&&<svg className="term-leader" viewBox={`0 0 ${line.width} ${line.height}`} preserveAspectRatio="none" data-term-side={line.side} aria-hidden="true"><path d={line.d}/><circle cx={line.x} cy={line.y} r={LEADER_MARKER_RADIUS}/></svg>}
 </div></TermContext.Provider>;
}
