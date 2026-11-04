"use client";
import Link from "next/link";
import {useState} from "react";

export type LogoutOutcome="complete"|"unconfirmed"|"error";

/** A received unconfirmed response has already cleared local cookies. Do not
 * turn a second request with no cookies into apparent remote revocation success. */
export async function requestLogout(fetcher:typeof fetch=fetch):Promise<LogoutOutcome>{
 try {
  const response=await fetcher("/api/auth",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"logout"}),credentials:"same-origin"});
  const body:unknown=await response.json();
  if(response.status===503 && body && typeof body==="object" && "error" in body && body.error==="LOGOUT_REVOCATION_UNCONFIRMED")return "unconfirmed";
  if(response.ok && body && typeof body==="object" && "ok" in body && body.ok===true)return "complete";
 }catch{/* A network failure does not establish whether cookies were cleared. */}
 return "error";
}

export function LogoutUnconfirmed(){
 return <div className="site-root"><main className="error-page">
  <div role="alert"><h1>이 브라우저에서는 로그아웃했습니다.</h1>
   <p>로그인 쿠키는 삭제했지만, 원격 인증 서버의 세션 폐기는 확인하지 못했습니다.</p>
   <p>같은 로그아웃 요청을 반복해도 원격 세션 폐기를 확인할 수는 없습니다. 확인이 필요하면 운영자에게 문의해 주세요.</p>
   <p>공용 기기라면 Google 계정의 로그인 상태도 별도로 확인하세요. Google 로그아웃은 이 서비스의 원격 세션 폐기 확인을 대신하지 않습니다.</p>
  </div><a className="button-primary" href="/">공개 홈으로 이동</a>
 </main></div>;
}

export function Workspace({email}:{email:string}){
 const [state,setState]=useState<"idle"|"busy"|"error"|"unconfirmed">("idle");
 async function logout(){
  if(state==="busy" || state==="unconfirmed")return;
  setState("busy");
  const outcome=await requestLogout();
  if(outcome==="complete"){window.location.assign("/");return;}
  setState(outcome);
 }
 // Remove the stale authenticated identity and actions after local logout.
 if(state==="unconfirmed")return <LogoutUnconfirmed/>;
 return <div className="site-root">
  <header className="site-topbar shell"><Link href="/" className="brand"><span className="brand-glyph">A</span><span><strong>ALEPH.</strong><small>MY SECURITY LAB</small></span></Link><button className="text-control" onClick={logout} disabled={state==="busy"}>{state==="busy"?"로그아웃 중…":"로그아웃 ↗"}</button></header>
  <main className="workspace shell"><div className="workspace-heading"><span className="section-eyebrow">SERVER-VERIFIED SESSION</span><h1>오늘도 피라냥과<br/><em>근거를 찾아볼까요?</em></h1><p>연구실 접근 권한이 서버에서 확인되었습니다. 실습과 발표는 공개이지만 개인 정보는 인증 구간에서만 확인합니다.</p><small>인증된 계정 · {email}</small></div><div className="workspace-mascot"><img src="/assets/piranyang/poses/work.webp" alt="피라냥이 사이버 보안 연구를 하는 모습" width="448" height="432"/></div>
   <section className="workspace-links" aria-label="연구 메뉴"><a href="/dashboard"><span>00 / OPERATIONS CENTER</span><strong>DNS 관제센터</strong><p>정책 검토·배포와 서명된 노드 상태를 확인합니다.</p><b>↗</b></a><Link href="/fishing"><span>01 / SECURITY EXERCISE</span><strong>가상 사이트 검증 실습</strong><p>보기 좋은 사이트와 진짜 신뢰성의 차이를 검증합니다.</p><b>↗</b></Link><Link href="/capstone"><span>02 / PROJECT PRESENTATION</span><strong>Protective DNS 캡스톤</strong><p>정책·집행·증거·한계를 따라가는 발표입니다.</p><b>↗</b></Link></section>
   {state==="error"&&<p role="alert" className="danger-text">로그아웃 결과를 확인하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.</p>}
  </main>
 </div>;
}
