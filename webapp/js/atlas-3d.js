import * as T from '../assets/three/three.module.js';
import { OrbitControls } from '../assets/three/addons/controls/OrbitControls.js';
import { GLTFLoader } from '../assets/three/addons/loaders/GLTFLoader.js';
import { mergeGeometries } from '../assets/three/addons/utils/BufferGeometryUtils.js';
import { buildExportYard, equipExportYard, harborTextures, loadExportCargo, loadHarborCoast } from './tropia-port.js';
import { seaRoute } from './map-navigation.js';
import { buildMineWorks, equipMinePort, loadMineTerrain } from './mineria-port.js';

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
function loadModel(name, root = assetRoot) {
  const key = new URL(`${name}.glb`, root).href;
  if (!modelCache.has(key)) modelCache.set(key, new GLTFLoader().loadAsync(key).then(gltf => {
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
  }).catch(error => { modelCache.delete(key); throw error; }));
  return modelCache.get(key);
}

function loadGeography(url) {
  if (!modelCache.has(url)) {
    modelCache.set(url, new GLTFLoader().loadAsync(url).catch(error => {
      modelCache.delete(url);
      throw error;
    }));
  }
  return modelCache.get(url);
}

export class Atlas3D {
  constructor(surface, layout, { onSelect, onProject, onStatus, onFailure }) {
    this.surface = surface; this.layout = layout;
    Object.assign(this, { onSelect, onProject, onStatus, onFailure });
    this.countries = new Map(); this.routes = new Map(); this.materials = new Map();
    this.pending = new Set(); this.failures = new Set(); this.disposed = false; this.active = true;
    this.visible = true; this.dirty = true; this.elapsed = 0; this.lastFrame = 0; this.depthScale = .105;
    this.reducedQuery = matchMedia('(prefers-reduced-motion: reduce)'); this.reduced = this.reducedQuery.matches;
    this.motionChange = e => { this.reduced = e.matches; this.dirty = true; };
    this.reducedQuery.addEventListener('change', this.motionChange);
    this.scene = new T.Scene(); this.scene.background = new T.Color('#9ebfc0');
    this.scene.fog = new T.Fog('#89aeb0', 260, 480);
    this.renderer = new T.WebGLRenderer({ antialias: true, powerPreference: 'low-power' });
    this.renderer.outputColorSpace = T.SRGBColorSpace;
    this.renderer.toneMapping = T.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.08;
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = T.PCFSoftShadowMap;
    this.renderer.domElement.className = 'atlas-webgl';
    this.renderer.domElement.setAttribute('aria-label', '실제 3D 세계 지도. 드래그로 회전, 두 손가락이나 휠로 확대. 나라 이름 버튼으로도 선택할 수 있어요.');
    this.renderer.domElement.setAttribute('role', 'img');
    this.surface.prepend(this.renderer.domElement);
    this.camera = new T.OrthographicCamera(-90, 90, 60, -60, .1, 600);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.screenSpacePanning = false; this.controls.enableDamping = false; this.controls.enablePan = true;
    this.controls.minZoom = .8; this.controls.maxZoom = 28; this.controls.zoomToCursor = true;
    this.controls.minPolarAngle = .22; this.controls.maxPolarAngle = 1.05;
    this.controls.minAzimuthAngle = -.65; this.controls.maxAzimuthAngle = .65;
    // A touch drag scrolls the classroom page; two fingers control the camera.
    this.controls.touches.ONE = null;
    this.controls.touches.TWO = T.TOUCH.DOLLY_PAN;
    this.renderer.domElement.style.touchAction = 'pan-y';
    this.controls.addEventListener('change', () => { this.dirty = true; });
    this.scene.add(new T.HemisphereLight('#fff4da', '#456757', 1.8));
    const sun = new T.DirectionalLight('#ffe8ba', 2.6); sun.position.set(-70, 125, 55); sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024); Object.assign(sun.shadow.camera, { left: -100, right: 100, top: 100, bottom: -100, near: 1, far: 280 });
    sun.shadow.bias = -.00035; sun.shadow.normalBias = .06; this.sun = sun; this.scene.add(sun, sun.target);
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
    const inlet = this.point(this.layout.countries.Tropia?.port ?? [0, 0]);
    const mineInlet = this.point(this.layout.countries.Mineria?.port ?? [0, 0]);
    const coast = new T.TextureLoader().load(new URL('../assets/map/materials/coast-distance.png', import.meta.url).href, () => { this.dirty = true; });
    this.coastTexture = coast;
    const ripples = new T.TextureLoader().load(new URL('../assets/map/materials/water-surface.png', import.meta.url).href, () => { this.dirty = true; });
    ripples.wrapS = ripples.wrapT = T.RepeatWrapping;
    this.rippleTexture = ripples;
    const uniforms = T.UniformsUtils.clone(T.UniformsLib.lights);
    Object.assign(uniforms, {
      time: { value: 0 }, coast: { value: coast }, ripples: { value: ripples },
      inlet: { value: new T.Vector2(inlet.x, -inlet.z) },
      mineInlet: { value: new T.Vector2(mineInlet.x, -mineInlet.z) }, nearBlend: { value: 0 },
      chart: { value: new T.Vector2(this.layout.viewBox[2] * .105, this.layout.viewBox[3] * this.depthScale) },
      coastEnabled: { value: this.layout.terrainModel ? 1 : 0 },
    });
    this.water = new T.Mesh(new T.PlaneGeometry(750, 750), new T.ShaderMaterial({
      lights: true, uniforms,
      vertexShader: `varying vec2 p;
        #include <common>
        #include <shadowmap_pars_vertex>
        void main(){
          p = position.xy;
          vec3 transformedNormal = normalMatrix * normal;
          vec4 worldPosition = modelMatrix * vec4(position,1.);
          #include <shadowmap_vertex>
          gl_Position = projectionMatrix * viewMatrix * worldPosition;
        }`,
      fragmentShader: `varying vec2 p;
        uniform sampler2D coast, ripples;
        uniform vec2 inlet, mineInlet, chart;
        uniform float time, coastEnabled, nearBlend;
        uniform bool receiveShadow;
        #include <common>
        #include <packing>
        #include <shadowmap_pars_fragment>
        #include <shadowmask_pars_fragment>
        void main(){
          float offshore = (texture2D(coast, p/chart + .5).r * 255. - 128.) * .0525;
          float mineDistance = distance(mineInlet,p);
          float local = nearBlend * (1.-smoothstep(7.,14.,min(distance(inlet,p),mineDistance)));
          vec3 broad = texture2D(ripples, p*.008 + time*vec2(.0007,.0003)).rgb;
          float shelf = (1.-smoothstep(.05,4.9,offshore)) * coastEnabled;
          vec3 color = mix(vec3(.012,.056,.096),vec3(.028,.14,.155),shelf);
          color *= .91+.18*broad.g;
          if(local>.001){
            vec3 waves = texture2D(ripples,p*.22 + time*vec2(-.011,.006)).rgb;
            vec3 chop = texture2D(ripples,vec2(-p.y,p.x)*.48 + time*vec2(.012,.008)).rgb;
            vec2 slope = (waves.rg-.5)*.78 + (chop.gr-.5)*vec2(.28,-.28);
            vec3 normal = normalize(vec3(-slope.x,1.,slope.y));
            vec3 eye = normalize(vec3(viewMatrix[0][2],viewMatrix[1][2],viewMatrix[2][2]));
            vec3 reflected = reflect(-eye,normal);
            float shoal = (1.-smoothstep(-.12,2.8,offshore+.30*(broad.r-.5))) * coastEnabled;
            float shadow = getShadowMask();
            vec3 shallows = mix(vec3(.082,.31,.236),vec3(.083,.20,.20),1.-smoothstep(7.,14.,mineDistance));
            vec3 bay = mix(vec3(.008,.078,.108),shallows,shoal);
            bay += vec3(.046,.062,.040)*waves.b*chop.b*shoal;
            bay *= (.80+.36*normal.z+.19*broad.g)*mix(.45,1.,shadow);
            float sky = pow(1.-max(.0,dot(eye,normal)),2.);
            bay += vec3(.14,.23,.29)*sky;
            vec3 sun = normalize(vec3(-70.,125.,55.));
            bay += vec3(.62,.56,.41)*pow(max(.0,dot(sun,reflected)),65.)*shadow;
            float surge = offshore + .10*(waves.r+chop.g-1.) + .055*sin(time*1.1+broad.r*9.);
            float wash = (1.-smoothstep(.035,.20,abs(surge-.09))) * smoothstep(.30,.68,waves.g)*coastEnabled;
            bay = mix(bay,vec3(.43,.54,.49),wash*.48);
            color = mix(color,bay,local);
          }
          gl_FragColor=vec4(color,1.);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    }));
    this.water.receiveShadow = true;
    this.water.rotation.x = -Math.PI / 2; this.water.position.y = -.5; this.scene.add(this.water);
  }
  regionShape(points, origin = null) {
    const shape = new T.Shape(), offset = origin ? this.point(origin) : new T.Vector3();
    points.forEach((pair, i) => {
      const p = this.point(pair).sub(offset);
      if (i) shape.lineTo(p.x, -p.z); else shape.moveTo(p.x, -p.z);
    });
    shape.closePath(); return shape;
  }
  async loadTerrain(spec) {
    const url = new URL(spec.file, new URL('../assets/map/', import.meta.url)).href;
    const token = {};
    this.pending.add(token);
    try {
      const { scene } = await loadGeography(url);
      if (this.disposed) return;
      this.terrain = scene.clone(true);
      this.terrain.name = 'world-geography';
      this.terrain.scale.set(spec.scale, spec.scale * spec.relief, spec.scale);
      this.terrain.position.y = spec.baseY;
      this.terrainMaterials = [];
      const field = this.layout.countries.Tropia?.bananaField;
      this.terrain.traverse(part => {
        if (!part.isMesh) return;
        if (field) this.paintFarmSoil(part, field);
        if (part.material.map) part.material.map.anisotropy = Math.min(8,this.renderer.capabilities.getMaxAnisotropy());
        part.castShadow = part.receiveShadow = true;
        part.userData.sharedAsset = true;
      });
      this.scene.add(this.terrain);
      this.terrain.updateMatrixWorld(true);
      this.dirty = true;
    } catch {
      if (!this.disposed) {
        this.onFailure('세계 지형을 불러오지 못해 2D 지도를 표시해요.');
        this.dispose();
      }
    } finally {
      this.pending.delete(token);
      if (!this.disposed) this.report();
    }
  }
  paintFarmSoil(part, field) {
    // Tint the terrain itself so tilled rows follow its exact slopes at every zoom.
    const first = this.point(field.origin);
    const spacing = field.spacing * .105;
    const material = part.material.clone();
    part.material = material;
    this.terrainMaterials.push(material);
    const tiles = harborTextures();
    this.detailBlend = { value: 0 };
    material.onBeforeCompile = shader => {
      shader.uniforms.detailBlend = this.detailBlend;
      shader.uniforms.grassTile = { value: tiles.grass };
      shader.uniforms.earthTile = { value: tiles.earth };
      shader.uniforms.rockTile = { value: tiles.rock };
      shader.uniforms.farmOrigin = { value: new T.Vector2(first.x, first.z) };
      const mine = this.point(this.layout.countries.Mineria?.position ?? [-10000, -10000]);
      shader.uniforms.mineOrigin = { value: new T.Vector2(mine.x, mine.z) };
      shader.uniforms.farmSpacing = { value: spacing };
      shader.uniforms.farmExtent = { value: new T.Vector2(field.heights[0].length, field.heights.length) };
      shader.vertexShader = 'varying vec3 landNormal, landPosition; varying vec2 farmXZ;\n' + shader.vertexShader.replace('#include <worldpos_vertex>',
        '#include <worldpos_vertex>\nlandNormal = (vec4(normalize(normalMatrix * normal),0.) * viewMatrix).xyz; landPosition = (modelMatrix * vec4(transformed, 1.)).xyz; farmXZ = landPosition.xz;');
      shader.fragmentShader = 'varying vec3 landNormal, landPosition; uniform sampler2D grassTile, earthTile, rockTile; uniform float detailBlend; varying vec2 farmXZ; uniform vec2 farmOrigin, farmExtent, mineOrigin; uniform float farmSpacing;\n' +
        shader.fragmentShader.replace('#include <map_fragment>', `#include <map_fragment>
          vec2 grid = (farmXZ - farmOrigin) / farmSpacing + 0.5;
          vec2 edge = min(grid, farmExtent - grid);
          float mask = smoothstep(0., .24, min(edge.x, edge.y));
          float row = .5 + .5 * cos(grid.y * 6.283185);
          vec3 soil = vec3(.17, .108, .051) * (.83 + .27 * row + .24 * diffuseColor.g);
          vec3 overview = mix(diffuseColor.rgb, soil, mask * .94);
          diffuseColor.rgb = overview;
          if (detailBlend > .001) {
            vec3 n = abs(normalize(landNormal));
            vec3 w = pow(n,vec3(4.));
            w /= max(.001,w.x+w.y+w.z);
            vec3 rock = texture2D(rockTile,landPosition.zy*.27).rgb*w.x
                      + texture2D(rockTile,landPosition.xz*.27).rgb*w.y
                      + texture2D(rockTile,landPosition.xy*.27).rgb*w.z;
            vec3 meadow = texture2D(grassTile, farmXZ*.42).rgb;
            vec3 fine = mix(rock, meadow, smoothstep(.58,.94,n.y));
            float grain = dot(fine, vec3(.23,.64,.13));
            vec3 bedrock = mix(overview,vec3(.17,.16,.14),.40)*(.70+grain*2.1);
            vec3 land = mix(bedrock,overview*(.64+1.9*grain),smoothstep(.56,.91,n.y));
            float river = smoothstep(.01,.065,overview.b-overview.r) * smoothstep(.0,.034,overview.b-overview.g);
            diffuseColor.rgb = mix(overview,land,detailBlend*(1.-river)*(1.-mask)*.85);
            // Rebuild the upland surface at landscape scale, retaining mapped rivers.
            vec2 basin = (farmXZ-mineOrigin-vec2(-9.3,3.8))/vec2(19.,16.);
            float inland = 1.-smoothstep(.81,1.12,length(basin));
            if (inland > .001) {
              float soil = texture2D(earthTile, farmXZ*.09).g;
              float grass = dot(meadow,vec3(.27,.62,.11));
              float strata = dot(rock,vec3(.27,.62,.11));
              float rough = smoothstep(.09,.51,1.-n.y) + smoothstep(4.5,7.7,landPosition.y)*.58;
              vec3 pasture = mix(vec3(.064,.104,.045),vec3(.24,.256,.105),clamp(grass*3.7+soil*.65,0.,1.));
              vec3 shale = mix(vec3(.059,.067,.066),vec3(.35,.33,.277),clamp(strata*3.5,0.,1.));
              float weather = dot(texture2D(grassTile,farmXZ*.059).rgb,vec3(.27,.62,.11));
              vec3 localGround = mix(pasture,shale,clamp(rough+soil*.36+weather*.63,0.,1.));
              localGround *= .64 + clamp(grass*2.25 + weather*1.3,.0,.93);
              float frost = smoothstep(5.8,7.7,landPosition.y+soil*2.)*smoothstep(.48,.86,n.y);
              localGround = mix(localGround,vec3(.68,.70,.66)*(.73+strata),frost*.89);
              diffuseColor.rgb = mix(diffuseColor.rgb,localGround,detailBlend*inland*(1.-river)*.81);
            }
          }
          float mineDistance = distance(farmXZ,mineOrigin);
          if (detailBlend > .001 && mineDistance < 9.) {
            vec3 weights = pow(abs(normalize(landNormal)),vec3(4.));
            weights /= max(.0001,dot(weights,vec3(1.)));
            vec3 stone = texture2D(rockTile,landPosition.zy*.86).rgb*weights.x
                       + texture2D(rockTile,landPosition.xz*.86).rgb*weights.y
                       + texture2D(rockTile,landPosition.xy*.86).rgb*weights.z;
            vec3 gravel = texture2D(grassTile,landPosition.xz*.8).rgb * vec3(.82,.88,.76);
            vec3 ground = mix(stone * vec3(.77,.83,.87), gravel,weights.y*.82);
            diffuseColor.rgb = mix(diffuseColor.rgb,ground,detailBlend*(1.-smoothstep(4.,9.,mineDistance)));
          }
          if (detailBlend > .001 && distance(farmXZ, farmOrigin) < 12.) {
            vec3 turf = texture2D(grassTile, farmXZ * .72).rgb;
            vec3 loam = texture2D(earthTile, farmXZ * 1.55).rgb;
            float fertile = smoothstep(-.06,.19,overview.g-overview.r*.79);
            vec3 n = abs(normalize(landNormal));
            vec3 weights = pow(n,vec3(4.)); weights /= max(.0001,dot(weights,vec3(1.)));
            vec3 cliff = texture2D(rockTile,landPosition.zy*.79).rgb*weights.x
              + texture2D(rockTile,landPosition.xz*.79).rgb*weights.y
              + texture2D(rockTile,landPosition.xy*.79).rgb*weights.z;
            vec3 closeGround = turf * mix(vec3(.77,1.04,.67),vec3(.44,1.09,.58),fertile);
            closeGround = mix(cliff * vec3(.86,.94,1.), closeGround, smoothstep(.48,.89,n.y));
            closeGround *= mix(.60,1.,smoothstep(-.44,-.10,landPosition.y));
            vec3 furrows = loam * vec3(1.48,1.14,.84) * (.75 + .33 * row);
            float local = 1. - smoothstep(6.,12., distance(farmXZ, farmOrigin));
            vec2 lane = farmXZ - farmOrigin;
            float trail = (1. - smoothstep(.12,.25, abs(lane.x - .97 + .19 * lane.y))) *
                          smoothstep(-1.9,-1.7,lane.y) * (1. - smoothstep(-.3,.15,lane.y));
            closeGround = mix(closeGround,loam*1.14,trail);
            diffuseColor.rgb = mix(diffuseColor.rgb, mix(closeGround, furrows, mask), detailBlend * local);
          }`);
    };
  }
  buildContinents() {
    const geography = new T.Group(); geography.name = 'world-geography'; this.scene.add(geography);
    for (const mass of this.layout.landmasses || []) {
      const shape = this.regionShape(mass.outline);
      const geometry = new T.ExtrudeGeometry(shape, { depth: 2.6, bevelEnabled: true, bevelSize: .35, bevelThickness: .25, bevelSegments: 1, steps: 1 });
      geometry.rotateX(-Math.PI / 2);
      const land = new T.Mesh(geometry, [this.material('#83966c'), this.material('#8c8b6a')]);
      land.position.y = -1.3; land.receiveShadow = true; land.name = mass.id; geography.add(land);
      const points = mass.outline.map(pair => this.point(pair, -.2)); points.push(points[0]);
      const coast = new T.Line(new T.BufferGeometry().setFromPoints(points), new T.LineBasicMaterial({ color: '#c5d3a5', transparent: true, opacity: .55 })); geography.add(coast);
      // Shallow coastal shelf follows the exact landmass rather than a circular island base.
      const shelf = new T.ShapeGeometry(shape); shelf.rotateX(-Math.PI / 2);
      const center = new T.Box3().setFromBufferAttribute(shelf.attributes.position).getCenter(new T.Vector3());
      shelf.translate(-center.x, 0, -center.z); shelf.scale(1.035, 1, 1.035); shelf.translate(center.x, 0, center.z);
      const shallows = this.mesh(geography, shelf, '#417b76', 0, -.4, 0); shallows.castShadow = false;
    }
    for (const item of this.layout.terrain || []) {
      if (item.kind === 'river') {
        const points = item.points.map(pair => this.point(pair, 1.47));
        const curve = new T.CatmullRomCurve3(points);
        const river = this.mesh(geography, new T.TubeGeometry(curve, 60, .29, 5, false), '#75a9ac'); river.castShadow = false;
      } else for (const [i, pair] of item.points.entries()) {
        const p = this.point(pair);
        if (item.kind === 'ridge') {
          for (let j = 0; j < 2; j++) {
            const height = (3.6 + (i + j) % 3 * 1.4) * item.size;
            const peak = this.mesh(geography, new T.ConeGeometry(2.3 * item.size, height, 5), j ? '#8f9982' : '#6b7d70', p.x + j * 1.6, 1.4 + height / 2, p.z + j * 1.1); peak.rotation.y = i * .8;
            if (height > 5) this.mesh(geography, new T.ConeGeometry(.6, 1.3, 5), '#ded8b7', p.x + j * 1.6, 1.4 + height - .5, p.z + j * 1.1);
          }
        } else if (item.kind === 'forest') {
          for (const [dx,dz] of [[0,0],[1.5,1.3],[-1.2,1.4]]) this.tree(geography, p.x + dx, p.z + dz);
        }
      }
    }
    // Optional independently generated Tripo props, registered after the user supplies a GLB.
    for (const prop of this.layout.props || []) {
      const group = new T.Group(); group.position.copy(this.point(prop.position, 1.4)); geography.add(group);
      this.asset(group, prop.model, prop.size || 10, [0, 0, 0], prop.rotation || 0, () => true, null, new URL('../assets/map/props/', import.meta.url));
    }
  }
  buildCountries() {
    const imported = this.layout.terrainModel;
    if (imported) {
      this.loadTerrain(imported);
      for (const prop of this.layout.props || []) {
        const position = this.point(prop.position, prop.ground ?? 0);
        this.asset(this.scene, prop.model, prop.size || 10, position.toArray(), prop.rotation || 0, () => true, null, new URL('../assets/map/props/', import.meta.url));
      }
    } else this.buildContinents();
    for (const [key, spec] of Object.entries(this.layout.countries)) {
      const group = new T.Group(); group.userData.country = key; this.scene.add(group);
      let halo;
      if (imported) {
        halo = new T.Mesh(new T.RingGeometry(2.3, 2.55, 48), new T.MeshBasicMaterial({ color: '#f9d474', depthTest: false, transparent: true, opacity: .8 }));
        halo.rotation.x = -Math.PI / 2;
        halo.renderOrder = 2;
        group.add(halo);
      } else {
        let points = spec.region;
        if (!points) points = Array.from({ length: 18 }, (_, i) => [spec.position[0] + Math.cos(i / 18 * Math.PI * 2) * 120, spec.position[1] + Math.sin(i / 18 * Math.PI * 2) * 95]);
        const shape = this.regionShape(points, spec.position);
        const geometry = new T.ShapeGeometry(shape); geometry.rotateX(-Math.PI / 2);
        const surface = this.mesh(group, geometry, spec.color || '#8a9b75', 0, 1.36, 0); surface.castShadow = false;
        const borderPoints = points.map(pair => this.point(pair, 1.5).sub(this.point(spec.position))); borderPoints.push(borderPoints[0]);
        const border = new T.Line(new T.BufferGeometry().setFromPoints(borderPoints), new T.LineBasicMaterial({ color: '#d2c89b', transparent: true, opacity: .65 })); group.add(border);
        halo = new T.Mesh(geometry.clone(), new T.MeshBasicMaterial({ color: '#ebcd7d', transparent: true, opacity: .20, depthWrite: false, side: T.DoubleSide }));
        halo.position.y = 1.41; halo.visible = false; group.add(halo);
      }
      const town = new T.Group(); town.name = 'port-town'; town.scale.setScalar(imported ? .24 : .65); town.position.y = imported ? -.4 : .48; group.add(town);
      if (!spec.bananaField && !spec.mineWorks) {
        this.box(town, [19, .08, 1.1], [0, 1.73, 3.3], '#c4b589');
        this.box(town, [1.1, .08, 12], [4, 1.74, -.3], '#c4b589');
        for (const [x,z] of [[-8,-2],[-10,2],[8,-2],[10,0]]) this.tree(town, x, z, ['Tropia','Agrea'].includes(key));
        for (let i = 0; i < 4; i++) this.house(town, -7 + i * 3.6, 6.3, i % 2 ? '#bd8a59' : '#a56245');
      }
      const assets = new T.Group(); town.add(assets);
      const port = new T.Group(); port.userData.country = key; port.scale.setScalar(imported ? .46 : .72); port.rotation.y = spec.portAngle || 0; this.scene.add(port);
      this.countries.set(key, { key, group, town, assets, port, halo, spec, signature: '', stage: -1, revision: 0 });
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
  async asset(parent, name, length, position, angle = 0, guard = () => true, height = null, root = assetRoot) {
    const token = {}; this.pending.add(token); this.report();
    try {
      const prototype = await loadModel(name, root);
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
  async loadInterior(entry) {
    const spec = entry.spec.interior;
    const group = new T.Group();
    group.name = 'mineria-interior';
    entry.group.add(group);
    entry.interior = group;
    this.pending.add(group);
    try {
      const {scene} = await loadGeography(new URL('../assets/map/'+spec.file, import.meta.url).href);
      if (this.disposed) return;
      const landscape = scene.clone(true);
      landscape.traverse(o => {
        if (o.isMesh) { o.userData.sharedAsset = true; o.receiveShadow = true; }
      });
      group.add(landscape);
      this.districtLabels = spec.places.map(place => {
        const el = document.createElement('span');
        el.className = 'district-name';
        el.hidden = true;
        el.textContent = place.name;
        this.surface.append(el);
        return {el, anchor:this.point(place.position,place.ground + .48)};
      });
      this.dirty = true;
    } catch {
      if (!this.disposed) this.failures.add(spec.file);
    } finally {
      this.pending.delete(group);
      if (!this.disposed) this.report();
    }
  }
  projectDistricts() {
    const width = this.surface.clientWidth, height = this.surface.clientHeight;
    const placed = [];
    for (const {el,anchor} of this.districtLabels || []) {
      const p = anchor.clone().project(this.camera);
      const x = (1+p.x)*width/2, y = (1-p.y)*height/2 - 10;
      const visible = this.camera.zoom >= 2.6 && p.z > -1 && p.z < 1 &&
        x > 48 && x < width-48 && y > 18 && y < height-12 &&
        !placed.some(other => Math.abs(x-other.x)<88 && Math.abs(y-other.y)<21);
      el.hidden = !visible;
      if (visible) {
        el.style.left = x+'px'; el.style.top = y+'px';
        placed.push({x,y});
      }
    }
  }
  updateCountry(entry, profile) {
    const stage = stageFor(profile), signature = `${stage}:${profile?.main}`;
    if (entry.signature === signature) return;
    entry.signature = signature; entry.stage = stage; entry.revision++;
    const revision = entry.revision, current = () => entry.revision === revision;
    this.clear(entry.assets); this.clear(entry.port);
    const spec = stages[stage];
    if (entry.spec.bananaField) {
      if (!entry.yard) {
        entry.yard = buildExportYard(this, entry);
        entry.yard.add(entry.assets);
        entry.port.scale.setScalar(1);
      }
      equipExportYard(this, entry, stage, spec, current);
    } else if (entry.spec.mineWorks) {
      if (!entry.mineYard) {
        entry.mineYard = buildMineWorks(this, entry);
        entry.mineYard.add(entry.assets);
        entry.port.scale.setScalar(1);
      }
      equipMinePort(this, entry, stage, spec, current);
    } else {
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
    }
    if (profile?.main === 'banana' && entry.spec.bananaField) {
      if (!entry.orchard) entry.orchard = this.buildBananaField(entry);
      entry.orchard.visible = true;
    } else {
      if (entry.orchard) entry.orchard.visible = false;
      if (!(entry.spec.mineWorks && profile?.main === 'ore')) this.industry(entry.assets, profile?.main);
    }
    this.dirty = true;
  }
  buildBananaField(entry) {
    const { origin, spacing, heights } = entry.spec.bananaField;
    const field = new T.Group();
    entry.group.add(field);
    const center = this.point(entry.spec.position, entry.spec.ground);
    const root = new URL('../assets/map/props/', import.meta.url);
    heights.forEach((line, row) => line.forEach((height, col) => {
      const coords = [origin[0] + col * spacing, origin[1] + row * spacing];
      const p = this.point(coords, height).sub(center);
      this.asset(field, 'banana-plant', .48 + col * .025, p.toArray(), (row * line.length + col) * 2.4, undefined, null, root);
    }));
    return field;
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
      entry.group.position.copy(this.point(entry.spec.position, entry.spec.ground ?? 0)); entry.port.position.copy(this.point(entry.spec.port));
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
        let curve;
        if (this.layout.landmasses?.length) {
          const points = seaRoute(this.layout, this.layout.countries[data.seller].port, this.layout.countries[data.buyer].port).map(p => this.point(p, .25));
          curve = new T.CurvePath(); for (let i = 1; i < points.length; i++) curve.add(new T.LineCurve3(points[i - 1], points[i]));
        } else curve = new T.QuadraticBezierCurve3(from, mid, to);
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
    this.inspectionTilt = 0;
    this.mineBearing = 0;
    this.controls.minAzimuthAngle = -.65;
    this.controls.maxAzimuthAngle = .65;
    this.camera.position.set(0, 145, 108); this.controls.target.set(0, 0, 0); this.camera.zoom = 1; this.camera.updateProjectionMatrix(); this.controls.update(); this.dirty = true;
  }
  zoom(factor) { this.camera.zoom = T.MathUtils.clamp(this.camera.zoom * factor, this.controls.minZoom, this.controls.maxZoom); this.camera.updateProjectionMatrix(); this.dirty = true; }
  frameInterior(key) {
    const spec = this.countries.get(key)?.spec;
    if (!spec?.interior) return;
    const sites = spec.interior.places.map(site => this.point(site.position, site.ground));
    sites.push(this.point(spec.port));
    const center = new T.Box3().setFromPoints(sites).getCenter(new T.Vector3());
    this.reset();
    this.controls.target.copy(center);
    this.camera.position.add(center);
    this.controls.update();
    this.camera.updateMatrixWorld();
    const extent = Math.max(...sites.map(site => {
      const p = site.project(this.camera);
      return Math.max(Math.abs(p.x),Math.abs(p.y));
    }));
    this.zoom(Math.min(5, .72 / Math.max(.01,extent)));
  }
  resize() {
    const width = this.surface.clientWidth, height = this.surface.clientHeight; if (!width || !height || this.disposed) return;
    const scale = .105, changed = this.depthScale !== scale; this.depthScale = scale;
    const aspect = width / height, vertical = Math.max(this.layout.landmasses?.length ? 96 : 112, (this.layout.terrainModel ? 124 : 161) / aspect);
    this.camera.left = -vertical * aspect / 2; this.camera.right = vertical * aspect / 2;
    this.camera.top = vertical / 2; this.camera.bottom = -vertical / 2; this.camera.updateProjectionMatrix();
    const pixelRatio = Math.max(1,Math.min(Math.max(devicePixelRatio,1.25),2,Math.sqrt(2000000/(width*height))));
    if (this.renderer.getPixelRatio() !== pixelRatio) this.renderer.setPixelRatio(pixelRatio);
    this.renderer.setSize(width, height); this.dirty = true;
    if (changed) { for (const entry of this.routes.values()) { this.scene.remove(entry.group); this.clear(entry.group); } this.routes.clear(); }
    if (this.state) this.update(this.state, this.tradeData, this.selected, this.showRoutes);
  }
  project() {
    this.camera.updateMatrixWorld();
    const close = this.camera.zoom >= 8;
    if (this.surface.classList.contains('harbor-detail') !== close) this.surface.classList.toggle('harbor-detail', close);
    const positions = new Map();
    for (const [key, entry] of this.countries) {
      entry.halo.visible = this.camera.zoom < 4 && (key === this.selected || key === this.state?.country);
      const point = this.point(entry.spec.label, 3).project(this.camera);
      const anchor = this.point(entry.spec.position, (entry.spec.ground ?? 0) + 1.5).project(this.camera);
      positions.set(key, { x: close ? 0 : (point.x + 1) * 50, y: close ? 0 : (1 - point.y) * 50, anchorX: (anchor.x + 1) * 50, anchorY: (1 - anchor.y) * 50, visible: point.z > -1 && point.z < 1 && Math.abs(anchor.x) <= 1 && Math.abs(anchor.y) <= 1 });
    }
    this.onProject(positions);
  }
  pick(event) {
    if (!this.pointerStart || Math.hypot(event.clientX - this.pointerStart[0], event.clientY - this.pointerStart[1]) > 6) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ray = new T.Raycaster(); ray.setFromCamera(new T.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), this.camera);
    const targets = [...this.countries.values()].flatMap(c => [c.group, c.port]);
    if (this.terrain) targets.push(this.terrain);
    // The selection ring is an annotation, so only solid geometry can take a hit.
    const hit = ray.intersectObjects(targets, true).find(({object}) => {
      if (!object.isMesh || object.geometry.type === 'RingGeometry') return false;
      for (let node = object; node; node = node.parent) if (!node.visible) return false;
      return true;
    });
    if (hit && this.terrain && hit.point.y < this.water.position.y) return;
    for (let object = hit?.object; object; object = object.parent) if (object.userData.country) { this.onSelect(object.userData.country); return; }
    if (hit && this.terrain) {
      // The terrain is a single mesh. Assign land to its nearest country center.
      const closest = [...this.countries.values()].reduce((best, entry) => {
        const distance = Math.hypot(hit.point.x - entry.group.position.x, hit.point.z - entry.group.position.z);
        return distance < best.distance ? { distance, key: entry.key } : best;
      }, { distance: Infinity });
      this.onSelect(closest.key);
    }
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
    if (this.detailBlend) this.detailBlend.value = T.MathUtils.smoothstep(this.camera.zoom, 1.25, 3.4);
    if (this.camera.zoom > 1.45 && this.terrainMaterials?.length && !this.detailColorRequested &&
        this.layout.terrainModel.detailColor && this.renderer.capabilities.maxTextureSize >= 4096) {
      this.detailColorRequested = true;
      const url = new URL('../assets/map/' + this.layout.terrainModel.detailColor, import.meta.url).href;
      if (!modelCache.has(url)) modelCache.set(url,new T.TextureLoader().loadAsync(url).catch(error => {
        modelCache.delete(url); throw error;
      }));
      modelCache.get(url).then(texture => {
        if (this.disposed) return;
        texture.flipY = false; texture.colorSpace = T.SRGBColorSpace;
        texture.anisotropy = Math.min(8,this.renderer.capabilities.getMaxAnisotropy());
        for (const material of this.terrainMaterials) material.map = texture;
        this.dirty = true;
      }).catch(() => { /* The embedded terrain map remains available offline. */ });
    }
    this.water.material.uniforms.nearBlend.value = this.layout.countries.Tropia?.bananaField ?
      T.MathUtils.smoothstep(this.camera.zoom, 2, 6) : 0;
    for (const entry of this.routes.values()) {
      const t = ((this.elapsed / 27 + entry.phase) % 1 + 1) % 1;
      entry.vessel.position.copy(entry.curve.getPoint(t));
      const tangent = entry.curve.getTangent(t); entry.vessel.rotation.y = -Math.atan2(tangent.z, tangent.x);
    }
    if (this.dirty) {
      const tilt = T.MathUtils.smoothstep(this.camera.zoom, 2, 11);
      const mineria = this.countries.get('Mineria');
      const focus = this.controls.target;
      const mineDistance = mineria?.mineYard ? Math.hypot(focus.x-mineria.group.position.x,focus.z-mineria.group.position.z) : Infinity;
      if (mineria?.spec.interior && this.camera.zoom > 1.45 && mineDistance < 62 && !mineria.interior)
        this.loadInterior(mineria);
      if (mineria?.interior) mineria.interior.visible = this.camera.zoom > 1.45;
      const bearing = 2.36 * tilt * (1-T.MathUtils.smoothstep(mineDistance,8,26));
      if (Math.abs(tilt - this.inspectionTilt) > .0001 || Math.abs(bearing - this.mineBearing) > .0001) {
        const delta = tilt - this.inspectionTilt;
        const orbit = new T.Spherical().setFromVector3(this.camera.position.clone().sub(this.controls.target));
        orbit.phi = T.MathUtils.clamp(orbit.phi + .34 * delta, this.controls.minPolarAngle, this.controls.maxPolarAngle);
        this.controls.minAzimuthAngle = bearing - .65;
        this.controls.maxAzimuthAngle = bearing + .65;
        orbit.theta = T.MathUtils.clamp(orbit.theta - .37 * delta + bearing - this.mineBearing, this.controls.minAzimuthAngle, this.controls.maxAzimuthAngle);
        this.camera.position.copy(this.controls.target).add(new T.Vector3().setFromSpherical(orbit));
        this.inspectionTilt = tilt;
        this.mineBearing = bearing;
        this.controls.update();
      }
      const tropia = this.countries.get('Tropia');
      if (mineria?.mineYard) {
        const anchor = mineria.group.position.clone().project(this.camera);
        const closeZoom = this.camera.zoom > 1.65;
        const near = closeZoom && (mineDistance < 12 || (Math.abs(anchor.x) < 2 && Math.abs(anchor.y) < 2));
        if (near && !mineria.mineDetail) mineria.mineDetail = loadMineTerrain(this, mineria.mineYard, mineria.spec.mineWorks);
        if (mineria.mineDetail) mineria.mineDetail.visible = closeZoom;
      }
      if (tropia?.yard) {
        const harbor = tropia.group.position.clone().project(this.camera);
        const detail = this.camera.zoom > 1.65 && Math.abs(harbor.x) < 2.5 && Math.abs(harbor.y) < 2.5;
        tropia.grove.visible = detail;
        if (detail && !tropia.cargo) tropia.cargo = loadExportCargo(this, tropia.yard);
        if (tropia.cargo) tropia.cargo.visible = detail;
        if (detail && tropia.spec.nearTerrain?.length && !tropia.coast)
          tropia.coast = loadHarborCoast(this, tropia.yard, tropia.spec.nearTerrain);
        if (tropia.coast) {
          const relief = T.MathUtils.smoothstep(this.camera.zoom, 1.65, 4.5);
          tropia.coast.visible = detail;
          tropia.coast.position.y = (relief - 1) * 2;
        }
      }
      const extent = Math.max(6, 110 / this.camera.zoom);
      this.sun.target.position.copy(focus);
      this.sun.position.set(focus.x - 70, focus.y + 125, focus.z + 55);
      Object.assign(this.sun.shadow.camera, { left: -extent, right: extent, top: extent, bottom: -extent });
      this.sun.shadow.camera.updateProjectionMatrix();
      this.sun.shadow.normalBias = extent * .00055;
      this.camera.updateMatrixWorld();
      this.projectDistricts();
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
    for (const {el} of this.districtLabels || []) el.remove();
    this.clear(this.scene); for (const material of this.materials.values()) material.dispose();
    for (const material of this.terrainMaterials || []) material.dispose();
    this.coastTexture?.dispose(); this.rippleTexture?.dispose();
    this.renderer.dispose(); this.renderer.domElement.remove();
  }
}
