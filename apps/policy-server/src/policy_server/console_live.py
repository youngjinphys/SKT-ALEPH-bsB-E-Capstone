"""Serialized, bounded near-real-time polling; no permanent server connection."""
JS = r'''
function createLivePoller({poll,eligible,onState,onError,setTimer,clearTimer,period=10000}) {
  let timer=null,busy=false,running=false,epoch=0,failures=0;
  function clear(){if(timer!==null){clearTimer(timer);timer=null;}}
  function schedule(delay){clear();if(running&&eligible()&&!busy)timer=setTimer(tick,delay);}
  async function tick(){
    timer=null;if(!running||!eligible()||busy)return;
    busy=true;const attempt=epoch;onState('fetching');
    try{await poll();if(attempt===epoch&&running){failures=0;onState('live');}}
    catch(error){if(!error.stale&&attempt===epoch&&running){failures=Math.min(failures+1,3);onState('error');onError(error);}}
    finally{busy=false;if(running&&attempt===epoch)schedule(Math.min(60000,period*2**failures));else if(running)schedule(period);}
  }
  return {
    resume(){if(!eligible()){clear();return;}if(!running){running=true;epoch++;failures=0;}if(!busy)schedule(period);},
    stop(){running=false;epoch++;clear();},
    refresh(){if(!eligible())return;running=true;clear();if(!busy)return tick();},
    inspect(){return {busy,running,failures,timer:timer!==null};}
  };
}
// Browser integration: preserve form edits; only read-only views are polled.
function obsLiveState(state){
  const pill=$('obs-live');pill.dataset.state=state;
  showText('obs-live',({fetching:'수신 상태 확인 중',live:'10초 자동 갱신',error:'연결 지연 · 재시도',paused:'자동 갱신 일시정지',offline:'오프라인 · 마지막 관측',hidden:'백그라운드 대기',locked:'인증 후 조회'})[state]||'대기');
}
const opsLive=createLivePoller({
  eligible:()=>!!token&&!obsPaused&&!document.hidden&&navigator.onLine!==false&&['overview','deployment'].includes(currentView),
  poll:async()=>{
    if(expireIdleSession())return;
    const view=currentView,session=sessionEpoch,epoch=viewEpoch;
    const pending=refreshView(view),read=viewRequestEpochs[view],analytics=obsRequest;
    const current=()=>!!token&&view===currentView&&session===sessionEpoch&&epoch===viewEpoch&&
      read===viewRequestEpochs[view]&&(view!=='overview'||analytics===obsRequest);
    try{const result=await pending;if(!current())throw staleRequest();if(result?.partial)throw Error('일부 상태 조회 실패');}
    catch(error){if(!current())throw staleRequest();throw error;}
  },
  onState:obsLiveState,
  onError:error=>{if(!error.stale&&token){document.querySelector('.verification-strip').dataset.state='error';showText('verification-status','조회 실패 · 미확인 항목은 현재 상태로 표시하지 않습니다.');}},
  setTimer:(fn,ms)=>window.setTimeout(fn,ms),clearTimer:id=>window.clearTimeout(id)
});
function syncOpsLive(){
  if(!token){opsLive.stop();obsLiveState('locked');return;}
  if(obsPaused){opsLive.stop();obsLiveState('paused');return;}
  if(navigator.onLine===false){opsLive.stop();obsLiveState('offline');return;}
  if(document.hidden){opsLive.stop();obsLiveState('hidden');return;}
  if(!['overview','deployment'].includes(currentView)){opsLive.stop();return;}
  obsLiveState('live');opsLive.resume();
}
$('obs-pause').addEventListener('click',()=>{obsPaused=!obsPaused;$('obs-pause').setAttribute('aria-pressed',String(obsPaused));$('obs-pause').textContent=obsPaused?'자동 갱신 재개':'자동 갱신 일시정지';syncOpsLive();});
document.addEventListener('ops:poll-view',()=>{opsLive.stop();syncOpsLive();});
document.addEventListener('ops:locked',()=>{opsLive.stop();obsPaused=false;$('obs-pause').setAttribute('aria-pressed','false');$('obs-pause').textContent='자동 갱신 일시정지';obsLiveState('locked');});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&token)expireIdleSession();syncOpsLive();});
window.addEventListener('online',syncOpsLive);window.addEventListener('offline',syncOpsLive);
window.setInterval(()=>{if(token&&!document.hidden){obsTick();if(obsLastFetch&&Date.now()-obsLastFetch>45000&&!obsPaused&&navigator.onLine!==false)obsLiveState('error');}},1000);
'''
