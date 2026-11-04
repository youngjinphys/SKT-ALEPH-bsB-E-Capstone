"use client";
import Link from "next/link";
import {RestoredMascot} from "./RestoredScene";
import {useEffect,useState} from "react";

type AuthState="checking"|"ready"|"disabled"|"unknown";
const authErrors:Record<string,string>={
 google_disabled:"Google 로그인이 아직 연결되지 않았습니다.",
 provider_unavailable:"인증 공급자 상태를 확인하지 못했습니다.",
 not_configured:"인증 서버 설정을 확인해 주세요.",
 expired_flow:"로그인 요청이 만료되었습니다. 처음부터 진행해 주세요.",
 cancelled:"로그인이 취소되었습니다.",
 invalid_callback:"인증 응답을 확인할 수 없습니다.",
 exchange_failed:"Google 인증 교환에 실패했습니다.",
 access_denied:"인증된 계정이지만 연구실 접근 승인이 필요합니다.",
 auth_unavailable:"인증 서버에 일시적으로 연결할 수 없습니다.",
 flow_failed:"로그인 요청을 처리할 수 없습니다.",
};
type LandingContent = {
 hero:{intro:string;emphasis:string;lead:string[]};
 trail:{key:string;name:string;title:string;body:string;warning:string;hash:string}[];
 layers:{index:string;eyebrow:string;title:string;desc:string;hash:string}[];
};
type LandingStats = {main:number;appendix:number;seconds:number};
export function Landing({content,stats}:{content:LandingContent;stats:LandingStats}){
 const trail=content.trail;
 const [auth,setAuth]=useState<AuthState>("checking");
 const [message,setMessage]=useState("Google 로그인 연결을 확인 중입니다.");
 const [callbackError,setCallbackError]=useState<string|null>(null);
 const [selected,setSelected]=useState(0);
 const [paused,setPaused]=useState(false);
 const [greet,setGreet]=useState(0);
 const [retry,setRetry]=useState(0);
 useEffect(()=>{
  const params=new URLSearchParams(window.location.search);
  const error=params.get("auth_error");
  if(error && authErrors[error]){
   setCallbackError(authErrors[error]);
   params.delete("auth_error");
   window.history.replaceState(null,"",window.location.pathname+(params.toString()?"?"+params:"")+window.location.hash);
  }
 },[]);
 useEffect(()=>{
  const controller=new AbortController();
  const load=async()=>{
   setAuth("checking");
   try{
    const reply=await fetch("/api/oauth?action=status",{cache:"no-store",credentials:"same-origin",signal:controller.signal});
    if(!reply.ok)throw Error("provider");
    const value=await reply.json() as {state?:string};
    if(controller.signal.aborted)return;
    if(value.state==="enabled"){setAuth("ready");setMessage("Google 인증 연결이 준비되었습니다.");}
    else if(value.state==="disabled"){setAuth("disabled");setMessage("운영자의 Google OAuth 연결 설정이 필요합니다.");}
    else{setAuth("unknown");setMessage("인증 공급자 상태를 확인할 수 없습니다.");}
   }catch{if(!controller.signal.aborted){setAuth("unknown");setMessage("인증 공급자 상태 확인에 실패했습니다.");}}
  };
  void load();
  return()=>controller.abort();
 },[retry]);
 const current=trail[selected];
 return <div className={`site-root ${paused?"motion-paused":""}`}>
  <a className="skip-link" href="#auth">로그인 영역으로 이동</a>
  <header className="site-topbar shell">
   <Link className="brand" href="/" aria-label="ALEPH 캡스톤 홈"><span><strong>ALEPH<span className="accent">.</span></strong><small>SECURITY CAPSTONE</small></span></Link>
   <nav className="top-links" aria-label="페이지 메뉴"><Link href="/capstone">캡스톤 발표 <span aria-hidden="true">↗</span></Link><Link href="/fishing">보안 시연실 <span aria-hidden="true">↗</span></Link><a href="/dashboard" className="nav-emphasis">관제센터 ↗</a><a href="#auth">연구실 입장</a></nav>
  </header>
  <main className="landing-main shell">
   <section className="landing-intro" aria-labelledby="landing-title">
    <div className="landing-copy">
     <h1 id="landing-title">{content.hero.intro}<br/><em>{content.hero.emphasis}</em></h1>
     <p className="lead">{content.hero.lead.map((line,i)=><span key={i}>{line}{i<content.hero.lead.length-1&&<br/>}</span>)}</p>
     <div className="landing-actions"><Link href="/capstone" className="button-primary">발표 살펴보기 <span aria-hidden="true">↗</span></Link><Link href="/fishing" className="button-outline">안전한 시뮬레이션</Link></div>
     <div className="landing-facts" aria-label="캡스톤 발표 구성">
      <div><strong>{String(stats.main).padStart(2,"0")}</strong><span>본편 슬라이드</span></div>
      <div><strong>{String(stats.appendix).padStart(2,"0")}</strong><span>참고·부록</span></div>
      <div><strong>정책→DNS</strong><span>검증 대상 흐름</span></div>
     </div>
     <div className="trail-panel">
      <div className="section-eyebrow">PROBLEM → EVIDENCE → RESPONSIBILITY</div>
      <div className="trail-tabs" role="group" aria-label="연구 과정">{trail.map((item,i)=><button key={item.key} type="button" className={i===selected?"selected":""} onClick={()=>setSelected(i)} aria-pressed={i===selected}>{item.name}</button>)}</div>
      <div className="trail-info" aria-live="polite"><h2>{current.title}</h2><p>{current.body}</p><small>{current.warning}</small><Link href={`/capstone#${current.hash}`}>관련 슬라이드 보기 ↗</Link></div>
     </div>
    </div>
    <div className="landing-scene">
      <div className="orbit orbit-a" aria-hidden="true"/><div className="orbit orbit-b" aria-hidden="true"/>
      <button type="button" className="mascot-button" onClick={()=>setGreet(n=>n+1)} aria-label="피라냥에게 인사하기">
       {/* The mascot is a project-owned asset; not an AI agent or a threat detector. */}
       {/* eslint-disable-next-line @next/next/no-img-element */}
       <RestoredMascot paused={paused}/>
      </button>
      <div className="mascot-message"><div><span className="live-dot"/> 피라냥 · PROJECT GUIDE</div><p aria-live="polite">{greet%3===1?"반가워! 관측과 추측을 나눠 보자.":greet%3===2?"확인한 근거부터 차근차근 연결해 봐!":"어서 와! 오늘도 근거로 확인해 보자. 🐾"}</p><button className="motion-toggle" aria-pressed={paused} onClick={()=>setPaused(n=>!n)}>{paused?"움직임 켜기":"움직임 멈추기"}</button></div>
      <p className="mascot-disclaimer">캐릭터는 보안 개념을 설명하는 교육용 안내 요소입니다. 실제 탐지·정책 적용 결과는 실험·관제 기록으로 확인합니다.</p>
    </div>
   </section>
   <section className="landing-layers" aria-label="검증의 세 경계">
    {content.layers.map(layer=><Link href={"/capstone#"+layer.hash} className="landing-layer" key={layer.index}>
     <div className="layer-topline"><span>{layer.index} / {layer.eyebrow}</span><span aria-hidden="true">↗</span></div>
     <strong>{layer.title}</strong>
     <p>{layer.desc}</p>
    </Link>)}
   </section>
   <section className="access-section" id="auth" aria-labelledby="access-title"><div className="access-intro"><span className="section-eyebrow">AUTHENTICATION ≠ AUTHORIZATION</span><h2 id="access-title">보안 연구실 입장</h2><p>계정 인증 후 서버에서 접근 권한을 별도로 검증합니다. 인증 토큰은 브라우저 스크립트에 노출하지 않습니다.</p></div><div className="access-panel"><div className="provider-state" data-state={auth} role="status" aria-live="polite"><span className="live-dot"/>{auth==="ready"?"Google 로그인 가능":auth==="checking"?"연결 확인 중":auth==="disabled"?"설정 필요":"연결 확인 불가"}</div>{auth==="ready"?<a href="/api/oauth?action=start" onClick={()=>setCallbackError(null)} className="button-primary google-entry">Google로 계속하기 <span aria-hidden="true">→</span></a>:<button className="button-primary google-entry" disabled>Google 인증 연결 대기</button>}<p role="status" className="access-message">{message}</p>{callbackError&&<p role="alert" className="access-message">{callbackError}</p>}<button className="text-control" type="button" disabled={auth==="checking"} onClick={()=>setRetry(n=>n+1)}>연결 다시 확인 ↻</button><hr/><p className="access-small">비밀번호·결제정보는 이 사이트에서 입력받지 않습니다. 공개 시연은 로그인 없이 열 수 있습니다.</p></div></section>
  </main>
  <footer className="site-footer shell"><span>© 2026 SKT ALEPH · E TEAM</span><span>서명 · 집행 · 철회 · 복구 · 검증</span></footer>
 </div>;
}
