# 무역 게임 웹앱

검증한 v17 엔진(확정 규칙 v1)을 그대로 쓰는 수업용 웹앱이다. 화면은 기능 확인용이며 디자인은 따로 입힌다(`API.md`).

## 구조

- **교사 화면**(`host.html`)이 브라우저 안에서 Python 엔진을 돌린다(Pyodide, Web Worker). 게임 상태의 주인은 교사 화면 하나다.
- **학생 화면**(`student.html`)은 방 코드·나라·접속 번호로 들어와 상태를 받고 행동을 보낸다.
- **연결**: Firebase Realtime Database(학생 기기). 설정이 없으면 같은 브라우저의 탭끼리만 연결되는 로컬 시험 모드.

| 경로 | 내용 |
| --- | --- |
| `py/classroom.py` | 학생 입력을 받는 세션. 원본 엔진은 수정하지 않고 하위 클래스로 덮어씀 |
| `engine_bundle.json` | 엔진 파일 25개 묶음(`build_bundle.py`로 생성, SHA-256 포함) |
| `js/engine-core.js` | Pyodide에서 엔진 실행 |
| `js/engine-worker.js`, `js/engine-client.js` | 교사 화면의 Web Worker와 그 손잡이 |
| `js/host.js` | 교사 쪽 진행: 접속 번호 확인, 행동 순서 처리, 상태 배포, 저장·이어하기 |
| `js/student-client.js` | 학생 쪽 API |
| `js/transport.js` | 로컬(BroadcastChannel)·Firebase 연결 |
| `js/host-ui.js`, `js/student-ui.js`, `*.html` | 기능 확인용 화면 |
| `vendor/pyodide/` | Pyodide 0.27.7 런타임(14MB, MPL-2.0). 없으면 jsDelivr CDN에서 받음 |
| `tests/` | 검증 스크립트 |

## 한 라운드 진행

| 단계 | 학생 | 선생님이 다음 단계로 넘기면 |
| --- | --- | --- |
| 판매 등록 | 물건 내놓기·거두기·가격 바꾸기 | AI 판매 등록, AI 1차 구매 |
| 거래 | 시장에서 사기, 직접 거래 제안·수락, 추가로 내놓기 | AI 2차 구매 → 안 팔린 학생 물건은 창고로 → 정산(식량, 전자제품, 국가 운영, 국가 수입) |
| 투자·주력 선택 | 투자(1~7라운드, 1번), 다음 주력 산업 | AI 투자, 주력, 가격 갱신 → 다음 라운드 생산 |

생산과 정산은 자동이다. 학생이 아무것도 하지 않아도 게임은 진행된다.

## 사람이 하기 위해 더한 규칙

학생이 0명이면 원본 엔진과 결과가 똑같다(아래 검증). 학생이 있을 때만 다음이 적용된다.

- 학생이 시장에 내놓은 물건만 AI가 살 수 있다. AI는 기준 가격 이하로 내놓은 물건만 시장에서 산다. 협상에서는 AI가 부르는 값(기준 × (0.95 − 신뢰 할인)) 이하일 때 학생이 정한 값에 산다.
- AI가 학생과 자동으로 물물교환하지 않는다. 학생 창고에서 내놓지 않은 물건을 가져가지 않는다.
- 학생이 AI 나라에 제안하면 원본 엔진의 협상 조건으로 답한다. 팔 때는 AI가 부르는 값 이상이어야 한다. 살 때는 AI에게 필요한 물건이어야 하고 기준 가격 이하여야 한다. 물물교환은 가치 비율이 0.75~1.33이어야 한다.
- 안 팔린 학생 물건은 거래 단계가 끝나면 창고로 돌아온다. 판매 중인 물건은 정산에 쓸 수 없다.
- AI용 투자 안전장치(예비금, 생활 우선, 다음 생산 재료 확인)는 학생을 막지 않는다. 법적 조건(1~7라운드, 라운드당 1번, 비용, 광물, 기계 세대, 레벨 4 미만, 새 산업은 3라운드부터)은 그대로다.

