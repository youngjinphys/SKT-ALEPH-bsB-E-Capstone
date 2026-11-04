/** Self-hosted NASA composites, stylized rotation; never live Earth or live traffic.
 * One mount owns every GPU object, observer, request and animation frame. */
import * as THREE from 'three';
import {TRAIL_COUNT,TRAIL_SPACING,packetPhase,routeSample,trailScale} from './earth-traffic.mjs';
import {geographicUnit,greatCirclePoints,boundedFrameDelta,createTextureBatch} from './earth-model.mjs';
const MAPS=Object.freeze({day:'/capstone/assets/earth-day.webp',night:'/capstone/assets/earth-night.webp',clouds:'/capstone/assets/earth-clouds.webp'});
// The offline fallback renderer imports the same framing to keep map pins aligned.
export const EARTH_VIEW=Object.freeze({fov:39,distance:3.36,tilt:23.44*Math.PI/180,spin:2.51});
// 3D orbit traces extend beyond the Earth's projected limb. Keep globe size
// unchanged, but allocate a transparent off-limb framebuffer.
export const EARTH_OVERSCAN=1.30;
// Maximum rasterized GPU pixels per device class, not texture pixel count.
export const EARTH_QUALITY_BUDGETS=Object.freeze({
  compact:1_150_000,fullHD:2_200_000,qhd:3_500_000,ultraHD:5_500_000
});
export function earthRenderViewport(width,height){
 if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)throw new RangeError('Positive viewport dimensions required');
 const factor=EARTH_OVERSCAN;
 return {width:width*factor,height:height*factor,
  padX:width*(factor-1)/2,padY:height*(factor-1)/2,
  fov:2*Math.atan(Math.tan(EARTH_VIEW.fov*Math.PI/360)*factor)*180/Math.PI};
}
/** Match the monitor's effective pixel density and the globe's CSS footprint.
 * screen resolution chooses a conservative budget; a small globe never renders
 * a full desktop-sized framebuffer. The 4K NASA surface stays the same.
 */
