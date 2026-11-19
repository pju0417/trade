"""Experiment: industrial target as a number of level-ups (option A; user chose A, 2026-11-19).

Pre-registered before running (do not change after seeing results)
  Economy      v17 baseline + operating 'light' + emergency purchase 1.0x.
  Baseline     current candidate score: economic 20 = export measure 'useful_export_noswap'
               with its targets (export_noswap_report.json); all else = v17 fixed score.
  One factor   industrial capacity component (15 pts): 15*clip(capacity growth / v15 step target)
               -> 15*min(1, level-ups / K), K = 2 for every country, K = 3 for Technia.
               A level-up is any successful investment (existing industry or entering the
               designated expansion industry). Utilization 10 pts unchanged.
  Games        normal seeds 130000-130099 (100); seeds 132000-132029: normal (30), each
               country focal 'invest' (6x30), 'trade' = no investment (6x30), 'idle' (6x30).
  Criteria     G1 feasibility: investment-focused play reaches K in >= 80% of games, every country.
               G2 burden: in investment-focused play, mean satisfaction drop vs paired normal
                  <= 5 points and mean operating-shortage rounds <= 1, every country.
               G3 fairness: G1 reach rates differ across countries by <= 0.30.
               G4 no-investment play ('trade') gets 0 industrial capacity points, every country.
  Reported, not judged: normal-AI reach rates, which industries were upgraded, total scores.
Result of the run above: G1-G3 failed. Diagnosis: the AI 'invest' policy keeps aiming at one
preferred industry (e.g. Mechania machine level 3: 185G + 2 ore) and never switches, so it does
not show whether a student could reach K.

Follow-up, pre-registered before running (stage 'student'):
  Policy       sim_lib.LevelUpStudent: until K level-ups are made, the focal country plans the
               cheapest currently legal upgrade; all engine checks still apply. Otherwise normal AI.
  Games        each country focal, seeds 132000-132029 (6x30), paired with stored normal games.
  Criteria     H1 reach K in >= 80% of games, every country.
               H2 mean satisfaction drop vs paired normal <= 5 and operating-shortage rounds <= 1.
               H3 H1 reach rates differ across countries by <= 0.30.
Result: H1 and H3 failed (Tropia reach 3%, Grainia 0%). Diagnosis: agricultural countries hold
only 65-85G in R2-R6 (electronics 166G and operating resources 72G are bought), while the engine's
AI cash reserve (40-60G) is also required on top of the cost. That reserve is an AI policy, not a
student rule (handoff 4.2).

Second follow-up, pre-registered before running (stage 'student_noreserve'):
  Policy       sim_lib.LevelUpNoReserve = LevelUpStudent without the AI cash reserve at the moment
               the focal country invests (cost, ore, machine checks unchanged).
  Games/criteria  same as 'student' (6x30, seeds 132000-132029; H1, H2, H3).
Usage: python3 industrial_levelup.py run|student|student_noreserve ; ... report|report_student|report_noreserve
"""
import gzip
import json
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L

OUT = os.path.join(HERE, 'new_games')
K = {n: 2 for n in L.NAMES}; K['Technia'] = 3
STRESS = range(132000, 132030)


def task(spec):
    tag, seed, focal, style = spec
    kw = dict(fee=1.0)
    if style in ('student', 'student_noreserve'):
        kw['levelup'] = {focal: K[focal]}
        kw['no_reserve'] = style == 'student_noreserve'
    elif style in ('invest', 'trade'):
        kw.update(focal=focal, style=style)
    elif style == 'idle':
        kw['behaviors'] = {focal: 'idle'}
    try:
        m = L.run_metrics(L.make_game(seed, **kw))
        return {'tag': tag, 'seed': seed, 'focal': focal, 'style': style, 'ok': True, 'm': m}
    except Exception as e:
        return {'tag': tag, 'seed': seed, 'focal': focal, 'style': style, 'ok': False, 'error': repr(e)[:300]}


