import './diagram-text.css';

/** Keep authored labels mounted so text can crossfade without moving the diagram.
 * Inactive copies reserve layout only; assistive technology sees the current text.
 * CSS owns interruption/reversal, so replay and rapid selection need no timers.
 */
export function DiagramText({value,values,paused=false}:{value:string;values:readonly string[];paused?:boolean}){
 const labels=[...new Set([...values,value])];
 return <span className="diagram-text-swap" data-motion-paused={paused}>
  {labels.map(label=><span className="diagram-text-layer" key={label} aria-hidden={label!==value}>{label}</span>)}
 </span>;
}
