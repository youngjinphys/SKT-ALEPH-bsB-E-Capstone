"use client";
import Link from "next/link";
import "./reference-links.css";
import {useCallback,useEffect,useLayoutEffect,useRef,useState} from "react";
import {ClapControl} from "@/components/ClapControl";
import {SlideVisual} from "@/components/SlideVisual";
import {useMobilePresentation} from "@/components/useMobilePresentation";
import {clampSlideIndex,slideIndexFromHash} from "@/lib/deck";
import type {DeckSlide,SourceRegistry} from "@/lib/deck";

const statusLabels:Record<string,string>={
 implemented:"구현 범위",research:"연구 소개",hypothesis:"검증 가설",proposal:"확장 제안",
 "evidence-snapshot":"실험 기록","scope-limit":"적용 경계","known-limit":"확인된 한계",
 "evaluation-plan":"향후 평가","planned-not-measured":"실측 계획 · 미실행","experimental":"실측 기록","conclusion":"결론",reference:"참고 자료",
};
const INLINE=new Set<string>(); // Source tables remain available in the presenter notes.
function EvidenceStrip({slide}:{slide:DeckSlide}){
 const evidence=slide.reading;
 if(!evidence||!INLINE.has(slide.id))return null;
 return <section className="slide-evidence-strip" aria-label={evidence.title}>
  <header><h2>{evidence.title}</h2><a href={evidence.source} target="_blank" rel="noopener noreferrer">근거 자료 ↗</a></header>
  <div className="slide-evidence-grid">{evidence.rows.slice(0,3).map((row,i)=><article key={i}><strong>{row[0]}</strong><p>{row[1]}</p><small>{row[2]}</small></article>)}</div>
 </section>;
}
function TitleLines({value}:{value:string}){
 return <>{value.split("\n").map((segment,i)=><span className="title-line" key={i}>{segment}</span>)}</>;
}

function SlideItem({
 slide,
 index,
 totalSlides,
 mainSlideCount,
 sources,
 motionPaused,
 mobile,
 isLeaving=false,
}:{
 slide:DeckSlide;
 index:number;
 totalSlides:number;
 mainSlideCount:number;
 sources:SourceRegistry;
 motionPaused:boolean;
 mobile:ReturnType<typeof useMobilePresentation>;
 isLeaving?:boolean;
}){
 const tableLayout=(["evidence","metrics"].includes(slide.kind)&&Boolean(slide.reading))||slide.kind==="sources";
 const mobileDiagram=mobile.shortBudget&&mobile.layout==='panes'&&mobile.pane==='visual';
 const displayedTitle=mobileDiagram?(slide.presentation?.compactTitle||slide.title):slide.title;
 const mobileId=`mobile-${slide.id}`;
 // Presentation view choices use native buttons, so arrows keep navigating slides.
 const choosePane=(pane:'points'|'visual')=>{mobile.select(pane);document.getElementById('slide-area')?.scrollTo({top:0,behavior:'instant'});};

 return <section
  className={`deck-slide slide-${slide.id}${tableLayout?" slide-table-layout":""}`}
  data-mobile-layout={mobile.layout}
  data-mobile-pane={mobile.pane}
  data-mobile-budget={mobile.shortBudget?'short':'regular'}
  data-mobile-tight={mobile.tightBudget}
  aria-roledescription="슬라이드"
  aria-label={`${index+1}번째 슬라이드 · ${slide.title.replaceAll("\n"," ")}`}
  tabIndex={isLeaving?-1:undefined}
  inert={isLeaving?true:undefined}
 >
  <div className="slide-overline"><span>{String(index+1).padStart(2,"0")} / {String(totalSlides).padStart(2,"0")}</span><span>{slide.chapter} · {index<mainSlideCount?"본편":"부록"}</span></div>
  <div className="slide-columns">
    <div className="slide-narrative" style={{touchAction:"pan-y pinch-zoom"}}>
     <div className="slide-heading">
      <h1><TitleLines value={displayedTitle}/></h1>
      {!mobileDiagram&&slide.subtitle&&<p>{slide.subtitle}</p>}
      {slide.credits&&<p className="slide-credits" aria-label="조원">{slide.credits.split(',').map((entry,i)=><span key={i}>{i>0&&', '}<span className={entry.trim().startsWith('*')?'credits-leader':undefined}>{entry.trim().startsWith('*')&&<svg className="credits-star" role="img" aria-label="별표" viewBox="0 0 24 24"><path d="m12 2.8 2.84 5.75 6.35.92-4.6 4.48 1.09 6.32L12 17.29l-5.68 2.98 1.09-6.32-4.6-4.48 6.35-.92Z"/></svg>}{entry.trim().replace(/^\*/, '')}</span></span>)}</p>}
     </div>
     {mobile.controls&&<div className="mobile-pane-controls">
      {mobile.layout==='panes'&&<div className="mobile-pane-tabs" role="group" aria-label="슬라이드 보기">
       <button type="button" id={`${mobileId}-points-tab`} aria-controls={`${mobileId}-points`} aria-pressed={mobile.pane==='points'} onClick={()=>choosePane('points')}>요점</button>
       <button type="button" id={`${mobileId}-visual-tab`} aria-controls={`${mobileId}-visual`} aria-pressed={mobile.pane==='visual'} onClick={()=>choosePane('visual')}>도식</button>
      </div>}
      <button type="button" className="mobile-full-view" aria-pressed={mobile.full} onClick={mobile.toggleFull}>{mobile.full?'한 화면 보기':'전체 보기'}</button>
     </div>}
     {!tableLayout&&slide.kind!=="thanks"&&<div className="slide-points" id={`${mobileId}-points`} role={mobile.layout==='panes'?'region':undefined} aria-labelledby={mobile.layout==='panes'?`${mobileId}-points-tab`:undefined} hidden={mobile.pointsHidden} inert={mobile.pointsHidden} aria-hidden={mobile.pointsHidden||undefined}>{slide.points.slice(0,4).map((p,i)=><article className="slide-point" key={i}><span className="point-index">{slide.id==="dns"&&i>=2?(i===2?"A":"B"):`0${i+1}`}</span><div><h2>{p.title}</h2><p>{p.body}</p></div></article>)}</div>}
    </div>
    <div className="slide-visual-container" id={`${mobileId}-visual`} role={mobile.layout==='panes'?'region':undefined} aria-labelledby={mobile.layout==='panes'?`${mobileId}-visual-tab`:undefined} hidden={mobile.visualHidden} inert={mobile.visualHidden} aria-hidden={mobile.visualHidden||undefined}><SlideVisual slide={slide} sources={sources} motionPaused={motionPaused||Boolean(isLeaving)}/></div>
  </div>
  <EvidenceStrip slide={slide}/>
 </section>;
}

