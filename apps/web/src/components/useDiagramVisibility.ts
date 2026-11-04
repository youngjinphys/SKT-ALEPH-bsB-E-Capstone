"use client";
import {useCallback,useEffect,useState} from 'react';

/** Only animate a meaningfully visible diagram; observation does not alter user intent. */
export function useDiagramVisibility(){
 const [element,setElement]=useState<HTMLElement|null>(null);
 const [inView,setInView]=useState(false);
 const ref=useCallback((node:HTMLElement|null)=>{setElement(node)},[]);
 useEffect(()=>{
  setInView(false);
  if(!element)return;
  if(typeof IntersectionObserver==='function'){
   const observer=new IntersectionObserver(entries=>{
    const entry=entries.find(item=>item.target===element);
    if(entry)setInView(entry.isIntersecting&&entry.intersectionRatio>=.2);
   },{threshold:[0,.2]});
   observer.observe(element);return()=>observer.disconnect();
  }
  // Older engines: measure on nested scrolling/resize, never assume offscreen is visible.
  let frame=0;
  const measure=()=>{
   frame=0;const rect=element.getBoundingClientRect();
   let left=Math.max(0,rect.left),right=Math.min(innerWidth,rect.right),top=Math.max(0,rect.top),bottom=Math.min(innerHeight,rect.bottom);
   for(let parent=element.parentElement;parent;parent=parent.parentElement){
    const style=getComputedStyle(parent),box=parent.getBoundingClientRect();
    if(/auto|scroll|hidden|clip/.test(style.overflowX)){left=Math.max(left,box.left);right=Math.min(right,box.right)}
    if(/auto|scroll|hidden|clip/.test(style.overflowY)){top=Math.max(top,box.top);bottom=Math.min(bottom,box.bottom)}
   }
   const area=rect.width*rect.height;
   setInView(area>0&&Math.max(0,right-left)*Math.max(0,bottom-top)/area>=.2);
  };
  const schedule=()=>{if(!frame)frame=requestAnimationFrame(measure)};
  measure();window.addEventListener('scroll',schedule,true);window.addEventListener('resize',schedule);
  return()=>{if(frame)cancelAnimationFrame(frame);window.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',schedule)};
 },[element]);
 return {ref,inView};
}
