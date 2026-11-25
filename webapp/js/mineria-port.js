import * as T from '../assets/three/three.module.js';
import { harborTextures } from './tropia-port.js';

const props = new URL('../assets/map/props/', import.meta.url);
const terrain = new URL('../assets/map/terrain/', import.meta.url);
const deck = 3.28;
const trackZ = -2.03;

function beam(atlas, group, start, end, width, color) {
  const delta = new T.Vector3(...end).sub(new T.Vector3(...start));
  const center = new T.Vector3(...start).addScaledVector(delta, .5);
  const bar = atlas.box(group,[width,delta.length(),width],center.toArray(),color);
  bar.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),delta.normalize());
}

// Repeated tracks and wagon wheels share geometry, material and a draw call.
function repeat(group, geometry, material, placements) {
  const mesh = new T.InstancedMesh(geometry, material, placements.length);
  const transform = new T.Object3D();
  placements.forEach(([x,y,z,angle],i) => {
    transform.position.set(x,y,z);
    transform.rotation.set(angle || 0,0,0);
    transform.updateMatrix();
    mesh.setMatrixAt(i,transform.matrix);
  });
  mesh.castShadow = mesh.receiveShadow = true;
  group.add(mesh);
}

export function buildMineWorks(atlas, entry) {
  const yard = new T.Group();
  yard.name = 'mineria-ore-yard';
  yard.position.y = -entry.spec.ground;
  entry.group.add(yard);
  const gravel = new T.MeshStandardMaterial({map:harborTextures().earth,color:'#b5a395',roughness:.98});
  const masonry = new T.MeshStandardMaterial({map:harborTextures().paving,color:'#9b9180',roughness:1});
  const base = new T.BoxGeometry(5.3,3.88,2.14);
  const {position,normal,uv} = base.attributes;
  for (let i=0;i<position.count;i++) {
    const top = Math.abs(normal.getY(i)) > .5;
    uv.setXY(i, (Math.abs(normal.getX(i)) > .5 ? position.getZ(i) : position.getX(i)) * 1.6,
      (top ? position.getZ(i) : position.getY(i)) * 1.6);
  }
  const platform = new T.Mesh(base,[masonry,masonry,gravel,masonry,masonry,masonry]);
  platform.position.set(.03,deck-1.94,-1.92);
  platform.receiveShadow = platform.castShadow = true;
  yard.add(platform);
  for (const side of [-1,1]) atlas.box(yard,[5.2,.038,.034],[.02,deck+.047,trackZ+side*.112],'#616260');
  const ties = Array.from({length:32},(_,i)=>[-2.49+i*.16,deck+.014,trackZ]);
  repeat(yard,new T.BoxGeometry(.066,.035,.39),atlas.material('#604b36'),ties);
  const wheels = [];
  for (const x of [-.22,.42,1.06]) {
    const y = deck+.24;
    atlas.box(yard,[.46,.10,.29],[x,y-.045,trackZ],'#4d4135');
    for (const side of [-1,1]) {
      const panel = atlas.box(yard,[.54,.22,.026],[x,y+.076,trackZ+side*.176],'#89533b');
      panel.rotation.x = side*.22;
      atlas.box(yard,[.033,.20,.33],[x+side*.246,y+.07,trackZ],'#6e4834');
      for (const axle of [-.17,.17]) wheels.push([x+axle,deck+.115,trackZ+side*.128,Math.PI/2]);
    }
    const ore = atlas.mesh(yard,new T.IcosahedronGeometry(.21,0),'#5f392b',x,y+.16,trackZ);
    ore.scale.set(1.15,.52,.73);
  }
  repeat(yard,new T.CylinderGeometry(.073,.073,.044,10),atlas.material('#414448'),wheels);
  const stockpile = new T.InstancedMesh(new T.DodecahedronGeometry(1),atlas.material('#fff'),48);
  const transform = new T.Object3D();
  for (let i=0;i<stockpile.count;i++) {
    const angle = i*2.39996, radius = .36*Math.sqrt((i%16)/16);
    transform.position.set(.15+Math.floor(i/16)*.54+radius*Math.cos(angle),
      deck+.095+(.36-radius)*.59, -2.63+radius*.55*Math.sin(angle));
    transform.rotation.set(i*.52,angle,i*.71);
    transform.scale.set(.10+.03*Math.sin(i),.095,.10);
    transform.updateMatrix();
    stockpile.setMatrixAt(i,transform.matrix);
    stockpile.setColorAt(i,new T.Color(['#78442f','#62453b','#884c37','#4e4a44'][i%4]));
  }
  stockpile.castShadow = stockpile.receiveShadow = true;
  yard.add(stockpile);
  // The elevated ore line ends above the berth, with a chute down to the quay.
  for (const z of [trackZ-.26,trackZ+.26]) {
    beam(atlas,yard,[2.41,.40,z],[2.41,deck,z],.085,'#5c4938');
    beam(atlas,yard,[2.41,1.20,z],[3.08,2.52,z],.065,'#705942');
    beam(atlas,yard,[2.39,deck-.08,z],[3.76,.64,z],.09,'#826755');
  }
  const chute = atlas.box(yard,[2.91,.064,.51],[3.075,1.92,trackZ],'#56524c');
  chute.rotation.z = -1.08;
  return yard;
}

export function loadMineTerrain(atlas, yard, config) {
  const detail = new T.Group();
  detail.name = 'mineria-mine-detail';
  yard.add(detail);
  for (const [name,piece] of Object.entries(config)) {
    atlas.asset(detail,name,piece.length,piece.offset,piece.rotation,undefined,piece.height,
      name === 'ore-bench' ? terrain : props);
  }
  return detail;
}

export function equipMinePort(atlas,entry,stage,models,current) {
  const group = entry.assets;
  atlas.asset(group,models.warehouse,1.28,[.36,deck,-1.23],0,current);
  atlas.asset(group,models.truck,.46,[1.52,deck,-1.23],.12,current);
  atlas.asset(group,stage ? 'gantry-crane' : 'harbor-crane',.72,[2.15,deck,-1.32],-.3,current);
  atlas.asset(entry.port,models.dock,2.0,[0,-.56,0],0,current,.80);
  atlas.asset(entry.port,models.ship,2.85,[.95,-.55,0],Math.PI/2,current,stage ? null : .98);
  if (stage) {
    const apron=atlas.box(group,[2.45,.65,.85],[-1.69,2.51,-3.14],'#817d71');
    atlas.asset(group,models.plane,.76,[-1.55,apron.position.y+.325,-3.14],0,current);
    atlas.asset(group,'factory',.85,[-.88,deck,-1.29],0,current);
  }
}
