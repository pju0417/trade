"""Does a sensible HUMAN-style student reach the scores the simulator's 'good' student reached?

Pre-registered (descriptive check of the classroom adaptations; do not tune after seeing results)
  Session: webapp classroom.Session (validated engine + human-play adaptations).
  Students: Tropia, Mechania, Mineria (same trio as docs/virtual_students.md), seeds 160000-160029.
  Policy H (what a careful student can do with the student screen only):
    listing  keep what this round's settlement needs (food, electronics, operating resource due
             this round or next round, 1 ore while the main industry is not yet levelled);
             list the rest at min(cheapest other seller of that good/gen - 1, 90% of reference), >= 1G
    trading  for each settlement shortage, buy the cheapest listing up to 1.5x reference;
             also buy 1 ore if the main-industry investment needs ore
    invest   level up the main industry once when possible; focus stays on the main industry
  Reference: simulator 'good' student in docs/virtual_students.md: 민준 91.6, 서연(good) 92.5, 지호(good) 92.8.
  Flag (not a pass/fail of the rules): policy-H mean below 80 for any country.
Usage: python3 human_policy.py [A K]
"""
import json
import statistics as st
import sys

import paths  # noqa: F401
import classroom as C

STU = ['Tropia', 'Mechania', 'Mineria']


def keep_amount(v, good):
    k = sum(r['need'] for r in v['settlement']['rows'] if r['good'] == good)
    sched = v['operating_schedule']
    if good in ('fuel', 'ore') and (v['round'] + 1) in sched[good]:
        k += 1
    if good == 'ore' and not v['progress']['main_levelled']:
        k += 1
    return k


def play(s, n):
    v = s.view(n)
    if v['phase'] == 'listing':
        for row in v['stock']:
            extra = row['free'] - keep_amount(v, row['good'])
            if extra <= 0:
                continue
            ref = v['quotes'][row['good']][row['gen']]
            others = [o['price'] for o in v['market'] if o['good'] == row['good'] and o['gen'] == row['gen'] and o['seller'] != n]
            price = max(1, min(int(ref * .9), (min(others) - 1) if others else ref))
            s.apply({'type': 'list', 'country': n, 'good': row['good'], 'gen': row['gen'], 'qty': extra, 'price': price})
    elif v['phase'] == 'trading':
        wants = [(r['good'], r['short']) for r in v['settlement']['rows'] if r['short'] > 0]
        main = next((o for o in v['invest_options'] if o['main']), None)
        if main and main['ore'] and not v['progress']['main_levelled']:
            have = sum(r['free'] for r in v['stock'] if r['good'] == 'ore')
            due = sum(r['need'] for r in v['settlement']['rows'] if r['good'] == 'ore')
            if have - due < main['ore']:
                wants.append(('ore', main['ore'] - (have - due)))
        for good, k in wants:
            for _ in range(k):
                v = s.view(n)
                cands = sorted((o for o in v['market'] if o['good'] == good and o['seller'] != n
                                and o['price'] <= 1.5 * o['reference']), key=lambda o: o['price'])
                if not cands:
                    break
                s.apply({'type': 'buy', 'country': n, 'oid': cands[0]['oid'], 'qty': 1})
    elif v['phase'] == 'invest':
        if not v['progress']['main_levelled']:
            opt = next((o for o in v['invest_options'] if o['main']), None)
            if opt and opt['ok']:
                s.apply({'type': 'invest', 'country': n, 'good': opt['good']})
        s.apply({'type': 'focus', 'country': n, 'good': v['main']})


def main(a0=160000, k=30):
    res = {n: [] for n in STU}
    parts = {n: [] for n in STU}
    for seed in range(a0, a0 + k):
        s = C.Session(seed, STU)
        while s.phase != 'finished':
            for n in STU:
                play(s, n)
            assert s.apply({'type': 'advance'})['ok']
        for n in STU:
            res[n].append(s.results[n]['total'])
            parts[n].append(s.results[n]['parts'] | {'export_value': s.results[n]['export_value'],
                                                      'op_short': s.results[n]['operating_short_days']})
    out = {}
    for n in STU:
        t = res[n]
        out[n] = {'mean': st.mean(t), 'min': min(t), 'max': max(t),
                  'grades': {g: sum(C.grade(x) == g for x in t) for g in 'ABCD'},
                  'parts': {key: st.mean(p[key] for p in parts[n]) for key in parts[n][0]}}
    print(json.dumps({'games': k, 'seeds': [a0, a0 + k - 1], 'result': out}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(*(map(int, sys.argv[1:3])) if len(sys.argv) > 2 else ())
