# #11 무역 게임 — 작업 지침

초등학교 6학년 사회 무역 단원 마무리 게임을 만드는 프로젝트다. 지금 있는 것은 9개국·9라운드 Python 경제 시뮬레이터(v17)와 검증 자료, 그리고 그 엔진을 브라우저(Pyodide)에서 그대로 돌리는 수업용 웹앱(`webapp/`)이다. 웹앱은 게임식 화면(첫 화면 = 3D 지도가 배경인 게임 타이틀, 학생 화면 = 전체 화면 3D 세계 지도 + HUD, 조언 캐릭터 '마루 선장', 교사 화면 = 항만 관제실, 혼자 해 보기 `play.html`)이다(2026-11-28).

## 대화 방식

- 한국어로 답한다.
- 짧고 직접적으로 말한다. 진단하고 바로 실행하되, 되돌리기 어려운 결정은 먼저 묻는다.

## 먼저 읽을 것

1. `docs/RULES_v1.md` — 확정 규칙 v1
2. `README.md` — 폴더 구조, 현재 상태, 다음 할 일
3. `docs/claude_review_report_v17.md` — Claude 교차 검증 보고서(문제 목록, 실험 결과)
4. `handoff_v17/TRADE_GAME_HANDOFF_V17_KO.txt` — ChatGPT가 만든 v17 인수인계서(규칙·코드 구조·재현 절차)

## 확정된 규칙 (사용자, 2026-11-19)

전체 목록은 `docs/RULES_v1.md`에 있다. 규칙을 바꿀 때는 이 문서부터 고친다.

- 결과는 **나라별 목표 달성도**로 보여 준다. 순위는 중심이 아니다. **공동 목표는 없다.**
- 국가 운영 자원: 연료 R3·6·9, 광물 R4·8에 나라마다 1묶음(`light`). 없으면 긴급 조달(연료 30G, 광물 20G를 국가 수입에서 차감)과 생활 점수 −1점(모자란 날마다).
- 투자: 레벨 3 비용 = 레벨 2 비용(할증 없음). 레벨 4는 2배.
- 경제 점수 20점 = 쓰인 수출 가치 / 나라별 수출 목표. 다른 나라가 실제로 쓴 물건만, min(판매가, 기준 가치), 물물교환은 기준 가치, 같은 물건 맞바꾸기 제외. 다른 물건 맞거래는 허용한다.
- 산업 능력 15점 = 대표 산업(처음 주력 산업)을 1번 이상 레벨 업하면 만점.
- 등급: A ≥ 90, B ≥ 80, C ≥ 60, D < 60.
- 대상: 학생 3명이 일부 국가를 맡고 나머지는 AI, 수업 40분+40분. 규칙은 초등학생이 직관적으로 이해할 수 있어야 한다.

## 잠정·미확인

- 시뮬레이터 수출 목표(트로피아 205, 그레니아 155, 오일리아 340, 메카니아 235, 미네리아 315, 테크니아 765G)와 웹앱 목표는 모두 잠정이다. 시범 수업 뒤 다시 본다.
- 실제 학생의 이해도, 80분 진행, 학교 기기에서의 웹앱 동작, 여러 기기 동시 접속은 확인하지 않았다. 지도를 0.25 간격으로 촘촘하게 그리면서(2026-11-27) 무거워졌으니 크롬북·iPad에서 꼭 본다. 1서버(Firebase `trade-a55c6`)와 GitHub Pages(`https://pju0417.github.io/trade/webapp/`) 연결은 2026-11-20 방 1개로 확인했다.
- 웹앱은 수출 목표 v2(트로피아 255, 그레니아 205, 오일리아 425, 메카니아 155, 미네리아 330, 테크니아 475G)를 쓴다(사용자 결정 2026-11-20). W1·W3 통과, W2 실패. 5G 내림(v3)도 W2 실패로 채택하지 않았다(`docs/webapp_human_play.md`). 원자재 진단은 `docs/raw_materials_diagnosis.md`.
- 최종 시뮬레이션(혼합 행동, 학생 3명 vs 6명)은 기준 F1~F7을 모두 통과했다(`docs/final_simulation.md`). 추가 3개국에는 수출 목표가 없어 학생 7명 이상이면 따로 정해야 한다.
- 학생 투자를 흉내 낼 때는 AI 예비금 조건을 빼고 본다(`sim_lib.LevelUpNoReserve`, `MainIndustryStudent`). 예비금은 AI 정책이지 학생 규칙이 아니다.
- 시뮬레이터 기본값(`operating_profile='none'` 등)은 원본 그대로다. 확정 규칙은 `sim_lib.make_game(seed, fee=1.0, l3_flat=True)`와 `final_validation.py`의 점수 함수로 적용한다.

