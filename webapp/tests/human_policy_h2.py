"""Policy H2 = human_policy.H + direct sell offers to AI countries (one added factor).

Pre-registered before running (descriptive; do not tune after seeing results)
  Same trio and seeds as human_policy.py (Tropia, Mechania, Mineria; 160000-160029).
  H2 trading phase, BEFORE buying: for each of my listings, take it back and offer its units
  one at a time to each AI country in the fixed order Tropia..Ferria (skipping students) at the
  listed price; move to the next country when an offer is refused; re-list what is left at the
  same price. Everything else is policy H.
  Question: does using direct offers bring every country's mean to >= 80 (flag otherwise)?
"""
import json
import statistics as st
import sys

import paths  # noqa: F401
import classroom as C
import human_policy as H

ORDER = list(C.ORIGINAL + C.ADDED)


def direct_sales(s, n):
    v = s.view(n)
    for o in list(v['my_orders']):
        r = s.apply({'type': 'cancel', 'country': n, 'oid': o['oid']})
        if not r['ok']:
            continue
        left = o['qty']
        for to in ORDER:
            if left == 0:
                break
            if to == n or to in s.g.students:
                continue
            while left:
                r = s.apply({'type': 'offer', 'country': n, 'to': to, 'kind': 'sell',
                             'give': {'good': o['good'], 'gen': o['gen'], 'qty': 1}, 'cash': o['price']})
                if not (r['ok'] and r.get('accepted')):
                    break
                left -= 1
        if left:
            s.apply({'type': 'list', 'country': n, 'good': o['good'], 'gen': o['gen'], 'qty': left, 'price': o['price']})


def play(s, n):
    if s.phase == 'trading':
        direct_sales(s, n)
    H.play(s, n)


def main(a0=160000, k=30):
    STU = H.STU
    res = {n: [] for n in STU}; parts = {n: [] for n in STU}
    for seed in range(a0, a0 + k):
        s = C.Session(seed, STU)
        while s.phase != 'finished':
            for n in STU:
                play(s, n)
            assert s.apply({'type': 'advance'})['ok']
        for n in STU:
            res[n].append(s.results[n]['total'])
            parts[n].append(s.results[n]['parts'] | {'export_value': s.results[n]['export_value']})
    for n in STU:
        t = res[n]
        print(n, round(st.mean(t), 1), round(min(t), 1), round(max(t), 1),
              {g: sum(C.grade(x) == g for x in t) for g in 'ABCD'},
              {key: round(st.mean(p[key] for p in parts[n]), 1) for key in parts[n][0]})


if __name__ == '__main__':
    main(*(map(int, sys.argv[1:3])) if len(sys.argv) > 2 else ())
