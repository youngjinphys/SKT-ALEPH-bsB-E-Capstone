import './diagram-text.css';

export function DiagramText({value,values,paused=false}:{value:string;values:readonly string[];paused?:boolean}){
 const labels=[...new Set([...values,value])];
 return <span className="diagram-text-swap" data-motion-paused={paused}>
  {labels.map(label=><span className="diagram-text-layer" key={label} aria-hidden={label!==value}>{label}</span>)}
 </span>;
}
