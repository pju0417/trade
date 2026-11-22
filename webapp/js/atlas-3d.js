import * as T from '../assets/three/three.module.js';
import { OrbitControls } from '../assets/three/addons/controls/OrbitControls.js';
import { GLTFLoader } from '../assets/three/addons/loaders/GLTFLoader.js';
import { mergeGeometries } from '../assets/three/addons/utils/BufferGeometryUtils.js';

// Local, preserved GLBs. Shared geometry/textures are loaded once across room maps.
const modelCache = new Map();
const assetRoot = new URL('../assets/harbor/', import.meta.url);
const stages = [
  { name: '증기 항구', warehouse: 'brick-warehouse', dock: 'timber-pier', ship: 'steam-freighter', truck: 'early-truck' },
  { name: '산업 항구', warehouse: 'modern-warehouse', dock: 'concrete-quay', ship: 'diesel-freighter', truck: 'diesel-truck', plane: 'biplane' },
  { name: '현대 물류 항구', warehouse: 'smart-warehouse', dock: 'smart-quay', ship: 'container-ship', truck: 'electric-truck', plane: 'cargo-jet' },
];
const colors = { market: '#f4cb74', direct: '#8af0db', barter: '#d6b0ff' };
export function stageFor(profile) {
  const level = Number(profile?.levels?.[profile?.main] || 1);
  return level >= 4 ? 2 : level >= 2 ? 1 : 0;
}
function loadModel(name) {
  if (!modelCache.has(name)) modelCache.set(name, new GLTFLoader().loadAsync(new URL(`${name}.glb`, assetRoot).href).then(gltf => {
    // These are static props: bake transforms and batch by material (403 container-ship meshes -> 12 draws).
    const batched = new T.Group(), byMaterial = new Map(), originals = new Set();
    gltf.scene.updateMatrixWorld(true);
    gltf.scene.traverse(o => {
      if (!o.isMesh) return;
      if (Array.isArray(o.material) || o.isSkinnedMesh) { batched.add(o.clone()); return; }
      let geometry = o.geometry.clone().applyMatrix4(o.matrixWorld);
      if (geometry.index) { const indexed = geometry; geometry = geometry.toNonIndexed(); indexed.dispose(); }
      for (const attribute of Object.keys(geometry.attributes)) if (!['position', 'normal', 'uv'].includes(attribute)) geometry.deleteAttribute(attribute);
      if (!geometry.attributes.normal) geometry.computeVertexNormals();
      if (!geometry.attributes.uv) geometry.setAttribute('uv', new T.BufferAttribute(new Float32Array(geometry.attributes.position.count * 2), 2));
      if (!byMaterial.has(o.material)) byMaterial.set(o.material, []);
      byMaterial.get(o.material).push(geometry); originals.add(o.geometry);
    });
    for (const [material, geometries] of byMaterial) {
      const merged = mergeGeometries(geometries);
      for (const geometry of geometries) geometry.dispose();
      batched.add(new T.Mesh(merged, material));
    }
    for (const geometry of originals) geometry.dispose();
    batched.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; o.userData.sharedAsset = true; } });
    return batched;
  }).catch(error => { modelCache.delete(name); throw error; }));
  return modelCache.get(name);
}

