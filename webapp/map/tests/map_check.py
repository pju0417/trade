"""지도 브라우저 검사 (Playwright + Chrome, SwiftShader).

저장소를 HTTP로 띄우고 webapp/map/index.html을 연다.
  1) 확대 단계별 스크린샷(세계·대륙·항구 9곳)
  1-1) 나라마다 수도·마을, 건물 수
  2) 게임 상태 넣기(update: profiles·world_trades·country) → 무역로 수·산업 건물 수 확인
  3) 나라 클릭 → 나라 카드, 드래그·휠, 항구 버튼 → 날아가기
  4) 작은 GLB를 만들어 불러오기 → 등대 자리에 배치
오류(pageerror, console.error)가 하나라도 있으면 실패.
사용법: python3 webapp/map/tests/map_check.py OUTDIR [CHROME_PATH]
"""
import functools
import http.server
import json
import os
import struct
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/map_results'
CHROME = sys.argv[2] if len(sys.argv) > 2 else '/usr/bin/google-chrome'
os.makedirs(OUT, exist_ok=True)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def tiny_glb():
    """밑면 사각형 + 꼭짓점 하나인 피라미드(파란색) GLB."""
    pos = [-1, 0, -1, 1, 0, -1, 1, 0, 1, -1, 0, 1, 0, 2.5, 0]
    idx = [0, 2, 1, 0, 3, 2, 0, 1, 4, 1, 2, 4, 2, 3, 4, 3, 0, 4]
    pb = struct.pack('<15f', *pos)
    ib = struct.pack('<18H', *idx) + b'\0\0'
    binc = pb + ib
    gltf = {
        'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1, 'material': 0}]}],
        'materials': [{'pbrMetallicRoughness': {'baseColorFactor': [0.2, 0.45, 0.9, 1], 'metallicFactor': 0}}],
        'buffers': [{'byteLength': len(binc)}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(pb)}, {'buffer': 0, 'byteOffset': len(pb), 'byteLength': 36}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 5, 'type': 'VEC3', 'min': [-1, 0, -1], 'max': [1, 2.5, 1]},
                      {'bufferView': 1, 'componentType': 5123, 'count': 18, 'type': 'SCALAR'}],
    }
    js = json.dumps(gltf).encode()
    js += b' ' * ((4 - len(js) % 4) % 4)
    body = struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(binc), 0x004E4942) + binc
    return struct.pack('<III', 0x46546C67, 2, 12 + len(body)) + body


srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/webapp/map/index.html?test&me=Tropia'
errors, fails = [], []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  ({detail})' if detail else ''))
    if not ok:
        fails.append(name)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
    pg = b.new_page(viewport={'width': 1280, 'height': 800})
    pg.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: errors.append('console.error: ' + m.text) if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_function('window.worldMap', timeout=90000)
    nations = pg.evaluate('worldMap.nations')
    check('나라 9개', len(nations) == 9)
    S = pg.evaluate('worldMap.worldScale')
    small = [n['key'] for n in nations if n['cells'] < 3000 * S * S]
    check('모든 나라 땅 넓이 충분(3000×비율² 칸 이상)', not small, ', '.join(f"{n['key']}={n['cells']}" for n in nations))

    def shot(name, x, z, d, wait=1500):
        pg.evaluate(f'worldMap.setView({x},{z},{d})')
        pg.wait_for_timeout(wait)
        pg.screenshot(path=os.path.join(OUT, name + '.png'))
        return pg.evaluate('worldMap.getState()')

    st0 = pg.evaluate('worldMap.settlements')
    caps = [x for x in st0 if x['capital']]
    check('도시: 나라마다 수도 1곳 + 마을 2곳 이상', len(caps) == 9 and all(sum(1 for x in st0 if x['nation'] == n['key'] and not x['capital']) >= 2 for n in nations), f'수도 {len(caps)}, 전체 {len(st0)}')
    for c in caps:
        if c['nation'] in ('Technia', 'Oilia', 'Tropia', 'Ferria'):
            shot('3-capital-' + c['nation'], c['x'], c['z'] + 2.5, 5, 1200)
    st_c = pg.evaluate('worldMap.getState()')
    check('도시 건물 1000채 이상', st_c['buildings'] > 1000, f"buildings={st_c['buildings']}")
    home = pg.evaluate('worldMap.home')
    s = shot('1-world', *home)
    check('세계 보기에 데모 무역로', s['routes'] > 0, f"routes={s['routes']}")
    gr = next(n for n in nations if n['key'] == 'Grainia')
    shot('2-continent', gr['center']['x'] - 4, gr['center']['z'], 26)
    for n in nations:
        st = shot('3-port-' + n['key'], n['port']['x'], n['port']['z'] + 0.4, 3.4, 1200)
    check('항구 가까이에서 산업 건물 보임', st['props'] > 0, f"props={st['props']}")

    # 게임 상태 넣기
    state = {
        'country': 'Oilia', 'round': 4, 'phase_label': '거래',
        'names': {'Oilia': '오일리아'},
        'profiles': {n['key']: {'main': n['good'], 'expand': None, 'focus': n['good'], 'levels': {n['good']: 3}, 'student': n['key'] in ('Oilia', 'Tropia'), 'evaluated': True} for n in nations},
        'world_trades': [
            {'channel': 'market', 'legs': [{'seller': 'Oilia', 'buyer': 'Technia', 'good': 'fuel', 'label': '연료', 'gen': 1, 'qty': 3}]},
            {'channel': 'offer', 'legs': [{'seller': 'Tropia', 'buyer': 'Oilia', 'good': 'banana', 'label': '바나나', 'gen': 1, 'qty': 2},
                                         {'seller': 'Oilia', 'buyer': 'Tropia', 'good': 'fuel', 'label': '연료', 'gen': 1, 'qty': 1}]},
            {'channel': 'market', 'legs': [{'seller': 'Mineria', 'buyer': 'Mechania', 'good': 'ore', 'label': '광물', 'gen': 1, 'qty': 2}]},
        ],
    }
    pg.evaluate('s => worldMap.update(s)', state)
    s = shot('4-game-state-world', *home)
    check('게임 거래 4묶음 → 무역로 4개', s['routes'] == 4, f"routes={s['routes']}")
    check('레벨 3 → 산업 건물 9×10개', s['props'] == 90, f"props={s['props']}")
    label = pg.evaluate("Array.from(document.querySelectorAll('div')).some(d => d.textContent === '오일리아우리 나라')")
    check('우리 나라 표시', label)

    # 나라 클릭(오일리아 중심)
    oil = next(n for n in nations if n['key'] == 'Oilia')
    pg.evaluate(f"worldMap.setView({oil['center']['x']},{oil['center']['z']},45)")
    pg.wait_for_timeout(400)
    pg.mouse.click(640, 400)
    pg.wait_for_timeout(400)
    card = pg.evaluate("Array.from(document.querySelectorAll('div')).filter(d => d.style.bottom === '78px' && d.style.display === 'block').map(d => d.innerText)")
    check('나라 클릭 → 카드', bool(card) and '오일리아' in card[0] and '판 물건 4' in card[0], card[0].replace('\n', ' | ') if card else '')
    pg.screenshot(path=os.path.join(OUT, '5-select.png'))

    s0 = pg.evaluate('worldMap.getState()')
    pg.mouse.move(700, 420); pg.mouse.down(); pg.mouse.move(500, 320, steps=8); pg.mouse.up()
    s1 = pg.evaluate('worldMap.getState()')
    check('드래그로 이동', s1['x'] > s0['x'] + 5 and s1['z'] > s0['z'] + 3, f"{s0['x']:.1f},{s0['z']:.1f} -> {s1['x']:.1f},{s1['z']:.1f}")
    for _ in range(4):
        pg.mouse.wheel(0, -300); pg.wait_for_timeout(40)
    s2 = pg.evaluate('worldMap.getState()')
    check('휠로 확대', s2['dist'] < s1['dist'] * 0.5, f"{s1['dist']:.1f} -> {s2['dist']:.1f}")
    pg.click('button:has-text("미네리아")')
    pg.wait_for_timeout(3500)
    s3 = pg.evaluate('worldMap.getState()')
    mi = next(n for n in nations if n['key'] == 'Mineria')
    check('나라 버튼 → 항구로 날아가기', abs(s3['x'] - mi['port']['x']) < 2 and s3['dist'] < 5, f"x={s3['x']:.1f} dist={s3['dist']:.1f}")

    # GLB 불러오기
    glb = list(tiny_glb())
    pg.evaluate("bytes => worldMap.loadFile(new File([new Uint8Array(bytes)], 'tripo_test.glb'))", glb)
    pg.wait_for_timeout(2500)
    toast = pg.evaluate("Array.from(document.querySelectorAll('div')).filter(d => d.style.opacity === '1' && d.style.top === '14px').map(d => d.textContent)")
    check('GLB 불러오기 → 등대 자리 배치', bool(toast) and '미네리아' in toast[0], toast[0] if toast else '')
    pg.screenshot(path=os.path.join(OUT, '6-glb.png'))
    b.close()

check('브라우저 오류 없음', not errors, '; '.join(errors[:5]))
print('결과:', '모두 통과' if not fails else '실패 ' + ', '.join(fails))
sys.exit(1 if fails else 0)
