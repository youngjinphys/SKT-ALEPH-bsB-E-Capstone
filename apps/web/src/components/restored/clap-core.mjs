/**
 * Local clap-onset heuristics. Values are digital amplitudes, NOT calibrated dB SPL.
 * Frequency evidence uses linear POWER derived from dBFS FFT bins, never the
 * sums of 8-bit log-spectrum values. No network or recording is performed.
 */
const EPS = 1e-12;
export const CALIBRATION_MS = 1400;
export const MIN_CLAP_GAP_MS = 210;
export const MAX_CLAP_GAP_MS = 1050;
export const ADVANCE_COOLDOWN_MS = 1450;

export function extractAudioFeatures(samples, frequenciesDb, sampleRate, previousPower) {
  if (!(sampleRate > 1000) || !samples?.length || !frequenciesDb?.length) {
    throw new TypeError('Expected time-domain samples, FFT dBFS bins and sample rate');
  }
  let sq = 0;
  for (const v of samples) {
    if (!Number.isFinite(v)) throw new TypeError('Invalid time-domain sample');
    sq += v * v;
  }
  const rms = Math.sqrt(sq / samples.length);
  const powers = new Float32Array(frequenciesDb.length);
  const stepHz = sampleRate / (2 * frequenciesDb.length);
  let bandSum = 0, highSum = 0, logSum = 0, flatCount = 0;
  let positiveFlux = 0, priorSum = 0;
  for (let i = 0; i < frequenciesDb.length; i++) {
    const db = frequenciesDb[i];
    const power = Number.isFinite(db) ? 10 ** (Math.max(-110, Math.min(0, db)) / 10) : 0;
    powers[i] = power;
    const freq = i * stepHz;
    if (freq < 300 || freq > 8500) continue;
    bandSum += power;
    logSum += Math.log(Math.max(power, EPS));
    flatCount++;
    if (freq >= 1700) highSum += power;
    const previous = previousPower?.[i] ?? 0;
    positiveFlux += Math.max(0, power - previous);
    priorSum += Math.max(0, previous);
  }
  const flatness = flatCount ? Math.exp(logSum / flatCount) / (bandSum / flatCount + EPS) : 0;
  return {
    rms,
    highRatio: highSum / Math.max(bandSum, EPS),
    flatness: Math.min(1, Math.max(0, flatness)),
    flux: Math.min(100, positiveFlux / Math.max(priorSum, EPS)),
    powers,
  };
}

const GATES = Object.freeze([
  {minRms:.110, floorFactor:6.0, attack:2.15, high:.32, flatness:.23, flux:1.7},
  {minRms:.085, floorFactor:5.2, attack:1.95, high:.28, flatness:.19, flux:1.35},
  {minRms:.064, floorFactor:4.6, attack:1.75, high:.23, flatness:.15, flux:1.0},
  {minRms:.048, floorFactor:3.7, attack:1.5, high:.19, flatness:.115, flux:.75},
  {minRms:.036, floorFactor:3.0, attack:1.32, high:.15, flatness:.08, flux:.55},
]);

export function isClapOnset(f, {noiseRms, priorRms, noiseFlux, sensitivity=3}) {
  if (![f?.rms, f?.highRatio, f?.flatness, f?.flux, noiseRms, priorRms, noiseFlux].every(Number.isFinite)) return false;
  const gates = GATES[Math.min(5, Math.max(1, Math.round(sensitivity))) - 1];
  return f.rms >= Math.max(gates.minRms, Math.max(.005, noiseRms) * gates.floorFactor)
    && f.rms >= Math.max(.009, priorRms) * gates.attack
    && f.highRatio >= gates.high
    && f.flatness >= gates.flatness
    && f.flux >= Math.max(gates.flux, noiseFlux * 2.25);
}

/** The double-clap state machine. Timestamps are monotonic milliseconds. */
export class DoubleClapDetector {
  constructor({sensitivity=3}={}) { this.sensitivity=sensitivity; this.reset(); }
  reset() {
    this.start=null;
    this.noiseRms=.009;
    this.noiseFlux=.09;
    this.priorRms=.01;
    this.firstHit=null;
    this.lastHit=-Infinity;
    this.lastAdvance=-Infinity;
  }
  setSensitivity(value) {this.sensitivity=Math.min(5,Math.max(1,Math.round(Number(value)||3)));this.firstHit=null;}
  analyze(features, now) {
    if (!Number.isFinite(now)) throw new TypeError('Monotonic time required');
    if (this.start===null) this.start=now;
    const warmup=now-this.start<CALIBRATION_MS;
    const onset=!warmup && isClapOnset(features, this);
    const rms=Number.isFinite(features?.rms)?Math.max(0,features.rms):0;
    const flux=Number.isFinite(features?.flux)?Math.max(0,features.flux):0;
    // Update only when quiet. A sudden clap must not raise the baseline.
    if(warmup || (rms < Math.max(.025,this.noiseRms*2.1) && !onset)) {
      this.noiseRms=this.noiseRms*.976+rms*.024;
      this.noiseFlux=this.noiseFlux*.985+Math.min(5,flux)*.015;
    }
    if (this.firstHit!==null && now-this.firstHit>MAX_CLAP_GAP_MS) this.firstHit=null;
    const level=Math.min(100,Math.max(0,Math.round(rms*480)));
    const debug={level,rms,flux,highRatio:features?.highRatio??0,flatness:features?.flatness??0,noiseRms:this.noiseRms};
    // Use frame-before-current RMS for attack, not the EWMA after the current frame.
    this.priorRms=Math.max(rms,.001);
    if(warmup) return {type:'calibrating',...debug};
    if(now-this.lastAdvance<ADVANCE_COOLDOWN_MS) return {type:'cooldown',...debug};
    if(!onset || now-this.lastHit<MIN_CLAP_GAP_MS) return {type:'listening',...debug};
    this.lastHit=now;
    if(this.firstHit!==null && now-this.firstHit>=MIN_CLAP_GAP_MS && now-this.firstHit<=MAX_CLAP_GAP_MS) {
      this.firstHit=null;this.lastAdvance=now;
      return {type:'advance',...debug};
    }
    this.firstHit=now;
    return {type:'first',...debug};
  }
}
