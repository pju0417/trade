# 항구 지도 · 2026-11-23

기존 `pju0417/trade` 저장소를 `game-source/`에 가져와 화면 계층에 3D 항구를 추가했다. 기존 배포 웹앱의 경로는 `/trade/webapp/`다. 이 작업은 로컬 변경이며 GitHub에 push하거나 배포하지 않았다.

## 실행

저장소 루트 `game-source/`에서 `python -m http.server 8001 --bind 127.0.0.1`을 실행한 뒤 다음 주소를 연다.

- 지도 미리보기: <http://127.0.0.1:8001/webapp/harbor.html>
- 기존 게임: <http://127.0.0.1:8001/webapp/>
- 교사 로컬 시험: <http://127.0.0.1:8001/webapp/host.html?local=1>
- 학생 로컬 시험: <http://127.0.0.1:8001/webapp/student.html?local=1>

미리보기에는 방 접속 없이 나라·산업 레벨·세대를 바꾸는 조작부가 있다. 실제 학생 화면에는 임의로 발전시키는 조작부가 없고, 접속 후 ‘우리 나라 항구 지도 열기’를 누르면 엔진이 보낸 상태만 반영한다. `file://`로 직접 HTML을 열면 모듈·GLB를 읽지 못하므로 HTTP 서버가 필요하다. 배포 파일에는 Three.js를 포함해 CDN 없이 로드한다.

## 코드에서 확인한 연결점

- `webapp/API.md`, `webapp/py/classroom.py:view()`: `levels`, `main`, `machine_gen`, `electronics_gen`, `stock`, `room`, `transactions_this_round`가 이미 있다.
- 원래 엔진에 자동차·비행기·운송 시간이라는 상품이나 계산 규칙은 없다. 따라서 이번 차량·항공기는 산업 발전의 **외형 표현**이다.
- 화면은 `webapp/js/student-ui.js`에서 상태를 받아 `harbor-embed.js`에 전달한다. 새 캔버스는 매번 다시 그리는 거래 폼 바깥에 있으므로 카메라와 지도는 상태 갱신 때 유지된다.
- `webapp/py/`, `engine_bundle.json`, `js/engine-*`, `host.js`, `student-client.js`, `transport.js`, 동결 원본은 수정하지 않았다.
- 교사 화면의 ‘항구 외형 미리보기’는 해당 나라를 선택해 여는 **독립 미리보기**다. 실시간 연동은 학생 화면의 지도에서 한다.

## 발전 기준

| 표현 | 엔진의 실제 입력 | 단계 |
| --- | --- | --- |
| 항구·창고 | `levels[main]` 1~4 | 벽돌 창고·목재 부두 / 증축·소형 크레인 / 현대 창고·콘크리트 안벽 / 태양광 창고·스마트 부두 |
| 배·트럭 | `machine_gen`와 창고에 남은 기계의 가장 높은 세대 중 큰 값 | 증기 화물선·초기 트럭 / 디젤 화물선·디젤 트럭 / 컨테이너선·전기 물류차 |
| 비행기 | `electronics_gen`와 창고에 남은 전자제품의 가장 높은 세대 중 큰 값 | 복엽기 / 쌍발 프로펠러기 / 제트 화물기 |
| 하역장 화물 | 창고의 사용 가능한 재고 합계 | 최대 18개로 시각화; 실제 개수는 기존 창고 UI 확인 |
| 국가 배경 | 선택한 국가 | 바나나 농장 / 밀밭 / 유류 탱크 / 기계 공장 / 광산 / 전자 산업 건물 |

다른 나라가 시장에 올린 첨단 제품만으로는 우리 나라의 외형이 바뀌지 않는다. 수입한 첨단 제품을 보유하면 해당 세대를 보여 주고, 판매해 창고에서 없어지면 원래 생산 세대로 돌아갈 수 있다. 라운드나 돈만으로 자동 근대화하지 않는다. 게임 내 일시정지와 OS의 동작 줄이기를 반영한다.

이것은 역사 연대의 엄밀한 재현이나 새로운 보너스 체계가 아니다. 모든 나라가 기계·전자제품 투자 또는 수입으로 기술 표현을 바꿀 수 있다. 운송 수단을 실제 생산량·거래 속도와 연결하려면 별도의 규칙 합의와 균형 검증이 필요하다.

## 파일과 모델

`webapp/assets/harbor/`에 기존 모델 3개의 최적화 사본과 새로 만든 독립 GLB 15개가 있다. 원본 3개는 상위 작업 폴더에 그대로 보존된다.

| 기존 모델 | 원본 | 웹용 | 삼각형 |
| --- | ---: | ---: | ---: |
| 벽돌 창고 | 70,872,192 B | 1,439,712 B | 33,557 |
| 목재 부두 | 67,050,292 B | 1,463,808 B | 34,307 |
| 증기 화물선 | 66,832,100 B | 1,540,164 B | 35,303 |

