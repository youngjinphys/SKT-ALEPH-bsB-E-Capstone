import type {Metadata} from 'next';
import Link from 'next/link';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {slides,sources} from '@/lib/deck.server';
import {buildReferenceIndex} from '@/lib/references';
import './references.css';

export const metadata:Metadata={title:'발표 참조 · 근거와 Q&A',description:'캡스톤 발표 슬라이드별 근거, 원문 링크, 실험 해석과 최종 원고의 예상 질문 답변.'};

function InlineText({text}:{text:string}){
 const tokens=text.split(/(\[[^\]\n]+\]\(https:\/\/[^\s)]+\)|`[^`\n]+`)/g);
 return <>{tokens.map((token,index)=>{
  const link=/^\[([^\]\n]+)\]\((https:\/\/[^\s)]+)\)$/.exec(token);
  if(link)return <a key={index} href={link[2]} target="_blank" rel="noopener noreferrer">{link[1]} ↗</a>;
  if(token.startsWith('`')&&token.endsWith('`'))return <code key={index}>{token.slice(1,-1)}</code>;
  return <span key={index}>{token}</span>;
 })}</>;
}
export default function ReferencesPage(){
 const manuscript=readFileSync(join(process.cwd(),'docs','presentation','final-20min-scenario.md'),'utf8');
 const {entries,slideIndex,questions}=buildReferenceIndex(slides,sources,manuscript);
 const byId=new Map(entries.map(entry=>[entry.id,entry]));
 return <div className="reference-page">
  <a className="reference-skip" href="#reference-main">참조 내용으로 이동</a>
  <header className="reference-topbar"><Link href="/" className="reference-brand">ALEPH<span>.</span> <small>E TEAM</small></Link><Link href="/capstone">발표로 돌아가기</Link></header>
  <main id="reference-main">
   <div className="reference-intro"><p className="reference-eyebrow">SOURCES &amp; QUESTIONS</p><h1>발표의 근거를<br/>원문에서 확인하세요</h1><p>본편 {slides.length}개 화면의 출처 {entries.length}개와 최종 발표 원고의 질문·답변을 모았습니다. 화면의 주장과 실험 조건을 함께 확인할 수 있습니다.</p></div>
   <nav className="reference-jumps" aria-label="참조 페이지 목차"><a href="#slide-index">화면별 근거</a><a href="#bibliography">전체 출처</a><a href="#questions">질문과 답변</a></nav>
   <aside className="reference-scope" aria-label="근거를 읽는 기준"><h2>서로 다른 근거를 구분합니다</h2><ul><li>외부 관측과 기존 서비스는 배경 자료입니다. 우리 시스템의 탐지 성능이나 추가 보호 효과가 아닙니다.</li><li>코드·CI·실험 링크는 기록된 커밋과 실행 조건의 자료입니다. 최신 배포 상태나 전체 LAN의 보호를 보증하지 않습니다.</li><li>Pi 지연, 합성 DNS 응답, 실제 위협 탐지는 서로 다른 측정입니다. 원고와 원시 기록의 날짜·표본·실험 경로를 함께 확인하세요.</li></ul></aside>
   <section id="slide-index" className="reference-section"><div className="reference-section-heading"><p>01 / SLIDE INDEX</p><h2>화면별 근거</h2></div><ol className="reference-slide-list">{slideIndex.map(slide=><li id={`slide-${slide.id}`} key={slide.id}><div className="reference-slide-heading"><span>{String(slide.number).padStart(2,'0')}</span><h3><a href={`/capstone#${slide.id}`}>{slide.title} ↗</a></h3></div>{slide.references.length?<ul>{slide.references.map(id=><li key={id}><a href={`#${id}`}>{byId.get(id)!.label}</a></li>)}</ul>:<p>소개·마무리 화면입니다. 개별 근거는 관련 본문 화면에서 확인하세요.</p>}</li>)}</ol></section>
   <section id="bibliography" className="reference-section"><div className="reference-section-heading"><p>02 / ORIGINAL SOURCES</p><h2>전체 출처 <span>{entries.length}</span></h2></div><p className="reference-section-lead">같은 문서의 중복 인용은 합쳤습니다. 링크는 원문으로 열리며, 아래 설명은 발표에서 사용한 범위입니다.</p><ol className="reference-bibliography">{entries.map((entry,index)=><li id={entry.id} key={entry.id}><span className="reference-number">{String(index+1).padStart(2,'0')}</span><div><h3><a href={entry.url} target="_blank" rel="noopener noreferrer">{entry.label} ↗</a></h3><p className="reference-domain">{new URL(entry.url).hostname}</p>{entry.note&&<p>{entry.note}</p>}<p className="reference-used">{entry.slides.length?<>사용 화면: {entry.slides.map((number,i)=><span key={number}>{i>0?' · ':''}<a href={`#slide-${slides[number-1].id}`}>{String(number).padStart(2,'0')}</a></span>)}</>:'최종 원고의 질문·답변에서 인용'}</p></div></li>)}</ol></section>
   <section id="questions" className="reference-section"><div className="reference-section-heading"><p>03 / QUESTIONS &amp; ANSWERS</p><h2>질문과 답변</h2></div><p className="reference-section-lead">최종 발표 시나리오의 ‘발표자 참고’ 절을 그대로 연결했습니다. 원고가 바뀌면 이 내용도 함께 바뀝니다.</p><div className="reference-questions">{questions.map(question=><details id={question.id} key={question.id}><summary>{question.title}</summary><div>{question.paragraphs.map((paragraph,index)=><p key={index}><InlineText text={paragraph}/></p>)}</div></details>)}</div></section>
   <footer className="reference-footer"><p>SKT ALEPH E조 · Protective DNS</p><Link href="/capstone">발표로 돌아가기</Link><a href="#reference-main">맨 위로 ↑</a></footer>
  </main>
 </div>;
}
