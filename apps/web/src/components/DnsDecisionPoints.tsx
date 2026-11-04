import {useId} from "react";
import type {Point} from "@/lib/deck";
import styles from "./dns-decision-points.module.css";

export function DnsDecisionPoints({points}:{points:Point[]}){
 const id=useId();
 const [query,condition,blocked,forwarded]=points;
 return <>
  <article className="slide-point"><span className="point-index">01</span><div><h2>{query.title}</h2><p>{query.body}</p></div></article>
  <section className={styles.decision} aria-labelledby={`${id}-question`} aria-describedby={`${id}-exclusive`} data-dns-decision="exclusive">
   <div className={styles.condition}>
    <span className={styles.step}>02 · 정책 대조</span>
    <h2 id={`${id}-question`}>{condition.title}</h2>
    <p>{condition.body}</p>
   </div>
   <ul className={styles.branches} aria-label="정책 일치 여부에 따른 두 갈래">
    {[{point:blocked,match:"yes",label:"예 · 일치"},{point:forwarded,match:"no",label:"아니오 · 불일치"}].map(({point,match,label})=><li key={match} className={styles.branch} data-policy-match={match}>
     <span className={styles.answer}>{label}</span>
     <h3>{point.title}</h3>
     <p>{point.body}</p>
    </li>)}
   </ul>
   <p id={`${id}-exclusive`} className={styles.exclusive}><strong>OR</strong> 한 질의에는 둘 중 하나만 실행</p>
  </section>
 </>;
}
