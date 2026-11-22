# 세계지도용 Tripo 에셋 제작 지시서

나라 전체를 9번 따로 생성하지 않습니다. 공통 세계 지형 위에 재사용할 조각을
배치합니다. 국경·해안선·항구 좌표·항로는 게임이 관리하고, Tripo 모델은 그 위의
지형/도시 장식을 담당합니다. 기존 창고·부두·증기선·트럭·공장·후기 시대 모델은
재사용하므로 새로 만들 필요가 없습니다.

## 먼저 만들 것: 산맥, 해안 절벽, 구시가지 (각각 독립 GLB)

### 1. 산맥 조각 — mountain-ridge.glb

미네리아·페리아와 대륙의 분수령에 회전/반복 배치합니다.

```text
A single modular mountain ridge prop for an original historical trade strategy game. Five connected craggy peaks forming a long gently curved ridge, weathered gray granite, warm gray exposed rock, mossy olive green foothills, a little pale snow only on the two tallest peaks. Strong readable silhouette from a distant elevated three-quarter camera. Broad low foothills blend into terrain; the underside is flat, open terrain edges, no raised pedestal or island. Stylized hand-painted natural materials, restrained realistic proportions, medium-low polygon game art, softly faceted rocks, no tiny surface clutter. One cohesive static terrain prop, centered, Y up, ground-level pivot. No buildings, no roads, no ocean, no labels, no text, no people, no background geometry. Export one textured GLB with compact textures. This is a reusable ridge segment, not a whole country or a full environment.
```

### 2. 해안 절벽 조각 — coastal-cliff.glb

대륙 해안 중 절벽이 필요한 곳에 배치합니다. 해안 전체나 바다는 포함하지 않습니다.

```text
A single modular coastal cliff segment for an original 19th-century trade strategy game. A curved stretch of layered warm gray limestone cliff, an irregular grassy olive green upper rim, visible vertical rock strata, a few large rocks at the foot. About three times wider than tall, shallow depth, flat rear edge for embedding into a larger landmass. Both ends taper down to low rock so repeated segments can blend. Stylized hand-painted game art, strong silhouette from an elevated three-quarter view, medium-low polygon geometry, readable broad material shapes, muted natural colors. One static terrain prop, Y up, ground-level pivot, no floating display base. No ocean or water plane, no foam mesh, no buildings, no trees, no ships, no sky, no labels or text. Export a single textured GLB. Only the cliff segment, not an island or country.
```

### 3. 19세기 도시 중심부 — old-town-block.glb

메카니아·노비아·테크니아의 도시 핵심부에 사용합니다. 도시 전체를 만들지 않습니다.

```text
A single small European-inspired 19th-century merchant town block for an original educational trade strategy game. Six to eight compact two- and three-story plaster and red-brick buildings around a tiny cobbled courtyard, varied burnt terracotta and muted verdigris roofs, one modest civic clock tower, chimneys and broad readable windows. Buildings have believable separate volumes and a varied skyline, no giant cathedral or palace. Restrained warm ivory, brick red, slate green and aged copper palette. Stylized hand-painted medium-low-poly game art, readable from a distant elevated three-quarter camera. One compact static modular city cluster with a flat ground-level underside and no raised display pedestal, Y up, centered pivot. No people, no cars, no ocean, no harbor, no ships, no large terrain, no labels, no signs, no text. Export one textured GLB with compact textures. Original design, not copied architecture or assets from an existing game.
```

## 다음 단계: 농경지와 열대 숲

### 4. 농경지 조각 — wheat-farm.glb

그레니아의 넓은 평야를 표현합니다. 같은 모델을 조금씩 회전/축척 변경해 재사용합니다.

```text
A single compact wheat farm terrain prop for an original 19th-century world trade strategy game. Four adjacent gently irregular rectangular fields at ground level, alternating harvested ochre soil and golden wheat rows, one small weathered timber barn and a short dirt path, a few low hedges. Wheat is represented by broad stylized rows, not thousands of individual stalk meshes. Warm muted gold, olive green, natural brown and a small terracotta roof. Readable from a distant elevated three-quarter view, stylized hand-painted medium-low-poly game art. Flat underside, very thin ground patch that can be embedded into continuous terrain, no raised pedestal, Y up. One static modular farm cluster. No people, no tractor, no modern equipment, no ocean, no mountains, no text or labels. Export one textured GLB.
```

### 5. 열대 숲 조각 — tropical-grove.glb

트로피아·아그레아의 녹지를 표현합니다. 별도 바나나 농장 모델은 나중에 추가해도 됩니다.

```text
A single reusable tropical grove cluster for an original historical world trade strategy game. Seven to ten varied palms and broad-leaf tropical trees, layered deep olive and muted emerald foliage, a few banana-like broad leaves, slim warm brown trunks, naturally uneven canopy heights. Dense but readable silhouette, tree crowns formed from clean broad shapes, no individual leaf clutter and no alpha-card foliage. Stylized hand-painted medium-low-poly game art, readable from a distant elevated three-quarter view. One static modular vegetation prop, flat ground-level underside, Y up, centered pivot, no raised island or display pedestal. No buildings, no beach, no ocean, no people, no fruit labels, no text, no background scene. Export a single textured GLB with compact textures.
```

## 제작·검수 기준

- 한 번에 프롬프트 하나씩, 파일도 모델별 독립 GLB로 내보내기.
- 가능하면 모델당 3,000–8,000 triangles를 목표로 하고 큰 산맥/도시도 15,000 이내로 조정.
  생성 결과의 실제 삼각형 수는 내보낸 파일에서 별도로 확인합니다.
- 텍스처는 우선 1K, 도시처럼 가까이 확대할 핵심 모델만 필요하면 2K.
- 중앙 하단 피벗, Y-up, 애니메이션/리깅 없음. 모델 크기는 지도에 넣을 때 통일합니다.
- 바다·하늘·전체 나라·두꺼운 전시 받침대가 생성되면 제외하고 다시 조정합니다.
- 위에서 비스듬히 봤을 때 형태가 읽히는지, 검거나 비어 있는 면이 없는지 확인합니다.
- 파일은 이 문서와 같은 폴더의 `props/`에 위 파일명으로 둡니다. 완성 후
  `layout.json`의 `props` 배열에 아래처럼 등록하면 지도에서 읽습니다.
  배열이 비어 있는 지금은 기본 절차형 지형/장식을 사용합니다.

  ```json
  {"model":"mountain-ridge","position":[1100,440],"size":18,"rotation":0.4}
  ```

  `model`은 .glb를 제외한 파일명, `position`은 지도 좌표, `size`는 3D 장면의
  최대 가로 길이, `rotation`은 Y축 라디안 회전입니다. 지형을 덮어 장식하는
  방식이므로 나라 경계와 무역 규칙에는 영향을 주지 않습니다.
- 유료 생성은 이 작업에서 실행하지 않았습니다. 사용자가 Tripo에서 제작할 프롬프트입니다.
