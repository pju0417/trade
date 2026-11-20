# 무역 게임 웹앱 API (화면 디자인용)

화면(디자인)을 새로 만들 때는 **이 문서의 객체만 쓰면 된다.** 게임 규칙·계산은 모두 교사 화면에서 도는 엔진(`webapp/py/classroom.py` + 검증된 v17 엔진)이 한다. 화면은 상태를 그리고 행동을 보내기만 한다.

바꾸면 안 되는 것: `webapp/py/`, `webapp/engine_bundle.json`, `webapp/js/engine-*.js`, `webapp/js/host.js`, `webapp/js/student-client.js`, `webapp/js/transport.js`, `webapp/vendor/`.
바꿔도 되는 것: `webapp/*.html`, `webapp/js/host-ui.js`, `webapp/js/student-ui.js`, `webapp/js/lobby.js`, `webapp/js/dom.js`, CSS, 이미지. React 등 다른 틀로 새로 만들어도 된다. 서버 목록은 `webapp/js/config.js`(`FIREBASE_SETUP.md`).

화면을 만들 때 주의: 남은 시간처럼 1초마다 바뀌는 값은 그 글자만 바꾸고, 버튼이 있는 부분 전체를 1초마다 다시 그리지 않는다(누르는 순간 버튼이 바뀌면 클릭이 빠진다).

## 학생 화면: `StudentClient`

```js
import { StudentClient } from './js/student-client.js';
import { openServer, parseRoomCode, serverList } from './js/transport.js';

const code = parseRoomCode('2-K7QPM-1');            // null이면 잘못된 방 코드. code.server = '2'
const server = await openServer(code.server);       // 서버 연결(페이지당 하나)
const me = new StudentClient({ transport: server.room(code.code), country: 'Tropia', token: '4821' });
me.onState((state) => draw(state));     // 상태가 바뀔 때마다 전체 상태가 온다
const r = await me.connect();            // {ok, msg}
const leave = server.presence.join({ role: 'student', room: code.code, country: 'Tropia' }); // 접속 인원에 표시
```

- 방 코드는 `서버-수업-방번호`다(예: `2-K7QPM-1`). 로컬 시험 모드는 서버 자리가 `L`이다.
- 같은 나라에 여러 기기가 같은 접속 번호로 들어와도 된다(모둠). 모두 같은 상태를 받고, 누가 누르든 차례대로 처리된다.

모든 행동은 `Promise<{ok, msg, ...}>`를 돌려준다. `ok:false`면 `msg`(한국어)를 그대로 보여 주면 된다. 화면에서 미리 막지 않아도 엔진이 규칙을 검사한다.

| 메서드 | 단계 | 설명 |
| --- | --- | --- |
| `list(good, qty, price, gen=1)` | 판매 등록, 거래 | 창고 물건을 시장에 내놓기. 가격은 1G 이상 정수 |
| `cancel(oid)` | 판매 등록, 거래 | 내 판매 물건 거두기 |
| `reprice(oid, price)` | 판매 등록, 거래 | 가격 바꾸기 |
| `buy(oid, qty)` | 거래 | 시장 물건 사기 |
| `offerSell(to, {good, qty, gen}, cash)` | 거래 | 다른 나라에 돈 받고 팔겠다고 제안 |
| `offerBuy(to, {good, qty, gen}, cash)` | 거래 | 다른 나라 물건을 돈 주고 사겠다고 제안 |
| `offerBarter(to, give, get)` | 거래 | 물물교환 제안(같은 물건끼리는 안 됨) |
| `respond(offerId, accept)` | 거래 | 나에게 온 제안 수락/거절 |
| `withdraw(offerId)` | 거래 | 내가 보낸 제안 취소 |
| `ready(on)` | 모든 단계 | 우리 나라 "준비 완료"(on=true) / 취소(false). 모둠이면 누가 눌러도 나라 단위 |
| `invest(good)` | 투자 | 산업 레벨 업(라운드당 1번, 1~7라운드) |
| `focus(good)` | 투자 | 다음 라운드 주력 산업 |

- 판매 등록 단계가 시작될 때 AI 나라들의 판매 물건이 이미 `market`에 올라와 있다. 학생은 그 가격을 보고 정한다.
- 물건 키: `wheat` 밀, `banana` 바나나, `fuel` 연료, `ore` 광물, `machine` 기계, `electronics` 전자제품. `gen`(세대)은 기계·전자제품만 1~3이다.
- AI 나라에 보낸 제안은 바로 답이 온다: `{ok:true, accepted:true|false, msg}`. 거절이면 `msg`에 조건이 들어 있다(예: "개당 18G 이상이면 팔게요").
- 학생 나라에 보낸 제안은 상대가 `respond`할 때까지 `pending`이다. 거래 단계가 끝나면 `expired`가 된다.

## 학생 상태 `state` (주요 필드)

