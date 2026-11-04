// Sites authenticates on the server. No identity or access credential is accepted
// from browser storage; only the verified /api/ops/session can unlock controls.
let cloudLoggingOut=false;
async function cloudConnect(){
  if(cloudLoggingOut)return;
  lock();
  const attempt=sessionEpoch;
  const current=()=>attempt===sessionEpoch&&!cloudLoggingOut;
  showText('cloud-login-message','ChatGPT 로그인과 DNS 운영자 권한을 확인합니다.');
  try{
    token='sites-session';
    const identity=await api('/api/ops/session');
    if(!current())return;
    unlock();
    showText('connection-text','운영자 · '+identity.email);
  }catch(error){
    if(!current()||error.stale)return;
    lock();
    showText('cloud-login-message',error.message||'관제 서버 연결 실패. ChatGPT로 로그인한 뒤 다시 연결하세요.');
  }
}
$('cloud-logout').addEventListener('click',()=>{
  cloudLoggingOut=true;
  lock();
});
