"use client";

import {useState} from "react";
import capture from "../../public/capstone/evidence/dns-terminal-20261104.json";

type Domain="google.com"|"example.com";
type Transport="TCP"|"UDP";
type Route="system"|"private";

/** A redacted, timestamped capture. Selecting a record never runs a command. */
export function ServerDnsObservation(){
 const [domain,setDomain]=useState<Domain>("google.com");
 const [transport,setTransport]=useState<Transport>("TCP");
 const [route,setRoute]=useState<Route>("private");
 const record=capture.queries.find(query=>query.domain===domain&&query.transport===transport&&query.route===route)!;
 const output=[record.header,record.flags,";; QUESTION SECTION:",record.question,";; ANSWER SECTION:",...record.answers,`;; Query time: ${record.queryMs} msec`,record.server].join("\n");
 return <section className="server-dns-observation" aria-label="server 실제 DNS 질의 결과" data-query-id={record.id}>
  <header className="server-dns-heading">
   <div><span className="server-dns-kicker">SERVER · CAPTURED SESSION</span><h3>실제 DNS 질의 기록</h3></div>
   <time dateTime="2026-11-04T02:42:20Z">2026.11.04<br/>02:42 UTC</time>
  </header>
  <div className="server-dns-selectors">
   <div role="group" aria-label="저장된 질의 이름 선택">{(["google.com","example.com"] as const).map(value=><button type="button" data-scenario-step="true" key={value} aria-pressed={domain===value} onClick={()=>setDomain(value)}>{value}</button>)}</div>
   <div role="group" aria-label="저장된 전송 방식 선택">{(["TCP","UDP"] as const).map(value=><button type="button" data-scenario-step="true" key={value} aria-pressed={transport===value} onClick={()=>setTransport(value)}>{value}</button>)}</div>
  </div>
  <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{domain} {transport}, {route==="private"?"사설 DNS":"기본 DNS"}, NOERROR, 주소 {record.answerCount}개. 저장된 기록입니다.</p>
  <figure className="dns-terminal" aria-label={`${domain} ${transport} ${route==="private"?"사설 DNS":"기본 DNS"} 저장된 터미널 출력`}>
   <figcaption className="dns-terminal-titlebar"><span className="dns-terminal-lights" aria-hidden="true"><i/><i/><i/></span><span>server / dig</span><span>READ ONLY</span></figcaption>
   <div className="dns-terminal-routes" role="group" aria-label="저장된 DNS 경로 선택">{(["system","private"] as const).map(value=>{
    const peer=capture.queries.find(query=>query.domain===domain&&query.transport===transport&&query.route===value)!;
    return <button type="button" data-scenario-step="true" key={value} aria-pressed={route===value} onClick={()=>setRoute(value)}><span>{value==="system"?"기본 DNS · 로컬 stub":"사설 DNS · 직접 지정"}</span><b>A {peer.answerCount}개</b></button>;
   })}</div>
   <div className="dns-terminal-body">
    <p className="dns-terminal-command"><span aria-hidden="true">$ </span><code>{record.command}</code></p>
    <pre className="dns-terminal-output"><code>{output.split("\n").map((line,index,lines)=><span key={index} className={line.includes("SECTION:")?"dns-terminal-line--section":!line.startsWith(";;")?"dns-terminal-line--answer":undefined}>{line}{index<lines.length-1?"\n":""}</span>)}</code></pre>
    <div className="dns-terminal-status"><span>exit {record.exitCode} · NOERROR</span><time dateTime={record.timestamp}>{record.timestamp.slice(11,23)} UTC</time></div>
   </div>
  </figure>
 </section>;
}
