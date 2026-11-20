"""Browser end-to-end test (Playwright + Chrome, local test mode = BroadcastChannel between tabs).

Serves the repository over HTTP. Teacher page (engine in a Web Worker, vendored Pyodide) creates a
class of 2 rooms (Tropia/Oilia/Mineria as students, mode "ready", round 1 teacher-led).
Room 1: three student tabs; room 2: one tab. Through the pages' own buttons:
  R1 listing, refused input, per-room advance, market buy, student-to-student offer, investment,
  "all rooms" advance, R2 auto-advance when all three are ready (countdown), pause (nothing moves),
  switch to "ready or timer" with 3-second phases -> both rooms finish by themselves,
  lobby head count, host reload + resume reproduces the results. Screenshots go to OUTDIR.
Usage: python3 browser_e2e.py OUTDIR [CHROME_PATH]
"""
import functools
import http.server
import os
import re
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = sys.argv[1]
CHROME = sys.argv[2] if len(sys.argv) > 2 else '/usr/bin/google-chrome'
os.makedirs(OUT, exist_ok=True)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{srv.server_address[1]}/webapp/'
errors = []
KO = {'트로피아': 'Tropia', '오일리아': 'Oilia', '미네리아': 'Mineria'}


def h1(pg):
    return pg.inner_text('h1')


def wait_h1(pg, text, timeout=60000):
    pg.wait_for_function(f"document.querySelector('h1') && document.querySelector('h1').innerText.includes({text!r})", timeout=timeout)