이 추가 규칙이 점수 균형에 주는 영향은 `docs/webapp_human_play.md`에 있다.

## 실행

```bash
# 저장소 루트에서
python3 -m http.server 8000
# 교사: http://localhost:8000/webapp/host.html
# 학생: http://localhost:8000/webapp/student.html  (로컬 모드는 같은 브라우저의 다른 탭)
```

`file://`로 열면 Web Worker가 동작하지 않는다. 반드시 웹 서버(로컬 서버나 GitHub Pages)로 연다.

## 학생 기기에서 접속하기 (Firebase)

1. Firebase 콘솔에서 프로젝트를 만들고 **웹 앱**을 추가한다.
2. **Realtime Database**를 만든다(위치 아무 곳).
3. 규칙을 수업용으로 연다(방 코드를 아는 사람만 쓰는 수준의 보안):
   ```json
   { "rules": { "rooms": { "$room": { ".read": true, ".write": true } } } }
   ```
4. 웹 앱 설정 객체(`apiKey`, `authDomain`, `databaseURL`, `projectId`, `appId` 등)를 `js/config.js`의 `FIREBASE_CONFIG`에 붙여 넣는다.
5. 웹앱을 GitHub Pages 등에 올리고, 학생은 `student.html` 주소로 들어온다.

접속 번호는 교사 화면에만 있고 데이터베이스에 저장하지 않는다. 다만 학생 행동은 처리될 때까지 잠깐 데이터베이스에 남는다. 그래서 초등 수업 수준의 보안으로 본다.

## 검증 (모두 `tests/`)

| 스크립트 | 확인 내용 | 결과 |
| --- | --- | --- |
| `test_equivalence.py A K` | 학생 0명 세션을 단계별로 진행한 결과가 `sim_lib.make_game(seed, fee=1.0, l3_flat=True)`와 같음(점수, 전체 거래 목록, 가격, 라운드 기록) | 200판 일치 |
| `test_equivalence.py targets` | 수출 목표·점수 공식이 `final_validation`과 같음 | 일치 |
| `test_actions.py unit` | 행동 종류별 규칙·거절 메시지·이어하기 | 통과 |
| `test_actions.py fuzz A K` | 무작위 행동: 내부 오류 0, 매 행동 뒤 엔진 `verify()`, 기록 재생 일치 | 100판, 행동 약 3만 4천 개 통과 |
| `make_golden.py` + `node_crosscheck.mjs` | CPython과 Pyodide(브라우저용)의 화면 상태가 행동마다 같음 | 14판 일치 |
| `node_host.mjs` | 교사·학생 3명 전체 흐름, 접속 번호, 중복 요청, 이어하기 | 통과 |
| `node_firebase_mock.mjs` | Firebase 연결 코드(가짜 DB): 요청·결과·정리, 교사 화면 재시작 | 통과 |
| `browser_e2e.py OUTDIR` | 실제 크롬: Pyodide 로딩, 교사 1 + 학생 3 탭, 버튼으로 한 판, 새로고침 후 이어하기 | 통과 |

```bash
cd webapp/tests
PYTHONDONTWRITEBYTECODE=1 python3 test_equivalence.py 0 20
PYTHONDONTWRITEBYTECODE=1 python3 test_actions.py unit
npm install pyodide@0.27.7   # Node 테스트용(한 번)
PYODIDE_MODULE=$PWD/node_modules/pyodide/pyodide.mjs node node_host.mjs
python3 browser_e2e.py /tmp/e2e     # playwright + chrome 필요
```

엔진이나 `py/classroom.py`를 바꾸면 `python3 webapp/build_bundle.py`로 묶음을 다시 만든다. `--check`로 묶음과 원본이 같은지 확인한다.

## 확인하지 못한 것

- 실제 Firebase 서버 연결(여기서는 접속 불가). 연결 코드는 가짜 DB로, 함수 이름은 firebase@10.12.2 패키지로만 확인했다.
- 학교 PC·태블릿에서의 Pyodide 로딩 시간과 메모리.
- 실제 학생의 사용성, 80분 진행.
