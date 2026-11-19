"""Experiment: economic score measured by export revenue (Claude, 2026-11-19; user chose 'export revenue').

Pre-registered before running (do not change after seeing results)
  Economy      v17 baseline + operating 'light' + emergency purchase 1.0x (condition B).
  One factor   economic-growth component (20 pts) = 20*clip(X / target). Everything else in the
               fixed score (reserve 5, capacity 15, utilization 10, wellbeing 25, trade 25) is kept.
  Primary X    'useful export value': for every unit a country sold (cash or barter),
               min(unit price, base reference value), counted only if another country actually
               used the unit by game end. Barter counts at reference value.
               (Plain cash revenue is reported as a secondary measure only, to show the
               wash-trade risk.)
  Targets      same v15 method on calibration seeds 90000-90059 (normal + each country
               invest/trade, 780 games, 180 own samples/country, equal weights):
               5*ceil(max(50, P75)/5).
  Validation   seeds 130000-130099 normal (100); seeds 132000-132029: normal (30), each country
               idle (6x30), each country 1G public price 'minimum' (6x30), Tropia+Oilia+Technia
               at once half price 'cheap' (30) and 1G 'minimum' (30), wash-trading pairs
               Tropia-Grainia (30) and Oilia-Mineria (30).
  Criteria     E1 idle student's economic attainment mean < 0.8 for all 6.
               E2 normal-play economic-target reach range across countries < 0.83 (v15 targets).
               E3 single 1G seller: economic attainment below its paired normal game in >= 25/30
                  games, for every country.
               E4 trio half price: Oilia and Technia (the sellers) have lower mean economic
                  attainment than in paired normal games.
               E5 wash trading: each pair member's mean economic attainment rises by <= 0.10 vs
                  paired normal games.
               E6 every country reaches its economic target in >= 1 normal game.

Usage: python3 export_revenue.py run cal|valid ; python3 export_revenue.py report
"""
import gzip
import json
import math
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L

OUT = os.path.join(HERE, 'new_games')
CAL = range(90000, 90060)
STRESS = range(132000, 132030)
TRIO = ('Tropia', 'Oilia', 'Technia')
WASH = {'wash_TG': (('Tropia', 'Grainia'),), 'wash_OM': (('Oilia', 'Mineria'),)}


def task(spec):
    tag, seed, focal, style = spec
    kw = dict(fee=1.0)
    if tag == 'cal' and style in ('invest', 'trade'):
        kw.update(focal=focal, style=style)
    elif style in ('idle', 'minimum'):
        kw['behaviors'] = {focal: style}
    elif style in ('trio_cheap', 'trio_minimum'):
        kw['behaviors'] = {n: style.split('_')[1] for n in TRIO}
    elif style in WASH:
        kw['wash'] = WASH[style]
    try:
        g = L.make_game(seed, **kw)
        m = L.run_metrics(g)  # run first, then read the wash counter
        return {'tag': tag, 'seed': seed, 'focal': focal, 'style': style, 'ok': True,
                'wash_count': getattr(g, 'wash_count', 0), 'm': m}
    except Exception as e:
        return {'tag': tag, 'seed': seed, 'focal': focal, 'style': style, 'ok': False, 'error': repr(e)[:300]}


def specs(stage):
    if stage == 'cal':
        s = [('cal', x, None, 'normal') for x in CAL]
        return s + [('cal', x, n, st) for n in L.NAMES for st in ('invest', 'trade') for x in CAL]
    s = [('valid', x, None, 'normal') for x in range(130000, 130100)]
    s += [('stress', x, None, 'normal') for x in STRESS]
    s += [('stress', x, n, b) for b in ('idle', 'minimum') for n in L.NAMES for x in STRESS]
    s += [('stress', x, None, b) for b in ('trio_cheap', 'trio_minimum', 'wash_TG', 'wash_OM') for x in STRESS]
    return s


