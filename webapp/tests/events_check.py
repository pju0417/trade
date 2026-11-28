"""World event cards (docs/RULES_v1.md section 10): safe, correct, and not breaking the balance?

Pre-registered (written before the first run; do not tune events or criteria after seeing results)
  E1 safety   With events on: random-action fuzz (test_actions.random_action) on seeds 180100-180119 -
              no internal error, engine verify() passes, the log replays to identical results and views.
  E2 effect   In 0-student sessions the R2 event changes R2 production exactly as the rule table says:
              seeds 180200-180259 (60 games), compare the units minted in R2 with events on vs off
              (state before R2 production is identical). Expected: delta per (country, good), at least 1 made.
  E3 balance  Careful human-style students (human_policy H) for Tropia, Mechania, Mineria, seeds 180000-180029:
              mean total with events on is at most 8 points below events off, for every country.
  E4 balance  H A+B rate with events on >= 70% for every country.
  Reported, not judged: N (no action) and F-normal (advisor follower) on/off, score stdev, event counts.
Usage: PYTHONDONTWRITEBYTECODE=1 python3 events_check.py  -> prints JSON, writes results/events_check.json
"""
import json
import os
import random
import statistics as st
from collections import Counter

import paths  # noqa: F401
import classroom as C
from human_policy import play as play_h
from advisor_follower import follow
from test_actions import random_action

STU = ['Tropia', 'Mechania', 'Mineria']


def e1_fuzz(a0=180100, k=20):
    stats = {'games': 0, 'actions': 0, 'accepted': 0}
    for seed in range(a0, a0 + k):
        rng = random.Random(seed)
        students = rng.sample(list(C.ORIGINAL), rng.choice((1, 3, 3, 6)))
        s = C.Session(seed, students, events=True)
        while s.phase != 'finished':
            for _ in range(rng.randint(0, 25)):
                n = rng.choice(students)
                act = random_action(rng, s, n)
                r = s.apply(act)
                assert 'error' not in r, (seed, act, r)
                stats['actions'] += 1; stats['accepted'] += r['ok']
            assert s.apply({'type': 'advance'})['ok'], seed
            s.g.verify()
        for n in students:
            json.dumps(s.view(n))
        json.dumps(s.teacher_view())
        s2 = C.Session.replay(seed, students, s.log, events=True)
        assert json.dumps(s.results, sort_keys=True) == json.dumps(s2.results, sort_keys=True), seed
        assert json.dumps(s.view(students[0]), sort_keys=True) == json.dumps(s2.view(students[0]), sort_keys=True), seed
        stats['games'] += 1
    return stats


def minted(s):
    """units made in the current round's production, per (country, good)"""
    r = s.g.r
    return Counter((u.origin, u.good) for u in s.g.units.values() if u.born == r)


def e2_effect(a0=180200, k=60):
    ok, bad, kinds = 0, [], Counter()
    for seed in range(a0, a0 + k):
        off = C.Session(seed, [])
        on = C.Session(seed, [], events=True)
        for s in (off, on):  # advance both to the start of R2 (R1 has no event, so the states are identical)
            while s.g.r < 2:
                s.apply({'type': 'advance'})
        e = on.events[2]
        kinds[e['kind']] += 1
        # expected change: base quantity b -> max(1, b + delta) for the hit (country, good)
        expect = {}
        for n, c in off.g.cs.items():
            if e['good'] in c.levels and (e['country'] in (None, n)):
                b = off.g.base_quantity(c, e['good'])
                d = e['delta'] if e['good'] == 'machine' else max(1, b + e['delta']) - b  # machines: added after production
                if d:
                    expect[(n, e['good'])] = d
        m_off, m_on = minted(off), minted(on)
        diff = {key: m_on.get(key, 0) - m_off.get(key, 0) for key in set(m_off) | set(m_on) if m_on.get(key, 0) != m_off.get(key, 0)}
        if diff == expect:
            ok += 1
        else:
            bad.append({'seed': seed, 'event': e['kind'], 'expect': {f'{x}:{y}': v for (x, y), v in expect.items()}, 'diff': {f'{x}:{y}': v for (x, y), v in diff.items()}})
    return {'games': k, 'ok': ok, 'kinds': dict(kinds), 'mismatches': bad[:10]}


def run(policy, events, a0=180000, k=30):
    out = {n: [] for n in STU}
    for seed in range(a0, a0 + k):
        s = C.Session(seed, STU, events=events)
        while s.phase != 'finished':
            for n in STU:
                policy(s, n)
            assert s.apply({'type': 'advance'})['ok']
        for n in STU:
            out[n].append(s.results[n]['total'])
    return {n: {'mean': round(st.mean(t), 1), 'stdev': round(st.stdev(t), 1),
                'AB_rate': round(sum(C.grade(x) in 'AB' for x in t) / len(t), 3),
                'grades': {gr: sum(C.grade(x) == gr for x in t) for gr in 'ABCD'}} for n, t in out.items()}


def main():
    res = {'E1_fuzz': e1_fuzz(), 'E2_effect': e2_effect()}
    pol = {'H': play_h, 'N': lambda s, n: None, 'F-normal': lambda s, n: follow(s, n, 'normal')}
    res['scores'] = {f'{p}-{"on" if ev else "off"}': run(f, ev) for p, f in pol.items() for ev in (False, True)}
    h_off, h_on = res['scores']['H-off'], res['scores']['H-on']
    res['criteria'] = {
        'E1_safe': res['E1_fuzz']['games'] == 20,
        'E2_effect_all': res['E2_effect']['ok'] == res['E2_effect']['games'],
        'E3_H_drop_le_8': {n: h_off[n]['mean'] - h_on[n]['mean'] <= 8 for n in STU},
        'E4_H_AB_ge_70pct': {n: h_on[n]['AB_rate'] >= 0.70 for n in STU},
    }
    c = res['criteria']
    c['all_pass'] = c['E1_safe'] and c['E2_effect_all'] and all(c['E3_H_drop_le_8'].values()) and all(c['E4_H_AB_ge_70pct'].values())
    os.makedirs(os.path.join(os.path.dirname(__file__), 'results'), exist_ok=True)
    with open(os.path.join(os.path.dirname(__file__), 'results', 'events_check.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
