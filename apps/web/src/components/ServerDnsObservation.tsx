"use client";

import {useState} from "react";
import google from "../../public/capstone/evidence/google-dns-observation.json";
import block from "../../public/capstone/evidence/block-test-loopback-20261104.json";

type Domain="google.com"|"block.test";
const output=[google.header,google.flags,";; QUESTION SECTION:",google.question,";; ANSWER SECTION:",...google.answers,`;; Query time: ${google.queryMs} msec`].join("\n");
const blocked=block.phases.find(phase=>phase.name==="blocked")!;
const blockedQuery=blocked.queries.find(query=>query.qtype==="A"&&query.transport==="UDP")!;

/** Recorded observations from separate public-DNS and isolated loopback tests. */
export function ServerDnsObservation(){
 const [domain,setDomain]=useState<Domain>("google.com");
 const publicDns=domain==="google.com";
 return <section className="server-dns-observation" aria-label="DNS 질의 기록" data-evidence-state={publicDns?"captured":"fixture"} data-query-id={publicDns?google.id:"block-test-loopback"}>
  <header className="server-dns-heading">
   <div><span className="server-dns-kicker">{publicDns?"PUBLIC DNS · STORED RECORD":"ISOLATED LOOPBACK · CAPTURED"}</span><h3>{publicDns?"공개 DNS 질의 기록":"격리 DNS 질의 기록"}</h3></div>
   <time dateTime={publicDns?google.timestamp:block.started_at}>{(publicDns?google.timestamp:block.started_at).slice(0,10)}<br/>{(publicDns?google.timestamp:block.started_at).slice(11,19)} UTC</time>
  </header>
  <div className="server-dns-selectors">
   <div role="group" aria-label="질의 이름 선택">{(["google.com","block.test"] as const).map(value=><button type="button" data-scenario-step="true" key={value} aria-pressed={domain===value} onClick={()=>setDomain(value)}>{value}</button>)}</div>
  </div>
  <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{publicDns?`google.com, NOERROR, 주소 ${google.answerCount}개. 공개 DNS 1.1.1.1의 별도 저장 기록입니다.`:"block.test 격리 실험. 적용 전 정상 응답, BLOCK 적용 후 NXDOMAIN, 철회 후 정상 응답. A와 AAAA, UDP와 TCP 각각 확인."}</p>
  <figure className="dns-terminal" aria-label={publicDns?"google.com 저장된 터미널 출력":"block.test 격리 DNS 실험 기록"}>
   <figcaption className="dns-terminal-titlebar"><span className="dns-terminal-lights" aria-hidden="true"><i/><i/><i/></span><span>{publicDns?"public DNS / dig":"loopback / dig"}</span><span>READ ONLY</span></figcaption>
   <div className="dns-terminal-body">
    {publicDns?<>
     <p className="dns-terminal-excerpt">공개 DNS 별도 관측 · 1.1.1.1 · 명령 옵션 일부 생략</p>
     <p className="dns-terminal-command" data-command-display="summary"><span aria-hidden="true">$ </span><code>dig @1.1.1.1 google.com A</code></p>
     <pre className="dns-terminal-output"><code>{output.split("\n").map((line,index,lines)=><span key={index} className={line.includes("SECTION:")?"dns-terminal-line--section":!line.startsWith(";;")?"dns-terminal-line--answer":undefined}>{line}{index<lines.length-1?"\n":""}</span>)}</code></pre>
     <div className="dns-terminal-status"><span>exit {google.exitCode} · NOERROR</span><time dateTime={google.timestamp}>{google.timestamp.slice(11,19)} UTC</time><a href="/capstone/evidence/google-dns-observation.json" target="_blank" rel="noopener noreferrer">기록 ↗</a></div>
    </>:<>
     <p className="dns-terminal-excerpt">ISOLATED LOOPBACK · BLOCK 적용 · A / UDP</p>
     <p className="dns-terminal-command" data-command-display="recorded"><span aria-hidden="true">$ </span><code>{blockedQuery.command.join(" ")}</code></p>
     <pre className="dns-terminal-output"><code>{blockedQuery.stdout}</code></pre>
     <p className="dns-fixture-summary">적용 전 NOERROR · BLOCK 적용 NXDOMAIN · 철회 후 NOERROR<br/>A·AAAA / UDP·TCP, 12/12 기대 응답 일치</p>
     <p className="dns-fixture-boundary">통제된 로컬 DNS 실험 · 운영 DNS 적용 증거 아님</p>
     <div className="dns-terminal-status"><span>exit {blockedQuery.exit_code} · {blockedQuery.rcode}</span><time dateTime={blockedQuery.started_at}>{blockedQuery.started_at.slice(11,19)} UTC</time><a href="/capstone/evidence/block-test-loopback-20261104.json" target="_blank" rel="noopener noreferrer">실험 기록 ↗</a></div>
    </>}
   </div>
  </figure>
 </section>;
}
