"use client";
import {useEffect,useRef,useState} from 'react';
import {createClapController} from './restored/clap.mjs';
import './clap-control.css';
const messages:Record<string,string>={calibrating:'주변 소리를 측정합니다. 잠시 조용히 기다려 주세요.',listening:'두 번 박수를 기다립니다.',first:'첫 박수 감지 · 한 번 더 쳐 주세요.',advance:'두 박수 감지 · 다음 장으로 이동합니다.',cooldown:'중복 넘김 방지 중입니다.'};
export function ClapControl({onAdvance,onActiveChange,stopToken}:{onAdvance:()=>void;onActiveChange:(active:boolean)=>void;stopToken:number}){
 const advance=useRef(onAdvance);advance.current=onAdvance;
 const control=useRef<ReturnType<typeof createClapController>|null>(null);
 const mounted=useRef(false);
 const [active,setActive]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('선택 기능: 두 번 박수로 다음 장.');
 const [sensitivity,setSensitivity]=useState(3),[level,setLevel]=useState(0);
 useEffect(()=>{
  mounted.current=true;
  control.current=createClapController({onAdvance:()=>advance.current(),onEvent:event=>{
   if(!mounted.current)return;
   if(typeof event.level==='number')setLevel(Math.max(0,Math.min(100,event.level)));
   if(messages[event.type])setMessage(messages[event.type]);
   if(['denied','unsupported','audio-error'].includes(event.type)){setMessage('마이크를 사용할 수 없습니다. 목차에서 장을 선택해 발표를 계속할 수 있습니다.');setActive(false);setLevel(0);}
  }});
  setSensitivity(control.current.getSensitivity());
  const leave=()=>{control.current?.stop();setActive(false);setLevel(0);setMessage('마이크를 껐습니다. 다시 켜려면 버튼을 누르세요.');};
  const stop=()=>{if(document.hidden)leave();};
  document.addEventListener('visibilitychange',stop);window.addEventListener('pagehide',leave);
  return()=>{mounted.current=false;control.current?.stop();control.current=null;document.removeEventListener('visibilitychange',stop);window.removeEventListener('pagehide',leave);};
 },[]);
 useEffect(()=>{onActiveChange(active);},[active,onActiveChange]);
 useEffect(()=>{control.current?.stop();setActive(false);setLevel(0);},[stopToken]);
 async function toggle(){
  if(active){control.current?.stop();setActive(false);setLevel(0);setMessage('마이크를 껐습니다.');return;}
  setBusy(true);const ok=await control.current?.start();
  if(!mounted.current)return;
  setActive(Boolean(ok));setBusy(false);
 }
 function changeSensitivity(value:number){control.current?.setSensitivity(value);setSensitivity(control.current?.getSensitivity()??value);}
 return <div className="clap-control"><button type="button" disabled={busy} aria-pressed={active} onClick={()=>void toggle()}>{busy?'마이크 연결 중':active?'박수 넘김 끄기':'박수 넘김 켜기'}</button>
  <div className="clap-settings"><label htmlFor="clap-sensitivity">감도 <span className="clap-sensitivity-value">{sensitivity} / 5</span></label><input id="clap-sensitivity" type="range" min="1" max="5" step="1" value={sensitivity} onChange={event=>changeSensitivity(Number(event.target.value))} aria-describedby="clap-sensitivity-help"/><small id="clap-sensitivity-help">1 둔감 · 5 민감 · 기본 3</small>
  <label htmlFor="clap-signal">입력 신호</label><meter id="clap-signal" min="0" max="100" value={active?level:0} aria-describedby="clap-signal-help"/><small id="clap-signal-help">마이크 입력의 상대 신호량</small></div>
  <p role="status">{message}</p><p className="clap-privacy">켜기를 누를 때만 마이크를 요청합니다. 오디오는 녹음·저장·전송하지 않으며, 숨긴 탭에서는 중지합니다.</p>
 </div>;
}