def specs():
    s = [('valid', x, None, 'normal') for x in range(130000, 130100)]
    s += [('stress', x, None, 'normal') for x in STRESS]
    s += [('stress', x, n, b) for b in ('invest', 'trade', 'idle') for n in L.NAMES for x in STRESS]
    return s


def run(student=False):
    st = student if isinstance(student, str) else 'student'
    sp = [('stress', x, n, st) for n in L.NAMES for x in STRESS] if student else specs()
    with Pool(2) as p:
        rows = p.map(task, sp, chunksize=4)
    name = f'levelup_{st}_games.jsonl.gz' if student else 'levelup_games.jsonl.gz'
    with gzip.open(os.path.join(OUT, name), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print('games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def report():
    with gzip.open(os.path.join(OUT, 'levelup_games.jsonl.gz'), 'rt', encoding='utf-8') as f:
        rows = [json.loads(x) for x in f]
    assert all(r['ok'] for r in rows)
    T = json.load(open(os.path.join(OUT, 'export_noswap_report.json')))['targets_useful_export']
    mean = lambda a: sum(a) / len(a)
    econ = lambda m, n: 20 * min(1, m[n]['useful_export_noswap'] / T[n])
    cap = lambda m, n: 15 * min(1, m[n]['upgrades'] / K[n])
    base_score = lambda m, n: m[n]['score'] - m[n]['econ_old'] + econ(m, n)  # current candidate
    new_score = lambda m, n: base_score(m, n) - m[n]['cap_old'] + cap(m, n)
    normal = [r for r in rows if r['tag'] == 'valid']
    pair = {r['seed']: r for r in rows if r['tag'] == 'stress' and r['style'] == 'normal'}
    sel = lambda b, n: [r for r in rows if r['tag'] == 'stress' and r['style'] == b and r['focal'] == n]
    res = {'K': K, 'export_targets': T, 'countries': {}}
    for n in L.NAMES:
        inv, trd, idl = sel('invest', n), sel('trade', n), sel('idle', n)
        paths = {}
        for r in inv:
            for _, g, _lv in r['m'][n]['upgrade_path']:
                paths[g] = paths.get(g, 0) + 1
        res['countries'][n] = {
            'normal_ai': {'reach': mean([r['m'][n]['upgrades'] >= K[n] for r in normal]),
                          'mean_upgrades': mean([r['m'][n]['upgrades'] for r in normal]),
                          'cap_old': mean([r['m'][n]['cap_old'] for r in normal]),
                          'cap_new': mean([cap(r['m'], n) for r in normal]),
                          'score_before': mean([base_score(r['m'], n) for r in normal]),
                          'score_after': mean([new_score(r['m'], n) for r in normal])},
            'invest': {'reach': mean([r['m'][n]['upgrades'] >= K[n] for r in inv]),
                       'mean_upgrades': mean([r['m'][n]['upgrades'] for r in inv]),
                       'd_happy': mean([r['m'][n]['happy'] - pair[r['seed']]['m'][n]['happy'] for r in inv]),
                       'op_short': mean([r['m'][n]['op_short'] for r in inv]),
                       'emergency_G': mean([r['m'][n]['emergency'] for r in inv]),
                       'upgraded_industries': paths,
                       'score_after': mean([new_score(r['m'], n) for r in inv]),
                       'd_score_after_vs_normal': mean([new_score(r['m'], n) - new_score(pair[r['seed']]['m'], n) for r in inv])},
            'trade': {'cap_new': mean([cap(r['m'], n) for r in trd]),
                      'score_after': mean([new_score(r['m'], n) for r in trd]),
                      'd_score_after_vs_normal': mean([new_score(r['m'], n) - new_score(pair[r['seed']]['m'], n) for r in trd])},
            'idle': {'score_after': mean([new_score(r['m'], n) for r in idl])},
        }
    C = res['countries']
    reach = [C[n]['invest']['reach'] for n in L.NAMES]
    res['criteria'] = {
        'G1_invest_reach_ge_0.8': all(x >= .8 for x in reach),
        'G2_burden': all(C[n]['invest']['d_happy'] >= -5 and C[n]['invest']['op_short'] <= 1 for n in L.NAMES),
        'G3_reach_range_le_0.3': max(reach) - min(reach) <= .3,
        'G4_no_invest_zero': all(C[n]['trade']['cap_new'] == 0 for n in L.NAMES),
    }
    res['games'] = len(rows)
    json.dump(res, open(os.path.join(OUT, 'levelup_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def report_student(st='student'):
    def load(name):
        with gzip.open(os.path.join(OUT, name), 'rt', encoding='utf-8') as f:
            rows = [json.loads(x) for x in f]
        assert all(r['ok'] for r in rows)
        return rows
    base = load('levelup_games.jsonl.gz'); stu = load(f'levelup_{st}_games.jsonl.gz')
    T = json.load(open(os.path.join(OUT, 'export_noswap_report.json')))['targets_useful_export']
    mean = lambda a: sum(a) / len(a)
    econ = lambda m, n: 20 * min(1, m[n]['useful_export_noswap'] / T[n])
    cap = lambda m, n: 15 * min(1, m[n]['upgrades'] / K[n])
    score = lambda m, n: m[n]['score'] - m[n]['econ_old'] + econ(m, n) - m[n]['cap_old'] + cap(m, n)
    pair = {r['seed']: r for r in base if r['tag'] == 'stress' and r['style'] == 'normal'}
    res = {'K': K, 'countries': {}}
    for n in L.NAMES:
        rows = [r for r in stu if r['focal'] == n]
        paths = {}
        for r in rows:
            for _, g, _lv in r['m'][n]['upgrade_path'][:K[n]]:
                paths[g] = paths.get(g, 0) + 1
        res['countries'][n] = {
            'reach': mean([r['m'][n]['upgrades'] >= K[n] for r in rows]),
            'mean_upgrades': mean([r['m'][n]['upgrades'] for r in rows]),
            'first_K_upgrades_by_industry': paths,
            'main_industry': L.engine.Game.__mro__ and None,
            'd_happy': mean([r['m'][n]['happy'] - pair[r['seed']]['m'][n]['happy'] for r in rows]),
            'op_short': mean([r['m'][n]['op_short'] for r in rows]),
            'emergency_G': mean([r['m'][n]['emergency'] for r in rows]),
            'econ_attain': mean([econ(r['m'], n) / 20 for r in rows]),
            'econ_attain_normal': mean([econ(pair[r['seed']]['m'], n) / 20 for r in rows]),
            'score': mean([score(r['m'], n) for r in rows]),
            'd_score_vs_normal': mean([score(r['m'], n) - score(pair[r['seed']]['m'], n) for r in rows]),
            'better_than_normal': sum(score(r['m'], n) > score(pair[r['seed']]['m'], n) + 1e-9 for r in rows),
        }
        del res['countries'][n]['main_industry']
    C = res['countries']; reach = [C[n]['reach'] for n in L.NAMES]
    res['criteria'] = {'H1_reach_ge_0.8': all(x >= .8 for x in reach),
                       'H2_burden': all(C[n]['d_happy'] >= -5 and C[n]['op_short'] <= 1 for n in L.NAMES),
                       'H3_range_le_0.3': max(reach) - min(reach) <= .3}
    res['games'] = len(stu)
    json.dump(res, open(os.path.join(OUT, f'levelup_{st}_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    {'run': run, 'student': lambda: run(True), 'student_noreserve': lambda: run('student_noreserve'),
     'report': report, 'report_student': report_student,
     'report_noreserve': lambda: report_student('student_noreserve')}[sys.argv[1]]()
