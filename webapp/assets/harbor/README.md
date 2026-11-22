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

Country centers and ports still come from `webapp/assets/map/layout.json`.
`position` locates the country's town, `port` locates its dock, and `label` anchors
the HTML country button. Coordinates use the JSON `viewBox`, and remain editable
without changing the engine. The SVG `background` is used by the title and 2D
fallback; changing that image does not replace the actual 3D terrain geometry.

The current world uses two connected continental landmasses, three sovereign
islands and five small islets. `landmasses[].outline` contains the shared coastline;
each country's `region` polygon specifies its territory. Neighboring countries
reuse exactly the same border vertices, so they do not become separate island
pedestals. `color` tints the territory and `portAngle` rotates the dock in radians.
`terrain` supplies ridge/forest/river paths. Geography keeps the same scale and
coordinates across screen sizes; only the camera and label callouts adapt.

Sea routes use `js/map-navigation.js` to find water paths around the shared
coastlines. This changes the drawn route only, not trade rules or delivery times.

Optional new Tripo GLBs go in `assets/map/props/` and are registered in the layout's
`props` list, e.g. `{"model":"mountain-ridge","position":[1100,440],"size":18,"rotation":0.4}`.
The filename excludes `.glb`; position is in map coordinates, size is the maximum
horizontal length in 3D units, and rotation is in radians. The staged prompts and
export checklist are in `assets/map/tripo-brief.md`. Existing terrain remains usable
with an empty props list; paid model generation was not run.

The 2D button preserves the original SVG map and all country/trade interactions.
If WebGL is unavailable or its context is lost, the same fallback appears
automatically. The 3D button can retry after context loss.

Three.js and its GLTF loader/OrbitControls are bundled locally under
`webapp/assets/three/`, with the original MIT `LICENSE`. There is no CDN,
runtime package installation or build step.