| 필드 | 뜻 |
| --- | --- |
| `round`, `phase`, `phase_label` | 1~9, `listing`/`trading`/`invest`/`finished`, 한국어 이름 |
| `country`, `label`, `is_student` | 내 나라 키·이름, 지금 학생이 운영 중인지(false면 선생님이 AI에게 맡김) |
| `cash`, `main`, `focus`, `next_focus`, `levels` | 돈, 대표 산업, 이번 주력, 다음 주력, 산업별 레벨 `{banana:2, ...}` |
| `stock` | `[{good, label, gen, free, listed, own_made, imported}]` free=창고, listed=판매 중 |
| `my_orders` | 내 판매 목록 `[{oid, good, label, gen, qty, price, reference}]` |
| `market` | 모든 판매 목록 `[{oid, seller, seller_label, seller_is_student, good, label, gen, qty, price, reference}]` |
| `settlement` | 이번 라운드 정산에 필요한 것 `{settled, rows:[{good, label, purpose, need, have, short}]}` |
| `operating_schedule` | `{fuel:[3,6,9], ore:[4,8]}` |
| `invest_options` | `[{good, label, level, next_level, new_industry, main, cost, ore, machine_gen, ok, reasons:[...]}]` |
| `offers` | 나와 관련된 제안 `[{id, round, from, to, kind, give, get, cash, status, note}]` |
| `transactions_this_round` | `[{channel, legs:[{seller, buyer, good, label, gen, qty}], cash:{payer, payee, amount}}]` |
| `progress` | `{export_value, export_target, main_levelled, avg_happy, operating_short_days, emergency_paid}` |
| `happiness`, `cash_by_round`, `upgrades`, `trust` | 라운드별 만족도·현금, 투자 기록, 나라별 신뢰도 |
| `quotes`, `prices`, `base_prices` | 기준 가격 `{good:{gen:G}}`, 시세, 기초 가격 |
| `names`, `goods` | 나라·물건 한국어 이름 |
| `room` | 진행 정보 `{code, mode, paused, ready:[나라], need:[나라], countdown_ms, deadline_ms, phase_seconds}`. 남은 시간은 상태를 받은 순간 기준(받은 뒤 흐른 시간을 빼서 표시; `paused`면 멈춤) |
| `results` | 게임이 끝나면 나라별 `{total, grade, parts:{export, industry, living, trade, utilization, cash}, ...}` |

## 진행 방식

| `room.mode` | 넘어가는 때 |
| --- | --- |
| `teacher` | 선생님이 넘길 때만 |
| `ready` | 학생 나라가 모두 "준비 완료"를 누르면 `countdown_ms` 뒤(기본 5초). 그 사이 누가 취소하면 멈춤 |
| `ready_timer` | 위와 같고, 단계 시간(`deadline_ms`)이 끝나도 넘어감 |

선생님은 언제든 넘기거나 모든 방을 멈출 수 있다(`paused`). "1라운드는 선생님이 넘김"을 켜면 1라운드의 `mode`는 `teacher`다.

## 교사 화면: `ClassHost` (여러 방)

```js
import { EngineClient } from './js/engine-client.js';
import { ClassHost, browserStorage, savedClasses, DEFAULT_SETTINGS } from './js/host.js';
import { openServer, serverList, countOnline } from './js/transport.js';

serverList()                                   // [{id:'1', name:'1서버', capacity:90, ...}]
await countOnline(serverList()[0])             // 지금 접속 인원(연결을 유지하지 않고 읽음)
const engine = new EngineClient(); await engine.init();          // Pyodide + 엔진 (처음 몇 초)
const cls = new ClassHost({ engine, server: await openServer('1'), storage: browserStorage, onChange: (summary) => draw(summary) });
await cls.create({ students: ['Tropia', 'Oilia', 'Mineria'], rooms: 3,
                   settings: { mode: 'ready_timer', firstRoundTeacher: true, countdownSec: 5,
                               timer: { listing: 120, trading: 240, invest: 60 } } });
// 또는 이어하기: await cls.restore(savedClasses(browserStorage)[0])
cls.startTicker();                             // 타이머·자동 진행(0.5초마다 확인)
await cls.advance('1-K7QPM-2')                 // 이 방 다음 단계
await cls.advanceAll()                         // 모든 방 다음 단계
await cls.pause() / cls.resume()               // 모든 방 멈춤(시간도 멈춤) / 다시 시작
await cls.setSettings({ mode: 'teacher' })     // 진행 방식·시간 바꾸기(지금 단계 시간은 새로 셈)
await cls.teacherAction(code, { type: 'set_controller', country: 'Mineria', mode: 'ai' })  // 결석 학생 나라를 AI에게
await cls.finish({ clearServer: true })        // 수업 끝내기(서버의 방 자료 삭제)
```

`summary`: `{cls, server, settings, paused, server_online, rooms:[{code, view, info, tokens, online:[나라]}]}`
- `view`: 방의 교사 상태 — `round, phase, seed, students, nations:[{country, label, student, cash, levels, focus, happy, stock, listed, invested_this_round, progress}], market, pending_offers, transactions_this_round, log_length, results`
- `info`: 위의 `room`과 같은 진행 정보
- `tokens`: `{나라: 접속 번호}`
- `online`: 그 방에 지금 접속한 학생 기기의 나라 목록(같은 나라가 여러 번이면 모둠 기기 수)

교사 화면을 닫거나 새로고침해도 방마다 행동 기록이 브라우저에 저장되어 있어 `restore`로 똑같이 이어진다.