export function earthRenderQuality({width,height,devicePixelRatio=1,
  screenWidth=0,screenHeight=0,deviceMemory=undefined}={}){
 const viewport=earthRenderViewport(width,height);
 const dpr=Number.isFinite(devicePixelRatio)&&devicePixelRatio>0?devicePixelRatio:1;
 const sw=Number.isFinite(screenWidth)&&screenWidth>0?screenWidth:width;
 const sh=Number.isFinite(screenHeight)&&screenHeight>0?screenHeight:height;
 const physicalScreenPixels=sw*sh*dpr*dpr;
 const compact=Math.min(width,height)<480||sw<740;
 const tier=compact?'compact':physicalScreenPixels>=6_500_000?'ultraHD':
  physicalScreenPixels>=3_000_000?'qhd':'fullHD';
 let maxPixels=EARTH_QUALITY_BUDGETS[tier];
 // A high-resolution monitor does not guarantee that the client has a GPU.
 if(Number.isFinite(deviceMemory)&&deviceMemory<=4)maxPixels=Math.min(maxPixels,2_200_000);
 const maxDpr=tier==='compact'?1.25:tier==='fullHD'?1.5:tier==='qhd'?1.75:2;
 const pixelRatio=Math.min(dpr,maxDpr,Math.sqrt(maxPixels/(Math.ceil(viewport.width)*Math.ceil(viewport.height))));
 return Object.freeze({tier,viewport,maxPixels,pixelRatio,
  renderWidth:Math.max(1,Math.ceil(viewport.width*pixelRatio)),
  renderHeight:Math.max(1,Math.ceil(viewport.height*pixelRatio))});
}
export function geoVector(lat,lon,radius=1){
 if(!Number.isFinite(radius)||radius<0)throw new RangeError('Invalid sphere radius');
 return new THREE.Vector3(...geographicUnit(lat,lon)).multiplyScalar(radius);
}
export function arcPoints(from,to,count=72){return greatCirclePoints(from,to,count).map(p=>new THREE.Vector3(...p));}
export function projectGeoAnchor(lat,lon,rotation,camera,width,height){
 const surface=geoVector(lat,lon).applyQuaternion(rotation);
 const frontScore=surface.dot(camera.position.clone().sub(surface));
 const pin=geoVector(lat,lon,1.035).applyQuaternion(rotation).project(camera);
 const visible=frontScore>.015&&pin.z>=-1&&pin.z<=1&&Number.isFinite(pin.x)&&Number.isFinite(pin.y);
 return {x:(pin.x+1)*width/2,y:(1-pin.y)*height/2,frontScore,visible,alpha:visible?THREE.MathUtils.smoothstep(frontScore,.015,.22):0};
}
const VERTEX=`
 varying vec2 vUvEarth; varying vec3 vNormalEye; varying vec3 vViewEye;
 void main(){vUvEarth=uv;vec4 p=modelViewMatrix*vec4(position,1.0);vNormalEye=normalize(normalMatrix*normal);vViewEye=-p.xyz;gl_Position=projectionMatrix*p;}
`;
const SURFACE=`
 uniform sampler2D mapDay;uniform sampler2D mapNight;uniform vec3 sunDirection;
 varying vec2 vUvEarth;varying vec3 vNormalEye;varying vec3 vViewEye;
 void main(){
  vec3 N=normalize(vNormalEye),V=normalize(vViewEye),L=normalize(sunDirection);
  float mu=dot(N,L),daylight=smoothstep(-0.12,0.20,mu);
  vec3 terrain=texture2D(mapDay,vUvEarth).rgb;
  float cities=texture2D(mapNight,vUvEarth).r;
  vec3 day=terrain*(0.57+0.97*max(mu,0.0));
  vec3 night=terrain*vec3(0.08,0.13,0.22)+cities*vec3(1.70,1.08,0.43);
  vec3 color=mix(night,day,daylight);
  // A conservative blue-water mask: aesthetic glint, not bathymetry or a measured ocean model.
  float water=smoothstep(0.02,0.18,terrain.b-terrain.r);
  float shine=pow(max(dot(N,normalize(L+V)),0.0),64.0);
  color+=vec3(0.012,0.055,0.11)*water*daylight;
  color+=vec3(0.52,0.73,0.96)*water*shine*0.52*daylight;
  float edge=pow(1.0-max(dot(N,V),0.0),4.2);
  float dawn=exp(-18.0*abs(mu));
  color+=vec3(0.12,0.61,0.88)*edge*(0.34+0.30*daylight);
  color+=vec3(0.20,0.06,0.018)*edge*dawn*0.27;
  gl_FragColor=vec4(color,1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
 }
`;
const CLOUDS=`
 uniform sampler2D mapClouds;uniform vec3 sunDirection;
 varying vec2 vUvEarth;varying vec3 vNormalEye;varying vec3 vViewEye;
 void main(){
  float density=texture2D(mapClouds,vUvEarth).r;
  float daylight=smoothstep(-0.20,0.26,dot(normalize(vNormalEye),normalize(sunDirection)));
  float limb=pow(1.0-max(dot(normalize(vNormalEye),normalize(vViewEye)),0.0),2.0);
  vec3 color=mix(vec3(0.23,0.35,0.51),vec3(0.95,0.98,1.0),daylight);
  gl_FragColor=vec4(color,smoothstep(0.12,0.90,density)*(0.13+0.46*daylight+0.10*limb));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
 }
`;
const ATMOSPHERE=`
 uniform vec3 sunDirection;uniform vec3 glowColor;uniform float glowStrength;uniform float limbFacing;
 varying vec2 vUvEarth;varying vec3 vNormalEye;varying vec3 vViewEye;
 void main(){
  vec3 N=normalize(vNormalEye),V=normalize(vViewEye);
  // Brightest at Earth's limb, fading out instead of forming a detached ring.
  float rim=pow(smoothstep(0.0,limbFacing,abs(dot(N,V))),2.0);
  float lit=smoothstep(-0.30,0.55,dot(N,normalize(sunDirection)));
  float rose=pow(max(N.x-N.y*0.45,0.0),2.0)*0.10;
  vec3 color=mix(glowColor,vec3(1.0,0.38,0.68),rose)*(0.70+0.30*lit);
  gl_FragColor=vec4(color,rim*glowStrength);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
 }
`;
const BEACON=`
 uniform vec3 glowColor;varying vec3 vNormalEye;varying vec3 vViewEye;
 void main(){
  float center=max(dot(normalize(vNormalEye),normalize(vViewEye)),0.0);
  gl_FragColor=vec4(glowColor,pow(center,3.0)*0.33);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
 }
`;
const inert=()=>Object.freeze({ready:Promise.resolve(false),setMotion(){},destroy(){}});
export function mountEarthGlobe(host,{motion=true,anchors=[],onProjection=null,onFallback=null}={}){
 if(!host||typeof window==='undefined')return inert();
 const win=window,doc=host.ownerDocument||document;
 let renderer,scene,spinning,clouds,disposed=false,lost=false,failed=false,rendererReleased=false;
 let wanted=Boolean(motion),visible=true,rafId=null,revealFirst=null,revealSecond=null;
 let lastTime=0,lastRender=0,width=0,height=0,resizeObserver,intersectionObserver;
 const MIN_FRAME_MS = 1000 / 30 - 1; // Share GPU time with the independent mascot layer.
 const geometryList=[],materials=[],ownedFallbackTextures=[],cleanups=[],pulses=[],beacons=[];
 const trailTransform=new THREE.Object3D();let animationTime=0;
 const loader=new THREE.TextureLoader(),batch=createTextureBatch(url=>loader.loadAsync(url),{timing:win,timeout:10000});
 const rotation=new THREE.Quaternion(),camera=new THREE.PerspectiveCamera(EARTH_VIEW.fov,1,.1,12);
 camera.position.set(0,0,EARTH_VIEW.distance);
 const sun=new THREE.Vector3(-.48,.31,.84).normalize();
 const reduced=win.matchMedia?.('(prefers-reduced-motion: reduce)')||{matches:false};
 const projectedAnchors=anchors.filter(a=>a&&typeof a.id==='string'&&Number.isFinite(a.lat)&&Math.abs(a.lat)<=90&&Number.isFinite(a.lon));
 const ownGeometry=g=>(geometryList.push(g),g),ownMaterial=m=>(materials.push(m),m);
 function listen(target,event,fn){target?.addEventListener?.(event,fn);cleanups.push(()=>target?.removeEventListener?.(event,fn));}
 function stopFrames(){if(rafId!==null)win.cancelAnimationFrame(rafId);rafId=null;lastTime=lastRender=0;host.dataset.earthAnimating='false';}
 function cancelReveal(){if(revealFirst!==null)win.cancelAnimationFrame(revealFirst);if(revealSecond!==null)win.cancelAnimationFrame(revealSecond);revealFirst=revealSecond=null;}
 function canPaint(){return !disposed&&!failed&&!lost&&Boolean(scene)&&visible&&!doc.hidden&&host.isConnected&&width>0&&height>0;}
 function canAnimate(){return canPaint()&&wanted&&!reduced.matches;}
 function fallbackProjection(){
  // Fallback projection uses the unchanged original camera, not the
  // overscanned live renderer's widened FOV.
  const stillCamera=new THREE.PerspectiveCamera(EARTH_VIEW.fov,1,.1,12);
  stillCamera.position.set(0,0,EARTH_VIEW.distance);
  stillCamera.updateProjectionMatrix();stillCamera.updateMatrixWorld();
  const stillRotation=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),EARTH_VIEW.tilt)
   .multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),EARTH_VIEW.spin));
  return projectedAnchors.map(a=>({id:a.id,...projectGeoAnchor(a.lat,a.lon,stillRotation,stillCamera,1,1)}));
 }
 function announceFallback(reason='render-failed'){host.dataset.earthFallbackReason=reason;host.dataset.earthState='fallback';host.dataset.earthAnimating='false';try{onFallback?.(fallbackProjection());}catch{/* caller UI must not strand GPU ownership */}}
 function releaseResources(){
  for(const pulse of pulses)pulse.trail?.dispose();beacons.length=0;
  for(const g of geometryList.splice(0))g.dispose();for(const m of materials.splice(0))m.dispose();
  for(const t of ownedFallbackTextures.splice(0))t.dispose();batch.destroy();pulses.length=0;scene=null;
 }
 function releaseRenderer(){if(rendererReleased||!renderer)return;rendererReleased=true;renderer.domElement?.remove();renderer.dispose();renderer.forceContextLoss();}
 function fail(reason='render-failed'){if(disposed||failed)return;failed=true;stopFrames();cancelReveal();releaseResources();releaseRenderer();announceFallback(reason);}
 function draw(){
  if(!canPaint())return false;
  try{
   const context=renderer.getContext();
   if(!context||context.isContextLost()){lost=true;fail('context-lost');return false;}
   spinning.updateWorldMatrix(true,false);camera.updateMatrixWorld();
   spinning.getWorldQuaternion(rotation);
   renderer.render(scene,camera);
   if(typeof onProjection==='function'){
    const view=earthRenderViewport(width,height);
    onProjection(projectedAnchors.map(a=>{
     const p=projectGeoAnchor(a.lat,a.lon,rotation,camera,view.width,view.height);
     // DOM cards use original host coordinates, never padded canvas pixels.
     return {id:a.id,...p,x:p.x-view.padX,y:p.y-view.padY};
    }));
   }
   return true;
  }catch{fail();return false;}
 }
 function revealWhenPainted(){
  if(!canPaint())return;
  if(host.dataset.earthState==='ready'||revealFirst!==null||revealSecond!==null)return;
  cancelReveal();host.dataset.earthState='revealing';
  revealFirst=win.requestAnimationFrame(()=>{
   revealFirst=null;if(!draw())return;
   revealSecond=win.requestAnimationFrame(()=>{revealSecond=null;if(canPaint())host.dataset.earthState='ready';});
  });
 }
 function frame(time){
  rafId=null;if(!canAnimate()){stopFrames();return;}
  if(lastRender&&time-lastRender<MIN_FRAME_MS){rafId=win.requestAnimationFrame(frame);return;}
  const dt=boundedFrameDelta(time,lastTime);lastTime=lastRender=time;
  spinning.rotation.y=(spinning.rotation.y+.086*dt)%(Math.PI*2);
  clouds.rotation.y=(clouds.rotation.y+.012*dt)%(Math.PI*2);
  animationTime+=dt;
  for(const pulse of pulses){
   pulse.progress=packetPhase(pulse.progress+dt*pulse.speed);
   routeSample(pulse.points,pulse.progress,pulse.mesh.position);
   for(let i=0;i<TRAIL_COUNT;i++){
    routeSample(pulse.points,packetPhase(pulse.progress,(i+1)*TRAIL_SPACING),trailTransform.position);
    trailTransform.scale.setScalar(trailScale(i));trailTransform.updateMatrix();pulse.trail.setMatrixAt(i,trailTransform.matrix);
   }
   pulse.trail.instanceMatrix.needsUpdate=true;
  }
  for(let i=0;i<beacons.length;i++){const beat=(animationTime*.36+i*.21)%1;beacons[i].scale.setScalar(1+.45*Math.sin(Math.PI*beat)**2);}
  if(draw()&&canAnimate())rafId=win.requestAnimationFrame(frame);
 }
 function resume(){
  if(disposed||failed)return;
  if(!canAnimate())stopFrames();
  if(canPaint()&&draw())revealWhenPainted();
  if(canAnimate()&&rafId===null){host.dataset.earthAnimating='true';rafId=win.requestAnimationFrame(frame);}
 }
 function resize(){
  if(disposed||failed||lost||!renderer)return;
  const bounds=host.getBoundingClientRect();width=host.clientWidth||bounds.width;height=host.clientHeight||bounds.height;
  if(width<4||height<4){stopFrames();return;}
  const view=earthRenderViewport(width,height);
  camera.aspect=width/height;camera.fov=view.fov;camera.updateProjectionMatrix();
  const quality=earthRenderQuality({width,height,
   devicePixelRatio:win.devicePixelRatio,
   screenWidth:win.screen?.width??win.innerWidth,
   screenHeight:win.screen?.height??win.innerHeight,
   deviceMemory:win.navigator?.deviceMemory});
  renderer.setPixelRatio(quality.pixelRatio);
  renderer.setSize(Math.round(view.width),Math.round(view.height),false);
  host.dataset.earthQuality=quality.tier;
  resume();
 }
 try{
  // A single probe selects the raster quietly on browsers with GPU rendering disabled.
  const canvas=doc.createElement('canvas'),options={alpha:true,antialias:true,premultipliedAlpha:false,powerPreference:'low-power'};
  host.dataset.earthFallbackReason='webgl2-unavailable';
  const context=canvas.getContext('webgl2',options);if(!context)throw new Error('WebGL 2 is unavailable');
  host.dataset.earthFallbackReason='renderer-init-failed';
  renderer=new THREE.WebGLRenderer({canvas,context,...options});
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.22;renderer.setClearColor(0,0);
  renderer.domElement.className='cyber-earth-canvas';
  renderer.domElement.setAttribute('aria-hidden','true');
  const gutter=(EARTH_OVERSCAN-1)*50;
  renderer.domElement.style.left=renderer.domElement.style.top='-'+gutter+'%';
  renderer.domElement.style.width=renderer.domElement.style.height=EARTH_OVERSCAN*100+'%';
  renderer.domElement.style.right=renderer.domElement.style.bottom='auto';
  renderer.domElement.style.borderRadius='0';
  host.append(renderer.domElement);
 }catch{batch.destroy();releaseRenderer();announceFallback(host.dataset.earthFallbackReason);return Object.freeze({ready:Promise.resolve(false),setMotion(){},destroy(){if(disposed)return;disposed=true;delete host.dataset.earthState;delete host.dataset.earthAnimating;delete host.dataset.earthDetail;delete host.dataset.earthQuality;delete host.dataset.earthFallbackReason;}});}
 delete host.dataset.earthFallbackReason;host.dataset.earthState='loading';host.dataset.earthAnimating='false';
 listen(renderer.domElement,'webglcontextlost',event=>{event.preventDefault();if(disposed||failed)return;lost=true;fail('context-lost');});
 // Card projections are fixed once fallback is selected. Recover on slide remount,
 // never by restarting a restored context against that static geographic frame.
 listen(renderer.domElement,'webglcontextrestored',()=>{if(disposed||failed||lost)return;resize();});
 listen(doc,'visibilitychange',resume);listen(reduced,'change',resume);
 // ResizeObserver does not necessarily fire when a window is moved between
 // screens with different DPR but unchanged CSS layout.
 let densityQuery=null;
 function watchDensity(){
  if(disposed||failed)return;
  const value=Number(win.devicePixelRatio)||1;
  const query=win.matchMedia?.('(resolution: '+value+'dppx)');
  if(query&&query!==reduced&&typeof query.addEventListener==='function'){
   densityQuery=query;query.addEventListener('change',onDensityChange);
  }
 }
 function onDensityChange(){
  densityQuery?.removeEventListener?.('change',onDensityChange);
  densityQuery=null;
  watchDensity();
  resize();
 }
 watchDensity();
 cleanups.push(()=>densityQuery?.removeEventListener?.('change',onDensityChange));
 listen(win,'resize',resize);
 if(typeof ResizeObserver==='function'){resizeObserver=new ResizeObserver(resize);resizeObserver.observe(host);}else listen(win,'resize',resize);
 if(typeof IntersectionObserver==='function'){intersectionObserver=new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting!==false;resume();},{rootMargin:'60px'});intersectionObserver.observe(host.closest?.('.hero-visual')||host);}
 function blackTexture(){const t=new THREE.DataTexture(new Uint8Array([0,0,0,255]),1,1,THREE.RGBAFormat);t.needsUpdate=true;ownedFallbackTextures.push(t);return t;}
 const ready=Promise.allSettled(Object.values(MAPS).map(url=>batch.request(url))).then(results=>{
  if(disposed||failed)return false;
  if(results[0].status!=='fulfilled'){fail('day-texture-unavailable');return false;}
  const dayMap=results[0].value,nightMap=results[1].status==='fulfilled'?results[1].value:blackTexture(),cloudMap=results[2].status==='fulfilled'?results[2].value:blackTexture();
  host.dataset.earthDetail=results.every(x=>x.status==='fulfilled')?'complete':'day-only';
  dayMap.colorSpace=THREE.SRGBColorSpace;nightMap.colorSpace=cloudMap.colorSpace=THREE.NoColorSpace;
  for(const t of [dayMap,nightMap,cloudMap]){t.wrapS=THREE.RepeatWrapping;t.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy());}
  scene=new THREE.Scene();const tilt=new THREE.Group();tilt.rotation.z=EARTH_VIEW.tilt;scene.add(tilt);
  spinning=new THREE.Group();spinning.rotation.y=EARTH_VIEW.spin;tilt.add(spinning);
  spinning.add(new THREE.Mesh(ownGeometry(new THREE.SphereGeometry(1,88,56)),ownMaterial(new THREE.ShaderMaterial({vertexShader:VERTEX,fragmentShader:SURFACE,uniforms:{sunDirection:{value:sun},mapDay:{value:dayMap},mapNight:{value:nightMap}}}))));
  clouds=new THREE.Mesh(ownGeometry(new THREE.SphereGeometry(1.014,88,56)),ownMaterial(new THREE.ShaderMaterial({vertexShader:VERTEX,fragmentShader:CLOUDS,transparent:true,depthWrite:false,uniforms:{sunDirection:{value:sun},mapClouds:{value:cloudMap}}})));spinning.add(clouds);
  for(const [radius,color,strength] of [[1.124,new THREE.Vector3(.055,.48,1),.34],[1.035,new THREE.Vector3(.52,.91,1),.72]]){
   scene.add(new THREE.Mesh(ownGeometry(new THREE.SphereGeometry(radius,70,48)),ownMaterial(new THREE.ShaderMaterial({vertexShader:VERTEX,fragmentShader:ATMOSPHERE,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,side:THREE.BackSide,uniforms:{sunDirection:{value:sun},glowColor:{value:color},glowStrength:{value:strength},limbFacing:{value:Math.sqrt(1-1/(radius*radius))}}}))));
  }
  const beaconGeometry=ownGeometry(new THREE.SphereGeometry(.06,14,10)),beaconMaterials=new Map();
  function beaconGlow(color,scale=1){
   if(!beaconMaterials.has(color))beaconMaterials.set(color,ownMaterial(new THREE.ShaderMaterial({vertexShader:VERTEX,fragmentShader:BEACON,uniforms:{glowColor:{value:new THREE.Color(color)}},transparent:true,blending:THREE.AdditiveBlending,depthWrite:false,depthTest:true})));
   const halo=new THREE.Mesh(beaconGeometry,beaconMaterials.get(color));halo.scale.setScalar(scale);return halo;
  }
  const seoul=[37.57,126.98],destinations=[[37.77,-122.42],[51.51,-.12],[1.35,103.82],[-33.87,151.21]];
  const pinGeometry=ownGeometry(new THREE.SphereGeometry(.013,10,8));
  const pinMaterial=ownMaterial(new THREE.MeshBasicMaterial({color:0xe3fcff,transparent:true,opacity:.98,blending:THREE.AdditiveBlending,depthWrite:false}));
  for(const coordinate of [seoul,...destinations]){const pin=new THREE.Mesh(pinGeometry,pinMaterial);pin.position.copy(geoVector(...coordinate,1.035));pin.add(beaconGlow(0x59dcff,.85));spinning.add(pin);}
  const geoPin=ownGeometry(new THREE.SphereGeometry(.018,12,10)),geoRing=ownGeometry(new THREE.TorusGeometry(.027,.004,6,22));
  const colors={government:0x9defff,isp:0x58ffd2,users:0xb2bdff,attacker:0xff648c};
  for(const a of projectedAnchors){const normal=geoVector(a.lat,a.lon);const material=ownMaterial(new THREE.MeshBasicMaterial({color:colors[a.id]??0x77e7ff,transparent:true,opacity:.96,depthTest:true,depthWrite:false}));
   const pin=new THREE.Mesh(geoPin,material);pin.position.copy(normal).multiplyScalar(1.035);pin.add(beaconGlow(colors[a.id]??0x77e7ff));spinning.add(pin);
   const ring=new THREE.Mesh(geoRing,material);ring.position.copy(normal).multiplyScalar(1.035);ring.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),normal);spinning.add(ring);beacons.push(ring);
  }
  const arcMaterial=ownMaterial(new THREE.LineBasicMaterial({color:0x94f3ff,transparent:true,opacity:.50,blending:THREE.AdditiveBlending,depthWrite:false}));
  const arcGlowMaterial=ownMaterial(new THREE.MeshBasicMaterial({color:0x2ccfff,transparent:true,opacity:.13,blending:THREE.AdditiveBlending,depthWrite:false}));
  const pulseGeometry=ownGeometry(new THREE.SphereGeometry(.015,10,8)),pulseMaterial=ownMaterial(new THREE.MeshBasicMaterial({color:0xf0feff,transparent:true,opacity:.98,blending:THREE.AdditiveBlending,depthWrite:false}));
  for(const [i,target] of destinations.entries()){
   const points=arcPoints(seoul,target,64),trace=new THREE.Line(ownGeometry(new THREE.BufferGeometry().setFromPoints(points)),arcMaterial);spinning.add(trace);
   spinning.add(new THREE.Mesh(ownGeometry(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),64,.009,6,false)),arcGlowMaterial));
   const mesh=new THREE.Mesh(pulseGeometry,pulseMaterial);mesh.add(beaconGlow(0x8deaff,.9));mesh.position.copy(points[Math.floor(i/4*(points.length-1))]);spinning.add(mesh);
   const trail=new THREE.InstancedMesh(pulseGeometry,pulseMaterial,TRAIL_COUNT);
   trail.instanceMatrix.setUsage(THREE.DynamicDrawUsage);trail.frustumCulled=false;
   for(let n=0;n<TRAIL_COUNT;n++){trailTransform.position.copy(mesh.position);trailTransform.scale.setScalar(0);trailTransform.updateMatrix();trail.setMatrixAt(n,trailTransform.matrix);trail.setColorAt(n,new THREE.Color(0x70eaff).multiplyScalar(.7*(1-n/TRAIL_COUNT)));}
   spinning.add(trail);pulses.push({mesh,trail,points,progress:i/4,speed:.14+i*.018});
  }
  resize();resume();return !failed;
 }).catch(()=>{fail();return false;});
 return Object.freeze({ready,setMotion(on){if(disposed)return;wanted=Boolean(on);resume();},destroy(){
  if(disposed)return;disposed=true;stopFrames();cancelReveal();resizeObserver?.disconnect();intersectionObserver?.disconnect();for(const cleanup of cleanups)cleanup();releaseResources();
  releaseRenderer();
  delete host.dataset.earthState;delete host.dataset.earthAnimating;delete host.dataset.earthDetail;delete host.dataset.earthQuality;delete host.dataset.earthFallbackReason;
 }});
}


