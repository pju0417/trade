import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, prune, weld, simplify, textureCompress } from '@gltf-transform/functions';
import { MeshoptSimplifier } from 'meshoptimizer';
import sharp from 'sharp';

const root = fileURLToPath(new URL('../', import.meta.url));
const out = path.join(root, 'webapp/assets/harbor');
await fs.mkdir(out, { recursive: true });
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
await MeshoptSimplifier.ready;
const report = [];
const triangles = doc => doc.getRoot().listMeshes().reduce((n, m) => n + m.listPrimitives().reduce((v, p) => v + (p.getIndices()?.getCount() ?? p.getAttribute('POSITION').getCount()) / 3, 0), 0);
for (const [source, name] of [['벽돌창고.glb', 'brick-warehouse'], ['목재 부두.glb', 'timber-pier'], ['소형 증기 화물선.glb', 'steam-freighter']]) {
  const input = path.resolve(root, '..', source);
  const output = path.join(out, `${name}.glb`);
  const doc = await io.read(input);
  const before = triangles(doc);
  // Original exports contain about two million triangles each. Preserve the originals.
  await doc.transform(dedup(), weld(), simplify({ simplifier: MeshoptSimplifier, ratio: 0.018, error: 0.008 }), prune(), textureCompress({ encoder: sharp, resize: [1024, 1024], targetFormat: 'webp', quality: 82 }));
  await io.write(output, doc);
  const entry = { source, file: `${name}.glb`, originalBytes: (await fs.stat(input)).size, bytes: (await fs.stat(output)).size, originalTriangles: before, triangles: triangles(doc) };
  report.push(entry);
  console.log(JSON.stringify(entry));
}
await fs.writeFile(path.join(out, 'optimization-report.json'), JSON.stringify(report, null, 2) + '\n');
// Ship the rendering runtime locally: no CDN is needed during a lesson.
const vendor = path.join(root, 'webapp/vendor/three');
await fs.mkdir(path.join(vendor, 'addons/loaders'), { recursive: true });
await fs.mkdir(path.join(vendor, 'addons/controls'), { recursive: true });
await fs.mkdir(path.join(vendor, 'addons/utils'), { recursive: true });
for (const file of ['build/three.module.js', 'examples/jsm/loaders/GLTFLoader.js', 'examples/jsm/controls/OrbitControls.js', 'examples/jsm/utils/BufferGeometryUtils.js']) {
  const dest = file.replace('build/', '').replace('examples/jsm/', 'addons/');
  await fs.copyFile(path.join(root, 'node_modules/three', file), path.join(vendor, dest));
}
await fs.copyFile(path.join(root, 'node_modules/three/LICENSE'), path.join(vendor, 'LICENSE'));
