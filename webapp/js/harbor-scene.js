import * as T from 'three';
import { OrbitControls } from '../vendor/three/addons/controls/OrbitControls.js';
import { GLTFLoader } from '../vendor/three/addons/loaders/GLTFLoader.js';
import { box, cylinder, beam, material, container, makeCrane, makeTruck, makeShip, makePlane, makeWarehouse, makeDock, makeFactory } from './harbor-models.js';
import { COUNTRIES, STAGES, SHIPS, VEHICLES, PLANES, projectHarborState } from './harbor-state.js';

const ASSETS = new URL('../assets/harbor/', import.meta.url);
export class HarborScene {
  constructor(element, { onSelect = () => {}, onStatus = () => {} } = {}) {
    this.element = element; this.onSelect = onSelect; this.onStatus = onStatus;
    this.destroyed = false; this.visible = true; this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.scene = new T.Scene(); this.scene.background = new T.Color('#a4c2c5');
    this.scene.fog = new T.Fog('#a4c2c5', 145, 340);
    this.renderer = new T.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = T.PCFSoftShadowMap;
    this.renderer.outputColorSpace = T.SRGBColorSpace;
    this.renderer.toneMapping = T.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.2;
    this.renderer.domElement.setAttribute('aria-label', '드래그로 회전하고 휠로 확대하는 항구 지도');
    this.renderer.domElement.setAttribute('role', 'img');
    element.prepend(this.renderer.domElement);
    this.camera = new T.PerspectiveCamera(38, 1, .5, 650);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true; this.controls.maxPolarAngle = Math.PI * .47;
    this.controls.minDistance = 38; this.controls.maxDistance = 220;
    this.controls.target.set(0, 1, 2); this.resetCamera();
    this.scene.add(new T.HemisphereLight('#e8f2ec', '#60796e', 2.1));
    this.sun = new T.DirectionalLight('#fff0d1', 3.6); this.sun.position.set(-45, 85, 35);
    this.sun.castShadow = true; this.sun.shadow.mapSize.set(2048, 2048);
    Object.assign(this.sun.shadow.camera, { left: -75, right: 75, top: 75, bottom: -75, near: 1, far: 200 });
    this.sun.shadow.bias = -.0007; this.sun.shadow.normalBias = .15; this.scene.add(this.sun);
    this.static = new T.Group(); this.dynamic = new T.Group(); this.scene.add(this.static, this.dynamic);
    this.prototypes = new Map(); this.pending = new Map(); this.failed = new Set();
    this.buildLand(); this.clock = new T.Clock(); this.elapsed = 0;
    this.resizeObserver = new ResizeObserver(() => this.resize()); this.resizeObserver.observe(element);
    this.intersectionObserver = new IntersectionObserver(e => { this.visible = e[0].isIntersecting; }); this.intersectionObserver.observe(element);
    this.pickDown = e => { this.pointerStart = [e.clientX, e.clientY]; };
    this.pickUp = e => this.pick(e);
    this.renderer.domElement.addEventListener('pointerdown', this.pickDown);
    this.renderer.domElement.addEventListener('pointerup', this.pickUp);
    this.contextLost = e => { e.preventDefault(); this.onStatus('3D 화면 연결이 끊겼어요. 지도를 닫았다 다시 열어 주세요.', true); };
    this.renderer.domElement.addEventListener('webglcontextlost', this.contextLost);
    this.renderer.setAnimationLoop(() => this.frame());
  }
  resetCamera() {
    const wide=this.element.clientWidth>680;
    const embedded=Boolean(this.element.closest('.harbor-embed'));
    this.camera.position.set(wide?96:106,108,wide?144:137);
    this.controls.target.set(wide&&!embedded?-10:0,0,wide&&!embedded?7:0);this.controls.update();
  }
  resize() {
    const w = this.element.clientWidth, h = this.element.clientHeight;
    if (!w || !h) return;
    this.camera.aspect = w/h; this.camera.updateProjectionMatrix(); this.renderer.setSize(w, h);
    const narrow=w<=680;
    this.camera.zoom=this.element.closest('.harbor-embed')?1.35:narrow?.65:1;
    this.camera.updateProjectionMatrix();
    if(this.narrow!==narrow){this.narrow=narrow;this.resetCamera();}
  }
  buildLand() {
    const water = new T.ShaderMaterial({
      uniforms: { time: { value: 0 } },
      vertexShader: 'uniform float time; varying vec3 v; void main(){v=position; vec3 p=position; p.z+=sin(p.x*.12+time*.7)*.09+cos(p.y*.16+time*.5)*.06; gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}',
      fragmentShader: 'varying vec3 v; uniform float time; void main(){float a=sin(v.x*.9+v.y*.43+time*.8); float b=sin(v.y*.75-v.x*.16+time*.5); float ripple=pow(max(0.,a*b),14.); float d=smoothstep(20.,230.,length(v.xy)); vec3 col=mix(vec3(.13,.36,.42),vec3(.32,.54,.58),d); col+=ripple*.045; gl_FragColor=vec4(col,1.); #include <tonemapping_fragment>\n#include <colorspace_fragment> }',
    });
    // Shader include directives must start on their own line.
    water.fragmentShader = water.fragmentShader.replace('; #include', ';\n#include');
    this.water = new T.Mesh(new T.PlaneGeometry(900, 900, 100, 100), water); this.water.rotation.x=-Math.PI/2; this.water.position.y=-.25; this.scene.add(this.water);
    const shape = new T.Shape();
    const points = [[-49,-31],[-39,-40],[28,-40],[45,-29],[49,-9],[44,13],[34,18],[-39,18],[-49,6]];
    points.forEach(([x,z],i)=>i?shape.lineTo(x,-z):shape.moveTo(x,-z)); shape.closePath();
    const geo=new T.ExtrudeGeometry(shape,{depth:3,bevelEnabled:true,bevelSize:1.4,bevelThickness:.8,bevelSegments:2,steps:1}); geo.rotateX(-Math.PI/2);
    const island=new T.Mesh(geo,[material('#b1b88b'),material('#a2a28b')]);island.position.y=-2.8;island.receiveShadow=true;this.static.add(island);
    box(this.static,[79,.45,13],[-1,.7,11.5],'#b3b0a0');
    box(this.static,[80,2,1.4],[-1,-.05,18],'#8e978d');
    for(let x=-39;x<39;x+=3) {box(this.static,[2.8,.2,1.9],[x,1.06,17.4],'#d7cfb7');cylinder(this.static,.17,.5,[x,1.2,17.6],'#4d5f60');}
    box(this.static,[85,.12,5.5],[-1,1,-7],'#718381');
    box(this.static,[5.5,.12,37],[30,1,-.5],'#718381');
    for(let x=-40;x<41;x+=4)box(this.static,[1.8,.025,.12],[x,1.075,-7],'#e6dcbe');
    for(let z=-16;z<17;z+=4)box(this.static,[.12,.025,1.8],[30,1.075,z],'#e6dcbe');
    // A small airfield in the inland corner.
    box(this.static,[42,.12,6],[14,1,-28],'#758882');
    for(let x=-5;x<34;x+=4)box(this.static,[2,.025,.16],[x,1.08,-28],'#e7e1c9');
    for(const x of [-5,33]) for(const z of [-29.6,-28.8,-27.2,-26.4])box(this.static,[1.8,.03,.22],[x,1.1,z],'#e7e1c9');
    box(this.static,[15,.13,9],[24,1,-19],'#9baba0');
    box(this.static,[5,3.5,5],[36,2.8,-20],'#c8cbb2');
    box(this.static,[6,.4,6],[36,4.7,-20],'#537a7d');
    box(this.static,[3,2,3],[36,6,-20],'#b6c9bf');
    for(const z of [-21.55,-18.45])box(this.static,[2.8,.8,.06],[36,6.2,z],'#597f8b');
    // Gentle navigation channel and buoys.
    for(const x of [-42,42]) {cylinder(this.static,.55,.6,[x,.1,35],'#d7d5b1');cylinder(this.static,.14,1.3,[x,.85,35],x<0?'#b86448':'#64a589');}
    for(let i=0;i<14;i++) this.tree(this.static,-42+(i%7)*5,-17-Math.floor(i/7)*6,1+(i%3)*.12);
    this.countryDecor=new T.Group();this.static.add(this.countryDecor);
  }
  tree(parent,x,z,s=1,palm=false) {
    const g=new T.Group();g.position.set(x,1,z);g.scale.setScalar(s);parent.add(g);
    cylinder(g,.17,2.5,[0,1.25,0],'#887351',6);
    if(palm) for(let i=0;i<6;i++){const leaf=box(g,[3.2,.12,.65],[Math.cos(i)*.8,2.8,Math.sin(i)*.8],'#68936c');leaf.rotation.y=i;leaf.rotation.z=.18;}
    else {const crown=new T.Mesh(new T.IcosahedronGeometry(1.5,0),material('#729375'));crown.position.y=3.2;crown.castShadow=true;g.add(crown);}
  }
  clearGroup(g) {
    // Shared cached Tripo geometry stays alive until the whole viewer is disposed.
    g.traverse(o => {if(o.isMesh && !o.userData.cached) o.geometry.dispose();});g.clear();
  }
  update(state) {
    const v=projectHarborState(state);this.state=v;
    const key=JSON.stringify([v.country,v.stage,v.machine,v.electronics,v.cargo]);
    if(key===this.key)return;this.key=key;this.rebuild();
  }
  load(name) {
    if(this.prototypes.has(name)||this.pending.has(name)||this.failed.has(name))return;
    const p=new GLTFLoader().loadAsync(new URL(`${name}.glb`,ASSETS).href).then(gltf=>{
      if(this.destroyed) {gltf.scene.traverse(o=>{if(o.isMesh){o.geometry.dispose();for(const m of [].concat(o.material))m.dispose();}});return;}
      gltf.scene.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;o.userData.cached=true;}});
      this.prototypes.set(name,gltf.scene);this.rebuild();
    }).catch(()=>{this.failed.add(name);if(!this.destroyed)this.onStatus('일부 상세 모델을 불러오지 못해 간단한 모형으로 표시해요.',true);}).finally(()=>{this.pending.delete(name);if(!this.destroyed&&!this.pending.size&&!this.failed.size)this.onStatus('지도 준비 완료');});
    this.pending.set(name,p);
  }
  imported(name,length,axis='x',height=null) {
    const p=this.prototypes.get(name);if(!p){this.load(name);return null;}
    const obj=p.clone(true);const bounds=new T.Box3().setFromObject(obj);const size=bounds.getSize(new T.Vector3());const center=bounds.getCenter(new T.Vector3());
    const scale=length/size[axis];obj.scale.set(scale,height===null?scale:height/size.y,scale);
    obj.position.set(-center.x*scale,-bounds.min.y*obj.scale.y,-center.z*scale);
    const holder=new T.Group();holder.add(obj);return holder;
  }
  tag(object,kind,title,description) {object.userData.detail={kind,title,description};return object;}
  rebuild() {
    if(!this.state||this.destroyed)return;
    const v=this.state;this.clearGroup(this.dynamic);this.clearGroup(this.countryDecor);
    const add=(obj,pos,angle=0)=>{obj.position.set(...pos);obj.rotation.y=angle;this.dynamic.add(obj);return obj;};
    let warehouse=v.stage<3?this.imported('brick-warehouse',17,'z'):makeWarehouse(v.stage===4);
    warehouse ||= makeWarehouse(false);
    add(this.tag(warehouse,'warehouse',v.stage<3?'붉은 벽돌 창고':v.stage===3?'현대 물류 창고':'스마트 물류 센터',`대표 산업 레벨 ${v.stage} · ${STAGES[v.stage-1]}`),[-20,1,4],v.stage<3?Math.PI/2:0);
    if(v.stage===2){const annex=this.imported('brick-warehouse',10,'z')||makeWarehouse();annex.scale.multiplyScalar(.65);add(annex,[-32,1,6],Math.PI/2);}
    let dock=v.stage<3?this.imported('timber-pier',21,'z',3.7):makeDock(v.stage===4);
    dock ||= makeDock(false);add(this.tag(dock,'dock',v.stage<3?'목재 부두':'콘크리트 안벽',`대표 산업 레벨 ${v.stage}에 맞춰 하역 시설이 발전해요.`),[-6,v.stage<3?-2.1:1,27.5]);
    if(v.stage>=2)add(this.tag(makeCrane(v.stage>=3),'crane',v.stage>=3?'컨테이너 갠트리 크레인':'항구 하역 크레인','산업 투자에 따라 하역 시설의 모습이 달라져요.'),[v.stage>=3?-6:3,1,17],0);
    const ship=v.machine===1?(this.imported('steam-freighter',22)||makeShip(2)):makeShip(v.machine);
    this.ship=add(this.tag(ship,'ship',SHIPS[v.machine-1],`기계 ${v.machine}세대 · 선박 외형 표현`),[17,v.machine===1?-.8:-1.3,39],Math.PI);
    this.truck=add(this.tag(makeTruck(v.machine),'truck',VEHICLES[v.machine-1],`기계 ${v.machine}세대 · 도로 운송`),[-5,1.1,-7]);
    const second=makeTruck(v.machine);second.scale.setScalar(.85);add(second,[29,1.1,7],-Math.PI/2);
    this.plane=add(this.tag(makePlane(v.electronics),'plane',PLANES[v.electronics-1],`전자제품 ${v.electronics}세대 · 항공기 외형 표현`),[22,1.15,-20]);
    if(v.stage>=3)for(let i=0;i<Math.min(v.cargo,12);i++)container(this.dynamic,[8+(i%3)*5,1+Math.floor(i/6)*2.05,4+Math.floor((i%6)/3)*2.4],['#c36e50','#5e9796','#d3af65'][i%3]);
    else for(let i=0;i<v.cargo;i++){const x=9+(i%5)*1.5,z=7+Math.floor(i/5)*1.6;box(this.dynamic,[1.2,1.2,1.2],[x,1.6,z],'#ba9b67');for(const d of [-.4,.4])box(this.dynamic,[1.24,.08,.09],[x,1.6+d,z+.61],'#6e624d');}
    for(const x of [-35,-17,8,28]) {cylinder(this.dynamic,.07,5,[x,3.4,-3],'#465c5c',6);box(this.dynamic,[1.1,.18,.45],[x,6,-3],'#ece3b4');}
    this.decorateCountry(v.country,v.stage);
    if(!this.failed.size)this.onStatus(this.pending.size?'상세 모델을 불러오는 중…':'지도 준비 완료');
  }
  decorateCountry(country,stage) {
    const g=this.countryDecor,c=COUNTRIES[country];
    if(['farmland','tropical'].includes(c.landscape)) {
      for(let row=0;row<5;row++)for(let col=0;col<6;col++){
        const x=-37+col*3,z=-18-row*2.3;
        box(g,[2.8,.1,1.8],[x,1,z],'#889367');
        if(c.landscape==='tropical')this.tree(g,x,z,.48,true);
        else for(let j=0;j<3;j++)cylinder(g,.22,.7,[x+j*.65-.65,1.4,z],'#d5bd70',5,.1);
      }
    } else if(c.landscape==='mountain') {
      for(let i=0;i<5;i++){const m=new T.Mesh(new T.ConeGeometry(4+i%2,5+i%3,5),material(i%2?'#8c9794':'#9ba59f'));m.position.set(-38+i*5,3,-25-i%2*5);m.castShadow=true;g.add(m);}
      box(g,[5,2,4],[-30,2,-16],'#7d8984');
    } else if(c.landscape==='desert') {
      for(let i=0;i<3;i++) {
        cylinder(g,2,4,[-34+i*5,3,-20],'#b9bba7',16);cylinder(g,2.08,.22,[-34+i*5,5.1,-20],'#d2cfb1',16);
        beam(g,[-34+i*5,1,-25],[-34+i*5,6,-25],.25,'#665f4d');beam(g,[-36+i*5,6,-25],[-31+i*5,6.8,-25],.28,'#a27948');
      }
    } else if(c.landscape==='industrial') {const f=makeFactory();f.position.set(-30,1,-21);g.add(f);}
    else for(let i=0;i<5;i++) {box(g,[3.2,4+i%3*2,4],[-37+i*4,3+i%3,-21],'#b7c6b8');box(g,[3.3,.25,4.1],[-37+i*4,5.1+i%3*2,-21],'#64888b');}
    const flag=cylinder(g,.065,7,[-39,4.5,12],'#536c66',6);flag.name='national-flag';box(g,[2.5,1.4,.07],[-37.8,7,12],c.color);
    if(stage===4)for(let i=0;i<3;i++){cylinder(g,.09,6,[-8+i*4,4,-17],'#d7ddc4',6);for(let j=0;j<3;j++){const blade=box(g,[.14,2.8,.18],[-8+i*4,7,-17],'#e3e5d1');blade.rotation.z=j*Math.PI*2/3;}}
  }
  focus(kind) {
    const targets={overview:[[86,88,111],[0,0,0]],warehouse:[[-40,31,38],[-20,4,4]],dock:[[22,29,57],[-6,1,25]],ship:[[38,23,68],[17,4,39]],plane:[[45,25,5],[22,2,-20]],truck:[[14,15,12],[0,2,-7]]};
    if(kind==='overview')return this.resetCamera();
    const [pos,target]=targets[kind]||targets.overview;this.camera.position.set(...pos);this.controls.target.set(...target);this.controls.update();
  }
  pick(e) {
    if(!this.pointerStart||Math.hypot(e.clientX-this.pointerStart[0],e.clientY-this.pointerStart[1])>5)return;
    const r=this.renderer.domElement.getBoundingClientRect();const ray=new T.Raycaster();ray.setFromCamera(new T.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),this.camera);
    for(const hit of ray.intersectObjects(this.dynamic.children,true)){let obj=hit.object;while(obj&&!obj.userData.detail)obj=obj.parent;if(obj?.userData.detail){this.onSelect(obj.userData.detail);return;}}
  }
  frame() {
    const dt=Math.min(this.clock.getDelta(),.05);
    if(this.destroyed||!this.visible||document.hidden)return;
    this.controls.update();
    if(!this.reduced&&!this.state?.paused){this.elapsed+=dt;this.water.material.uniforms.time.value=this.elapsed;if(this.ship){this.ship.rotation.z=Math.sin(this.elapsed*.65)*.008;this.ship.position.y=(this.state.machine===1?-.8:-1.3)+Math.sin(this.elapsed*.9)*.05;}if(this.truck)this.truck.position.x=-3+Math.sin(this.elapsed*.09)*27;}
    this.renderer.render(this.scene,this.camera);
  }
  dispose() {
    this.destroyed=true;this.renderer.setAnimationLoop(null);this.resizeObserver.disconnect();this.intersectionObserver.disconnect();this.controls.dispose();
    this.renderer.domElement.removeEventListener('pointerdown',this.pickDown);this.renderer.domElement.removeEventListener('pointerup',this.pickUp);this.renderer.domElement.removeEventListener('webglcontextlost',this.contextLost);
    const geometries=new Set(),materials=new Set(),textures=new Set();
    const collect=root=>root.traverse(o=>{if(o.isMesh){geometries.add(o.geometry);for(const m of [].concat(o.material)){materials.add(m);for(const value of Object.values(m))if(value?.isTexture)textures.add(value);}}});
    collect(this.scene);for(const p of this.prototypes.values())collect(p);
    for(const g of geometries)g.dispose();for(const m of materials)m.dispose();for(const t of textures)t.dispose();
    this.renderer.dispose();this.renderer.domElement.remove();
  }
}
