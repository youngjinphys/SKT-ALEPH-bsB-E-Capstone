"use client";

import {useState} from "react";
import {terminalResultParts} from "../lib/dns-terminal-results";
import google from "../../public/capstone/evidence/google-dns-observation.json";
import pi from "../../public/capstone/evidence/pi-dns-block-20261105.json";

type Domain="google.com"|"block.test";
const output=[google.header,google.flags,";; QUESTION SECTION:",google.question,";; ANSWER SECTION:",...google.answers,`;; Query time: ${google.queryMs} msec`].join("\n");
const block=pi.block_queries.find(query=>query.qtype==="A"&&query.transport==="UDP")!;

function ResultText({text}:{text:string}){
 return <>{terminalResultParts(text).map((part,index)=>part.tone
  ?<strong key={index} className="dns-terminal-result" data-result={part.tone}>{part.text}</strong>
  :part.text)}</>;
}
function Transcript({text}:{text:string}){
 return <pre className="dns-terminal-output"><code>{text.split("\n").map((line,index,lines)=><span key={index} className={line.includes("SECTION:")?"dns-terminal-line--section":!line.startsWith(";;")?"dns-terminal-line--answer":undefined}><ResultText text={line}/>{index<lines.length-1?"\n":""}</span>)}</code></pre>;
}

/** Two stored observations, from separate public and Pi DNS resolvers. */
export function ServerDnsObservation(){
 const [domain,setDomain]=useState<Domain>("google.com");
 const publicDns=domain==="google.com";
 return <section className="server-dns-observation" aria-label="DNS 질의 기록" data-evidence-state="captured" data-query-id={publicDns?google.id:"pi-dns-block-20261105"}>
  <header className="server-dns-heading">
   <div><span className="server-dns-kicker">{publicDns?"PUBLIC DNS · STORED RECORD":"PI DNS · STORED RECORD"}</span><h3>{publicDns?"공개 DNS 질의 기록":"Pi DNS 질의 기록"}</h3></div>
   <time dateTime={publicDns?google.timestamp:block.started_at}>{(publicDns?google.timestamp:block.started_at).slice(0,10)}<br/>{(publicDns?google.timestamp:block.started_at).slice(11,19)} UTC</time>
  </header>
  <div className="server-dns-selectors">
   <div role="group" aria-label="질의 이름 선택">{(["google.com","block.test"] as const).map(value=><button type="button" data-scenario-step="true" key={value} aria-pressed={domain===value} onClick={()=>setDomain(value)}>{value}</button>)}</div>
  </div>
  <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{publicDns?`google.com, NOERROR, 주소 ${google.answerCount}개. 공개 DNS 1.1.1.1의 별도 저장 기록입니다.`:"block.test의 Pi DNS 실제 응답은 NXDOMAIN, 주소 0개입니다. 정책 적용 여부는 확인하지 못했습니다."}</p>
  <figure className="dns-terminal" aria-label={publicDns?"google.com 저장된 터미널 출력":"block.test Pi DNS 저장된 터미널 출력"}>
   <figcaption className="dns-terminal-titlebar"><span className="dns-terminal-lights" aria-hidden="true"><i/><i/><i/></span><span>{publicDns?"public DNS / dig":"pi DNS / dig"}</span><span>READ ONLY</span></figcaption>
   <div className="dns-terminal-body">
    {publicDns?<>
     <p className="dns-terminal-excerpt">공개 DNS 별도 관측 · 1.1.1.1 · 명령 옵션 일부 생략</p>
     <p className="dns-terminal-command" data-command-display="summary"><span aria-hidden="true">$ </span><code>dig @1.1.1.1 google.com A</code></p>
     <Transcript text={output}/>
     <div className="dns-terminal-status"><span>exit {google.exitCode} · <ResultText text="NOERROR"/></span><time dateTime={google.timestamp}>{google.timestamp.slice(11,19)} UTC</time><a href="/capstone/evidence/google-dns-observation.json" target="_blank" rel="noopener noreferrer">기록 ↗</a></div>
    </>:<>
     <p className="dns-terminal-excerpt">Pi DNS 실제 질의 · A / UDP</p>
     <p className="dns-terminal-command" data-command-display="summary"><span aria-hidden="true">$ </span><code>{"dig @${PI_DNS} block.test A"}</code></p>
     <Transcript text={block.stdout}/>
     <div className="dns-terminal-status"><span>exit {block.exit_code} · <ResultText text={block.rcode}/></span><time dateTime={block.started_at}>{block.started_at.slice(11,19)} UTC</time><a href="/capstone/evidence/pi-dns-block-20261105.json" target="_blank" rel="noopener noreferrer">기록 ↗</a></div>
    </>}
   </div>
  </figure>
 </section>;
}
