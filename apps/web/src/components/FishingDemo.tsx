"use client";
import Link from "next/link";
import {useEffect,useRef,useState} from "react";
type DialogType="consult"|"explainer"|"evidence"|null;
const staff=[
 {name:"조*정",field:"금융사기 · 피해사실 검토",image:"/assets/jo-yujeong.webp"},
 {name:"김*양",field:"디지털 자산 · 기록 추적",image:"/assets/kim-taeyang.webp"},
 {name:"김*영",field:"사칭 분쟁 · 소비자 보호",image:"/assets/kim-dayoung.webp"},
 {name:"염*진",field:"사이버 포렌식 · 위협 분석",image:"/assets/yeom-youngjin.webp"},
];
const dialogText={
 consult:{title:"사건 검토 시뮬레이션",desc:"교육용으로 구성한 가상 사건 검토 화면입니다. 이 페이지는 연락처·신분증·계좌·금전·암호를 수집하거나 전송하지 않습니다.",items:["공식 기관 등록과 실제 소속을 별도 경로로 확인","선납 수수료·환급 보장·긴급 송금 요구를 위험 신호로 취급","외부 메신저 전환 시 상대방 신원을 다시 검증"]},
 explainer:{title:"공식 경로에서 소속과 자격을 확인하세요",desc:"태양썬은 SKT ALEPH E조가 만든 교육 전용 가상 사이트입니다. 사이트의 법률 서비스·전문가·기관 표현은 합성 실습 설정입니다.",items:["HTTPS는 통신 구간을 암호화합니다. 사업자 자격은 공식 등록 자료로 별도 확인하세요.","상담·수임·회수 사례와 인물은 교육용으로 구성되었습니다.","입력·결제 절차 없이 합성 자료만 열람합니다."]},
 evidence:{title:"의심 신호 검증 순서",desc:"기관의 적법성과 진위는 공식 등록 자료와 독립적인 연락 경로로 확인하세요.",items:["도메인 등록과 소속 기관의 공식 출처를 교차 확인","대가성 선입금·추가 수수료·회수 보장 주장 검증","링크의 실제 목적지, 브라우저 경고, 보호 DNS 응답을 구분"]},
};
export function FishingDemo(){
 const [approved,setApproved]=useState(false);
 const [dialog,setDialog]=useState<DialogType>(null);
 const prev=useRef<HTMLElement|null>(null);
 const modalRef=useRef<HTMLDialogElement>(null);
 const mainRef=useRef<HTMLElement>(null);
 useEffect(()=>{if(approved)mainRef.current?.focus();},[approved]);
 useEffect(()=>{
  const modal=modalRef.current;
  if(dialog && modal && !modal.open)modal.showModal();
 },[dialog]);
 function open(kind:NonNullable<DialogType>){prev.current=document.activeElement as HTMLElement;setDialog(kind)}
 function close(){modalRef.current?.close();setDialog(null)}
 return <div className="fixture-page">
  <a href="#fixture-main" className="skip-link">본문으로 이동</a>
  <div className="fixture-banner" role="note"><strong>EDUCATIONAL SIMULATION</strong> · SKT ALEPH E조 · 교육용 가상 법률 사이트입니다. <button type="button" onClick={()=>open("explainer")}>실습 안내</button></div>
  {!approved?<main id="fixture-main" className="fixture-gate" tabIndex={-1}><div className="fixture-gate-art"><img src="/assets/taeyangsun-emblem.webp" width="140" height="140" alt="가상 법무법인 태양썬 로고"/></div><h1>가상 사이트 보안 실습</h1><p>다음 화면은 법률 사이트의 외형을 재현한 <strong>교육용 모의 페이지</strong>입니다. 모든 상담·사례·인물은 합성 설정이며, 개인정보·결제정보를 받지 않으며 실제 상담은 제공하지 않습니다.</p><div className="gate-controls"><button className="button-primary" onClick={()=>setApproved(true)}>실습 시작</button><Link className="button-outline" href="/">홈으로 돌아가기</Link></div></main>:
   <><header className="fixture-nav"><Link href="/fishing" className="fixture-brand"><img src="/assets/taeyangsun-emblem.webp" alt="" width="48" height="48"/><strong>법무법인 태양썬 <small>FICTIONAL LEGAL PRACTICE</small></strong></Link><nav aria-label="실습 페이지 메뉴"><a href="#expertise">업무 분야</a><a href="#approach">운영 원칙</a><a href="#people">가상 구성원</a><button onClick={()=>open("consult")}>사건 검토 신청 ↗</button></nav></header>
   <main ref={mainRef} id="fixture-main" tabIndex={-1}><section className="fixture-hero"><img className="fixture-bg" src="/assets/seoul-sunset-hero.webp" alt="" width="1672" height="941"/><div className="fixture-hero-copy"><p>THE SAFER TOMORROW · A SIMULATED BRAND</p><h1>잃어버린 일상에,<br/><em>다시 해가 떠오를 수 있도록.</em></h1><p>갑작스러운 금융사기와 디지털 피해.<br/>이럴 때 더욱 정확한 근거 확인이 필요합니다.</p><button className="fixture-cta" onClick={()=>open("consult")}>가상 사건 검토 ↗</button><p className="fixture-small">교육 목적으로 구성한 합성 실습 사이트입니다.</p></div></section>
    <section className="fixture-trust"><strong>01 사실 확인</strong><strong>02 증거 보전</strong><strong>03 명확한 절차</strong></section>
    <section className="fixture-section" id="expertise"><span>01 / PRACTICE AREAS</span><h2>복잡한 문제일수록,<br/>확인할 순서를 분명하게.</h2><div className="fixture-columns"><article><strong>금융 사칭과 피싱</strong><p>실제 기관 명의 도용 여부를 공식 출처와 대조합니다.</p></article><article><strong>디지털 자산 피해</strong><p>손실 복구 보장 문구보다 검증 가능한 기록을 우선합니다.</p></article><article><strong>사이버 포렌식</strong><p>신뢰 가능한 진단은 재현 가능한 증거에서 시작합니다.</p></article></div></section>
    <section className="fixture-section fixture-dark" id="approach"><span>02 / VERIFICATION FIRST</span><h2>보이는 것과 입증된 것을 구분합니다.</h2><p>소속·자격·도메인·송금 요청은 공식 자료와 별도 경로로 교차 검증해야 합니다. HTTPS 연결 확인과 함께 실제 기관·담당자의 신원 확인이 필요합니다.</p><button type="button" className="button-outline" onClick={()=>open("evidence")}>보안 검증 기준 보기 ↗</button></section>
    <section className="fixture-section" id="people"><span>03 / FICTIONAL TEAM</span><h2>가상의 구성원</h2><p>팀원 이름을 차용한 교육용 가상 프로필입니다. 소개된 법률 전문가 역할은 실습을 위한 설정입니다.</p><div className="fixture-people">{staff.map(person=><article key={person.name}><img src={person.image} alt="" width="230" height="240" loading="lazy"/><h3>{person.name}</h3><p>{person.field}</p><small>FICTIONAL PROFILE</small></article>)}</div></section>
    <section className="fixture-section fixture-lesson"><h2>당신은 무엇을 확인하시겠습니까?</h2><p>가짜 사이트를 직접 만들면, 사용자와 탐지기가 놓치는 신호를 더 정확히 이해할 수 있습니다.</p><button onClick={()=>open("evidence")} className="button-primary">검증 기준 확인</button><Link href="/capstone">Protective DNS 발표로 이어가기 ↗</Link></section>
   </main><footer className="fixture-footer">SKT ALEPH · EDUCATIONAL FIXTURE · NO COLLECTION <Link href="/">돌아가기 ↗</Link></footer></>}
   <dialog ref={modalRef} className="dialog-panel" aria-labelledby="fixture-dialog-title"
    onClose={()=>{setDialog(null);requestAnimationFrame(()=>prev.current?.focus())}}
    onClick={event=>{
     if(event.target!==event.currentTarget)return;
     const {left,right,top,bottom}=event.currentTarget.getBoundingClientRect();
     if(event.clientX<left||event.clientX>right||event.clientY<top||event.clientY>bottom)close();
    }}>
    {dialog && <><button className="dialog-close" type="button" aria-label="안내 닫기" onClick={close}>×</button><span>SAFETY NOTICE</span><h2 id="fixture-dialog-title">{dialogText[dialog].title}</h2><p>{dialogText[dialog].desc}</p><ul>{dialogText[dialog].items.map(item=><li key={item}>{item}</li>)}</ul><button className="button-primary" onClick={close}>확인</button></>}
   </dialog>
 </div>;
}
