import * as T from '../assets/three/three.module.js';

import { plantCoast } from './coastal-grove.js';

const materialRoot = new URL('../assets/map/materials/', import.meta.url);
const props = new URL('../assets/map/props/', import.meta.url);
let textures;

// Shared photographic tiles use world units, including on vertical quay walls.
export function harborTextures() {
  if (!textures) {
    const loader = new T.TextureLoader();
    textures = Object.fromEntries(Object.entries({
      grass: 'aerial_grass_rock', earth: 'brown_mud', paving: 'cobblestone_floor_01', rock: 'rock_face_03',
    }).map(([key, name]) => {
      const texture = loader.load(new URL(name + '.webp', materialRoot).href);
      texture.colorSpace = T.SRGBColorSpace;
      texture.wrapS = texture.wrapT = T.RepeatWrapping;
      texture.anisotropy = 4;
      return [key, texture];
    }));
  }
  return textures;
}

function pavedBlock(parent, x, z, width, depth, bottom, top, material) {
  const geometry = new T.BoxGeometry(width, top - bottom, depth);
  const { position, normal, uv } = geometry.attributes;
  for (let i = 0; i < position.count; i++) {
    const px = position.getX(i) + x, pz = position.getZ(i) + z;
    const py = position.getY(i) + (bottom + top) / 2;
    uv.setXY(i, (Math.abs(normal.getX(i)) > .5 ? pz : px) * 2,
      (Math.abs(normal.getY(i)) > .5 ? pz : py) * 2);
  }
  const mesh = new T.Mesh(geometry, material);
  mesh.position.set(x, (bottom + top) / 2, z);
  mesh.receiveShadow = mesh.castShadow = true;
  parent.add(mesh);
  return mesh;
}

// Straight spars, shrouds and cables share precise attachment points.
function span(atlas, group, a, b, radius, color, ends = radius) {
  const start = new T.Vector3(...a), end = new T.Vector3(...b);
  const direction = end.clone().sub(start);
  const middle = start.addScaledVector(direction, .5);
  const pole = atlas.mesh(group, new T.CylinderGeometry(ends, radius, direction.length(), 8), color, middle.x, middle.y, middle.z);
  pole.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), direction.normalize());
}

function buildDerrick(atlas, group) {
  const timber = '#755039', metal = '#433e35', cord = '#675c49';
  const head = [-2.50, 1.18, -.54], boom = [-3.04, .99, -.83];
  atlas.box(group, [.25, .075, .25], [-2.50, .277, -.54], metal);
  span(atlas, group, [-2.50,.31,-.54], head, .04, timber, .027);
  span(atlas, group, [-2.50,.43,-.54], boom, .033, timber, .024);
  span(atlas, group, head, boom, .009, cord);
  span(atlas, group, boom, [-3.04,.52,-.83], .006, metal);
  for (const anchor of [[-2.09,.26,-.22],[-2.13,.26,-.91]]) span(atlas, group, head, anchor, .007, cord);
  const drum = atlas.mesh(group,new T.CylinderGeometry(.055,.055,.14,12),metal,-2.37,.35,-.54);
  drum.rotation.z = Math.PI / 2;
  const hook = atlas.mesh(group,new T.TorusGeometry(.026,.006,5,12,Math.PI*1.6),metal,-3.04,.50,-.83);
  hook.rotation.z = -.4;
}

function handcart(atlas, yard, x, z) {
  const cart = new T.Group();
  cart.position.set(x,.77,z); cart.rotation.y = -.37; yard.add(cart);
  for (let i=0;i<5;i++) atlas.box(cart,[.042,.026,.39],[(i-2)*.046,.105,0],'#79573b');
  for (const side of [-1,1]) {
    span(atlas,cart,[side*.094,.11,.15],[side*.09,.135,.39],.012,'#654833');
    const wheel = atlas.mesh(cart,new T.TorusGeometry(.092,.014,6,16),'#504639',side*.144,.094,-.035);
    wheel.rotation.y=Math.PI/2;
    for (let n=0;n<3;n++) {
      const dy=.087*Math.sin(n*Math.PI/3), dz=.087*Math.cos(n*Math.PI/3);
      span(atlas,cart,[side*.144,.094-dy,-.035-dz],[side*.144,.094+dy,-.035+dz],.006,'#8c6946');
    }
  }
}

function buildHarborStreet(atlas, yard, paving) {
  // The office forecourt connects the low quay to the rear of the packing terrace.
  pavedBlock(yard,.09,-2.18,2.9,1.18,-.51,.25,paving);
  pavedBlock(yard,-1.48,-1.83,.50,.43,-.30,.25,paving);
  atlas.asset(yard,'customs-office',1.10,[.72,.254,-2.22],.08,undefined,null,props);
  atlas.asset(yard,'dock-cottage',.64,[-.94,.254,-2.26],-.12,undefined,null,props);
  atlas.asset(yard,'dock-cottage',.60,[-.19,.254,-2.43],.12,undefined,null,props);
  // Steps beside the later air apron keep this access in all three eras.
  for (let i=0;i<8;i++) {
    pavedBlock(yard,1.70,-1.92+i*.145,.32,.15,-.14,.31+i*.065,paving);
  }
  pavedBlock(yard,1.53,-2.02,.64,.35,-.16,.25,paving);
}