텍스처는 최대 1024픽셀 WebP, 지오메트리는 약 1.8%로 축소했다. 실루엣·재질을 브라우저에서 육안 확인했으며 원본 수준의 근접 디테일을 보존하는 파일은 아니다. 과정과 수치는 `optimization-report.json`에 기록했다.

추가 모델은 외부 AI 생성이 아닌 코드로 제작한 기본 로우폴리 모델이다. 모두 Y축 위, 미터 단위다. 지상 모델은 바닥 근처를 기준으로 하고 배는 수면 배치를 고려한 원점을 쓴다. 수정 가능한 원본은 `webapp/js/harbor-models.js`다.

- `harbor-crane.glb`, `gantry-crane.glb`
- `early-truck.glb`, `diesel-truck.glb`, `electric-truck.glb`
- `diesel-freighter.glb`, `container-ship.glb`
- `biplane.glb`, `turboprop.glb`, `cargo-jet.glb`
- `modern-warehouse.glb`, `smart-warehouse.glb`
- `concrete-quay.glb`, `smart-quay.glb`, `factory.glb`

맵은 `harbor-scene.js`에서 조립하는 실시간 Three.js 장면이다. **맵 전체를 합친 단일 GLB는 이 산출물에 포함되지 않는다.** 독립 에셋을 교체·배치할 수 있는 게임 맵을 구현했다.

## 다음 고품질 모델 제작 순서

1. **컨테이너선과 갠트리 크레인**: 기존 증기선과 현대 단계의 품질 차이가 가장 크므로 먼저 교체하면 좋다.
2. **세 국가 생산 시설**: 기계 공장, 전자제품 공장, 광산 입구. 실제 상품 `machine`, `electronics`, `ore`와 직접 대응한다.
3. **유류 저장 탱크·시추 시설, 바나나 농장·밀밭**: 나머지 세 나라의 특징을 강화한다.
4. **트럭 3종·항공기 3종**: 작은 화면에서는 잘 보이지 않으므로 주인공 모델보다 나중에 세밀하게 만든다.

Tripo로 만들 때는 각각 독립 작업으로 생성한다. 공통 조건: single standalone asset, complete geometry, realistic historical or modern industrial construction as specified, muted natural colors, no terrain, no people, no water, no scenery, no text or logos, no display base. 기존 19세기 모델과 맞추려면 ‘사실적 재질, 과도한 미래 장식 없음’을 유지한다. 새로운 Tripo 크레딧은 사용하지 않았다.

### 바로 쓸 수 있는 추가 프롬프트

**컨테이너선**

> A single standalone modern small coastal container cargo ship, full hull including keel and propeller, dark navy riveted steel hull with a muted red lower hull, cream aft superstructure with bridge windows, stacked corrugated shipping containers in muted rust red, teal and ochre, realistic working vessel proportions, complete geometry on all sides, weathered PBR materials. Ship only, no water, no harbor, no people, no text, no logos, no display base.

**갠트리 크레인**

> A single standalone modern port ship-to-shore gantry crane, muted industrial yellow steel frame, four sturdy wheeled legs, elevated operator cabin, long horizontal boom projecting over a quay, suspended rectangular container spreader with thick visible cables, realistic load-bearing structural geometry, weathered painted metal and bolts, complete 3D asset. Crane only, no container ship, no port ground, no water, no people, no text, no logos, no display base.

**기계 공장**

> A single standalone early 20th-century machine manufacturing factory, long weathered red brick workshop with a sawtooth roof, large industrial multi-pane windows, two brick smokestacks, wide steel loading doors, exposed exterior pipes, muted realistic materials, complete exterior on all sides. Building only, no terrain, no other buildings, no people, no smoke cloud, no text, no logos, no display base.

## 재생성과 확인

Node.js 개발 도구를 사용할 때 `npm ci` 후 `npm run assets`로 기존 3개를 최적화하고 추가 15개를 다시 만든다. 렌더링 파일은 이미 포함돼 있으므로 보통 실행에는 npm 설치가 필요 없다.

- `node --test webapp/tests/harbor.test.mjs`: 5개 통과. 실제 세대 반영, 시장 상품 오인 방지, 입력 비변경, 18개 GLB 무결성·용량 검사.
- `python -X utf8 webapp/tests/test_actions.py unit`: 69개 행동 통과.
- `python -X utf8 webapp/tests/test_equivalence.py 0 5`: 시드 0~4, 5판 기존 엔진과 일치.
- 기존 Node/Pyodide `node_host.mjs`: 133개 행동, 164개 로그 통과. `node_class.mjs`: 방 3개 진행 검사 통과.
- 브라우저: 기본·스마트 항구, 국가/단계 제어, 로컬 교사 수업 생성→학생 접속→지도 열기→투자(바나나 Lv.1→2)·지도 유지 확인. 학교 실제 여러 기기·Firebase 부하 검증은 하지 않았다.
- Windows `core.autocrlf=true` 때문에 기존 `build_bundle.py --check`의 바이트 해시 비교는 줄바꿈 차이로 실패한다. LF로 정규화해 비교한 25개 파일 내용은 기존 번들과 모두 같으며 번들을 재생성하지 않았다.
