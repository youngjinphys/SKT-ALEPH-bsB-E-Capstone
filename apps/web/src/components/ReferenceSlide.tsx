import type {DeckSlide,SourceRegistry} from '@/lib/deck';
import './reference-slide.css';

/** The bibliography is part of the deck, not a separate route or shortcut. */
export function ReferenceSlide({slide,sources}:{slide:DeckSlide;sources:SourceRegistry}){
 const groups=slide.referenceGroups||[{title:'전체 출처',keys:slide.sources}];
 return <section className="reference-slide" aria-label="발표 참고문헌">
  <p className="reference-slide-scope">외부 관측·프로토콜·자체 실험을 구분합니다. 기록된 날짜와 조건은 각 원문에서 확인하세요.</p>
  <div className="reference-slide-groups">{groups.map(group=><details key={group.title} className="reference-slide-group" name={`references-${slide.id}`}>
   <summary><span>{group.title}</span><span className="reference-slide-count">{group.keys.length}개 원문</span></summary>
   <ul>{group.keys.map(key=>{const source=sources[key];return <li key={key}><a href={source.url} target="_blank" rel="noopener noreferrer"><span>{source.label} ↗</span><small>{new URL(source.url).hostname}</small></a>{source.note&&<p>{source.note}</p>}</li>;})}</ul>
  </details>)}</div>
  <p className="reference-slide-footnote">총 {slide.sources.length}개 · 본편과 최종 발표 원고의 인용 자료</p>
 </section>;
}
