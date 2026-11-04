"use client";
import {useEffect,useState} from 'react';
import {classifyMobilePresentation} from '@/lib/mobile-presentation';

/** Keep browser zoom/short landscape in the complete, naturally scrolling view. */
export function useMobilePresentation(slideId:string,hasSeparatePoints:boolean,shortOnlyPoints=false){
 const [viewport,setViewport]=useState({mobile:false,fits:false,shortBudget:false,tightBudget:false});
 const [full,setFull]=useState(false);
 const [selection,setSelection]=useState<{id:string;pane:'points'|'visual'}>({id:slideId,pane:'visual'});
 useEffect(()=>{
  const media=window.matchMedia('(max-width:780px)');
  let frame:number|null=null;
  const sync=()=>{
   frame=null;
   const visual=window.visualViewport;
   const height=visual?.height??window.innerHeight;
   let paddingTop=0,paddingBottom=0;
   // Effects run after the deck DOM exists. Read resolved env(safe-area-*)
   // padding, while retaining the full viewport height for the root CSS size.
   try{
    const root=document.querySelector('.deck-root');
    if(root){const style=getComputedStyle(root);paddingTop=parseFloat(style.paddingTop);paddingBottom=parseFloat(style.paddingBottom);}
   }catch{/* Missing/unsupported computed styles fall back to zero padding. */}
   const {mobile,fits,shortBudget,tightBudget,unzoomed}=classifyMobilePresentation({height,paddingTop,paddingBottom,scale:visual?.scale??1,narrow:media.matches});
   if(unzoomed)document.documentElement.style.setProperty('--presentation-viewport-height',`${Math.floor(Math.min(height,window.innerHeight))}px`);
   else document.documentElement.style.removeProperty('--presentation-viewport-height');
   const next={mobile,fits,shortBudget,tightBudget};
   setViewport(previous=>previous.mobile===next.mobile&&previous.fits===next.fits&&previous.shortBudget===next.shortBudget&&previous.tightBudget===next.tightBudget?previous:next);
  };
  const schedule=()=>{if(frame===null)frame=window.requestAnimationFrame(sync);};
  sync();media.addEventListener('change',schedule);window.addEventListener('resize',schedule);window.addEventListener('orientationchange',schedule);
  window.visualViewport?.addEventListener('resize',schedule);window.visualViewport?.addEventListener('scroll',schedule);
  return()=>{
   if(frame!==null)window.cancelAnimationFrame(frame);
   media.removeEventListener('change',schedule);window.removeEventListener('resize',schedule);window.removeEventListener('orientationchange',schedule);
   window.visualViewport?.removeEventListener('resize',schedule);window.visualViewport?.removeEventListener('scroll',schedule);
   document.documentElement.style.removeProperty('--presentation-viewport-height');
  };
 },[]);
 useEffect(()=>{setSelection(previous=>previous.id===slideId?previous:{id:slideId,pane:'visual'});},[slideId]);
 const layout=!viewport.mobile?'desktop':full||!viewport.fits?'full':hasSeparatePoints||(shortOnlyPoints&&viewport.shortBudget)?'panes':'single';
 const pane=selection.id===slideId?selection.pane:'visual';
 return {layout,pane,shortBudget:viewport.shortBudget,tightBudget:viewport.tightBudget,controls:viewport.mobile&&viewport.fits,full,toggleFull:()=>setFull(value=>!value),select:(pane:'points'|'visual')=>setSelection({id:slideId,pane}),pointsHidden:layout==='panes'&&pane!=='points',visualHidden:layout==='panes'&&pane!=='visual'};
}