export function SlideDeck({deck,sources,mainSlideCount}:{deck:DeckSlide[];sources:SourceRegistry;mainSlideCount:number}){
 const [hydrated,setHydrated]=useState(false);
 const [index,setIndex]=useState(0);
 const indexRef=useRef(0);
 const slide=deck[index] || deck[0];
 const tableLayout=(["evidence","metrics"].includes(slide.kind)&&Boolean(slide.reading))||slide.kind==="sources";
 const separateMobilePoints=!tableLayout&&slide.points.length>0&&!['opening','introduction','thanks'].includes(slide.id);
 const mobile=useMobilePresentation(slide.id,separateMobilePoints,slide.id==='introduction'&&slide.points.length>0);
 const mobileRef=useRef(mobile);mobileRef.current=mobile;
 const leavingMobileRef=useRef<typeof mobile|null>(null);
 const [leavingIndex,setLeavingIndex]=useState<number|null>(null);
 const leavingTimerRef=useRef<ReturnType<typeof setTimeout>|null>(null);
 const navigationBurstUntil=useRef(0);
 const [direction,setDirection]=useState<"forward"|"back"|"none">("forward");
 const [showDetails,setShowDetails]=useState(false);
 const [fullscreen,setFullscreen]=useState(false);
 const [announcement,setAnnouncement]=useState("");
 const [motionPaused,setMotionPaused]=useState(false);
 const [micActive,setMicActive]=useState(false);
 const [micStop,setMicStop]=useState(0);
 const restoreSlideFocus=useRef(false);
 const menuRef=useRef<HTMLDialogElement>(null);
 const swipeRef=useRef<{id:number;x:number;y:number;started:number}|null>(null);
 const detailsCloseRef=useRef<HTMLButtonElement>(null);

 useEffect(()=>setHydrated(true),[]);
 useLayoutEffect(()=>{
  const viewport=document.getElementById('slide-area');
  viewport?.scrollTo({top:0,left:0,behavior:'instant'});
  if(restoreSlideFocus.current){viewport?.focus({preventScroll:true});restoreSlideFocus.current=false;}
 },[index]);

 useEffect(()=>{
  return()=>{
   if(leavingTimerRef.current){
    clearTimeout(leavingTimerRef.current);
    leavingTimerRef.current=null;
   }
  };
 },[]);

 useEffect(()=>{
  if(motionPaused){
   if(leavingTimerRef.current){clearTimeout(leavingTimerRef.current);leavingTimerRef.current=null;}
   setLeavingIndex(null);setDirection("none");
  }
  document.documentElement.dataset.motion=motionPaused?'off':'on';
  window.dispatchEvent(new CustomEvent('capstone:motion',{detail:{paused:motionPaused}}));
  return()=>{delete document.documentElement.dataset.motion;};
 },[motionPaused]);

 useEffect(()=>{
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  const stop=()=>{if(document.hidden||reduced.matches){
   if(leavingTimerRef.current){clearTimeout(leavingTimerRef.current);leavingTimerRef.current=null;}
   setLeavingIndex(null);setDirection("none");
  }};
  document.addEventListener('visibilitychange',stop);reduced.addEventListener('change',stop);
  return()=>{document.removeEventListener('visibilitychange',stop);reduced.removeEventListener('change',stop);};
 },[]);

 const transitionTo=useCallback((next:number)=>{
  const previous=indexRef.current;
  if(previous===next)return;
  indexRef.current=next;
  const dir=next>previous?"forward":"back";

  const now=performance.now();
  const interrupted=leavingTimerRef.current!==null||now<navigationBurstUntil.current;
  if(interrupted)navigationBurstUntil.current=now+180;
  if(leavingTimerRef.current){
   clearTimeout(leavingTimerRef.current);
   leavingTimerRef.current=null;
  }

  const isMobile=typeof window!=="undefined"&&window.innerWidth<=780;
  const immediate=interrupted||isMobile||mobileRef.current.layout==='full'||motionPaused||document.hidden||(typeof window!=="undefined"&&window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  restoreSlideFocus.current ||= Boolean(document.querySelector('.slide-active .deck-slide')?.contains(document.activeElement));

  if(immediate){
   setLeavingIndex(null);
   setDirection("none");
   setIndex(next);
  }else{
   leavingMobileRef.current=mobileRef.current;
   setLeavingIndex(previous);
   setDirection(dir);
   setIndex(next);
   leavingTimerRef.current=setTimeout(()=>{
    setLeavingIndex(null);
    leavingTimerRef.current=null;
   },380);
  }
 },[motionPaused]);

 const navigate=useCallback((target:number,replace=false)=>{
  const next=clampSlideIndex(target,deck.length);
  transitionTo(next);
  const href="#"+next;
  if(window.location.hash!==href){
    // Native fragment navigation avoids stale Next.js router history rewrites.
    if(replace)window.location.replace(href);
    else window.location.hash=href;
  }
 },[deck.length,transitionTo]);

 useEffect(()=>{
  const sync=()=>transitionTo(slideIndexFromHash(window.location.hash,deck));
  sync();
  // Next.js and history.replace/pushState can deliver same-document navigation
  // without a hashchange. Navigation API events cover that gap where supported.
  const navigation=(window as Window & {navigation?:EventTarget}).navigation;
  window.addEventListener("hashchange",sync);
  window.addEventListener("popstate",sync);
  navigation?.addEventListener("currententrychange",sync);
  return()=>{
    window.removeEventListener("hashchange",sync);
    window.removeEventListener("popstate",sync);
    navigation?.removeEventListener("currententrychange",sync);
  };
 },[deck,transitionTo]);

 useEffect(()=>{
  if(!showDetails)return;
  const trigger=document.activeElement instanceof HTMLElement?document.activeElement:null;
  detailsCloseRef.current?.focus();
  return()=>{if(trigger?.isConnected)trigger.focus();};
 },[showDetails]);

 useEffect(()=>{
  const onFull=()=>setFullscreen(Boolean(document.fullscreenElement));
  document.addEventListener("fullscreenchange",onFull);
  return()=>document.removeEventListener("fullscreenchange",onFull);
 },[]);

 useEffect(()=>{
  const onKey=(event:KeyboardEvent)=>{
   if(event.defaultPrevented||event.repeat)return;
   const el=event.target as Element|null;
   if(event.key==="Escape" && showDetails){event.preventDefault();setShowDetails(false);return;}
   // Preserve typing, native control keys and browser-modified shortcuts.
   if(event.altKey || event.ctrlKey || event.metaKey || event.isComposing)return;
   // Motion is a global accessibility control, including while a demo button
   // owns focus. Never consume typing in form/editable fields or key repeats.
   if(event.key.toLowerCase()==='m' && !el?.closest("input,select,textarea,[contenteditable]:not([contenteditable='false']),[role='textbox']")){
    event.preventDefault();if(!event.repeat)setMotionPaused(v=>!v);return;
   }
   if(event.key.toLowerCase()==='r'&&!menuRef.current?.open&&!showDetails&&!el?.closest("input,select,textarea,[contenteditable]:not([contenteditable='false']),[role='textbox']")){event.preventDefault();window.dispatchEvent(new Event('capstone:replay'));return;}
   const arrowStep=event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0;
   if(arrowStep){
    if(event.shiftKey||menuRef.current?.open||showDetails)return;
    // Key ownership follows semantics, not a diagram/container CSS class.
    // Ordinary (including toggle) buttons use Enter/Space and keep their focus;
    // only editing fields and widgets that own arrows suppress slide commands.
    if(el?.closest("input,select,textarea,[contenteditable]:not([contenteditable='false']),dialog,[role='dialog'],[role='textbox'],[role='tab'],[role='tablist'],[role='slider'],[role='scrollbar'],[role='spinbutton'],[role='combobox'],[role='listbox'],[role='radio'],[role='radiogroup'],[role='menu'],[role='menubar'],[role='tree'],[role='grid'],audio[controls],video[controls]"))return;
    event.preventDefault();navigate(indexRef.current+arrowStep);return;
   }
   if(el?.closest("a,input,select,textarea,summary,[contenteditable]:not([contenteditable='false']),[role='textbox'],[role='dialog'],.deck-slide button,.slide-details button,.deck-chapters button,.deck-header-actions>button,.restored-diagram"))return;
   if(event.key===" " && el?.closest("button"))return;
   if(menuRef.current?.open || showDetails){
    if(event.key==="Escape")setShowDetails(false);
    return;
   }
   if(event.key.toLowerCase()==='d'){
    const controls=[...document.querySelectorAll<HTMLButtonElement>('.slide-active .deck-slide [data-scenario-step="true"]')];
    if(controls.length){event.preventDefault();const active=Math.max(0,controls.findIndex(button=>button.getAttribute('aria-pressed')==='true'));controls[(active+1)%controls.length].click();}
    return;
   }
   if(event.key.toLowerCase()==="o")menuRef.current?.showModal();
   else if(event.key.toLowerCase()==="n")setShowDetails(value=>!value);
   else if(event.key.toLowerCase()==="f"){event.preventDefault();void toggleFullscreen();}
  };
  document.addEventListener("keydown",onKey);
  return()=>document.removeEventListener("keydown",onKey);
 },[showDetails,navigate,deck.length]);

 // Only a deliberate single-touch horizontal gesture on the noninteractive
 // narrative advances. Native vertical scrolling, pinch zoom and diagram input win.
 useEffect(()=>{
  const cancelSecondary=(event:PointerEvent)=>{if(event.pointerType==="touch"&&!event.isPrimary)swipeRef.current=null;};
  const cancel=()=>{swipeRef.current=null;};
  document.addEventListener("pointerdown",cancelSecondary,{passive:true});
  document.addEventListener("visibilitychange",cancel);
  window.addEventListener("pagehide",cancel);
  return()=>{document.removeEventListener("pointerdown",cancelSecondary);document.removeEventListener("visibilitychange",cancel);window.removeEventListener("pagehide",cancel);};
 },[]);
 const swipeExcluded=(target:EventTarget|null)=>!(target instanceof Element)||Boolean(target.closest("a,button,input,select,textarea,summary,[contenteditable]:not([contenteditable='false']),[role='button'],[role='slider'],[role='dialog'],.slide-visual-container,.slide-evidence-strip,.slide-details"));
 const hasSelection=()=>Boolean(window.getSelection()?.toString().trim());
 const startSwipe=(event:React.PointerEvent<HTMLElement>)=>{
  swipeRef.current=null;
  if(event.pointerType!=="touch"||!event.isPrimary||menuRef.current?.open||showDetails||swipeExcluded(event.target)||hasSelection())return;
  swipeRef.current={id:event.pointerId,x:event.clientX,y:event.clientY,started:performance.now()};
 };
 const moveSwipe=(event:React.PointerEvent<HTMLElement>)=>{
  const start=swipeRef.current;if(!start||event.pointerId!==start.id)return;
  const dx=Math.abs(event.clientX-start.x),dy=Math.abs(event.clientY-start.y);
  if(dy>14&&dy>dx*1.1)swipeRef.current=null;
 };
 const endSwipe=(event:React.PointerEvent<HTMLElement>)=>{
  const start=swipeRef.current;swipeRef.current=null;
  if(!start||event.pointerType!=="touch"||!event.isPrimary||event.pointerId!==start.id||menuRef.current?.open||showDetails||hasSelection()||swipeExcluded(event.target))return;
  const dx=event.clientX-start.x,dy=event.clientY-start.y;
  if(performance.now()-start.started>950||Math.abs(dx)<64||Math.abs(dx)<Math.abs(dy)*1.35)return;
  navigate(indexRef.current+(dx<0?1:-1));
 };

 const sourceItems=slide.sources.map(key=>({key,...sources[key]})).filter(v=>Boolean(v.url));
 const deckSourceItems=[...new Set(deck.flatMap(item=>item.sources))].map(key=>({key,...sources[key]})).filter(item=>Boolean(item.url));
 const currentChapter=slide.chapter;
 const chapterStarts=[...new Map<string,number>(deck.map((s,i)=>[s.chapter,i] as const).reverse()).entries()].reverse();
 const chapterLabel=(chapter:string)=>chapter.replace(/^\d+\s*·\s*/,"");
 async function toggleFullscreen(){
  try{
   if(document.fullscreenElement)await document.exitFullscreen();
   else if(typeof document.documentElement.requestFullscreen==="function")await document.documentElement.requestFullscreen();
   else{setAnnouncement("이 브라우저는 전체 화면 전환을 지원하지 않습니다. 브라우저의 전체 화면 기능을 이용해 주세요.");return;}
   setAnnouncement("");
  }catch{setAnnouncement("브라우저에서 전체 화면 전환을 허용하지 않았습니다. 일반 화면에서 발표를 계속할 수 있습니다.");}
 }
 return <div className="deck-root" data-hydrated={hydrated?"true":"false"}>
  <a className="skip-link" href="#slide-area" onClick={event=>{event.preventDefault();document.getElementById("slide-area")?.focus();}}>슬라이드 내용으로 이동</a>
  <header className="deck-topbar">
   <Link href="/" className="deck-logo" aria-label="ALEPH. E TEAM 홈으로">ALEPH<span>.</span> <small>E TEAM</small></Link>
   <nav className="deck-chapters" aria-label="발표 장">{chapterStarts.filter(([,at])=>deck[at].id!=="opening").map(([chapter,at])=><button key={chapter} type="button" aria-label={`${chapterLabel(chapter)} 장으로 이동`} aria-current={currentChapter===chapter?"step":undefined} onClick={()=>navigate(at)}>{chapterLabel(chapter)}</button>)}</nav>
   <div className="deck-header-actions"><a href="/dashboard" className="deck-reference-link deck-dashboard-link" aria-label="운영 대시보드로 이동">대시보드</a>{micActive&&<button type="button" className="mic-active" onClick={()=>setMicStop(v=>v+1)} aria-label="마이크 사용 중 · 박수 넘김 끄기" title="마이크 사용 중 · 끄기">● 끄기</button>}<button type="button" onClick={()=>setShowDetails(v=>!v)} aria-label={`참조·발표 노트 ${showDetails?'닫기':'보기'}`} aria-expanded={showDetails} aria-controls="slide-details">노트</button><button type="button" onClick={()=>menuRef.current?.showModal()} aria-haspopup="dialog">목차</button></div>
  </header>
  <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{hydrated?`${index+1} / ${deck.length} 슬라이드 · ${slide.title.replaceAll("\n"," ")}`:""}</p>
  {announcement&&<p role="status" className="deck-feedback">{announcement}</p>}
  <main id="slide-area" className="deck-viewport" aria-label="캡스톤 발표" aria-keyshortcuts="ArrowLeft ArrowRight" tabIndex={0} onPointerDown={startSwipe} onPointerMove={moveSwipe} onPointerUp={endSwipe} onPointerCancel={()=>{swipeRef.current=null;}}>
   <div className="deck-stage">
    {(leavingIndex!==null&&leavingIndex!==index?[leavingIndex,index]:[index]).map(trackIndex=>{
     const leaving=trackIndex!==index;
     return <div key={trackIndex} className={`slide-track ${leaving?'slide-leaving leave-':'slide-active enter-'}${direction}`} aria-hidden={leaving?true:undefined} inert={leaving?true:undefined}>
      <SlideItem
       slide={deck[trackIndex] || deck[0]}
       index={trackIndex}
       totalSlides={deck.length}
       mainSlideCount={mainSlideCount}
       sources={sources}
       motionPaused={motionPaused}
       mobile={leaving?(leavingMobileRef.current||mobile):mobile}
       isLeaving={leaving}
      />
     </div>;
    })}
   </div>
  </main>
  {showDetails && <aside id="slide-details" className="slide-details" aria-label="슬라이드 근거와 발표 노트">
   <div className="details-header"><h2>참조 · 발표 노트</h2><button ref={detailsCloseRef} type="button" onClick={()=>setShowDetails(false)} aria-label="근거 패널 닫기">×</button></div>
   <h3>이 페이지 참고 자료 · {sourceItems.length}개</h3><ul className="source-links">{sourceItems.map(item=><li key={item.key}><a href={item.url} target="_blank" rel="noreferrer noopener">{item.label} ↗</a>{item.note&&<small>{item.note}</small>}</li>)}</ul>
   <details><summary>전체 발표 참고 자료 · {deckSourceItems.length}개</summary><ul className="source-links">{deckSourceItems.map(item=><li key={item.key}><a href={item.url} target="_blank" rel="noreferrer noopener">{item.label} ↗</a>{item.note&&<small>{item.note}</small>}</li>)}</ul></details>
   <p className="details-cue">{slide.presentation?.cue||"발표용 추가 설명"}</p>
   {slide.presentation?.reviewNote && <div className="details-review"><strong>재평가 메모</strong><p>{slide.presentation.reviewNote}</p></div>}
   <details><summary>최종 발표 대본 · 화면 조작·전환 포함</summary><p>{slide.notes}</p></details>
   {slide.reading && <div className="reading-panel"><h3>{slide.reading.title}</h3><div className="reading-scroll"><table><thead><tr>{slide.reading.columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{slide.reading.rows.map((row,i)=><tr key={i}>{row.map((val,j)=><td key={j}>{val}</td>)}</tr>)}</tbody></table></div>{slide.reading.takeaway&&<p>{slide.reading.takeaway}</p>}<a href={slide.reading.source} target="_blank" rel="noreferrer noopener">{(slide.reading.sourceLabel||"자료 출처").replace(/(?:\s*↗)+\s*$/,"")} ↗</a></div>}
  </aside>}
  <dialog ref={menuRef} className="deck-overview" aria-label="슬라이드 목차" onClick={event=>{if(event.target===menuRef.current)menuRef.current.close()}}>
   <div className="overview-head"><h2>슬라이드 목차</h2><button onClick={()=>menuRef.current?.close()} aria-label="목차 닫기">×</button></div>
   <div className="overview-list">{deck.map((s,i)=><button type="button" key={s.id} className={i===index?"is-current":""} aria-current={i===index?"step":undefined} onClick={()=>{navigate(i);menuRef.current?.close()}}><span>{String(i+1).padStart(2,"0")}</span><div><small>{s.chapter} · {statusLabels[s.status]||s.status}</small><strong>{s.title.replaceAll("\n"," ")}</strong></div></button>)}</div>
   <div className="overview-help"><button type="button" aria-pressed={motionPaused} onClick={()=>setMotionPaused(v=>!v)} title="M">{motionPaused?"모션 켜기":"모션 정지"}</button> <button type="button" onClick={toggleFullscreen} aria-label={fullscreen?"전체 화면 종료":"전체 화면"} title="F">{fullscreen?"축소":"전체 화면"}</button></div>
   {announcement&&<p role="status" className="overview-help fullscreen-feedback">{announcement}</p>}
   <ClapControl onActiveChange={setMicActive} stopToken={micStop} onAdvance={()=>{menuRef.current?.close();navigate(indexRef.current+1);}}/><p className="overview-help">←/→: 이전·다음 슬라이드 · ↑/↓: 스크롤 · 터치 화면은 좌우 스와이프 · O: 목차 · N: 참조·노트 · F: 전체 화면 · M: 모션 · R: 시연 재생 · D: 다음 사례</p>
  </dialog>
 </div>;
}

