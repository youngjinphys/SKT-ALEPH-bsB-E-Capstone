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
    <pre className="dns-terminal-output"><code>{output}</code></pre>
    <div className="dns-terminal-status"><span>exit {record.exitCode} · NOERROR</span><time dateTime={record.timestamp}>{record.timestamp.slice(11,23)} UTC</time></div>
   </div>
  </figure>
  <p className="server-dns-result"><b>8건 모두 주소 반환</b><span>이 기록에서 google.com 차단 응답은 관측되지 않았습니다.</span></p>
  <footer className="server-dns-note">
   <p>저장된 8건 중 선택한 기록입니다. 선택해도 명령을 실행하지 않습니다.</p>
   <p>주소·일부 출력은 생략했습니다. 시간은 단건 dig 표기이며 성능 비교가 아닙니다.</p>
   <p>기본 DNS의 후단·캐시와 현재 정책은 미확인입니다.</p>
   <a href={capture.sourceUrl} target="_blank" rel="noopener noreferrer">질의 8건 · 원본 해시 ↗</a><span aria-hidden="true"> · </span><a href="/capstone/evidence/dns-terminal-20261104.json" target="_blank" rel="noopener noreferrer">터미널 발췌 데이터 ↗</a>
  </footer>
 </section>;
}