def wait_msg_change(pg, before, timeout=20000):
    pg.wait_for_function(f"document.querySelector('#msg').innerText !== {before!r}", timeout=timeout)
    return pg.inner_text('#msg')


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True)
    ctx = browser.new_context(viewport={'width': 1200, 'height': 900})
    host = ctx.new_page()
    host.on('pageerror', lambda e: errors.append(('host', str(e))))
    host.goto(BASE + 'host.html?local=1')
    host.wait_for_selector('text=엔진 준비됨', timeout=120000)
    host.fill('[data-k="rooms"]', '2')
    host.select_option('[data-k="mode"]', 'ready')
    host.click('[data-act="new"]')
    host.wait_for_selector('text=접속 정보 (학생에게 알려 주세요)', timeout=60000)
    html = host.content()
    rooms = re.findall(r'방 코드 <b>(L-[A-Z0-9]+-\d+)</b></h3><table>(.*?)</table>', html, re.S)
    assert len(rooms) == 2, html[html.find('접속 정보 ('):html.find('접속 정보 (')+600]
    pins = [dict(re.findall(r'<td>(트로피아|오일리아|미네리아)</td><td><b>(\d{4})</b>', t)) for _, t in rooms]
    code1, code2 = rooms[0][0], rooms[1][0]

    def student(code, ko, pin):
        pg = ctx.new_page()
        pg.on('pageerror', lambda e, ko=ko: errors.append((ko, str(e))))
        pg.goto(BASE + f'student.html?room={code}&country={KO[ko]}&pin={pin}&local=1')
        pg.wait_for_selector('text=이번 라운드 정산', timeout=30000)
        return pg

    s1 = {ko: student(code1, ko, pins[0][ko]) for ko in ('트로피아', '오일리아', '미네리아')}
    s2 = student(code2, '트로피아', pins[1]['트로피아'])
    t, o, m = s1['트로피아'], s1['오일리아'], s1['미네리아']
    assert '선생님이 넘겨요' in t.inner_text('#bar'), t.inner_text('#bar')

    # R1 listing in room 1
    t.fill('[data-k="lq-banana-1"]', '2'); t.fill('[data-k="lp-banana-1"]', '8')
    b = t.inner_text('#msg'); t.click('[data-act="list"][data-good="banana"]')
    assert '내놓았어요' in wait_msg_change(t, b)
    t.fill('[data-k="lq-wheat-1"]', '99'); t.fill('[data-k="lp-wheat-1"]', '5')
    b = t.inner_text('#msg'); t.click('[data-act="list"][data-good="wheat"]')
    assert '개뿐' in wait_msg_change(t, b)
    # everyone ready in round 1 (teacher-led): nothing moves
    for pg in s1.values():
        pg.click('[data-act="ready"]')
    time.sleep(7)
    assert '판매 등록' in h1(t), h1(t)
    host.screenshot(path=os.path.join(OUT, 'host_r1.png'), full_page=True)
    # teacher advances room 1 only
    host.click(f'[data-act="adv"][data-code="{code1}"]')
    wait_h1(t, '거래')
    assert '판매 등록' in h1(s2), 'room 2 did not move'
    b = m.inner_text('#msg'); m.click('[data-act="buy"] >> nth=0')
    buy_msg = wait_msg_change(m, b)
    o.select_option('[data-k="of-to"]', 'Tropia'); o.select_option('[data-k="of-kind"]', 'sell')
    o.select_option('[data-k="of-give-good"]', 'banana')
    o.fill('[data-k="of-give-qty"]', '1'); o.fill('[data-k="of-cash"]', '7')
    b = o.inner_text('#msg'); o.click('[data-act="offer"]')
    assert '제안' in wait_msg_change(o, b)
    t.wait_for_selector('[data-act="respond"][data-acc="1"]', timeout=20000)
    b = t.inner_text('#msg'); t.click('[data-act="respond"][data-acc="1"]')
    assert '받아들였어요' in wait_msg_change(t, b)
    t.screenshot(path=os.path.join(OUT, 'student_trading.png'), full_page=True)
    # all rooms advance: room 1 -> invest, room 2 -> trading
    host.click('[data-act="advall"]')
    wait_h1(t, '투자'); wait_h1(s2, '거래')
    invested = False
    if t.locator('[data-act="invest"][data-good="banana"]').count():
        b = t.inner_text('#msg'); t.click('[data-act="invest"][data-good="banana"]')
        invested = '레벨' in wait_msg_change(t, b)
    host.click('[data-act="advall"]')
    wait_h1(t, '2라운드 · 판매 등록'); wait_h1(s2, '투자')
    # R2: mode "ready" -> all three ready -> countdown -> trading
    assert '모두 준비하면' in t.inner_text('#bar')
    for pg in s1.values():
        pg.click('[data-act="ready"]')
    t.wait_for_function("document.querySelector('#bar').innerText.includes('초 뒤 다음 단계')", timeout=20000)
    wait_h1(t, '2라운드 · 거래', timeout=30000)
    assert '투자' in h1(s2), 'room 2 still waits for its teacher'
    # pause: switch to timer mode with 3-second phases, pause, nothing moves for 8 s
    host.click('[data-act="pause"]')
    host.select_option('[data-k="d_mode"]', 'ready_timer')
    for k in ('d_tl', 'd_tt', 'd_ti'):
        host.fill(f'[data-k="{k}"]', '3')
    host.click('[data-act="settings"]')
    host.wait_for_selector('text=진행 방식을 바꿨어요', timeout=20000)
    before = (h1(t), h1(s2))
    time.sleep(8)
    assert (h1(t), h1(s2)) == before, 'paused rooms must not move'
    assert '잠시 멈춤' in t.inner_text('#bar')
    host.click('[data-act="resume-all"]')
    # room 2 is still in round 1, which stays teacher-led: the teacher moves it on once
    host.click(f'[data-act="adv"][data-code="{code2}"]')
    wait_h1(s2, '2라운드', timeout=30000)
    # both rooms now run by the 3-second timer until the end
    try:
        host.wait_for_function("(document.body.innerText.match(/9R 끝/g) || []).length === 2", timeout=300000)
    except Exception:
        print('HOST:', host.inner_text('body')[:1500]); print('STUDENT:', t.inner_text('#bar'), h1(t)); raise
    host.wait_for_selector('text=결과 (나라별 목표 달성도)', timeout=60000)
    for pg in list(s1.values()) + [s2]:
        pg.wait_for_selector('h2:has-text("결과")', timeout=60000)
    host.screenshot(path=os.path.join(OUT, 'host_final.png'), full_page=True)
    m.screenshot(path=os.path.join(OUT, 'student_final.png'), full_page=True)
    res = re.findall(r'<td>(L-[A-Z0-9]+-\d+)</td><td>(트로피아|오일리아|미네리아)</td>\s*<td>([\d.]+)</td><td>([ABCD])</td>', host.content())
    assert len(res) == 6, res
    # lobby head count (host + 4 student tabs announce themselves)
    lobby = ctx.new_page()
    lobby.goto(BASE + 'index.html?local=1')
    lobby.wait_for_function("document.querySelector('#servers').innerText.includes('명 /')", timeout=20000)
    time.sleep(4)
    lobby.reload()
    lobby.wait_for_function("/([5-9]|\\d\\d)명 \\//.test(document.querySelector('#servers').innerText)", timeout=20000)
    lobby_text = lobby.inner_text('#servers')
    # reload the teacher page and resume the class from its saved logs
    host.reload()
    host.wait_for_selector('text=엔진 준비됨', timeout=120000)
    host.click('[data-act="resume"] >> nth=0')
    host.wait_for_function("(document.body.innerText.match(/9R 끝/g) || []).length === 2", timeout=120000)
    res2 = re.findall(r'<td>(L-[A-Z0-9]+-\d+)</td><td>(트로피아|오일리아|미네리아)</td>\s*<td>([\d.]+)</td><td>([ABCD])</td>', host.content())
    browser.close()

srv.shutdown()
assert not errors, errors
assert res and sorted(res) == sorted(res2), (res, res2)
print('browser e2e ok:', code1, code2, '| buy:', buy_msg, '| invested:', invested,
      '| lobby:', lobby_text.replace('\n', ' ').replace('\t', ' '), '| results:', res)
