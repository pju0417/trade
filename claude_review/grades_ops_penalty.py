"""Option 2 (user choice): national-operation shortages reduce the living (wellbeing) score directly.

Pre-registered before computing (do not change after seeing results); rescoring only, 0 new games
  One factor   wellbeing points (25) -> max(0, wellbeing points - 1 x number of settlement days on
               which a national-operation bundle was missing from stock). The emergency purchase
               fee is still charged; the economy and all play are unchanged (AI policies do not
               read the score), so the 900 games of grades.py are rescored.
  Scheme       score bands S of grades.py (A >= 90, B >= 80, C >= 60, D < 60).
  Criteria     Q1-Q7 of grades.py under the new wellbeing rule, plus
               R1 good play: mean total score changes by <= 0.5 point, every country.
Usage: python3 grades_ops_penalty.py
"""
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L
import grades as G

PENALTY = 1


def parts(m, n, T):
    total, checks, s, mm = G.parts(m, n, T)
    x = m[n]
    cut = min(x['well_pts'], PENALTY * x['op_short'])  # wellbeing cannot go below 0
    total2 = total - cut
    s2 = 4 if total2 >= 90 else 3 if total2 >= 80 else 2 if total2 >= 60 else 1
    return total2, s2, total, cut


def main():
    with gzip.open(os.path.join(G.OUT, 'grades_games.jsonl.gz'), 'rt', encoding='utf-8') as f:
        rows = [json.loads(x) for x in f]
    assert all(r['ok'] for r in rows)
    T = json.load(open(os.path.join(G.OUT, 'export_noswap_report.json')))['targets_useful_export']
    idx = {(r['b'], r['focal'], r['seed']): parts(r['m'], r['focal'], T) for r in rows}
    mean = lambda a: sum(a) / len(a)
    per = {}
    for n in L.NAMES:
        d = {}
        for b in G.BEHAVIOURS:
            g = [idx[(b, n, x)][1] for x in G.SEEDS]
            d[b] = {'dist': {G.GRADE[k]: g.count(k) for k in (4, 3, 2, 1)},
                    'A_rate': g.count(4) / 30, 'AB_rate': (g.count(4) + g.count(3)) / 30, 'D_rate': g.count(1) / 30,
                    'mean_total_new': mean([idx[(b, n, x)][0] for x in G.SEEDS]),
                    'mean_total_old': mean([idx[(b, n, x)][2] for x in G.SEEDS]),
                    'mean_cut': mean([idx[(b, n, x)][3] for x in G.SEEDS])}
            if b != 'good':
                diff = [idx[(b, n, x)][1] - idx[('good', n, x)][1] for x in G.SEEDS]
                d[b]['lower_than_good'] = sum(v < 0 for v in diff) / 30
                d[b]['not_higher_than_good'] = sum(v <= 0 for v in diff) / 30
                d[b]['mean_grade_diff'] = mean(diff)
        per[n] = d
    A = [per[n]['good']['A_rate'] for n in L.NAMES]
    crit = {'Q1_good_AB_ge_0.8': all(per[n]['good']['AB_rate'] >= .8 for n in L.NAMES),
            'Q2_good_A_range_le_0.3': max(A) - min(A) <= .3 + 1e-9,
            'Q3_good_A_ge_0.3': all(a >= .3 for a in A),
            'Q4_idle_D_ge_0.9': all(per[n]['idle']['D_rate'] >= .9 for n in L.NAMES),
            'Q5_minimum_lower_ge_0.8': all(per[n]['minimum']['lower_than_good'] >= .8 for n in L.NAMES),
            'Q6_skip_not_higher_ge_0.9_and_lower_mean': all(per[n]['skip_ops']['not_higher_than_good'] >= .9 and per[n]['skip_ops']['mean_grade_diff'] < 0 for n in L.NAMES),
            'Q7_no_invest_A_le_0.05': all(per[n]['no_invest']['A_rate'] <= .05 for n in L.NAMES),
            'R1_good_total_change_le_0.5': all(abs(per[n]['good']['mean_total_new'] - per[n]['good']['mean_total_old']) <= .5 for n in L.NAMES)}
    res = {'penalty_per_shortage_day': PENALTY, 'countries': per, 'criteria': crit, 'new_games': 0, 'rescored_games': len(rows)}
    json.dump(res, open(os.path.join(G.OUT, 'grades_ops_penalty_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
