"use client";

import {useState} from "react";
import capture from "../../public/capstone/evidence/dns-terminal-20261104.json";

type Domain="google.com"|"block.test";
// Preserve the original capture. A new domain is never substituted into it.
const google=capture.queries.find(query=>query.domain==="google.com"&&query.transport==="TCP"&&query.route==="private")!;
const output=[google.header,google.flags,";; QUESTION SECTION:",google.question,";; ANSWER SECTION:",...google.answers,`;; Query time: ${google.queryMs} msec`].join("\n");

/** A stored response and a clearly labelled simulated rejection, never a live shell. */
export function ServerDnsObservation(){
 const [domain,setDomain]=useState<Domain>("google.com");
 const recorded=domain==="google.com";
 return <section className="server-dns-observation" aria-label="server DNS 질의 기록 · 모의" data-evidence-state={recorded?"captured":"simulated"} data-query-id={recorded?google.id:undefined}>
  <header className="server-dns-heading">
   <div><span className="server-dns-kicker">SERVER · {recorded?"CAPTURED SESSION":"SIMULATION"}</span><h3>DNS 질의 기록</h3></div>
   {recorded?<time dateTime={google.timestamp}>2026.11.04<br/>02:42 UTC</time>:<span className="server-dns-unverified">모의</span>}
  </header>
  <div className="server-dns-selectors">
   <div role="group" aria-label="질의 이름 선택">{(["google.com","block.test"] as const).map(value=><button type="button" data-scenario-step="true" key={value} aria-pressed={domain===value} onClick={()=>setDomain(value)}>{value}</button>)}</div>
  </div>
  <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{recorded?`google.com, NOERROR, 주소 ${google.answerCount}개. 저장된 기록입니다.`:"block.test, 정책 모의 BLOCK, 차단 REJECT, DNS 응답 NXDOMAIN. 실제 질의 미실행."}</p>
  <figure className="dns-terminal" aria-label={recorded?"google.com 저장된 터미널 출력":"block.test 정책 차단 모의"}>
   <figcaption className="dns-terminal-titlebar"><span className="dns-terminal-lights" aria-hidden="true"><i/><i/><i/></span><span>server / dig</span><span>{recorded?"READ ONLY":"SIMULATION"}</span></figcaption>
   <div className="dns-terminal-body">
    {recorded?<>
     <p className="dns-terminal-excerpt">명령·응답 일부 생략</p>
     <p className="dns-terminal-command" data-command-display="summary"><span aria-hidden="true">$ </span><code>dig google.com A</code></p>
     <pre className="dns-terminal-output"><code>{output.split("\n").map((line,index,lines)=><span key={index} className={line.includes("SECTION:")?"dns-terminal-line--section":!line.startsWith(";;")?"dns-terminal-line--answer":undefined}>{line}{index<lines.length-1?"\n":""}</span>)}</code></pre>
     <div className="dns-terminal-status"><span>exit {google.exitCode} · NOERROR</span><time dateTime={google.timestamp}>{google.timestamp.slice(11,23)} UTC</time><a href="/capstone/evidence/dns-terminal-20261104.json" target="_blank" rel="noopener noreferrer">기록 ↗</a></div>
    </>:<div className="dns-terminal-pending" role="note" aria-label="정책 차단 모의">
     <span>SIMULATION</span><h4>block.test</h4><p>정책: BLOCK · 차단: REJECT · DNS 응답: NXDOMAIN</p><p>모의 · 실제 질의 미실행</p>
    </div>}
   </div>
  </figure>
 </section>;
}
