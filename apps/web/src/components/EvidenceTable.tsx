import type {DeckSlide} from "@/lib/deck";
import "./evidence-table.css";

/** Preserve the authored conditions, observations and limits as distinct columns. */
export function EvidenceTable({slide}:{slide:DeckSlide;paused?:boolean}) {
 const reading=slide.reading;
 if(!reading)return null;
 const headingId=`${slide.id}-evidence-table-title`;
 const caveatId=`${slide.id}-evidence-table-caveat`;
 return <section className="evidence-table-panel" aria-labelledby={headingId}>
  <table className="evidence-table" aria-describedby={reading.takeaway?caveatId:undefined}>
   <caption id={headingId}>{reading.title}</caption>
   <thead><tr>{reading.columns.map((column,index)=><th key={index} scope="col">{column}</th>)}</tr></thead>
   <tbody>{reading.rows.map((row,index)=><tr key={index}>{row.map((value,column)=>column===0
    ? <th key={column} scope="row"><span className="evidence-cell-label" aria-hidden="true">{reading.columns[column]}</span>{value}</th>
    : <td key={column}><span className="evidence-cell-label" aria-hidden="true">{reading.columns[column]}</span>{value}</td>)}</tr>)}</tbody>
  </table>
  {reading.takeaway&&<p className="evidence-table-caveat" id={caveatId}>{reading.takeaway}</p>}
  <a className="evidence-table-source" href={reading.source} target="_blank" rel="noopener noreferrer">{reading.sourceLabel||"검증 출처"}</a>
 </section>;
}
