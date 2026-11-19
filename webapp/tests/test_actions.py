"""Student action tests for webapp/py/classroom.py.

  python3 test_actions.py unit          scripted checks of every action type
  python3 test_actions.py fuzz A K      K games from seed A with random student actions:
                                        no internal error, engine verify() after every action,
                                        exact replay from the action log, scores computable
"""
import json
import random
import sys

import paths  # noqa: F401
import classroom as C

STU = ['Tropia', 'Mechania', 'Mineria']


def ok(r):
    assert r['ok'], r
    return r


def bad(r, text=None):
    assert not r['ok'], r
    assert 'error' not in r, r  # a rule refusal, not an internal error
    if text:
        assert text in r['msg'], r
    return r


def free(s, n, good, gen=1):
    return len(s._free_ids(s.g.cs[n], good, gen))


def advance(s):
    return ok(s.apply({'type': 'advance'}))


def unit():
    s = C.Session(4242, STU)
    g = s.g
    assert s.phase == 'listing' and g.r == 1
    # --- rules on inputs and phases
    bad(s.apply({'type': 'buy', 'country': 'Tropia', 'oid': 1, 'qty': 1}), '단계')
    bad(s.apply({'type': 'list', 'country': 'Grainia', 'good': 'wheat', 'qty': 1, 'price': 5}), '학생')
    bad(s.apply({'type': 'list', 'country': 'Tropia', 'good': 'banana', 'qty': 1, 'price': 0}), '가격')
    bad(s.apply({'type': 'list', 'country': 'Tropia', 'good': 'banana', 'qty': 1, 'price': 2.5}), '가격')
    bad(s.apply({'type': 'list', 'country': 'Tropia', 'good': 'banana', 'qty': 99, 'price': 5}), '개뿐')
    bad(s.apply({'type': 'list', 'country': 'Tropia', 'good': 'banana', 'gen': 2, 'qty': 1, 'price': 5}), '세대')
    bad(s.apply({'type': 'invest', 'country': 'Tropia', 'good': 'banana'}), '단계')
    # --- list / reprice / cancel
    b0 = free(s, 'Tropia', 'banana')
    r = ok(s.apply({'type': 'list', 'country': 'Tropia', 'good': 'banana', 'qty': 2, 'price': 500}))
    oid = r['oid']
    assert free(s, 'Tropia', 'banana') == b0 - 2 and g.orders[oid].price == 500
    ok(s.apply({'type': 'reprice', 'country': 'Tropia', 'oid': oid, 'price': 400}))
    bad(s.apply({'type': 'reprice', 'country': 'Mechania', 'oid': oid, 'price': 1}), '내 판매')
    ok(s.apply({'type': 'cancel', 'country': 'Tropia', 'oid': oid}))
    assert free(s, 'Tropia', 'banana') == b0 and oid not in g.orders
    # an overpriced listing is never bought by AI; it returns to stock when trading closes
    hi = ok(s.apply({'type': 'list', 'country': 'Tropia', 'good': 'banana', 'qty': 1, 'price': 500}))['oid']
    # a cheap listing is bought by AI only if some AI needs it (not asserted), but never refused for price
    advance(s)
    assert s.phase == 'trading'
    assert hi in g.orders, 'AI bought a student listing above the reference price'
    # --- market buy from an AI listing
    ai_orders = [o for o in g.orders.values() if o.seller not in g.students]
    assert ai_orders, 'no AI listing to test against'
    o = min(ai_orders, key=lambda o: o.price)
    cash0, seller_cash0 = g.cs['Mechania'].cash, g.cs[o.seller].cash
    good, price, seller = o.good, o.price, o.seller
    have0 = len(s._free_ids(g.cs['Mechania'], good, o.gen))
    ok(s.apply({'type': 'buy', 'country': 'Mechania', 'oid': o.oid, 'qty': 1}))
    assert g.cs['Mechania'].cash == cash0 - price and g.cs[seller].cash == seller_cash0 + price
    assert len(s._free_ids(g.cs['Mechania'], good, o.gen)) == have0 + 1
    bad(s.apply({'type': 'buy', 'country': 'Tropia', 'oid': hi, 'qty': 1}), '내 물건')
    bad(s.apply({'type': 'buy', 'country': 'Mechania', 'oid': 99999, 'qty': 1}), '없는')
    # --- direct offers to an AI country use the engine's negotiation terms
    ai = next(n for n in C.ORIGINAL + C.ADDED if n not in g.students and g.get_surplus(g.cs[n], 'wheat'))
    r = s.apply({'type': 'offer', 'country': 'Mineria', 'to': ai, 'kind': 'buy',
                 'get': {'good': 'wheat', 'qty': 1}, 'cash': 1})
    assert r['ok'] and r['accepted'] is False and '이상이면' in r['msg'], r
    ask = int(r['msg'].split('개당 ')[1].split('G')[0])
    c0 = g.cs['Mineria'].cash
    r = ok(s.apply({'type': 'offer', 'country': 'Mineria', 'to': ai, 'kind': 'buy',
                    'get': {'good': 'wheat', 'qty': 1}, 'cash': ask}))
    assert r['accepted'] and g.cs['Mineria'].cash == c0 - ask
    assert g.trust.get(tuple(sorted(('Mineria', ai))), 0) == 10
    # selling to an AI country that does not need the good is refused
    r = s.apply({'type': 'offer', 'country': 'Mechania', 'to': ai, 'kind': 'sell',
                 'give': {'good': 'machine', 'qty': 1}, 'cash': 99999})
    assert r['ok'] and r['accepted'] is False, r
    # --- student to student: pending until answered
    w0 = free(s, 'Tropia', 'wheat'); m0 = g.cs['Mechania'].cash; t0 = g.cs['Tropia'].cash
    r = ok(s.apply({'type': 'offer', 'country': 'Tropia', 'to': 'Mechania', 'kind': 'sell',
                    'give': {'good': 'wheat', 'qty': 1}, 'cash': 12}))
    oid = r['offer']
    assert s.offers[oid]['status'] == 'pending' and free(s, 'Tropia', 'wheat') == w0
    bad(s.apply({'type': 'respond', 'country': 'Tropia', 'offer': oid, 'accept': True}), '제안이 없')
    ok(s.apply({'type': 'respond', 'country': 'Mechania', 'offer': oid, 'accept': True}))
    assert free(s, 'Tropia', 'wheat') == w0 - 1 and g.cs['Tropia'].cash == t0 + 12 and g.cs['Mechania'].cash == m0 - 12
    bad(s.apply({'type': 'respond', 'country': 'Mechania', 'offer': oid, 'accept': True}), '끝난')
    # barter and buy-request between students
    tb, mw = free(s, 'Tropia', 'banana'), free(s, 'Mechania', 'wheat')
    if tb and mw:
        r = ok(s.apply({'type': 'offer', 'country': 'Tropia', 'to': 'Mechania', 'kind': 'barter',
                        'give': {'good': 'banana', 'qty': 1}, 'get': {'good': 'wheat', 'qty': 1}}))
        ok(s.apply({'type': 'respond', 'country': 'Mechania', 'offer': r['offer'], 'accept': True}))
        assert free(s, 'Tropia', 'banana') == tb - 1 and free(s, 'Mechania', 'wheat') == mw - 1
        assert s.g.transactions[-1]['channel'] == 'barter'
    tw, nc = free(s, 'Tropia', 'wheat'), g.cs['Mineria'].cash
    if tw:
        r = ok(s.apply({'type': 'offer', 'country': 'Mineria', 'to': 'Tropia', 'kind': 'buy',
                        'get': {'good': 'wheat', 'qty': 1}, 'cash': 9}))
        rj = ok(s.apply({'type': 'respond', 'country': 'Tropia', 'offer': r['offer'], 'accept': False}))
        assert s.offers[r['offer']]['status'] == 'rejected' and g.cs['Mineria'].cash == nc
    bad(s.apply({'type': 'offer', 'country': 'Tropia', 'to': 'Mineria', 'kind': 'barter',
                 'give': {'good': 'banana', 'qty': 1}, 'get': {'good': 'banana', 'qty': 1}}), '같은 물건')
    r = ok(s.apply({'type': 'offer', 'country': 'Tropia', 'to': 'Mineria', 'kind': 'sell',
                    'give': {'good': 'banana', 'qty': 1}, 'cash': 5}))
    ok(s.apply({'type': 'withdraw', 'country': 'Tropia', 'offer': r['offer']}))
    pend = ok(s.apply({'type': 'offer', 'country': 'Tropia', 'to': 'Mineria', 'kind': 'sell',
                       'give': {'good': 'banana', 'qty': 1}, 'cash': 5}))['offer']
    advance(s)  # -> invest; pending offers expire, unsold student listings return
    assert s.phase == 'invest' and s.offers[pend]['status'] == 'expired'
    assert not any(o.seller in g.students for o in g.orders.values())
    assert free(s, 'Tropia', 'banana') >= 0
    # --- investment rules
    tro = g.cs['Tropia']
    opts = {o['good']: o for o in s.invest_options(tro)}
    assert 'ore' in opts and not opts['ore']['ok'] and any('3라운드' in x for x in opts['ore']['reasons'])
    bad(s.apply({'type': 'invest', 'country': 'Tropia', 'good': 'ore'}), '3라운드')
    bad(s.apply({'type': 'invest', 'country': 'Tropia', 'good': 'machine'}), '투자할 수 없')
    cost = opts['banana']['cost']
    assert cost == 75
    if tro.cash >= cost:
        c0 = tro.cash
        ok(s.apply({'type': 'invest', 'country': 'Tropia', 'good': 'banana'}))
        assert tro.levels['banana'] == 2 and tro.cash == c0 - cost
        bad(s.apply({'type': 'invest', 'country': 'Tropia', 'good': 'wheat'}), '이미 투자')
    ok(s.apply({'type': 'focus', 'country': 'Tropia', 'good': 'wheat'}))
    bad(s.apply({'type': 'focus', 'country': 'Tropia', 'good': 'machine'}), '생산하는 산업')
    advance(s)
    assert g.r == 2 and s.phase == 'listing' and tro.focus == 'wheat'
    # --- teacher can hand a country to the AI and back
    ok(s.apply({'type': 'set_controller', 'country': 'Mineria', 'mode': 'ai'}))
    bad(s.apply({'type': 'list', 'country': 'Mineria', 'good': 'ore', 'qty': 1, 'price': 5}), '학생')
    ok(s.apply({'type': 'set_controller', 'country': 'Mineria', 'mode': 'student'}))
    # --- run to the end; R8+ investment refused
    while s.phase != 'finished':
        if s.phase == 'invest' and g.r >= 8:
            bad(s.apply({'type': 'invest', 'country': 'Tropia', 'good': 'banana'}), '7라운드')
        advance(s)
    assert set(s.results) == set(C.ORIGINAL) and all(0 <= x['total'] <= 100 for x in s.results.values())
    bad(s.apply({'type': 'advance'}), '끝났')
    # --- exact replay from the log
    s2 = C.Session.replay(4242, STU, s.log)
    for n in STU:
        assert json.dumps(s.view(n), sort_keys=True) == json.dumps(s2.view(n), sort_keys=True)
    assert json.dumps(s.teacher_view(), sort_keys=True) == json.dumps(s2.teacher_view(), sort_keys=True)
    print('unit ok:', len(s.log), 'actions;', {n: (round(x['total'], 1), x['grade']) for n, x in s.results.items() if x['student']})


