import type {DeckSlide,SourceRegistry} from './deck';

export type ReferenceEntry={id:string;label:string;url:string;note?:string;slides:number[]};
export type ReferenceQuestion={id:string;title:string;paragraphs:string[]};
const linkPattern=/\[([^\]\n]+)\]\((https:\/\/[^\s)]+)\)/g;
export function markdownLinks(text:string){
 return [...text.matchAll(linkPattern)].map(([,label,url])=>({label,url}));
}
function documentUrl(raw:string){
 const url=new URL(raw);
 if(url.protocol!=='https:')throw Error('Reference URLs must use HTTPS');
 url.hash='';
 return url.href;
}
export function buildReferenceIndex(slides:readonly DeckSlide[],sources:SourceRegistry,manuscript:string){
 const marker='# 발표자 참고 · 예상 질문과 답변';
 const start=manuscript.indexOf(marker);
 if(start<0)throw Error('Final manuscript Q&A section is missing');
 const appendix=manuscript.slice(start+marker.length);
 const questions:ReferenceQuestion[]=appendix.split(/^## /m).slice(1).map((section,index)=>{
  const newline=section.indexOf('\n');
  if(newline<0)throw Error('Malformed manuscript question');
  return {id:`question-${index+1}`,title:section.slice(0,newline).trim(),paragraphs:section.slice(newline+1).trim().split(/\n\s*\n/).filter(Boolean)};
 });
 if(!questions.length)throw Error('Final manuscript Q&A is empty');
 const entries:ReferenceEntry[]=[];
 const byUrl=new Map<string,ReferenceEntry>();
 const add=(source:{label:string;url:string;note?:string},slide?:number)=>{
  const key=documentUrl(source.url);
  let entry=byUrl.get(key);
  if(!entry){entry={id:`reference-${entries.length+1}`,...source,slides:[]};entries.push(entry);byUrl.set(key,entry);}
  if(slide!==undefined&&!entry.slides.includes(slide))entry.slides.push(slide);
  return entry;
 };
 const slideIndex=slides.map((slide,index)=>({id:slide.id,number:index+1,title:slide.title.replaceAll('\n',' '),references:[...new Set(slide.sources.map(key=>{
  const source=sources[key];if(!source)throw Error(`Missing reference: ${key}`);
  return add(source,index+1).id;
 }))]}));
 for(const source of markdownLinks(appendix))add(source);
 return {entries,slideIndex,questions};
}