## 코드 작업 규칙

- `trade_v17/source_v13/`의 `.py`와 `trade_v17/test_*.py`는 수정하지 않는다. 동결 해시 대상이라 바꾸면 기존 검증 영수증이 깨진다.
- `handoff_v17/`은 전달받은 원본이다. 수정하지 않는다(`HANDOFF_MANIFEST.json`에 해시가 있다).
- 새 검증 코드와 결과는 `claude_review/` 아래에 둔다. 엔진을 바꿀 때는 원본을 고치지 말고 하위 클래스로 덮어쓴다(`claude_review/new_sims.py`의 `Skip`, `Emergency` 참고).
- 실험은 한 번에 한 요인만 바꾼다. 성공 기준은 실행 전에 정한다. 결과를 보고 목표나 계수를 맞추지 않는다.
- 확정 규칙의 점수는 `final_validation.py`의 `total()`로 계산한다. v17 원래 비교 점수(`fixed_evaluation.score`, v15 목표)는 옛 기준과 비교할 때만 쓰고 섞지 않는다.
- 국가별 1위 횟수를 같게 만드는 것을 공정성 목표로 삼지 않는다. 생활 유지, 무역 필요, 투자 선택, 실제 활용, 목표 달성 가능성을 함께 본다.
- 실행한 게임 수, 시드, 실패·재시도를 기록한다. 읽지 않은 파일이나 돌리지 않은 계산을 확인했다고 쓰지 않는다.
- Python 3.10 이상, 표준 라이브러리만 쓴다. 바이트코드 파일이 원본 폴더에 생기지 않게 `PYTHONDONTWRITEBYTECODE=1`로 실행한다.

## 웹앱 작업 규칙

