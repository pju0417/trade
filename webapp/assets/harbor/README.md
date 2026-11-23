# Preserved harbor models used by the 3D world map

These 18 GLBs were restored from the previously preserved harbor project
(commit `25bf6b9`). No new generation or paid API call was made for this integration.

`brick-warehouse.glb`, `timber-pier.glb`, and `steam-freighter.glb` are the user's
original three Tripo assets, using the previously optimized copies (about 1.4–1.5 MB
and 34–35k triangles each). The remaining GLBs are the original locally made
low-poly harbor, vehicle, aircraft, factory and later-era variants from that project.

The renderer is `webapp/js/atlas-3d.js`. Shared geometry/textures are cached, static
parts are batched by material, models load on demand, pixel density is capped at
1.35 and rendering is capped at 30 frames/second. Offscreen/hidden maps stop drawing.
Reduced motion and teacher pause freeze the simulation. A removed room map disposes
its renderer; the shared model prototypes remain reusable within that page.

Visual eras read `profiles[country].levels[profiles[country].main]`:

| Main industry level | Warehouse / quay / ship | Vehicles and aircraft |
| --- | --- | --- |
| 0–1 | brick warehouse / timber pier / steam freighter | early truck |
| 2–3 | modern warehouse / concrete quay / diesel freighter | diesel truck / biplane |
| 4+ | smart warehouse / smart quay / container ship | electric truck / cargo jet |

This affects appearance only. Game state, investment costs, trading rules,
transport and the Python engine are unchanged. Moving route vessels use the lighter
diesel model in early eras and the container vessel in the modern era; original
steam freighters are moored in all early-era ports.

## Tropia export harbor

The banana plot, packing shed and outbound crates use the supplied Tripo models in
`webapp/assets/map/props/`. The source GLBs stay outside the web bundle. The yard
spans two elevations and includes a paved loading terrace, a ramp, dock equipment
and moorings. Zooming over the harbor lowers the camera continuously in the same
scene. Cargo stacks load on the first approach. The coastal planting uses shared,
instanced geometry at surveyed sites. The close-up treatment currently covers Tropia.

Three further Tripo Studio assets furnish the customs forecourt and the early
cargo fleet. The customs office and a pair of timber cottages share a street
linked to the quay and packing terrace. The banana lorry appears in the steam
era and yields to the standard diesel and electric trucks as industry advances.
Their GLB files are in `assets/map/props/` (`customs-office`, `dock-cottage` and
`banana-lorry`).

The coastal distance image comes from the terrain waterline. If that mesh changes,
update `materials/coast-distance.png`, the local `groveSites` and the crop ground
samples in `layout.json`. Grove coordinates are local east, absolute elevation,
and local south in scene units relative to the town's horizontal origin.

Ground tiles are local WebP conversions of CC0 photographs from Poly Haven.
The terrain blends the overhead texture with repeating soil, grass and rock at
close range. The apron and ramp use the cobblestone tile.

- [Brown Mud](https://polyhaven.com/a/brown_mud)
- [Aerial Grass Rock](https://polyhaven.com/a/aerial_grass_rock)
- [Rock Face 03](https://polyhaven.com/a/rock_face_03)
- [Cobblestone Floor 01](https://polyhaven.com/a/cobblestone_floor_01)

## Replacing the map

The close-up terrain at Tropia uses three independent Tripo meshes under
`webapp/assets/map/terrain/`. Their placements are in `countries.Tropia.nearTerrain`
in the layout. Each entry specifies its model filename without extension,
horizontal length, height, Y rotation in radians, and an [east, elevation, south]
offset from the town's horizontal center at world elevation zero. Models load on
approach and use the same camera and coordinates as the world terrain.

The title and 2D map use `webapp/assets/map/terrain-chart.webp`, an overhead view of the supplied mesh. Set `background` in `webapp/assets/map/layout.json` to another image filename in the same directory.

The 3D map loads `world-terrain-web.glb` (6.55 MB, 158,408 triangles, three 2048 px textures). Set `terrainModel.file` to a replacement GLB. Its origin is the chart center, Y is up and positive Z is south. Horizontal scale is 105, the vertical multiplier is 0.65, and base elevation is -0.875. Sea level is -0.5 in scene units.

The 1200 by 1100 chart and WebGL share coordinates. A chart unit equals 0.105 scene units. Each country's `position` is the town center, `ground` is surface elevation in scene units, and `label` anchors its name. The dock uses `port` and `portAngle` (radians). A short water segment to `approach` joins the offshore navigation grid. For a new coastline update these placements and `landmasses[].outline` together. The outlines follow the projected mesh at sea level with clearance for navigation.

Optional new Tripo GLBs go in `assets/map/props/` and are registered in the layout's
`props` list, e.g. `{"model":"mountain-ridge","position":[1100,440],"size":18,"rotation":0.4}`.
The filename excludes `.glb`; position is in map coordinates, size is the maximum
horizontal length in 3D units, and rotation is in radians. The staged prompts and
export checklist are in `assets/map/tripo-brief.md`. Existing terrain remains usable
with an empty props list.

The 2D button shows the overhead terrain chart and all country/trade interactions.
If WebGL is unavailable or its context is lost, the same fallback appears
automatically. The 3D button can retry after context loss.

Three.js and its GLTF loader/OrbitControls are bundled locally under
`webapp/assets/three/`, with the original MIT `LICENSE`. There is no CDN,
runtime package installation or build step.
