/** Styling tokens only: concatenating these parts always recovers the input. */
export function terminalResultParts(text:string){
 return text.split(/(\bNOERROR\b|\bNXDOMAIN\b|\bANSWER: \d+)/g).map(text=>({
  text,
  tone:text==="NXDOMAIN"||text==="ANSWER: 0"?"negative" as const:
   text==="NOERROR"||/^ANSWER: [1-9]\d*$/.test(text)?"success" as const:null
 }));
}
