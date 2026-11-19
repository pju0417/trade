"""Browser end-to-end test (Playwright + Chrome, local test mode = BroadcastChannel between tabs).

Serves the repository over HTTP, opens host.html (engine in a Web Worker with the vendored
Pyodide), starts a game for Tropia/Oilia/Mineria, opens three student tabs with their PINs and
plays a full game through the pages' own buttons. Saves screenshots to the given folder.
Usage: python3 browser_e2e.py OUTDIR [CHROME_PATH]
"""
import functools
import http.server
import os
import re
import sys
import threading

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

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True)
    ctx = browser.new_context(viewport={'width': 1200, 'height': 900})
    host = ctx.new_page()
    host.on('pageerror', lambda e: errors.append(('host', str(e))))
    host.goto(BASE + 'host.html')
    host.wait_for_selector('text=엔진 준비됨', timeout=120000)
    room = host.input_value('[data-k="room"]')
    host.click('[data-act="new"]')
    host.wait_for_selector('text=학생 접속 정보', timeout=60000)
    rows = host.locator('table').nth(0 if 'results' not in host.content() else 1)
    pins = dict(re.findall(r'<td>(트로피아|오일리아|미네리아)</td><td><b>(\d{4})</b>', host.content()))
    assert len(pins) == 3, pins
    code = {'트로피아': 'Tropia', '오일리아': 'Oilia', '미네리아': 'Mineria'}
    stu = {}
    for ko, pin in pins.items():
        pg = ctx.new_page()
        pg.on('pageerror', lambda e, ko=ko: errors.append((ko, str(e))))
        pg.goto(BASE + f'student.html?room={room}&country={code[ko]}&pin={pin}')
        pg.wait_for_selector('text=이번 라운드 정산', timeout=30000)
        stu[ko] = pg
    host.screenshot(path=os.path.join(OUT, 'host_r1.png'), full_page=True)
    stu['트로피아'].screenshot(path=os.path.join(OUT, 'student_r1.png'), full_page=True)

    def msg(pg):
        return pg.inner_text('#msg')

    def advance(expect):
        host.click('[data-act="advance"]')
        host.wait_for_selector(f'h1:has-text("{expect}")', timeout=60000)

    # Round 1 listing: Tropia lists 2 bananas at 8G through the form
    t = stu['트로피아']
    t.fill('[data-k="lq-banana-1"]', '2'); t.fill('[data-k="lp-banana-1"]', '8')
    t.click('[data-act="list"][data-good="banana"]')
    t.wait_for_function("document.querySelector('#msg').innerText.includes('내놓았어요')", timeout=20000)
    # bad input is refused with a message
    t.fill('[data-k="lq-wheat-1"]', '99'); t.fill('[data-k="lp-wheat-1"]', '5')
    t.click('[data-act="list"][data-good="wheat"]')
    t.wait_for_function("document.querySelector('#msg').innerText.includes('개뿐')", timeout=20000)
    advance('거래')
    for pg in stu.values():
        pg.wait_for_selector('h1:has-text("거래")', timeout=20000)
    # Mineria buys the first market listing it can afford
    m = stu['미네리아']
    m.click('[data-act="buy"] >> nth=0')
    m.wait_for_function("document.querySelector('#msg').innerText.length > 0", timeout=20000)
    buy_msg = msg(m)
    # Oilia offers wheat to Tropia (student to student), Tropia accepts
    o = stu['오일리아']
    o.select_option('[data-k="of-to"]', 'Tropia')
    o.select_option('[data-k="of-kind"]', 'sell')
    o.select_option('[data-k="of-give-good"]', 'banana')
    o.fill('[data-k="of-give-qty"]', '1'); o.fill('[data-k="of-cash"]', '7')
    o.click('[data-act="offer"]')
    o.wait_for_function("document.querySelector('#msg').innerText.includes('제안')", timeout=20000)
    t.wait_for_selector('[data-act="respond"][data-acc="1"]', timeout=20000)
    t.click('[data-act="respond"][data-acc="1"]')
    t.wait_for_function("document.querySelector('#msg').innerText.includes('받아들였어요')", timeout=20000)
    stu['트로피아'].screenshot(path=os.path.join(OUT, 'student_trading.png'), full_page=True)
    advance('투자')
    # Tropia invests in bananas if the page offers the button
    t.wait_for_selector('h1:has-text("투자")', timeout=20000)
    invested = False
    if t.locator('[data-act="invest"][data-good="banana"]').count():
        t.click('[data-act="invest"][data-good="banana"]')
        t.wait_for_function("document.querySelector('#msg').innerText.includes('레벨')", timeout=20000)
        invested = True
    # play the rest by advancing only
    for _ in range(40):
        if host.locator('[data-act="advance"]').count() == 0:
            break
        label = host.inner_text('h1')
        host.click('[data-act="advance"]')
        host.wait_for_function(f"document.querySelector('h1').innerText !== {label!r}", timeout=60000)
    host.wait_for_selector('text=결과 (나라별 목표 달성도)', timeout=60000)
    for pg in stu.values():
        pg.wait_for_selector('h2:has-text("결과")', timeout=30000)
    host.screenshot(path=os.path.join(OUT, 'host_final.png'), full_page=True)
    stu['미네리아'].screenshot(path=os.path.join(OUT, 'student_final.png'), full_page=True)
    grades = re.findall(r'<td>(트로피아|오일리아|미네리아)</td><td>학생</td><td>([\d.]+)</td><td>([ABCD])</td>', host.content())
    # reload the host page and resume from the saved log
    host.reload()
    host.wait_for_selector('text=엔진 준비됨', timeout=120000)
    host.click(f'[data-act="resume"][data-room="{room}"]')
    host.wait_for_selector('text=결과 (나라별 목표 달성도)', timeout=60000)
    grades2 = re.findall(r'<td>(트로피아|오일리아|미네리아)</td><td>학생</td><td>([\d.]+)</td><td>([ABCD])</td>', host.content())
    browser.close()

srv.shutdown()
assert not errors, errors
assert grades and grades == grades2, (grades, grades2)
print('browser e2e ok: room', room, '| market buy:', buy_msg, '| invested:', invested, '| results:', grades)
