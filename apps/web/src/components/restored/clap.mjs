import {DoubleClapDetector, extractAudioFeatures} from './clap-core.mjs';

/** Opt-in local audio analysis. Never records, persists, uploads or plays audio. */
export function createClapController({onAdvance, onEvent=()=>{}}={}) {
  const detector=new DoubleClapDetector();
  let stream=null,context=null,source=null,analyser=null,raf=0;
  let timeSamples=null,freqSamples=null,previousPower=null;
  let active=false,startNonce=0,lastUi=0,lastType='';
  const state=()=>active?'listening':'off';
  function notify(type,features={}) {
    // Visual meters update at <= 12.5 Hz; meaningful events are never throttled.
    const now=performance.now();
    if(type===lastType && type==='listening' && now-lastUi<80)return;
    lastType=type;lastUi=now;onEvent({type,...features});
  }
  function stop(reason='stopped') {
    ++startNonce;
    active=false;
    if(raf)cancelAnimationFrame(raf);raf=0;
    try{source?.disconnect();}catch{}
    if(stream)for(const track of stream.getTracks())track.stop();
    if(context)context.close().catch(()=>{});
    stream=context=source=analyser=timeSamples=freqSamples=previousPower=null;
    detector.reset();lastType='';notify(reason,{level:0});
  }
  function listen() {
    if(!active || !analyser)return;
    try {
      analyser.getFloatTimeDomainData(timeSamples);
      analyser.getFloatFrequencyData(freqSamples);
      const f=extractAudioFeatures(timeSamples,freqSamples,context.sampleRate,previousPower);
      previousPower=f.powers;
      const result=detector.analyze(f,performance.now());
      notify(result.type,result);
      if(result.type==='advance')onAdvance?.();
    } catch {
      stop('audio-error');return;
    }
    raf=requestAnimationFrame(listen);
  }
  async function start() {
    if(active)return true;
    if(!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      notify('unsupported');return false;
    }
    const nonce=++startNonce;
    try {
      const acquired=await navigator.mediaDevices.getUserMedia({
        audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false,
      });
      if(nonce!==startNonce || document.hidden){acquired.getTracks().forEach(t=>t.stop());return false;}
      stream=acquired;
      const AudioContext=window.AudioContext||window.webkitAudioContext;
      if(!AudioContext)throw new Error('Web Audio unavailable');
      context=new AudioContext({latencyHint:'interactive'});
      await context.resume();
      if(nonce!==startNonce){stop();return false;}
      analyser=context.createAnalyser();
      analyser.fftSize=2048;
      analyser.smoothingTimeConstant=.035;
      analyser.minDecibels=-110;
      analyser.maxDecibels=0;
      source=context.createMediaStreamSource(stream);
      source.connect(analyser); // Never connect to destination speakers.
      timeSamples=new Float32Array(analyser.fftSize);
      freqSamples=new Float32Array(analyser.frequencyBinCount);
      previousPower=null;
      detector.reset();
      active=true;
      notify('calibrating',{level:0});
      raf=requestAnimationFrame(listen);
      return true;
    } catch(err) {
      stop(err?.name==='NotAllowedError'?'denied':'audio-error');return false;
    }
  }
  return Object.freeze({start,stop,state,isActive:()=>active,
    setSensitivity:value=>detector.setSensitivity(value),
    getSensitivity:()=>detector.sensitivity});
}
