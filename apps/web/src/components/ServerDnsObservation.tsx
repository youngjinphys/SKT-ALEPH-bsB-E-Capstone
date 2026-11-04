"use client";

import {useState} from "react";
import {terminalResultParts} from "../lib/dns-terminal-results";
import google from "../../public/capstone/evidence/google-dns-observation.json";

type Domain="google.com"|"block.test";
const output=[google.header,google.flags,";; QUESTION SECTION:",google.question,";; ANSWER SECTION:",...google.answers,`;; Query time: ${google.queryMs} msec`].join("\n");
// Authored illustration, never loaded from a captured experiment or executed.
const exampleOutput="QUERY    block.test A\nPOLICY   BLOCK (example)\nRESULT   NXDOMAIN (expected)\nANSWER: 0 (expected)";

function ResultText({text}:{text:string}){
 return <>{terminalResultParts(text).map((part,index)=>part.tone
  ?<strong key={index} className="dns-terminal-result" data-result={part.tone}>{part.text}</strong>
  :part.text)}</>;
}
function Transcript({text}:{text:string}){
 return <pre className="dns-terminal-output"><code>{text.split("\n").map((line,index,lines)=><span key={index} className={line.includes("SECTION:")?"dns-terminal-line--section":!line.startsWith(";;")?"dns-terminal-line--answer":undefined}><ResultText text={line}/>{index<lines.length-1?"\n":""}</span>)}</code></pre>;
}

/** A stored public-DNS record and an explicitly unexecuted Pi DNS illustration. */
export function ServerDnsObservation(){
 const [domain,setDomain]=useState<Domain>("google.com");
 const publicDns=domain==="google.com";
 return <section className="server-dns-observation" aria-label="DNS 질의 기록과 예시" data-evidence-state={publicDns?"captured":"illustration"} data-query-id={publicDns?google.id:"block-test-illustration"}>
  <header className="server-dns-heading">
   <div><span className="server-dns-kicker">{publicDns?"PUBLIC DNS · STORED RECORD":"PI DNS · ILLUSTRATION"}</span><h3>{publicDns?"공개 DNS 질의 기록":"Pi DNS 차단 흐름 예시"}</h3></div>
   {publicDns?<time dateTime={google.timestamp}>{google.timestamp.slice(0,10)}<br/>{google.timestamp.slice(11,19)} UTC</time>:<span className="dns-example-badge">예시 · 미실행</span>}
  </header>
  <div className="server-dns-selectors">
   <div role="group" aria-label="질의 이름 선택">{(["google.com","block.test"] as const).map(value=><button type="button" data-scenario-step="true" key={value} aria-pressed={domain===value} onClick={()=>setDomain(value)}>{value}</button>)}</div>
  </div>
  <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{publicDns?`google.com, NOERROR, 주소 ${google.answerCount}개. 공개 DNS 1.1.1.1의 별도 저장 기록입니다.`:"block.test는 Pi DNS 차단 흐름을 설명하는 미실행 예시입니다. NXDOMAIN과 주소 0개는 동작 이해를 위한 예상 응답입니다."}</p>
  <figure className="dns-terminal" aria-label={publicDns?"google.com 저장된 터미널 출력":"block.test Pi DNS 미실행 예시"}>
   <figcaption className="dns-terminal-titlebar"><span className="dns-terminal-lights" aria-hidden="true"><i/><i/><i/></span><span>{publicDns?"public DNS / dig":"pi DNS / example"}</span><span>{publicDns?"READ ONLY":"NOT RUN"}</span></figcaption>
   <div className="dns-terminal-body">
    {publicDns?<>
     <p className="dns-terminal-excerpt">공개 DNS 별도 관측 · 1.1.1.1 · 명령 옵션 일부 생략</p>
     <p className="dns-terminal-command" data-command-display="summary"><span aria-hidden="true">$ </span><code>dig @1.1.1.1 google.com A</code></p>
     <Transcript text={output}/>
     <div className="dns-terminal-status"><span>exit {google.exitCode} · <ResultText text="NOERROR"/></span><time dateTime={google.timestamp}>{google.timestamp.slice(11,19)} UTC</time><a href="/capstone/evidence/google-dns-observation.json" target="_blank" rel="noopener noreferrer">기록 ↗</a></div>
    </>:<>
     <p className="dns-terminal-excerpt">Pi DNS 차단 예시 · 미실행</p>
     <p className="dns-terminal-command" data-command-display="illustration"><span aria-hidden="true">$ </span><code>{"dig @${PI_DNS} block.test A"}</code></p>
     <Transcript text={exampleOutput}/>
     <div className="dns-terminal-status"><span>예상 응답 · <ResultText text="NXDOMAIN"/></span><span>설명용 출력</span></div>
    </>}
   </div>
  </figure>
 </section>;
}
