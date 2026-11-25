# Tripo 3D 에셋 계획 (world-map-demo.html 기준)

## 공통 스타일 (모든 프롬프트 뒤에 붙임)
`stylized low-poly game asset, Civilization VI and Anno 1800 style, isometric strategy game, hand-painted textures, warm saturated colors, clean readable silhouette, single object on flat base, no background`

데모 적용 방식: `placeModel()`이 GLB를 최대 변 0.36 크기로 맞춰 항구 슬롯(등대 자리)에 둠. 머티리얼은 Lambert + 텍스처로 변환됨.
→ 텍스처는 켜고, 폴리곤은 낮게(가능하면 Low-poly / 10k 이하) 생성.

## 1순위 — 항구 랜드마크 (항구 타입별 1개, 데모의 등대 슬롯 교체)
| ID | 데모 타입 | 프롬프트 |
|---|---|---|
| port_container | container | container port terminal with two orange gantry cranes and stacked colorful shipping containers on a concrete quay |
| port_fruit | fruit | tropical fruit harbor with blue cranes, white refrigerated warehouse with green roof, crates of bananas |
| port_oil | oil | oil terminal with white cylindrical storage tanks, refinery towers with red bands, small flare stack |
| port_ore | ore | iron ore harbor with rust-red ore piles, yellow conveyor belt, loading tower and rail wagons |
| port_grain | grain | grain harbor with row of white silos with conical caps, elevator tower and brick warehouse |
| lighthouse | (공통) | white and red striped lighthouse on a small rocky base |

## 2순위 — 선박 (데모 makeShip 5종)
| ID | 프롬프트 |
|---|---|
| ship_container | container cargo ship, dark navy hull, stacked colorful containers, white bridge at stern |
| ship_fruit | white reefer cargo ship with white and yellow containers |
| ship_oil | oil tanker ship, dark red hull, deck pipelines, white bridge at stern |
| ship_bulk | bulk carrier ship, dark green hull, five cargo hatches, white bridge at stern |

## 3순위 — 산업 건물 (데모 PROP_GEO, 레벨업 시 늘어나는 것)
factory / tech / (crane·mine) / (oil derrick) / farm / plantation — 각 1개씩

## 4순위 — 도시 건물·자연
port town house (붉은 지붕), town hall with dome, pine tree, palm tree
