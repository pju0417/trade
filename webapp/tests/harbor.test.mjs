import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { projectHarborState, demoState, COUNTRIES } from '../js/harbor-state.js';
const assets=new URL('../assets/harbor/',import.meta.url);
test('development reads actual industrial level, not round or cash',()=>{
  const s=demoState('Tropia',1);s.round=9;s.cash=99999;
  assert.equal(projectHarborState(s).stage,1);
  s.levels.banana=4;assert.equal(projectHarborState(s).stage,4);
});
test('imported technology is visible only while held; another country market listing does not upgrade us',()=>{
  const s=demoState();s.market=[{good:'machine',gen:3,qty:50}];
  assert.equal(projectHarborState(s).machine,1);
  s.stock=[{good:'machine',gen:3,free:1},{good:'electronics',gen:2,free:1}];
  assert.equal(projectHarborState(s).machine,3);assert.equal(projectHarborState(s).electronics,2);
  s.stock[0].free=0;s.stock[0].listed=1;assert.equal(projectHarborState(s).machine,1);
});
test('all six countries and four development stages are safe, bounded, and do not mutate engine state',()=>{
  for(const country of Object.keys(COUNTRIES))for(let stage=1;stage<=4;stage++){
    const s=demoState(country,stage,3,2);const before=JSON.stringify(s);
    const v=projectHarborState(s);assert.equal(v.stage,stage);assert.equal(v.machine,3);assert.equal(v.electronics,2);assert.equal(v.country,country);assert.equal(JSON.stringify(s),before);
  }
  assert.equal(projectHarborState({country:'unknown',levels:{banana:99}}).stage,4);
  assert.equal(projectHarborState().stage,1);
});
test('pausing, shortages and transactions are projected without adding rules',()=>{
  const s=demoState();s.room={paused:true};s.settlement.rows=[{good:'fuel',short:1}];s.transactions_this_round=[{channel:'barter'}];
  const v=projectHarborState(s);assert.equal(v.paused,true);assert.equal(v.shortage,true);assert.equal(v.tradeCount,1);
});
test('all 18 assets load, use finite geometry, embed their data, and fit a classroom download budget',async()=>{
  const io=new NodeIO().registerExtensions(ALL_EXTENSIONS);
  const generated=JSON.parse(await fs.readFile(new URL('generated-models.json',assets)));
  const optimized=JSON.parse(await fs.readFile(new URL('optimization-report.json',assets)));
  assert.equal(generated.length,15);assert.equal(optimized.length,3);
  let bytes=0;
  for(const row of [...optimized,...generated]){
    const file=new URL(row.file,assets);const b=await fs.readFile(file);bytes+=b.length;
    assert.equal(b.readUInt32LE(0),0x46546c67);assert.equal(b.readUInt32LE(8),b.length);
    const json=JSON.parse(b.subarray(20,20+b.readUInt32LE(12)).toString());
    assert.ok(!(json.buffers||[]).some(x=>x.uri));assert.ok(!(json.images||[]).some(x=>x.uri));
    const doc=await io.read(fileURLToPath(file));
    assert.ok(doc.getRoot().listMeshes().length>0);
    for(const mesh of doc.getRoot().listMeshes())for(const p of mesh.listPrimitives()){
      assert.ok(p.getAttribute('POSITION').getCount()>0);
      for(const n of p.getAttribute('POSITION').getArray())assert.ok(Number.isFinite(n));
    }
    if(row.originalBytes){assert.ok(row.bytes<row.originalBytes*.1);assert.ok(row.triangles<50000);}
  }
  assert.ok(bytes<8*1024*1024,`Combined models: ${bytes} bytes`);
});