export class Atlas3D {
  constructor(surface, layout, { onSelect, onProject, onStatus, onFailure }) {
    this.surface = surface; this.layout = layout;
    Object.assign(this, { onSelect, onProject, onStatus, onFailure });
    this.countries = new Map(); this.routes = new Map(); this.materials = new Map();
    this.pending = new Set(); this.failures = new Set(); this.disposed = false; this.active = true;
    this.visible = true; this.dirty = true; this.elapsed = 0; this.lastFrame = 0; this.depthScale = .13;
    this.reducedQuery = matchMedia('(prefers-reduced-motion: reduce)'); this.reduced = this.reducedQuery.matches;
    this.motionChange = e => { this.reduced = e.matches; this.dirty = true; };
    this.reducedQuery.addEventListener('change', this.motionChange);
    this.scene = new T.Scene(); this.scene.background = new T.Color('#9ebfc0');
    this.scene.fog = new T.Fog('#89aeb0', 260, 480);
    this.renderer = new T.WebGLRenderer({ antialias: true, powerPreference: 'low-power' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.35));
    this.renderer.outputColorSpace = T.SRGBColorSpace;
    this.renderer.toneMapping = T.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.08;
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = T.PCFSoftShadowMap;
    this.renderer.domElement.className = 'atlas-webgl';
    this.renderer.domElement.setAttribute('aria-label', '실제 3D 세계 지도. 드래그로 회전, 두 손가락이나 휠로 확대. 나라 이름 버튼으로도 선택할 수 있어요.');
    this.renderer.domElement.setAttribute('role', 'img');
    this.surface.prepend(this.renderer.domElement);
    this.camera = new T.OrthographicCamera(-90, 90, 60, -60, .1, 600);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false; this.controls.enablePan = false;
    this.controls.minZoom = .8; this.controls.maxZoom = 3;
    this.controls.minPolarAngle = .22; this.controls.maxPolarAngle = 1.05;
    this.controls.minAzimuthAngle = -.65; this.controls.maxAzimuthAngle = .65;
    // A touch drag scrolls the classroom page; two fingers control the camera.
    this.controls.touches.ONE = null;
    this.controls.touches.TWO = T.TOUCH.DOLLY_ROTATE;
    this.renderer.domElement.style.touchAction = 'pan-y';
    this.controls.addEventListener('change', () => { this.dirty = true; });
    this.scene.add(new T.HemisphereLight('#fff4da', '#456757', 1.8));
    const sun = new T.DirectionalLight('#ffe8ba', 2.6); sun.position.set(-70, 125, 55); sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024); Object.assign(sun.shadow.camera, { left: -100, right: 100, top: 100, bottom: -100, near: 1, far: 280 });
    sun.shadow.bias = -.001; sun.shadow.normalBias = .15; this.scene.add(sun);
    this.buildWater(); this.buildCountries(); this.reset();
    this.resizeObserver = new ResizeObserver(() => this.resize()); this.resizeObserver.observe(surface);
    this.intersectionObserver = new IntersectionObserver(([e]) => { this.visible = e.isIntersecting; this.dirty = true; }); this.intersectionObserver.observe(surface);
    this.pointerDown = e => { this.pointerStart = [e.clientX, e.clientY]; };
    this.pointerUp = e => this.pick(e);
    this.contextLost = e => { e.preventDefault(); this.onFailure('3D 연결이 중단되어 2D 지도로 전환했어요. 3D 지도를 눌러 다시 시도할 수 있어요.'); this.dispose(); };
    this.renderer.domElement.addEventListener('pointerdown', this.pointerDown);
    this.renderer.domElement.addEventListener('pointerup', this.pointerUp);
    this.renderer.domElement.addEventListener('webglcontextlost', this.contextLost);
    this.resize(); this.renderer.setAnimationLoop(t => this.frame(t));
  }
  material(color, metalness = 0) {
    const key = `${color}:${metalness}`;
    if (!this.materials.has(key)) this.materials.set(key, new T.MeshStandardMaterial({ color, roughness: .84, metalness }));
    return this.materials.get(key);
  }
  mesh(parent, geometry, color, x = 0, y = 0, z = 0) {
    const mesh = new T.Mesh(geometry, this.material(color)); mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
  }
  box(parent, size, pos, color, angle = 0) {
    const m = this.mesh(parent, new T.BoxGeometry(...size), color, ...pos); m.rotation.y = angle; return m;
  }
  point(pair, height = 0) {
    const [ox, oy, width, depth] = this.layout.viewBox;
    return new T.Vector3((pair[0] - ox - width / 2) * .105, height, (pair[1] - oy - depth / 2) * this.depthScale);
  }
  buildWater() {
    this.water = new T.Mesh(new T.PlaneGeometry(750, 750, 1, 1), new T.ShaderMaterial({
      uniforms: { time: { value: 0 } },
      vertexShader: 'varying vec2 p; void main(){p=position.xy;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
      fragmentShader: `varying vec2 p; uniform float time;
        void main(){float a=sin(p.x*1.5+p.y*.7+time*.7);float b=cos(p.y*1.2-p.x*.2+time*.5);
        float wave=pow(max(0.,a*b),14.);float depth=smoothstep(30.,290.,length(p));
        vec3 color=mix(vec3(.025,.13,.17),vec3(.10,.27,.31),depth)+wave*.012;
        gl_FragColor=vec4(color,1.);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
        }`,
    }));
    this.water.rotation.x = -Math.PI / 2; this.water.position.y = -.5; this.scene.add(this.water);
  }
  buildCountries() {
    let index = 0;
    for (const [key, spec] of Object.entries(this.layout.countries)) {
      const group = new T.Group(); group.userData.country = key; this.scene.add(group);
      const shape = new T.Shape();
      for (let i = 0; i <= 18; i++) {
        const a = i % 18 / 18 * Math.PI * 2, radius = 1 + .11 * Math.sin(a * 5 + index * 1.7) + .07 * Math.cos(a * 3 - index);
        const x = Math.cos(a) * 16 * radius, z = Math.sin(a) * 11.8 * radius;
        if (i === 0) shape.moveTo(x, z); else shape.lineTo(x, z);
      }
      shape.closePath();
      const geometry = new T.ExtrudeGeometry(shape, { depth: 2.6, bevelEnabled: true, bevelSize: .65, bevelThickness: .35, bevelSegments: 1, steps: 1 });
      geometry.rotateX(-Math.PI / 2);
      const land = new T.Mesh(geometry, [this.material(key === 'Oilia' ? '#b8aa79' : index % 3 === 2 ? '#738977' : '#6d8b59'), this.material('#8c8c6e')]);
      land.position.y = -1.3; land.receiveShadow = true; group.add(land);
      const shoreline = new T.ShapeGeometry(shape); shoreline.rotateX(-Math.PI / 2);
      const shore = this.mesh(group, shoreline, '#427a72', 0, -.4, 0); shore.scale.set(1.12, 1, 1.12); shore.castShadow = false;
      const halo = new T.Mesh(new T.RingGeometry(18, 18.22, 64), new T.MeshBasicMaterial({ color: '#ebcd7d', transparent: true, opacity: .8, side: T.DoubleSide }));
      halo.rotation.x = -Math.PI / 2; halo.scale.y = .76; halo.position.y = -.25; halo.visible = false; group.add(halo);
      // Persistent miniature streets, town houses, woods and a waterfront plaza.
      this.box(group, [19, .08, 1.1], [0, 1.73, 3.3], '#c4b589');
      this.box(group, [1.1, .08, 12], [4, 1.74, -.3], '#c4b589');
      for (const [x,z] of [[-8,-2],[-10,2],[8,-2],[10,0]]) this.tree(group, x, z, index === 6 || index === 3);
      for (let i = 0; i < 4; i++) this.house(group, -7 + i * 3.6, 6.3, i % 2 ? '#bd8a59' : '#a56245');
      const assets = new T.Group(); group.add(assets);
      const port = new T.Group(); this.scene.add(port);
      const pin = this.mesh(port, new T.CylinderGeometry(.35, .35, .25, 8), '#eed28b', 0, .4, 0); pin.castShadow = false;
      this.countries.set(key, { key, group, assets, port, halo, spec, signature: '', stage: -1, revision: 0 }); index++;
    }
  }
  tree(parent, x, z, palm = false) {
    this.mesh(parent, new T.CylinderGeometry(.15, .23, 2.2, 5), '#866744', x, 2.4, z);
    if (palm) {
      for (let i = 0; i < 5; i++) { const leaf = this.mesh(parent, new T.ConeGeometry(.65, 3, 4), '#446b43', x, 3.8, z); leaf.rotation.z = 1.13; leaf.rotation.y = i * Math.PI * 2 / 5; }
    } else {
      this.mesh(parent, new T.ConeGeometry(1.3, 3.2, 6), '#406b48', x, 3.4, z);
      this.mesh(parent, new T.ConeGeometry(.9, 2.4, 6), '#63804f', x, 4.6, z);
    }
  }
  house(parent, x, z, roof) {
    this.box(parent, [2.3, 2.5, 2.3], [x, 2.8, z], '#d4c7a5');
    const top = this.mesh(parent, new T.CylinderGeometry(0, 1.9, 1.4, 4), roof, x, 4.65, z); top.rotation.y = Math.PI / 4;
    this.box(parent, [.5, .9, .06], [x, 2.8, z + 1.18], '#536a64');
  }
  clear(group) {
    const owned = new Set(this.materials.values());
    group.traverse(o => {
      if (o.isMesh && !o.userData.sharedAsset) { o.geometry.dispose(); for (const m of [].concat(o.material)) if (!owned.has(m)) m.dispose(); }
      if (o.isLine) { o.geometry.dispose(); o.material.dispose(); }
    });
    group.clear();
  }
  async asset(parent, name, length, position, angle = 0, guard = () => true, height = null) {
    const token = {}; this.pending.add(token); this.report();
    try {
      const prototype = await loadModel(name);
      if (this.disposed || !guard()) return;
      const object = prototype.clone(true);
      const bounds = new T.Box3().setFromObject(object), size = bounds.getSize(new T.Vector3()), center = bounds.getCenter(new T.Vector3());
      const scale = length / Math.max(size.x, size.z);
      object.scale.set(scale, height === null ? scale : height / size.y, scale);
      object.position.set(-center.x * scale, -bounds.min.y * object.scale.y, -center.z * scale);
      const holder = new T.Group(); holder.name = name; holder.userData.model = name; holder.add(object);
      holder.position.set(...position); holder.rotation.y = angle; parent.add(holder); this.dirty = true;
    } catch { if (!this.disposed) this.failures.add(name); }
    finally { this.pending.delete(token); if (!this.disposed) this.report(); }
  }
  report() {
    const status = this.failures.size ? `일부 3D 모델을 불러오지 못했어요. 2D 지도도 사용할 수 있어요.` : this.pending.size ? '항구 모델을 불러오는 중…' : '3D 항구 준비 완료';
    this.surface.dataset.assets = this.failures.size ? 'partial' : this.pending.size ? 'loading' : 'ready';
    this.onStatus(status);
  }
  updateCountry(entry, profile) {
    const stage = stageFor(profile), signature = `${stage}:${profile?.main}`;
    if (entry.signature === signature) return;
    entry.signature = signature; entry.stage = stage; entry.revision++;
    const revision = entry.revision, current = () => entry.revision === revision;
    this.clear(entry.assets); this.clear(entry.port);
    const spec = stages[stage];
    this.asset(entry.assets, spec.warehouse, 8.5, [-3, 1.8, -.5], Math.PI / 2, current);
    this.asset(entry.assets, spec.truck, 2.7, [3, 1.85, 3.1], 0, current);
    this.asset(entry.assets, stage ? 'gantry-crane' : 'harbor-crane', 4.2, [9.8, 1.75, 4], -.5, current);
    this.asset(entry.port, spec.dock, 7.4, [0, -.1, 0], 0, current, 1.25);
    this.asset(entry.port, spec.ship, 7.8, [4, -.15, 2], -.15, current, stage ? null : 2.8);
    if (stage) this.asset(entry.assets, 'factory', 6, [-5, 1.8, -5.5], .2, current);
    if (spec.plane) {
      this.box(entry.assets, [9.5, .08, 2.5], [1.5, 1.78, -6], '#6e7c6d');
      for (let i = 0; i < 4; i++) this.box(entry.assets, [1, .03, .12], [-1.5 + i * 2, 1.84, -6], '#e5d9b7');
      this.asset(entry.assets, spec.plane, 4, [3, 1.85, -6], 0, current);
    }
    this.industry(entry.assets, profile?.main);
    this.dirty = true;
  }
  industry(parent, main) {
    if (main === 'wheat' || main === 'banana') {
      this.box(parent, [5, .12, 4], [-11, 1.8, -.5], '#a59c55');
      for (let i = 0; i < 5; i++) this.box(parent, [.27, .28, 3.6], [-13 + i, 2, -.5], '#dac27c');
      if (main === 'banana') this.tree(parent, -12, -1, true);
    } else if (main === 'ore') {
      for (let i = 0; i < 3; i++) { const mountain = this.mesh(parent, new T.ConeGeometry(2.3, 4.5 + i, 5), i % 2 ? '#a1a28d' : '#7a8879', 6 + i * 2.6, 3.3, -3.5); mountain.rotation.y = i; }
    } else if (main === 'fuel') {
      for (let i = 0; i < 3; i++) this.mesh(parent, new T.CylinderGeometry(1.2, 1.2, 2.2, 12), '#c3bfa1', 6 + i * 2.7, 2.8, -3.5);
    } else if (main === 'electronics') {
      for (let i = 0; i < 3; i++) this.box(parent, [1.8, 3 + i * 1.1, 2], [7 + i * 2.3, 3.2 + i * .55, -3.5], '#cad1bc');
    }
  }
  update(state, routes, selected, showRoutes) {
    if (this.disposed) return;
    this.state = state; this.selected = selected; this.showRoutes = showRoutes; this.tradeData = routes;
    for (const [key, entry] of this.countries) {
      this.updateCountry(entry, state.profiles?.[key]);
      entry.group.position.copy(this.point(entry.spec.position)); entry.port.position.copy(this.point(entry.spec.port));
      entry.halo.visible = key === selected || key === state.country;
      entry.halo.material.color.set(key === state.country ? '#f9d474' : '#b4e3ce');
    }
    this.updateRoutes(routes); this.dirty = true;
  }
  updateRoutes(routes) {
    for (const [key, data] of routes) {
      const stage = stageFor(this.state.profiles?.[data.seller]);
      let entry = this.routes.get(key);
      if (!entry) {
        const from = this.point(this.layout.countries[data.seller].port, .25), to = this.point(this.layout.countries[data.buyer].port, .25);
        const mid = from.clone().lerp(to, .5); const delta = to.clone().sub(from);
        mid.x -= delta.z * .12; mid.z += delta.x * .12;
        const curve = new T.QuadraticBezierCurve3(from, mid, to);
        const geometry = new T.BufferGeometry().setFromPoints(curve.getPoints(40));
        const material = data.channel === 'direct' ? new T.LineBasicMaterial({ color: colors[data.channel] }) : new T.LineDashedMaterial({ color: colors[data.channel], dashSize: data.channel === 'barter' ? .45 : 1.3, gapSize: .8 });
        const line = new T.Line(geometry, material); line.computeLineDistances();
        const group = new T.Group(); group.add(line); this.scene.add(group);
        const arrows = [];
        for (const direction of data.channel === 'barter' ? [1,-1] : [1]) {
          const t = direction === 1 ? .8 : .2, tangent = curve.getTangent(t).multiplyScalar(direction);
          const arrow = new T.ArrowHelper(tangent, curve.getPoint(t), 2.3, colors[data.channel], 1.3, .8); group.add(arrow); arrows.push(arrow);
        }
        const vessel = new T.Group(); group.add(vessel);
        entry = { group, vessel, curve, stage: -1, revision: 0, phase: this.routes.size * .19 }; this.routes.set(key, entry);
      }
      entry.group.visible = this.showRoutes;
      if (entry.stage !== stage) {
        entry.stage = stage; entry.revision++; const revision = entry.revision;
        this.clear(entry.vessel);
        // Keep route traffic bounded; the high-detail original steamship remains moored in every early harbor.
        this.asset(entry.vessel, stage === 2 ? 'container-ship' : 'diesel-freighter', 3.7, [0, 0, 0], 0, () => entry.revision === revision && this.routes.get(key) === entry);
      }
    }
    for (const [key, entry] of this.routes) if (!routes.has(key)) { this.scene.remove(entry.group); this.clear(entry.group); this.routes.delete(key); }
  }
  reset() {
    this.camera.position.set(0, 145, 108); this.controls.target.set(0, 0, 0); this.camera.zoom = 1; this.controls.update(); this.dirty = true;
  }
  zoom(factor) { this.camera.zoom = T.MathUtils.clamp(this.camera.zoom * factor, .8, 3); this.camera.updateProjectionMatrix(); this.dirty = true; }
  resize() {
    const width = this.surface.clientWidth, height = this.surface.clientHeight; if (!width || !height || this.disposed) return;
    const scale = width < 600 ? .18 : .13, changed = this.depthScale !== scale; this.depthScale = scale;
    const aspect = width / height, vertical = Math.max(112, 161 / aspect);
    this.camera.left = -vertical * aspect / 2; this.camera.right = vertical * aspect / 2;
    this.camera.top = vertical / 2; this.camera.bottom = -vertical / 2; this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height); this.dirty = true;
    if (changed) { for (const entry of this.routes.values()) { this.scene.remove(entry.group); this.clear(entry.group); } this.routes.clear(); }
    if (this.state) this.update(this.state, this.tradeData, this.selected, this.showRoutes);
  }
  project() {
    this.camera.updateMatrixWorld();
    const positions = new Map();
    for (const [key, entry] of this.countries) {
      const point = this.point(entry.spec.label, 12).project(this.camera);
      positions.set(key, { x: (point.x + 1) * 50, y: (1 - point.y) * 50, visible: point.z > -1 && point.z < 1 });
    }
    this.onProject(positions);
  }
  pick(event) {
    if (!this.pointerStart || Math.hypot(event.clientX - this.pointerStart[0], event.clientY - this.pointerStart[1]) > 6) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ray = new T.Raycaster(); ray.setFromCamera(new T.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), this.camera);
    const hit = ray.intersectObjects([...this.countries.values()].map(c => c.group), true)[0];
    for (let object = hit?.object; object; object = object.parent) if (object.userData.country) { this.onSelect(object.userData.country); return; }
  }
  setActive(value) { this.active = value; this.renderer.domElement.hidden = !value; this.dirty = true; }
  frame(time) {
    if (this.disposed) return;
    if (!this.surface.isConnected) { this.dispose(); return; }
    if (!this.active || !this.visible || document.hidden || time - this.lastFrame < 33) return;
    const dt = Math.min((time - this.lastFrame) / 1000 || 0, .1); this.lastFrame = time;
    const moving = !this.reduced && !this.state?.room?.paused;
    if (!this.dirty && !moving) return;
    if (moving) this.elapsed += dt;
    this.water.material.uniforms.time.value = this.elapsed;
    for (const entry of this.routes.values()) {
      const t = ((this.elapsed / 27 + entry.phase) % 1 + 1) % 1;
      entry.vessel.position.copy(entry.curve.getPoint(t));
      const tangent = entry.curve.getTangent(t); entry.vessel.rotation.y = -Math.atan2(tangent.z, tangent.x);
    }
    this.project(); this.renderer.render(this.scene, this.camera); this.dirty = false;
    this.surface.dataset.triangles = this.renderer.info.render.triangles;
    this.surface.dataset.drawCalls = this.renderer.info.render.calls;
  }
  dispose() {
    if (this.disposed) return; this.disposed = true;
    this.renderer.setAnimationLoop(null); this.resizeObserver?.disconnect(); this.intersectionObserver?.disconnect();
    this.reducedQuery.removeEventListener('change', this.motionChange); this.controls.dispose();
    this.renderer.domElement.removeEventListener('pointerdown', this.pointerDown); this.renderer.domElement.removeEventListener('pointerup', this.pointerUp); this.renderer.domElement.removeEventListener('webglcontextlost', this.contextLost);
    this.clear(this.scene); for (const material of this.materials.values()) material.dispose();
    this.renderer.dispose(); this.renderer.domElement.remove();
  }
}