def random_action(rng, s, n):
    g = s.g
    c = g.cs[n]
    goods = list(C.GOODS)
    good = rng.choice(goods)
    gen = rng.choice((1, 1, 2, 3)) if good in C.DURABLES else 1
    others = [m for m in g.cs if m != n]
    p = s.phase
    choices = []
    if p in ('listing', 'trading'):
        choices += ['list'] * 3 + ['cancel', 'reprice']
    if p == 'trading':
        choices += ['buy'] * 4 + ['offer'] * 3 + ['respond'] * 2 + ['withdraw']
    if p == 'invest':
        choices += ['invest', 'focus']
    choices.append('junk')
    t = rng.choice(choices)
    a = {'type': t, 'country': n}
    if t == 'list':
        a.update(good=good, gen=gen, qty=rng.randint(0, 4), price=rng.choice((0, 1, 3, 8, 10, 15, 25, 60, 120, 400)))
    elif t in ('cancel', 'reprice'):
        mine = [o.oid for o in g.orders.values() if o.seller == n] or [0]
        a.update(oid=rng.choice(mine), price=rng.choice((1, 5, 20, 999)))
    elif t == 'buy':
        os_ = list(g.orders) or [0]
        a.update(oid=rng.choice(os_), qty=rng.randint(1, 3))
    elif t == 'offer':
        kind = rng.choice(('sell', 'buy', 'barter', 'x'))
        studs = [m for m in g.students if m != n]
        a.update(to=rng.choice(others + [n, 'Nowhere'] + studs * 6), kind=kind)
        side = lambda: {'good': rng.choice(goods), 'gen': rng.choice((None, 1, 2)), 'qty': rng.randint(1, 3)}
        if kind in ('sell', 'barter'):
            a['give'] = side()
        if kind in ('buy', 'barter'):
            a['get'] = side()
        a['cash'] = rng.choice((1, 10, 30, 80, 200, 5000))
    elif t in ('respond', 'withdraw'):
        f = 'to' if t == 'respond' else 'from'
        ids = [o['id'] for o in s.offers.values() if o['status'] == 'pending' and (o[f] == n or rng.random() < .2)] or [0]
        a.update(offer=rng.choice(ids), accept=rng.random() < .7)
    elif t in ('invest', 'focus'):
        a.update(good=good)
    else:
        a = rng.choice([{'type': 'list', 'country': n, 'good': 'gold', 'qty': 1, 'price': 5},
                        {'type': 'buy', 'country': n, 'oid': 'x', 'qty': True},
                        {'type': 'nothing', 'country': n}, {'country': n}])
    return a


