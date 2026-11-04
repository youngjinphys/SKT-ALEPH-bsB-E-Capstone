import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const read=relative=>JSON.parse(fs.readFileSync(path.join(root,relative),"utf8"));
const assert=(ok,message)=>{if(!ok)throw new Error("[deck data] "+message);};

export function validateContent(){
 const index=read("capstone/data/slides.index.json");
 const sequence=read("capstone/data/sequence.json");
 const references=read("capstone/data/sources.json");
 const dir=path.join(root,"capstone/data/slides");
 const listed=fs.readdirSync(dir).filter(name=>/\.json$/.test(name)).sort();
 assert(Array.isArray(index)&&index.length===23,"Keep original records, introduction, thank-you and Pi experiment plan");
 assert(JSON.stringify([...index].sort())===JSON.stringify(listed),"Indexed and on-disk slide sources differ");
 assert(index.every(name=>/^\d{2}-[a-z0-9-]+\.json$/.test(name)),"Invalid source filename");
 const records=index.map(file=>read("capstone/data/slides/"+file));
 const byId=new Map(records.map(s=>[s.id,s]));
 assert(byId.size===23,"Duplicate source slide IDs");
 const schema=read("capstone/data/slide.schema.json");
 const presentationFields=schema?.properties?.presentation?.properties;
 assert(presentationFields&&typeof presentationFields==="object","Missing presentation JSON schema");
 assert(references&&typeof references==="object"&&!Array.isArray(references),"Invalid citation registry");
 for(const [name,source] of Object.entries(references)){
  assert(typeof source?.label==="string"&&source.label.length>2,"Missing source label: "+name);
  assert(typeof source?.url==="string"&&URL.canParse(source.url)&&new URL(source.url).protocol==="https:","Invalid source URL: "+name);
 }
 for(const entry of records){
  assert(typeof entry.id==="string"&&/^[a-z][a-z0-9-]*$/.test(entry.id),"Invalid ID");
  assert(typeof entry.title==="string"&&entry.title.length>0,"Missing title");
  assert(typeof entry.subtitle==="string","Subtitle must be a string (empty is allowed)");
  assert(typeof entry.notes==="string"&&entry.notes.length>=10,"Missing presenter notes: "+entry.id);
  assert(Array.isArray(entry.sources)&&entry.sources.every(key=>Object.hasOwn(references,key)),"Unknown citation: "+entry.id);
  assert(Array.isArray(entry.points)&&entry.points.every(p=>typeof p?.title==="string"&&typeof p?.body==="string"),"Bad points: "+entry.id);
  if(entry.presentation){
   for(const [name,value] of Object.entries(entry.presentation)){
    assert(Object.hasOwn(presentationFields,name),"Undeclared field: "+entry.id+"."+name);
    const rule=presentationFields[name];
    if(rule.type==="string")assert(typeof value==="string"&&value.length>=(rule.minLength||0),"Invalid presentation field: "+entry.id+"."+name);
   }
   if(entry.presentation.points!==undefined)
    assert(Array.isArray(entry.presentation.points)&&entry.presentation.points.every(p=>typeof p?.title==="string"&&typeof p?.body==="string"),"Bad presentation points");
  }
  if(entry.visual){
   assert(["independent-trends","comparison-bars","cname-chain","topology","planet","dns-policy","policy-lifecycle","protocol-boundary","governance","evidence","source-directory"].includes(entry.visual.type),"Bad visualization: "+entry.id);
   if(entry.visual.type!=="topology"&&entry.visual.type!=="independent-trends")assert(Object.hasOwn(references,entry.visual.sourceKey),"Missing visual source");
   if(entry.visual.type==="topology")assert(["lab","proposal"].includes(entry.visual.mode),"Bad topology mode");
   if(entry.visual.type==="comparison-bars")assert(entry.visual.measurements?.length>0&&entry.visual.measurements.every(m=>Number.isFinite(m.value)&&m.value>=0),"Bad chart data");
   if(entry.visual.type==="independent-trends"){
    for(const name of ["left","right"]){
     const series=entry.visual[name];
     assert(series&&Object.hasOwn(references,series.sourceKey),"Independent-series source missing: "+name);
     if(series.additionalSourceKeys!==undefined)
      assert(Array.isArray(series.additionalSourceKeys)&&new Set(series.additionalSourceKeys).size===series.additionalSourceKeys.length&&series.additionalSourceKeys.every(key=>typeof key==="string"&&Object.hasOwn(references,key)),"Unknown or duplicate additional independent-series source: "+entry.id+"."+name);
     if(typeof series.context==="string"){
      assert(series.context.length>=10&&!Object.hasOwn(series,"values")&&!Object.hasOwn(series,"max")&&!Object.hasOwn(series,"unit")&&!Object.hasOwn(series,"periods"),"Qualitative context must remain separate from numerical series: "+entry.id);
      if(series.statistic!==undefined){
       const stat=series.statistic;
       assert(stat&&typeof stat==="object"&&!Array.isArray(stat)&&Object.keys(stat).sort().join(",")==="period,unit,value"&&Number.isSafeInteger(stat.value)&&stat.value>=0&&typeof stat.unit==="string"&&stat.unit.length>0&&typeof stat.period==="string"&&stat.period.length>0,"Invalid dated statistic: "+entry.id);
      }
     }else{
      assert(!Object.hasOwn(series,"statistic"),"Trend series cannot also declare a standalone statistic: "+entry.id);
      assert(Number.isFinite(series.max)&&series.max>0&&typeof series.unit==="string", "Missing independent scale: "+entry.id);
      assert(series.periods?.length>=2&&series.periods.length===series.values?.length&&series.values.every(v=>Number.isFinite(v)&&v>=0&&v<=series.max),"Bad independent-series values: "+entry.id);
     }
    }
   }
   if(entry.visual.type==="cname-chain")assert(entry.visual.nodes?.length===3&&entry.visual.links?.length===2,"Invalid CNAME visual");
  }
  if(entry.reading){
   assert(entry.reading.columns?.length===3&&entry.reading.rows?.every(row=>row.length===3),"Bad evidence table: "+entry.id);
   assert(typeof entry.reading.source==="string"&&URL.canParse(entry.reading.source)&&new URL(entry.reading.source).protocol==="https:","Bad evidence URL: "+entry.id);
  }
 }
 assert(sequence.mainSlideCount===14,"Expected 14 presentation slides");
 assert(Array.isArray(sequence.slides)&&sequence.slides.length===15,"Expected 14 main slides and one references appendix");
 assert(Array.isArray(sequence.archived)&&sequence.archived.length===8,"Expected 8 archived originals");
 const presented=new Set(sequence.slides.map(s=>s.id));
 const archived=new Set(sequence.archived);
 assert(presented.size===15&&archived.size===8,"Duplicate presented or archived slides");
 for(const id of presented)assert(byId.has(id)&&!archived.has(id),"Unknown/overlapping presented slide: "+id);
 for(const id of archived)assert(byId.has(id),"Unknown archived original: "+id);
 assert(presented.size+archived.size===records.length,"An authored source is missing from the deck and archive");
 for(const s of sequence.slides)
  assert(Number.isInteger(s.seconds)&&s.seconds>=0&&!Object.hasOwn(s,"compressedSeconds"),"Single-plan slide duration required");
 const reference=byId.get("sources");
 assert(sequence.slides.at(-1).id==="sources"&&reference.seconds===0,"References must follow the unchanged main presentation");
 const grouped=reference.referenceGroups.flatMap(group=>group.keys);
 assert(grouped.length===reference.sources.length&&new Set(grouped).size===grouped.length&&grouped.every(key=>reference.sources.includes(key)),"Reference groups must expose every source exactly once");
 for(const {id} of sequence.slides)for(const key of byId.get(id).sources)
  assert(grouped.includes(key),"Reference slide omits active citation: "+id+"/"+key);
 const seconds=sequence.slides.reduce((t,s)=>t+s.seconds,0);
 assert(seconds===1200,"20-minute presentation duration must total 1200 seconds");
 // Keep the written presenter script in the same order and 20-minute timeline.
 const script=fs.readFileSync(path.join(root,"docs/presentation/final-20min-scenario.md"),"utf8");
 const sections=[...script.matchAll(/^## (?:표지\.|\d{2}\.) [^\n]* — (\d{2}:\d{2})–(\d{2}:\d{2})\n\n\*상태: [^\n]* · 화면 id: \x60([a-z0-9-]+)\x60\*/gm)];
 assert(sections.length===sequence.slides.length,"Presenter script slide count differs from sequence");
 const clock=value=>String(Math.floor(value/60)).padStart(2,"0")+":"+String(value%60).padStart(2,"0");
 let elapsed=0;
 for(const [i,entry] of sequence.slides.entries()){
  const [,start,end,id]=sections[i];
  const authored=byId.get(entry.id);
  const block=script.slice(sections[i].index,sections[i+1]?.index??script.length);
  assert(authored.seconds===entry.seconds,"Authored slide timing differs from sequence: "+entry.id);
  assert(block.includes(authored.notes),"Presenter script notes differ from authored source: "+entry.id);
  assert(block.startsWith(`## ${String(i+1).padStart(2,"0")}. ${(authored.presentation?.title||authored.title).replaceAll("\n"," ")} — `),"Presenter script title/number differs from slide: "+entry.id);
  assert(id===entry.id&&start===clock(elapsed)&&end===clock(elapsed+entry.seconds),"Presenter script out of sync at "+entry.id);
  elapsed+=entry.seconds;
 }

 const landing=read("capstone/data/landing.json");
 assert(landing.hero?.intro&&landing.hero.emphasis&&landing.hero.lead?.length>=2,"Bad landing intro");
 assert(landing.trail?.length===4&&landing.layers?.length===3,"Broken landing structure");
 for(const target of [...landing.trail,...landing.layers])
  assert(presented.has(target.hash),"Landing link targets a hidden slide: "+target.hash);
 const dia=read("capstone/data/diagrams.json");
 assert(Object.keys(dia.dnsCases).sort().join(",")==="ALLOW,BLOCK,WARN","Missing DNS policy response cases");
 for(const mode of ["lab","proposal"])
  assert(dia.policyPipeline?.[mode]?.length===4&&dia.policyPipeline[mode].every(x=>x.label&&x.owner&&x.detail&&x.artifact),"Missing four-stage policy flow: "+mode);
 assert(dia.policyVerdicts?.length===4&&dia.policyVerdicts.map(x=>x.code).join(",")==="BLOCK,WARN,ALLOW,UNKNOWN","Invalid 4-state decision matrix");
 assert(dia.feedSnapshot?.length===3&&dia.feedSnapshot[0].value==="269"&&dia.feedSnapshot[1].value==="1"&&dia.feedSnapshot[2].value==="2","Missing labelled team run snapshot");
 assert(Object.keys(dia.dnsFlow||{}).sort().join(",")==="allow,block","DNS diagram must contain only normal and blocked lookup scenarios");
 return {authored:records.length,main:sequence.mainSlideCount,archived:sequence.archived.length,
         seconds,sources:Object.keys(references).length};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))
 console.log("Validated presentation:",validateContent());
