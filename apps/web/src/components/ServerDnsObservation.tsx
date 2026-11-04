"use client";

import {useState} from "react";
import {terminalResultParts} from "../lib/dns-terminal-results";
import google from "../../public/capstone/evidence/google-dns-observation.json";
import block from "../../public/capstone/evidence/block-test-loopback-20261104.json";

type Domain="google.com"|"block.test";
const output=[google.header,google.flags,";; QUESTION SECTION:",google.question,";; ANSWER SECTION:",...google.answers,`;; Query time: ${google.queryMs} msec`].join("\n");
const blocked=block.phases.find(phase=>phase.name==="blocked")!;
const blockedQuery=blocked.queries.find(query=>query.qtype==="A"&&query.transport==="UDP")!;
// Preserve the full command and EDNS metadata in the linked record. The visible
// excerpt omits transport details; every remaining response line is unchanged.
const blockedOutput=blockedQuery.stdout.split("\n")
 .filter(line=>!line.startsWith(";; OPT PSEUDOSECTION:")&&!line.startsWith("; EDNS:"))
 .join("\n");

function ResultText({text}:{text:string}){
 return <>{terminalResultParts(text).map((part,index)=>part.tone
  ?<strong key={index} className="dns-terminal-result" data-result={part.tone}>{part.text}</strong>
  :part.text)}</>;
}
function Transcript({text}:{text:string}){
 return <pre className="dns-terminal-output"><code>{text.split("\n").map((line,index,lines)=><span key={index} className={line.includes("SECTION:")?"dns-terminal-line--section":!line.startsWith(";;")?"dns-terminal-line--answer":undefined}><ResultText text={line}/>{index<lines.length-1?"\n":""}</span>)}</code></pre>;
}

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
  <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{publicDns?`google.com, NOERROR, 주소 ${google.answerCount}개. 공개 DNS 1.1.1.1의 별도 저장 기록입니다.`:"block.test 격리 실험. 적용 전 정상 응답, BLOCK 적용 후 NXDOMAIN, 철회 후 정상 응답. 12개 질의가 기대 응답과 일치."}</p>
  <figure className="dns-terminal" aria-label={publicDns?"google.com 저장된 터미널 출력":"block.test 격리 DNS 실험 기록"}>
   <figcaption className="dns-terminal-titlebar"><span className="dns-terminal-lights" aria-hidden="true"><i/><i/><i/></span><span>{publicDns?"public DNS / dig":"loopback / dig"}</span><span>READ ONLY</span></figcaption>
   <div className="dns-terminal-body">
    {publicDns?<>
     <p className="dns-terminal-excerpt">공개 DNS 별도 관측 · 1.1.1.1 · 명령 옵션 일부 생략</p>
     <p className="dns-terminal-command" data-command-display="summary"><span aria-hidden="true">$ </span><code>dig @1.1.1.1 google.com A</code></p>
     <Transcript text={output}/>
     <div className="dns-terminal-status"><span>exit {google.exitCode} · <ResultText text="NOERROR"/></span><time dateTime={google.timestamp}>{google.timestamp.slice(11,19)} UTC</time><a href="/capstone/evidence/google-dns-observation.json" target="_blank" rel="noopener noreferrer">기록 ↗</a></div>
    </>:<>
     <p className="dns-terminal-excerpt">격리 DNS 실험 · 명령·응답 일부 생략</p>
     <p className="dns-terminal-command" data-command-display="summary"><span aria-hidden="true">$ </span><code>dig block.test A</code></p>
     <Transcript text={blockedOutput}/>
     <div className="dns-terminal-status"><span>exit {blockedQuery.exit_code} · <ResultText text={blockedQuery.rcode}/></span><time dateTime={blockedQuery.started_at}>{blockedQuery.started_at.slice(11,19)} UTC</time><a href="/capstone/evidence/block-test-loopback-20261104.json" target="_blank" rel="noopener noreferrer">실험 기록 ↗</a></div>
    </>}
   </div>
  </figure>
 </section>;
}