def run(stage):
    with Pool(2) as p:
        rows = p.map(task, specs(stage), chunksize=4)
    with gzip.open(os.path.join(OUT, f'export_{stage}.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print(stage, 'games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def load(stage):
    with gzip.open(os.path.join(OUT, f'export_{stage}.jsonl.gz'), 'rt', encoding='utf-8') as f:
        rows = [json.loads(x) for x in f]
    assert all(r['ok'] for r in rows)
    return rows


def q75(a):
    a = sorted(a); pos = (len(a) - 1) * .75; lo = math.floor(pos); w = pos - lo
    return a[lo] * (1 - w) + a[min(lo + 1, len(a) - 1)] * w


def targets(cal, key):
    k = {(r['focal'], r['style'], r['seed']): r for r in cal}
    t, raw = {}, {}
    for n in L.NAMES:
        v = [k[(None if s == 'normal' else n, s, x)]['m'][n][key] for s in ('normal', 'invest', 'trade') for x in CAL]
        assert len(v) == 180
        raw[n] = q75(v); t[n] = 5 * math.ceil(max(50, raw[n]) / 5 - 1e-12)
    return t, raw


def report():
    cal, val = load('cal'), load('valid')
    T, raw = targets(cal, 'useful_export')
    T2, raw2 = targets(cal, 'revenue')
    att = lambda m, n, key='useful_export', t=T: min(1.0, m[n][key] / t[n])
    new_score = lambda m, n: m[n]['score'] - m[n]['econ_old'] + 20 * att(m, n)
    normal = [r for r in val if r['tag'] == 'valid']
    base = {r['seed']: r for r in val if r['tag'] == 'stress' and r['style'] == 'normal'}
    sel = lambda style, focal=None: [r for r in val if r['tag'] == 'stress' and r['style'] == style and r['focal'] == focal]
    mean = lambda a: sum(a) / len(a)
    res = {'targets_useful_export': T, 'raw_p75_useful_export': raw,
           'targets_plain_revenue': T2, 'raw_p75_plain_revenue': raw2}
    reach = {n: mean([r['m'][n]['useful_export'] >= T[n] for r in normal]) for n in L.NAMES}
    res['normal'] = {n: {'reach': reach[n], 'attain': mean([att(r['m'], n) for r in normal]),
                         'old_econ_attain': mean([r['m'][n]['econ_old'] / 20 for r in normal]),
                         'score_old': mean([r['m'][n]['score'] for r in normal]),
                         'score_new': mean([new_score(r['m'], n) for r in normal]),
                         'barter_share': mean([r['m'][n]['barter_value'] / max(1, r['m'][n]['useful_export']) for r in normal])}
                     for n in L.NAMES}
    res['idle'] = {n: {'attain': mean([att(r['m'], n) for r in sel('idle', n)]),
                       'score_new': mean([new_score(r['m'], n) for r in sel('idle', n)]),
                       'score_old': mean([r['m'][n]['score'] for r in sel('idle', n)])} for n in L.NAMES}

    def paired(rows, n):
        d = [att(r['m'], n) - att(base[r['seed']]['m'], n) for r in rows]
        ds = [new_score(r['m'], n) - new_score(base[r['seed']]['m'], n) for r in rows]
        do = [r['m'][n]['score'] - base[r['seed']]['m'][n]['score'] for r in rows]
        return {'d_attain': mean(d), 'lower_attain_games': sum(x < -1e-12 for x in d),
                'd_score_new': mean(ds), 'better_new': sum(x > 1e-9 for x in ds),
                'd_score_old': mean(do), 'better_old': sum(x > 1e-9 for x in do), 'n': len(rows)}
    res['minimum_single'] = {n: paired(sel('minimum', n), n) for n in L.NAMES}
    res['trio_cheap'] = {n: paired(sel('trio_cheap'), n) for n in L.NAMES}
    res['trio_minimum'] = {n: paired(sel('trio_minimum'), n) for n in L.NAMES}
    res['wash'] = {}
    for style, pairs in (('wash_TG', ('Tropia', 'Grainia')), ('wash_OM', ('Oilia', 'Mineria'))):
        rows = sel(style)
        res['wash'][style] = {n: {**paired(rows, n),
                                  'd_attain_plain_revenue': mean([att(r['m'], n, 'revenue', T2) - att(base[r['seed']]['m'], n, 'revenue', T2) for r in rows]),
                                  # unclipped size of the rise, as a fraction of each target
                                  'd_unclipped_useful': mean([(r['m'][n]['useful_export'] - base[r['seed']]['m'][n]['useful_export']) / T[n] for r in rows]),
                                  'd_unclipped_plain': mean([(r['m'][n]['revenue'] - base[r['seed']]['m'][n]['revenue']) / T2[n] for r in rows]),
                                  'wash_trades_per_game': mean([r['wash_count'] for r in rows])} for n in pairs}
    res['criteria'] = {
        'E1_idle_below_0.8': all(v['attain'] < .8 for v in res['idle'].values()),
        'E2_reach_range_below_0.83': max(reach.values()) - min(reach.values()) < .83,
        'E3_single_1G_lower_25of30': all(v['lower_attain_games'] >= 25 for v in res['minimum_single'].values()),
        'E4_trio_sellers_lower': all(res['trio_cheap'][n]['d_attain'] < 0 for n in ('Oilia', 'Technia')),
        'E5_wash_rise_le_0.10': all(v['d_attain'] <= .10 for w in res['wash'].values() for v in w.values()),
        'E6_every_country_reaches': all(v > 0 for v in reach.values()),
    }
    res['reach_range'] = max(reach.values()) - min(reach.values())
    res['games'] = {'cal': len(cal), 'valid': len(val)}
    json.dump(res, open(os.path.join(OUT, 'export_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    run(sys.argv[2]) if sys.argv[1] == 'run' else report()
