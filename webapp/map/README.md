# 무역 게임 세계 지도

9개국이 사는 **가상 세계**를 문명·Anno 느낌으로 보여 주는 지도 화면 부품이다. 멀리서는 나라 색·국경·무역로가 보이고, 확대하면 지형·밭·숲·도시, 더 확대하면 3D 항구·배·도시 건물·산업 건물이 보인다. 지도 디자인은 Claude가 맡는다(사용자 결정 2026-11-24). 게임 상태(`profiles`, `world_trades`)를 넣으면 그 라운드의 실제 거래가 무역로로, 산업 레벨이 건물 수로 그려진다.

- 데모: `https://pju0417.github.io/trade/webapp/map/` (주소 뒤 `?me=Tropia` 우리 나라 표시, `?nodemo` 가짜 거래 끄기, `?panel=0` 설명 패널 숨김)
- 화면 사진: `screenshots/`

## 파일

| 경로 | 내용 |
| --- | --- |
| `src/map-core.js` | **원본 코드 전부.** `createWorldMap(container, THREE, opts)` 한 함수. 고칠 때는 여기만 고친다 |
| `build.mjs` | `node webapp/map/build.mjs` → 아래 4개 파일을 다시 만든다 |
| `world-map.js` | 웹앱 화면용 ES 모듈(자동 생성) |
| `index.html` | 데모 페이지(자동 생성) |
| `dist/world-map-demo.html` | 한 파일짜리 데모, three는 CDN(자동 생성, PC용) |
| `dist/world-map-demo.jsx` | iPad(claude.ai 아티팩트) 테스트용(자동 생성). GLB 불러오기 없음 |
| `vendor/` | three.js r128 `three.min.js`, `GLTFLoader.js` (MIT, `LICENSE-three.txt`) |
| `tests/map_check.py` | 브라우저 검사(아래) |
| `TRIPO.md` | Tripo 3D 모델 만들기: 설정과 프롬프트 |

## 화면에 붙이기

```html
<div id="map" style="position:relative;width:100%;height:480px;"></div>
<script src="map/vendor/three.min.js"></script>
<script type="module">
  import { createWorldMap } from './map/world-map.js';
  const map = createWorldMap(document.getElementById('map'), THREE, { me: 'Tropia', panel: false });
  me.onState((state) => map.update(state));   // StudentClient 상태를 그대로 넣으면 된다
</script>
```

| 메서드 | 설명 |
| --- | --- |
| `update(state)` | 학생 상태(또는 같은 필드를 가진 객체)를 넣는다. 쓰는 필드: `names`, `country`(우리 나라), `profiles`(산업 레벨→건물 수, 학생 표시), `world_trades`(무역로), `round`, `phase_label` |
| `setTrades(trades)` / `setProfiles(p)` / `setMe(key)` | 위를 따로 넣기 |
| `flyToNation(key)`, `selectNation(key)`, `flyTo(x, z, 거리)`, `setView(x, z, 거리)` | 카메라·선택 |
| `getState()` | `{x, z, dist, zoom, trees, calls, routes, props}` (검사용) |
| `nations` | `[{key, ko, good, port:{x,z}, center:{x,z}, cells}]` |
| `loadFile(File)`, `placeModel(object3D, 이름, 나라?)` | Tripo GLB를 항구 등대 자리에 놓기(HTML에서 `opts.GLTFLoader` 줄 때만) |
| `dispose()` | 정리 |

`opts`: `me`, `demo`(가짜 라운드 자동 진행), `panel`(설명 패널, 기본 켬), `panelFolded`, `nationBar`(아래 나라 버튼, 기본 켬), `legend`(거래 범례, 기본 켬), `title`, `onSelect(key)`, `GLTFLoader`, `start:[x, z, 거리]`.

## 세계 구성

모양은 코드로 만들고 항상 같다(난수 시드 고정). 나라 배치는 `NATIONS`, 같은 대륙으로 잇는 나라는 `CONTINENTS`에 있다.

**세계 크기**: `opts.worldScale`(기본 0.65, 2026-11-24 "지도가 너무 크다"로 줄임). 나라 배치와 모양은 그대로 두고 크기만 바뀐다. 항구·집·나무 크기와 레이어가 바뀌는 카메라 거리는 그대로다. 작은 나라(노비아·페리아)는 수도·마을 자리를 못 찾으면 간격·높이 조건을 조금씩 풀어서 찾는다.

| 나라 | 대표 산업 | 지형 | 대륙 |
| --- | --- | --- | --- |
| 메카니아 | ⚙️ 기계 | 온대·숲 | 서북 대륙 |
| 그레니아 | 🌾 밀 | 들판(밭 무늬) | 서북 대륙 |
| 페리아 | ⛏️ 광물 | 침엽수·높은 산 | 서북 대륙 |
| 오일리아 | 🛢️ 연료 | 사막 | 가운데 대륙 |
| 트로피아 | 🍌 바나나 | 열대 밀림 | 가운데 대륙 |
| 테크니아 | 💻 전자제품 | 온대·숲 | 가운데 대륙 동북쪽 |
| 노비아 | 💻 전자제품 | 섬나라 | 동북 섬 |
| 미네리아 | ⛏️ 광물 | 붉은 황무지·산 | 남동 대륙 |
| 아그레아 | 🍌 바나나 | 열대 | 남서 대륙 |

