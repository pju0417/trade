"""Does following the advisor '마루 선장' literally make results uniform or hand out the answer?

Pre-registered (written before the first run; do not tune advice or criteria after seeing results)
  Session : webapp classroom.Session (validated engine + human-play adaptations), students Tropia, Mechania,
            Mineria (same trio as docs/virtual_students.md and human_policy.py), seeds 170000-170029 (30 games
            per policy, new seeds).
  Policies:
    N        no action (students only advance)
    H        careful human-style student (human_policy.play, unchanged)
    F-many   follows the advisor at help level 'many'   (coach every round)
    F-normal follows the advisor at help level 'normal' (coach R1, question hints R2-3, rule warnings only R4+)
    F-alerts follows the advisor at help level 'alerts' (rule warnings only)
  'Follow literally' = do only what a tip tells the student to do, as js/advisor-ui.js words it
  (port below, same thresholds). Questions ('몇 개를 팔고 몇 개를 남길까요?') are not instructions -> no action.
    listing  coach: list half (rounded up) of the top surplus good at the stepper default price (= quote)
    trading  every shortage ('정산 전에 구해야 해요'): buy from the cheapest market listing, one at a time;
             if none on the market: coach -> offer to buy from the first maker at quote x qty, else nothing.
             next-round fuel/ore warning: buy 1 from the cheapest listing.
    invest   coach and main industry not levelled and possible -> level it up;
             R6-7 deadline warning (all levels) -> level the main industry up if possible.
             Focus is never changed (the advisor gives no focus advice).
  Criteria for 'normal' (the default):
    C1  F-normal A-grade rate <= 10% for every country (following is not a winning recipe)
    C2  F-normal mean < H mean for every country (a thinking student does better than a follower)
    C3  F-normal mean > N mean for every country (the rule warnings still help)
  Reported, not judged: F-many and F-alerts, score spread (stdev) per policy.
Usage: PYTHONDONTWRITEBYTECODE=1 python3 advisor_follower.py [A K]  -> prints JSON, writes results/advisor_follower.json
"""
import json
import math
import os
import statistics as st
import sys

import paths  # noqa: F401
import classroom as C
from human_policy import play as play_h

STU = ['Tropia', 'Mechania', 'Mineria']
GEN_GOODS = ('machine', 'electronics')


def stage_for(level, rnd):
    if level == 'many':
        return 'coach'
    if level in ('alerts', 'off'):
        return 'quiet'
    return 'coach' if rnd <= 1 else 'hint' if rnd <= 3 else 'quiet'


def need_of(v, good):
    return sum(r['need'] for r in v['settlement']['rows'] if r['good'] == good)


def free_of(v, good):
    return sum(r['free'] for r in v['stock'] if r['good'] == good)


def cheapest(v, n, good):
    c = sorted((o for o in v['market'] if o['good'] == good and o['seller'] != n), key=lambda o: o['price'])
    return c[0] if c else None


def buy_cheapest(s, n, good, k):
    for _ in range(k):
        v = s.view(n)
        c = cheapest(v, n, good)
        if not c:
            return False
        if not s.apply({'type': 'buy', 'country': n, 'oid': c['oid'], 'qty': 1})['ok']:
            return False
    return True


def follow(s, n, level):
    v = s.view(n)
    stage = stage_for(level, v['round'])
    coach = stage == 'coach'
    if v['phase'] == 'listing':
        if not coach:
            return
        surplus = []
        for r in v['stock']:
            if r['free'] <= 0:
                continue
            extra = r['free'] - (need_of(v, r['good']) if (r['gen'] == 1 or r['good'] not in GEN_GOODS) else 0)
            if extra > 0:
                surplus.append((r['good'] != v['main'], -extra, r, extra))
        if surplus:
            surplus.sort(key=lambda x: (x[0], x[1]))
            _, _, r, extra = surplus[0]
            s.apply({'type': 'list', 'country': n, 'good': r['good'], 'gen': r['gen'], 'qty': math.ceil(extra / 2),
                     'price': v['quotes'][r['good']][r['gen']]})
    elif v['phase'] == 'trading':
        for r in [r for r in v['settlement']['rows'] if r['short'] > 0]:
            if cheapest(v, n, r['good']):
                buy_cheapest(s, n, r['good'], r['short'])
            elif coach:
                makers = [k for k, pr in (v.get('profiles') or {}).items()
                          if k != n and k in v['countries'] and (pr.get('levels') or {}).get(r['good'], 0) > 0]
                if makers:
                    q = v['quotes'][r['good']][1]
                    s.apply({'type': 'offer', 'country': n, 'kind': 'buy', 'to': makers[0],
                             'get': {'good': r['good'], 'gen': 1, 'qty': r['short']}, 'cash': q * r['short']})
        v = s.view(n)
        nxt = v['round'] + 1
        for good in ('fuel', 'ore'):
            if nxt in v['operating_schedule'][good] and free_of(v, good) - need_of(v, good) < 1:
                buy_cheapest(s, n, good, 1)
    elif v['phase'] == 'invest':
        main = next((o for o in v['invest_options'] if o['main']), None)
        if not main or v['progress']['main_levelled'] or not main['ok']:
            return
        deadline = 6 <= v['round'] <= 7
        if coach or deadline:
            s.apply({'type': 'invest', 'country': n, 'good': main['good']})


POLICIES = {
    'N': lambda s, n: None,
    'H': play_h,
    'F-many': lambda s, n: follow(s, n, 'many'),
    'F-normal': lambda s, n: follow(s, n, 'normal'),
    'F-alerts': lambda s, n: follow(s, n, 'alerts'),
}


def run(policy, a0, k):
    out = {n: [] for n in STU}
    for seed in range(a0, a0 + k):
        s = C.Session(seed, STU)
        while s.phase != 'finished':
            for n in STU:
                POLICIES[policy](s, n)
            assert s.apply({'type': 'advance'})['ok']
        for n in STU:
            r = s.results[n]
            out[n].append({'total': r['total'], 'grade': C.grade(r['total']), 'parts': r['parts']})
    return out


def summary(rows):
    t = [x['total'] for x in rows]
    return {'mean': round(st.mean(t), 1), 'stdev': round(st.stdev(t), 1), 'min': round(min(t), 1), 'max': round(max(t), 1),
            'A_rate': round(sum(x['grade'] == 'A' for x in rows) / len(rows), 3),
            'grades': {g: sum(x['grade'] == g for x in rows) for g in 'ABCD'},
            'parts': {p: round(st.mean(x['parts'][p] for x in rows), 1) for p in rows[0]['parts']}}


def main(a0=170000, k=30):
    res = {p: {n: summary(rows) for n, rows in run(p, a0, k).items()} for p in POLICIES}
    fn = res['F-normal']
    crit = {
        'C1_A_rate_le_10pct': {n: fn[n]['A_rate'] <= 0.10 for n in STU},
        'C2_below_H': {n: fn[n]['mean'] < res['H'][n]['mean'] for n in STU},
        'C3_above_N': {n: fn[n]['mean'] > res['N'][n]['mean'] for n in STU},
    }
    crit['all_pass'] = all(all(v.values()) for v in crit.values())
    out = {'games_per_policy': k, 'seeds': [a0, a0 + k - 1], 'students': STU, 'result': res, 'criteria': crit}
    os.makedirs(os.path.join(os.path.dirname(__file__), 'results'), exist_ok=True)
    with open(os.path.join(os.path.dirname(__file__), 'results', 'advisor_follower.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(*(map(int, sys.argv[1:3])) if len(sys.argv) > 2 else ())