export function buildExportYard(atlas, entry) {
  const yard = new T.Group();
  yard.name = 'tropia-export-yard';
  yard.position.y = -entry.spec.ground;
  entry.group.add(yard);
  const paving = new T.MeshStandardMaterial({ map: harborTextures().paving, color: '#d8c7ac', roughness: .96 });
  // Two working levels: high packing terrace and low quay at the water.
  pavedBlock(yard, .22, .36, 3.22, 2.46, -.03, .77, paving);
  pavedBlock(yard, -2.18, -.72, 1.48, 2.25, -.58, .24, paving);
  const ramp = pavedBlock(yard, -1.6, -.46, 1.42, .52, -.09, .06, paving);
  ramp.rotation.z = .42;
  ramp.position.y = .49;
  const stone = '#a09173', iron = '#373d3a';
  // Coping stones and mooring bollards break up the silhouette of the quay.
  for (let i = 0; i < 10; i++) {
    atlas.box(yard, [.12, .07, .214], [-2.9, .265, -1.72 + i * .223], stone);
  }
  for (const z of [-1.55, -.64, .25]) {
    atlas.mesh(yard, new T.CylinderGeometry(.037, .048, .13, 10), iron, -2.82, .355, z);
    atlas.mesh(yard, new T.CylinderGeometry(.058, .056, .028, 10), iron, -2.82, .429, z);
  }
  for (const x of [-1.19, .15, 1.62]) {
    atlas.mesh(yard, new T.CylinderGeometry(.015, .026, .42, 8), iron, x, .98, 1.48);
    atlas.box(yard, [.076, .094, .076], [x, 1.225, 1.48], '#e4c791');
    atlas.mesh(yard, new T.ConeGeometry(.071, .06, 4), iron, x, 1.3, 1.48);
  }
  atlas.asset(yard, 'packing-shed', 1.38, [-.55, .773, .93], Math.PI / 2, undefined, null, props);
  handcart(atlas,yard,.45,1.15);
  // Low timber rails beside the loading platform leave an opening to the farm.
  for (const [start,end] of [[-1.32,-.23],[.67,1.8]]) {
    for (const x of [start,(start+end)/2,end]) atlas.box(yard,[.045,.22,.045],[x,.875,1.56],'#725239');
    for (const y of [.845,.93]) span(atlas,yard,[start,y,1.56],[end,y,1.56],.014,'#94704b');
  }
  buildHarborStreet(atlas, yard, paving);
  entry.grove = plantCoast(yard, entry.spec.groveSites || []);
  return yard;
}

function dockWorker(atlas, group, x, y, z, angle, shirt) {
  const figure = new T.Group();
  figure.position.set(x,y,z); figure.rotation.y = angle; group.add(figure);
  const skin = '#b28766', trousers = '#424b50';
  for (const side of [-1,1]) {
    span(atlas,figure,[side*.014,.077,0],[side*.023,.01,side*.012],.012,trousers);
    span(atlas,figure,[side*.027,.123,0],[side*.031,.091,.017],.009,shirt);
    span(atlas,figure,[side*.031,.091,.017],[side*.024,.102,.043],.007,skin);
  }
  atlas.mesh(figure,new T.CylinderGeometry(.031,.022,.06,8),shirt,0,.104,0);
  atlas.mesh(figure,new T.SphereGeometry(.020,8,6),skin,0,.151,0);
  atlas.mesh(figure,new T.CylinderGeometry(.020,.029,.011,10),'#ad946d',0,.167,0);
}

export function loadExportCargo(atlas, yard) {
  const group = new T.Group();
  yard.add(group);
  for (const [x, y, z, size, angle] of [
    [-1.16, .773, .33, .28, .08], [-.81, .773, .28, .24, -.25],
    [-2.54, .24, -.98, .34, .09], [-2.15, .24, -1.35, .30, -.22],
    [-2.6, .24, .12, .22, .35],
  ]) atlas.asset(group, 'banana-cargo', size, [x, y, z], angle, undefined, null, props);
  dockWorker(atlas,group,-1.01,.77,.55,-.8,'#e6dcc5');
  dockWorker(atlas,group,-2.30,.24,-1.01,.5,'#647c82');
  dockWorker(atlas,group,.13,.77,.73,1.2,'#a26748');
  return group;
}

export function equipExportYard(atlas, entry, stage, models, current) {
  const group = entry.assets;
  atlas.asset(group, models.warehouse, 1.62, [.68, .77, -.3], Math.PI / 2, current);
  if (stage) atlas.asset(group, models.truck, .47, [.91, .775, .71], -.12, current);
  else atlas.asset(group, 'banana-lorry', .57, [.91, .775, .71], Math.PI / 2, current, null, props);
  if (stage) atlas.asset(group, 'gantry-crane', .71, [-2.45, .24, -.39], -1.1, current);
  else buildDerrick(atlas, group);
  // The berth runs parallel to the coastline. Its deck meets the lower apron.
  atlas.asset(entry.port, models.dock, 1.72, [0, -.52, .08], 0, current, .77);
  atlas.asset(entry.port, models.ship, 2.48, [-.81, -.55, .04], Math.PI / 2, current, stage ? null : .91);
  if (!stage) {
    for (const direction of [-1,1]) {
      const rope = new T.QuadraticBezierCurve3(
        new T.Vector3(-.66,-.12,direction*.86),
        new T.Vector3(-.52,-.16,direction*.73),
        new T.Vector3(-.31,.20,direction*.57),
      );
      atlas.mesh(entry.port,new T.TubeGeometry(rope,9,.008,5,false),'#9b8666');
    }
  }
  if (stage) atlas.asset(group, 'factory', .88, [1.38, .77, 1.14], 0, current);
  if (models.plane) {
    const apron = new T.MeshStandardMaterial({ color: '#817e6e', roughness: .95 });
    pavedBlock(group, .12, -1.3, 2.9, .93, .01, .77, apron);
    for (let i=0;i<6;i++) atlas.box(group,[.19,.008,.035],[-1+i*.45,.775,-1.35],'#c5bca2');
    atlas.asset(group, models.plane, .72, [.36, .78, -1.27], .12, current);
  }
}
