// Temporary test login is server-verified; no PIN/session is stored in JS storage.
let cloudPinLoginPending=null;
async function cloudPinStatus(current){
  try{
    const response=await fetch('/api/ops/test-auth',{credentials:'same-origin',cache:'no-store'});
    const state=response.ok?await response.json():{};
    if(!current())return false;
    $('cloud-pin-form').hidden=state.enabled!==true;
    $('cloud-extra-row').hidden=state.additionalCodeRequired!==true;
    $('cloud-access-code').required=state.additionalCodeRequired===true;
    return state.authenticated===true;
  }catch{return false;}
}
$('cloud-pin-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if(cloudPinLoginPending||cloudLoggingOut)return;
  lock();
  const epoch=sessionEpoch;
  const pin=$('cloud-pin').value,access_code=$('cloud-access-code').value;
  $('cloud-pin').value='';$('cloud-access-code').value='';
  $('cloud-pin-submit').disabled=true;
  showText('cloud-pin-message','테스트 PIN을 확인합니다.');
  cloudPinLoginPending=(async()=>{
    try{
      const response=await fetch('/api/ops/test-auth',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'login',pin,access_code})});
      const result=await response.json();
      if(epoch!==sessionEpoch||cloudLoggingOut)return;
      if(!response.ok)throw Error(result.error||'테스트 로그인 실패');
      token='cookie-session';
      const who=await api('/api/ops/session');
      if(epoch!==sessionEpoch||cloudLoggingOut)return;
      unlock();showText('connection-text','테스트 운영자 · 15분 세션');
    }catch(error){
      if(epoch===sessionEpoch&&!cloudLoggingOut){lock();showText('cloud-pin-message',error.message||'로그인 결과를 확인하지 못했습니다. 다시 연결해 주세요.');}
    }
  })();
  try{await cloudPinLoginPending;}finally{cloudPinLoginPending=null;$('cloud-pin-submit').disabled=false;}
});
