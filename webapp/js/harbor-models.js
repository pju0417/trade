import * as T from 'three';

// Reusable, original low-poly props. All models are also exported as independent GLBs.
const mats = new Map();
export function material(color, metalness = 0) {
  const key = color + ':' + metalness;
  if (!mats.has(key)) mats.set(key, new T.MeshStandardMaterial({ color, roughness: .77, metalness }));
  return mats.get(key);
}
export function box(parent, size, pos, color, rotation = 0) {
  const m = new T.Mesh(new T.BoxGeometry(...size), material(color));
  m.position.set(...pos); m.rotation.y = rotation; m.castShadow = true; m.receiveShadow = true; parent.add(m); return m;
}
export function cylinder(parent, radius, height, pos, color, sides = 12, top = radius) {
  const m = new T.Mesh(new T.CylinderGeometry(top, radius, height, sides), material(color));
  m.position.set(...pos); m.castShadow = true; m.receiveShadow = true; parent.add(m); return m;
}
export function beam(parent, a, b, width, color) {
  const from = new T.Vector3(...a), to = new T.Vector3(...b);
  const m = box(parent, [width, from.distanceTo(to), width], from.clone().add(to).multiplyScalar(.5).toArray(), color);
  m.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), to.sub(from).normalize()); return m;
}
export function container(parent, pos, color, length = 4.6) {
  const g = new T.Group(); g.position.set(...pos); parent.add(g);
  box(g, [length, 2, 2.1], [0, 1, 0], color);
  for (let i = -length / 2 + .2; i < length / 2; i += .38) for (const z of [-1.07, 1.07]) box(g, [.045, 1.84, .035], [i, 1, z], color);
  for (const x of [-length/2-.015, length/2+.015]) {
    box(g, [.05, 1.9, .035], [x, 1, 0], '#8d9b9c');
    for (const z of [-.7, .7]) box(g, [.05, 1.65, .04], [x, 1, z], '#bdc6c6');
  }
  return g;
}
export function makeCrane(modern = false) {
  const g = new T.Group(); g.name = modern ? 'gantry-crane' : 'harbor-crane';
  const color = modern ? '#e6b74f' : '#597b87';
  if (modern) {
    for (const x of [-3, 3]) for (const z of [-2.2, 2.2]) {
      box(g, [.5, 12, .5], [x, 6, z], color);
      box(g, [1.9, .5, 1], [x, .4, z], '#2a414a');
    }
    box(g, [7, .65, 5.3], [0, 12, 0], color);
    for (const x of [-2.5, 2.5]) box(g, [.4, .5, 17], [x, 12.7, 4], color);
    box(g, [5.7, .5, .6], [0, 12.7, 12], color);
    box(g, [1.6, 1.2, 1.5], [-2.5, 11.9, 5], '#e8ede5');
    for (const x of [-1.9, 1.9]) beam(g, [x, 12.6, 8], [x, 5, 8], .055, '#344e58');
    box(g, [4.8, .3, 2.4], [0, 5, 8], '#e6b74f');
  } else {
    cylinder(g, 1.6, .6, [0, .3, 0], '#344851');
    for (const x of [-.7, .7]) for (const z of [-.7, .7]) beam(g, [x, .6, z], [x*.35, 8, z*.35], .18, color);
    box(g, [1.7, 1.5, 1.7], [0, 8, 0], color);
    beam(g, [0, 8.4, 0], [0, 11, 6], .3, color);
    beam(g, [0, 9, -2], [0, 11, 6], .07, '#33454e');
    beam(g, [0, 11, 6], [0, 3, 6], .045, '#33454e');
    box(g, [.8, .25, .8], [0, 3, 6], '#e6b74f');
  }
  return g;
}
export function makeTruck(gen = 1) {
  const g = new T.Group(); g.name = ['early-truck', 'diesel-truck', 'electric-truck'][gen-1];
  const color = ['#a75a39', '#e7ad4e', '#dbe7df'][gen-1];
  box(g, [5.2, .35, 1.9], [0, .8, 0], '#263e48');
  box(g, [1.8, 1.5, 1.85], [1.5, 1.6, 0], color);
  box(g, [.05, .65, 1.5], [2.42, 1.9, 0], '#7fa5ac');
  for (const z of [-.945, .945]) box(g, [1.1, .65, .035], [1.45, 1.95, z], '#7fa5ac');
  box(g, [gen === 1 ? 2.9 : 3.1, gen === 1 ? .7 : 1.85, 1.85], [-1, gen === 1 ? 1.35 : 1.8, 0], gen === 1 ? '#90704c' : color);
  if (gen === 1) for (const z of [-.96, .96]) for (const y of [1.1, 1.4, 1.7]) box(g, [3, .12, .08], [-1, y, z], '#b6986f');
  if (gen === 3) { box(g, [3.2, .22, 1.8], [-1, 2.88, 0], '#3b6267'); box(g, [.3, 1, 1.9], [.65, 1.7, 0], '#6a9c8a'); }
  for (const x of [-1.65, 1.7]) for (const z of [-1, 1]) {
    const wheel = cylinder(g, .52, .25, [x, .57, z], '#253a42'); wheel.rotation.x = Math.PI/2;
    const hub = cylinder(g, .24, .27, [x, .57, z], '#b4beb5'); hub.rotation.x = Math.PI/2;
  }
  for (const z of [-.6, .6]) box(g, [.08, .22, .28], [2.43, 1.2, z], '#fbe7ad');
  return g;
}
export function makeShip(gen = 2) {
  const g = new T.Group(); g.name = gen === 2 ? 'diesel-freighter' : 'container-ship';
  const outline = new T.Shape(); outline.moveTo(-11, -1.8); outline.lineTo(-9, -2.7); outline.lineTo(7.5, -2.7); outline.lineTo(12, 0); outline.lineTo(7.5, 2.7); outline.lineTo(-9, 2.7); outline.lineTo(-11, 1.8); outline.closePath();
  const geo = new T.ExtrudeGeometry(outline, { depth: 2.8, bevelEnabled: true, bevelSize: .45, bevelThickness: .3, bevelSegments: 1, steps: 1 });
  geo.rotateX(-Math.PI/2);
  const hull = new T.Mesh(geo, material(gen === 2 ? '#345664' : '#294b5a')); hull.position.y = -.6; hull.castShadow=true; g.add(hull);
  box(g, [17.5, .2, 4.7], [-1, 2.3, 0], '#c2ab7c');
  box(g, [3.5, 3, 4.2], [-7.5, 3.8, 0], '#e6e5d5');
  box(g, [4, 1.1, 4.8], [-7.5, 5.8, 0], '#e6e5d5');
  for (const z of [-2.42, 2.42]) box(g, [3.2, .5, .04], [-7.5, 5.9, z], '#5b8997');
  cylinder(g, .6, 2.3, [-8, 7, 0], '#bf7443');
  if (gen === 3) {
    const colors = ['#ba654b', '#5e9295', '#d9b059', '#6a8299'];
    for (let i=0;i<3;i++) for (let j=0;j<2;j++) for (let k=0;k<2;k++) container(g, [-2+i*4.7, 2.4+k*2.05, -1.1+j*2.2], colors[(i+j+k)%4], 4.5);
  } else {
    for (const x of [-1, 5]) box(g, [4.5, .45, 3.8], [x, 2.7, 0], '#925f46');
    for (const x of [-3.5, 6.5]) { cylinder(g, .12, 7, [x, 5.8, 0], '#d9c498'); beam(g, [x, 8.8, 0], [x+3.5, 6.5, 0], .17, '#d9c498'); }
  }
  for (const z of [-2.5, 2.5]) for (let x=-10;x<8;x+=1.5) cylinder(g, .045, .7, [x, 2.75, z], '#e1d7bd', 6);
  return g;
}
export function makePlane(gen = 1) {
  const g = new T.Group(); g.name = ['biplane', 'turboprop', 'cargo-jet'][gen-1];
  const color = gen === 1 ? '#d4ad60' : '#e9e6d9';
  const body = cylinder(g, gen===1?.46:.7, gen===1?5:8, [0, 1.4, 0], color, 12, .2); body.rotation.z = -Math.PI/2;
  box(g, [gen===1?1.4:2.4, .15, gen===1?6.8:11], [-.3, 1.4, 0], color);
  if (gen===1) {
    box(g, [1.4, .13, 6.8], [-.3, 2.65, 0], color);
    for(const z of [-2.3,2.3]) for(const x of [-.8,.2]) beam(g,[x,1.4,z],[x,2.65,z],.045,'#604d3b');
  }
  box(g, [1.1, .12, 3.2], [-2.5, 1.7, 0], color);
  box(g, [1, 1.4, .12], [-2.6, 2.15, 0], '#538a91');
  box(g, [1.1,.35,.9], [.7,1.95,0], '#5b8791');
  const engines = gen===1 ? [0] : [-2.8,2.8];
  for(const z of engines) {
    const e = cylinder(g, gen===3?.47:.25, 1.7, [gen===1?2.5:.6,1.1,z], '#406571'); e.rotation.z=Math.PI/2;
    if(gen<3) box(g,[.08,2.1,.12],[gen===1?2.9:1.6,1.1,z],'#4b4b3d');
  }
  for(const z of [-.8,.8]) {const w=cylinder(g,.25,.18,[.4,.3,z],'#263e48');w.rotation.x=Math.PI/2;beam(g,[.4,.4,z],[.2,1.2,0],.08,'#445663');}
  return g;
}
export function makeWarehouse(smart = false) {
  const g = new T.Group(); g.name = smart ? 'smart-warehouse' : 'modern-warehouse';
  box(g, [15, 5, 9], [0, 2.5, 0], '#c3d0c8');
  const roof=box(g,[16,.35,10],[0,5.1,0],'#617d7d');
  for(let x=-5;x<=5;x+=5) {
    box(g,[3,3.3,.12],[x,1.65,4.57],'#496875');
    for(let y=.6;y<3.3;y+=.5) box(g,[2.9,.04,.15],[x,y,4.6],'#8ca09f');
    box(g,[3.6,.22,1.4],[x,.3,5],'#71827b');
  }
  for(let x=-6;x<7;x+=2) box(g,[1.3,.8,.04],[x,4.1,4.56],'#6c9fab');
  if(smart) {
    for(let x=-5;x<=5;x+=2.5) for(const z of [-2,1.6]) box(g,[2.1,.12,2.7],[x,5.35,z],'#305362');
    cylinder(g,.18,2.5,[6,6.3,3],'#e5e5cf'); box(g,[1.2,.12,.7],[6,7.6,3],'#7dbbba');
  }
  roof.name='roof'; return g;
}
export function makeDock(smart = false) {
  const g = new T.Group(); g.name = smart ? 'smart-quay' : 'concrete-quay';
  box(g,[12,1.5,21],[0,-.75,0],'#9ba59d');
  for(const x of [-6.05,6.05]) for(let z=-9;z<11;z+=3) {box(g,[.4,.75,.6],[x,-.5,z],'#344b50');cylinder(g,.18,.45,[x*.92,.2,z],'#dfb453');}
  for(let z=-9;z<10;z+=2) box(g,[.2,.02,.9],[0,.015,z],smart?'#74d7c4':'#ecd29a');
  return g;
}
export function makeFactory() {
  const g = new T.Group(); g.name='factory';
  box(g,[9,3.6,6],[0,1.8,0],'#9d7760');
  for(const x of [-2.3,2.3]) {const r=box(g,[4.2,.35,6.4],[x,4,0],'#4b6d70');r.rotation.z=.12;}
  for(let x=-3;x<=3;x+=1.5) box(g,[.85,1,.08],[x,2,3.05],'#b4d6cb');
  for(const x of [-3,-1.5]) cylinder(g,.5,7,[x,3.5,-1.8],'#977963');
  return g;
}
export const MODEL_BUILDERS = {
  'harbor-crane':()=>makeCrane(false), 'gantry-crane':()=>makeCrane(true),
  'early-truck':()=>makeTruck(1), 'diesel-truck':()=>makeTruck(2), 'electric-truck':()=>makeTruck(3),
  'diesel-freighter':()=>makeShip(2), 'container-ship':()=>makeShip(3),
  'biplane':()=>makePlane(1), 'turboprop':()=>makePlane(2), 'cargo-jet':()=>makePlane(3),
  'modern-warehouse':()=>makeWarehouse(false), 'smart-warehouse':()=>makeWarehouse(true),
  'concrete-quay':()=>makeDock(false), 'smart-quay':()=>makeDock(true), 'factory':()=>makeFactory(),
};
