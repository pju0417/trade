import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { Document, NodeIO } from '@gltf-transform/core';
import { MODEL_BUILDERS } from '../webapp/js/harbor-models.js';
const dest=new URL('../webapp/assets/harbor/',import.meta.url);await fs.mkdir(dest,{recursive:true});
const io=new NodeIO(),manifest=[];
for(const [name,build]of Object.entries(MODEL_BUILDERS)){
  const group=build();group.updateMatrixWorld(true);
  const doc=new Document(),buffer=doc.createBuffer(),scene=doc.createScene(name),materials=new Map();
  let triangles=0;
  group.traverse(mesh=>{
    if(!mesh.isMesh)return;
    const geometry=mesh.geometry.clone().applyMatrix4(mesh.matrixWorld);
    const source=mesh.material;
    if(!materials.has(source))materials.set(source,doc.createMaterial().setBaseColorFactor([source.color.r,source.color.g,source.color.b,1]).setRoughnessFactor(source.roughness).setMetallicFactor(source.metalness));
    const primitive=doc.createPrimitive().setMaterial(materials.get(source));
    for(const [attr,semantic]of [['position','POSITION'],['normal','NORMAL']]){
      const a=geometry.getAttribute(attr);if(a)primitive.setAttribute(semantic,doc.createAccessor().setType('VEC3').setArray(new Float32Array(a.array)).setBuffer(buffer));
    }
    if(geometry.index)primitive.setIndices(doc.createAccessor().setType('SCALAR').setArray(new Uint32Array(geometry.index.array)).setBuffer(buffer));
    triangles+=(geometry.index?.count||geometry.getAttribute('position').count)/3;
    scene.addChild(doc.createNode(mesh.name||name).setMesh(doc.createMesh().addPrimitive(primitive)));geometry.dispose();
  });
  const file=fileURLToPath(new URL(`${name}.glb`,dest));await io.write(file,doc);
  manifest.push({name,file:`${name}.glb`,triangles,bytes:(await fs.stat(file)).size,source:'Original procedural model; Y up; units in meters; ground pivot'});
}
await fs.writeFile(new URL('generated-models.json',dest),JSON.stringify(manifest,null,2)+'\n');console.log(`Exported ${manifest.length} independent GLB models (${manifest.reduce((n,m)=>n+m.triangles,0)} triangles total).`);