- 웹앱은 원본 엔진을 Pyodide에서 그대로 돌린다. 규칙·계산은 `webapp/py/classroom.py`(하위 클래스)에서만 바꾸고 원본은 건드리지 않는다.
- 학생 0명 세션은 `sim_lib.make_game(seed, fee=1.0, l3_flat=True)`와 결과가 같아야 한다(`webapp/tests/test_equivalence.py`). 사람용 추가 규칙은 학생이 있을 때만 작동해야 한다.
- `classroom.py`나 엔진 묶음 대상 파일을 바꾸면 `python3 webapp/build_bundle.py`로 `engine_bundle.json`을 다시 만들고 `webapp/README.md`의 검증을 다시 돌린다.
- 서버 1개 = Firebase 프로젝트 1개(무료 동시 접속 100). `webapp/js/config.js`의 `SERVERS` 순서가 방 코드의 서버 번호이므로 순서를 바꾸지 않는다. 교사 화면 하나가 여러 방(독립 게임)을 엔진 하나로 돌린다.
- 화면 디자인은 GPT와 Claude가 같이 작업한다(사용자, 2026-11-26). 학생 게임 화면은 전체 화면 지도 + HUD(`webapp/student.html`, `js/student-ui.js`, `game.css`)다. 화면 코드(`*.html`, `js/*-ui.js`)와 엔진·통신 코드(`py/`, `js/engine-*`, `host.js`, `student-client.js`, `transport.js`)를 섞지 않는다. 화면이 쓰는 계약은 `webapp/API.md`다.
- `webapp/tests/browser_e2e.py`는 학생 화면 개편(2026-11-26) 전 기준이라 새 화면 선택자로 고쳐야 한다(사용자가 이어서 작업 예정). 바뀐 것: 메시지는 `#msg` 대신 `#toasts` 알림, 준비 완료는 `.turn-dial`, 수량·가격은 [−]/[+] 조절기(`data-act="step"`), 처음에 선장 안내(`[data-adv=tour-skip]`), 혼자 해 보기 진행 막대는 접혀 있음(`#bar-handle`).
- 화면을 고치면 `webapp/tests/ui_play.cjs`, `ui_advisor.cjs`, `ui_host.cjs`로 확인한다(웹 서버 없이 Playwright가 파일을 직접 넘긴다). 게임 화면 버튼은 trade.css·atlas.css의 공통 버튼 규칙이 덮으므로 `game.css`·`host.css`에서는 `.game`·`.host-page` 접두어로 쓴다.
- 게임 글꼴은 주아(`webapp/assets/fonts/jua/`, SIL OFL)를 저장소에 넣어 쓴다(학교 네트워크에서 외부 글꼴이 막힐 수 있음). 이모지 대신 `js/good-icons.js`의 `goodIcon`·`uiIcon` 그림 아이콘을 쓴다.
- 조언 캐릭터 '마루 선장'(`webapp/js/advisor-ui.js`): 캐릭터 그림·말풍선 디자인은 GPT가 맡는다(사용자, 2026-11-27). 그림은 `face(mood)`(mood = '' | 'warn' | 'happy')와 `game.css`의 `.advisor*`만 바꾸면 된다. 조언 내용(`adviceFor`)과 안내 순서(`tour`)는 Claude가 맡는다. 결과가 일률적이 되지 않게 조언을 규칙 경고(늘)와 전략 조언(단계에 따라 줄임)으로 나누고, 교사가 도움 수준(많이·보통·경고만·끔, 기본 보통)을 고른다. 수량·가격은 칸에 미리 채우지 않는다(사용자 결정 2026-11-28). 선장 말대로만 하는 학생은 보통 수준에서 모두 D(49~55점), 생각하는 학생은 90~95점이었다(`docs/advisor_follower.md`, 150판). 조언을 늘릴 때는 이 시뮬레이션을 다시 돌린다.
- 재미 요소(`webapp/js/fun-ui.js`, 2026-11-28): 거래 연출·효과음, 라운드 시작 카드(결산 + 바닷길 신문), 업적 배지, 시상식, 지도 마을 분위기(`setMood`), 교사 무역로 다시 보기. 상태를 읽기만 하고 점수·규칙에 영향을 주지 않는다(배지도 점수 아님). 라운드 카드가 화면을 덮으므로 화면 검사 스크립트는 `.fun-card [data-fun=close]`로 닫는다. 확인은 `webapp/tests/ui_fun.cjs`.
- 세계 지도의 디자인은 Claude가 맡는다(사용자, 2026-11-24). 데모는 `version2/world-map-demo.html`, 게임용은 `webapp/js/world-engine.js`이고 둘에 같은 `createWorldMap`이 들어 있으므로 함께 고친다. 게임은 `political: false`, `theme: 'game'`(지도 컨트롤을 HUD 톤으로)으로 쓰고 학생 화면은 `card: false`, 첫 화면 배경은 `controls: false`(조작 버튼 없음)다. 첫 화면도 3D 지도를 그리므로 학교 기기 성능 확인 대상이다. 데모 기본도 게임과 같은 지도이고 `?political`이면 예전 정치 색 지도다. 지도를 고치면 `webapp/tests/map_audit.cjs`로 뜨거나 묻힌 물건·끊긴 길이 0인지 확인한다(물 위 길 1곳은 항구 부두). 물건·길·강은 화면에 그려지는 지형 높이 `meshH`에 놓는다. 해안은 바다까지 거리 `CD`로 모래사장·절벽을 나누고, 산업 하나가 레벨 3이 되면 고개 길이 터널로 바뀐다. three.js는 r128 고정(`webapp/assets/world/vendor/`). Tripo 원본 4K 모델은 `version2/assets/models/`에 로컬로만 두고, 경량화본만 저장소에 넣는다.

## 저장소에 없는 대형 파일

`trade_v17/operating_results/`의 대형 원본 6개(약 359MB)는 GitHub 용량 제한 때문에 넣지 않았다. 목록과 SHA-256은 `README.md`에 있다. 전체 원장 재검산이나 `recompute_v17.py` 재실행에만 필요하다. 그 결과를 요약한 `claude_review/games_compact.json.gz`는 저장소에 있다.