항구는 나라마다 하나, 해안 중 세계 가운데에 가까운 곳에 자동으로 놓인다. 항구 모양은 대표 산업을 따른다(컨테이너·석유·광석·곡물·과일).

**도시·마을** (`SETTLE`): 나라마다 수도 1곳(나라 가운데쯤 낮은 땅)과 마을 2~3곳(작은 나라 2곳). 모두 34곳, 건물 약 4,000채.
- 수도: 바둑판 거리, 가운데 광장과 시청(지붕이 나라 색)·깃발, 큰길 2개. 가운데로 갈수록 빽빽하고 높다. 고층 빌딩 비율은 `MODERN`(테크니아 1.0 … 페리아 0.15)
- 마을: 큰길 하나를 따라 집이 늘어선 모양, 가운데에 작은 마을회관
- 집 모양은 지형을 따른다(`STYLES`): 온대 주황 지붕, 사막 평지붕·돔, 열대 알록달록한 집과 초가 오두막, 침엽수 지대 나무집, 황무지 양철 지붕, 섬나라 흰 벽·파란 지붕
- 길: 수도↔항구, 마을↔가장 가까운 수도·항구·마을(바다를 건너는 길은 만들지 않음)
- 도시 둘레에 밭(셰이더로 그려서 확대해도 경계가 깨끗함). 그레니아는 나라 전체가 밭
- 건물은 모양 5가지(벽·박공지붕·돔·원뿔·원기둥)를 인스턴싱으로 그려 그리기 호출 6번이면 끝난다

## 확대 단계

레이어는 실제 카메라 거리로 정한다: `layerZ()` = 거리 1.6~190의 로그 비율(세계 크기와 무관). 카메라 기울기만 `zoomT()`(최대 거리 = 190 × 세계 크기)를 쓴다.

| z | 단계 | 보이는 것 |
| --- | --- | --- |
| > 0.64 | 1 세계 | 나라 색, 나라 이름·레벨, 무역로·화물 점 |
| 0.43 ~ 0.64 | 2 대륙 | 지형 색(사막·밭·밀림·산·눈), 큰 숲 덩어리, 도시·마을·길(z < 0.63부터), 수도 이름 |
| < 0.43 | 3 지역 | 나무 한 그루씩, 3D 항구·배·산업 건물·그림자, 도시 건물 가까이 |

국경선은 z > 0.3이면 보인다. 국경까지 거리(부호 있음)를 따로 저장해 화면 픽셀 기준으로 그려서 확대해도 계단이 생기지 않는다. 해안선도 지형 높이로 같은 방식으로 그린다.

산업 건물 수: 대표 산업 레벨 1/2/3/4 → 3/6/10/15개, 다른 산업 → 1/3/5/8개(나라당 자리 40개까지).

## 지켜야 할 것

- **three.js r128 고정.** claude.ai JSX 환경이 r128이라 맞춘다. `onBeforeCompile` 셰이더 패치가 r128 청크(`map_fragment`, `mapTexelToLinear`)에 기대고 있어 버전을 올리면 깨진다. 렌더러 출력은 Linear(색을 적은 그대로).
- `InstancedMesh.setColorAt`은 `count`를 0으로 바꾸기 **전에** 부른다(r128은 count 크기로 색 버퍼를 만든다. 아니면 나무가 검게 나온다). 인스턴스 메시는 `frustumCulled = false`.
- 지도는 화면 부품이다. 엔진·통신 코드(`py/`, `js/engine-*`, `host.js`, `student-client.js`, `transport.js`)를 건드리지 않고 상태만 읽는다.
- 학생 기기(iPad·크롬북)에서 돌아야 한다. 설명 패널의 "그리기 호출" 수와 나무 수를 보며 늘린다.

## 검증

```bash
node webapp/map/build.mjs
python3 webapp/map/tests/map_check.py /tmp/map_results          # Playwright + Chrome
```

2026-11-24 결과: 15개 항목 모두 통과(9개국 땅 넓이, 수도 9곳·마을, 도시 건물 수, 데모 무역로, 항구 9곳 스크린샷, 게임 상태 → 무역로 4개·건물 90개, 우리 나라 표시, 나라 클릭 카드, 드래그·휠, 나라 버튼 날아가기, GLB 배치, 브라우저 오류 없음). 헤드리스 크롬(SwiftShader)에서만 확인했고 **실제 iPad·크롬북 터치와 성능은 아직 확인하지 않았다.**

## 다음 할 일

1. 실제 iPad·크롬북에서 데모 열어 보기(터치, 속도)
2. Tripo로 등대 → 창고 → 크레인 순으로 만들어 데모에 끌어다 놓고 화풍 확인(`TRIPO.md`)
3. 화풍이 맞으면 `makePort()`·산업 건물의 임시 모델을 GLB로 바꾸는 구조 만들기
4. 학생·교사 화면(디자인 작업)에 지도 붙이기
