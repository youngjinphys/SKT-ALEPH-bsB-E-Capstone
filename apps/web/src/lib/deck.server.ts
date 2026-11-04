/** Server-only JSON registry; the published fourteen-slide sequence excludes archived sources. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { DeckSlide, SourceRegistry } from "./deck";

const directory = join(process.cwd(), "capstone", "data");
function readJson<T>(location: string): T {
 return JSON.parse(readFileSync(join(directory,location),"utf8")) as T;
}
type Sequence={
 mainSlideCount:number;
 slides:{id:string;seconds:number}[];
 archived:string[];
};
const index=readJson<string[]>("slides.index.json");
const sequence=readJson<Sequence>("sequence.json");
export const sources=readJson<SourceRegistry>("sources.json");
export const mainSlideCount=sequence.mainSlideCount;
const records=index.map(filename=>{
 if(!/^\d{2}-[a-z0-9-]+\.json$/.test(filename))throw Error("Invalid slide filename");
 return readJson<DeckSlide>(join("slides",filename));
});
const byId=new Map(records.map(item=>[item.id,item]));
if(byId.size!==records.length)throw Error("Duplicate source slide ID");
const ids=new Set(sequence.slides.map(slide=>slide.id));
if(ids.size!==14||sequence.mainSlideCount!==14||sequence.slides.length!==14)throw Error("Expected 14 presentation slides");
const archived=new Set(sequence.archived);
if(archived.size!==9||[...archived].some(id=>ids.has(id)||!byId.has(id))||ids.size+archived.size!==records.length)
 throw Error("Archived records must be retained but excluded from the published deck");
export const slides:DeckSlide[]=sequence.slides.map(({id,seconds})=>{
 const entry=byId.get(id);
 if(!entry)throw Error("Unknown authored slide: "+id);
 if(!Number.isInteger(seconds)||seconds<0)
  throw Error("Invalid slide timing");
 for(const key of entry.sources)if(!sources[key])throw Error("Unregistered source: "+key);
 return {...entry,seconds,
  title:entry.presentation?.title||entry.title,
  subtitle:entry.presentation?.subtitle??entry.subtitle,
  points:entry.presentation?.points||entry.points,
  sources:entry.sources,
  notes:entry.notes,
 };
});
if(slides.reduce((sum,s)=>sum+s.seconds,0)!==1200)
 throw Error("The single 20-minute presentation plan is inconsistent");
export const chapters=[...new Set(slides.map(s=>s.chapter))];
