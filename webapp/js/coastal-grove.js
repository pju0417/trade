import * as T from '../assets/three/three.module.js';

// One curved crown shared by coastal palms, with folded blades and separated tips.
function crownGeometry() {
  const positions = [], colors = [], indices = [];
  const green = new T.Color();
  function vertex(point, shade) {
    positions.push(...point);
    green.setRGB(.055 * shade, .215 * shade, .065 * shade);
    colors.push(green.r, green.g, green.b);
    return positions.length / 3 - 1;
  }
  for (let leaf = 0; leaf < 13; leaf++) {
    const angle = leaf * 2.4;
    const length = .45 + (leaf % 4) * .052;
    const height = .22 + (leaf % 3) * .055;
    const dx = Math.cos(angle), dz = Math.sin(angle);
    const axis = t => [dx * length * t, Math.sin(t * Math.PI) * height - t * t * .13, dz * length * t];
    for (let step = 0; step < 11; step++) {
      const t = step / 11, next = (step + 1) / 11;
      const a = axis(t), b = axis(next);
      const w = (.019 + Math.sin(next * Math.PI) * .10) * (1 - t * .3);
      for (const side of [-1, 1]) {
        const tip = axis(Math.min(1.08, next + .115));
        tip[0] -= dz * w * side; tip[1] -= w * .45; tip[2] += dx * w * side;
        indices.push(vertex(a, .77), vertex(tip, 1.18 + .12 * side), vertex(b, .95));
      }
    }
  }
  const g = new T.BufferGeometry();
  g.setAttribute('position', new T.Float32BufferAttribute(positions, 3));
  g.setAttribute('color', new T.Float32BufferAttribute(colors, 3));
  g.setIndex(indices); g.computeVertexNormals();
  return g;
}

export function plantCoast(yard, sites) {
  const leaves = new T.MeshStandardMaterial({ vertexColors: true, side: T.DoubleSide, roughness: .85 });
  const bark = new T.MeshStandardMaterial({ color: '#857554', roughness: 1 });
  const greenery = new T.Group();
  greenery.name = 'coastal-grove'; yard.add(greenery);
  const crowns = new T.InstancedMesh(crownGeometry(), leaves, sites.length);
  const trunks = new T.InstancedMesh(new T.CylinderGeometry(.031, .054, 1, 8, 3), bark, sites.length);
  const brush = new T.InstancedMesh(crowns.geometry, leaves, sites.length * 2);
  const stone = new T.InstancedMesh(new T.DodecahedronGeometry(.19, 0), new T.MeshStandardMaterial({ color: '#706e5d', roughness: 1 }), sites.length);
  const transform = new T.Object3D();
  let tall = 0, low = 0, stones = 0;
  function place(mesh, index, x, y, z, sx, sy, sz, angle, lean = 0) {
    transform.position.set(x, y, z); transform.scale.set(sx, sy, sz);
    transform.rotation.set(0, angle, lean, 'YXZ'); transform.updateMatrix();
    mesh.setMatrixAt(index, transform.matrix);
  }
  sites.forEach(([x,y,z], i) => {
    const angle = i * 2.39996, size = .7 + .34 * Math.sin(i * 17);
    if (i % 3 !== 1 && y > -.03) {
      const height = .72 + .35 * Math.cos(i * 5);
      const lean = .13 * Math.sin(i * 3);
      const offset = -Math.sin(lean) * height;
      place(trunks, tall, x + Math.cos(angle) * offset / 2, y + height / 2, z - Math.sin(angle) * offset / 2, size, height, size, angle, lean);
      place(crowns, tall++, x + Math.cos(angle) * offset, y + height * Math.cos(lean), z - Math.sin(angle) * offset, size, size, size, angle);
    } else {
      place(stone, stones++, x, y + .015, z, size * 1.57, size * .61, size, angle);
    }
    for (let k = 0; k < 2; k++) {
      const a = angle + k * 2;
      place(brush, low++, x + .23 * Math.cos(a), y + .035, z + .23 * Math.sin(a), .36, .62, .32, a);
    }
  });
  crowns.count = trunks.count = tall; brush.count = low; stone.count = stones;
  for (const mesh of [trunks, crowns, brush, stone]) {
    mesh.castShadow = mesh.receiveShadow = true;
    greenery.add(mesh);
  }
  return greenery;
}
