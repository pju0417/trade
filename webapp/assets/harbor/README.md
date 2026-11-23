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

## Replacing the map

The title and 2D map use `webapp/assets/map/terrain-chart.webp`, an overhead view of the supplied mesh. Set `background` in `webapp/assets/map/layout.json` to another image filename in the same directory.

The 3D map loads `world-terrain-web.glb` (6.55 MB, 158,408 triangles, three 2048 px textures). Set `terrainModel.file` to a replacement GLB. Its origin is the chart center, Y is up and positive Z is south. Horizontal scale is 105, the vertical multiplier is 0.65, and base elevation is -0.875. Sea level is -0.5 in scene units.

The 1200 by 1100 chart and WebGL share coordinates. A chart unit equals 0.105 scene units. Each country's `position` is the town center, `ground` is surface elevation in scene units, and `label` anchors its name. The dock uses `port` and `portAngle` (radians). A short water segment to `approach` joins the offshore navigation grid. For a new coastline update these placements and `landmasses[].outline` together. The outlines follow the projected mesh at sea level with clearance for navigation.

Optional new Tripo GLBs go in `assets/map/props/` and are registered in the layout's
`props` list, e.g. `{"model":"mountain-ridge","position":[1100,440],"size":18,"rotation":0.4}`.
The filename excludes `.glb`; position is in map coordinates, size is the maximum
horizontal length in 3D units, and rotation is in radians. The staged prompts and
export checklist are in `assets/map/tripo-brief.md`. Existing terrain remains usable
with an empty props list; paid model generation was not run.

The 2D button shows the overhead terrain chart and all country/trade interactions.
If WebGL is unavailable or its context is lost, the same fallback appears
automatically. The 3D button can retry after context loss.

Three.js and its GLTF loader/OrbitControls are bundled locally under
`webapp/assets/three/`, with the original MIT `LICENSE`. There is no CDN,
runtime package installation or build step.