def fuzz(a0, k):
    stats = {'games': 0, 'actions': 0, 'accepted': 0, 'by_type': {}}
    for seed in range(a0, a0 + k):
        rng = random.Random(seed)
        students = rng.sample(list(C.ORIGINAL), rng.choice((1, 3, 3, 6)))
        s = C.Session(seed, students)
        while s.phase != 'finished':
            for _ in range(rng.randint(0, 25)):
                n = rng.choice(students)
                act = random_action(rng, s, n)
                r = s.apply(act)
                assert 'error' not in r, (seed, act, r)
                stats['actions'] += 1; stats['accepted'] += r['ok']
                key = act.get('type')
                d = stats['by_type'].setdefault(str(key), [0, 0]); d[0] += 1; d[1] += r['ok']
            if rng.random() < .03:
                m = rng.choice(students)
                s.apply({'type': 'set_controller', 'country': m, 'mode': rng.choice(('ai', 'student'))})
            r = s.apply({'type': 'advance'})
            assert r['ok'], (seed, r)
        for n in students:
            json.dumps(s.view(n))
        json.dumps(s.teacher_view())
        s2 = C.Session.replay(seed, students, s.log)
        assert json.dumps(s.results, sort_keys=True) == json.dumps(s2.results, sort_keys=True), seed
        assert json.dumps(s.view(students[0]), sort_keys=True) == json.dumps(s2.view(students[0]), sort_keys=True)
        stats['games'] += 1
    print('fuzz ok:', json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    if sys.argv[1] == 'unit':
        unit()
    else:
        fuzz(int(sys.argv[2]), int(sys.argv[3]))
