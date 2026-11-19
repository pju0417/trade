"""Reproducible v5 paired comparison, with a held-out seed set.

Pilot 18000..18029 is excluded. Main: all five policies, 22000..22199.
Stress: baseline and balanced, 24000..24029, each original-six focal country
at half-reference selling prices or idle, plus matched normal/no-trade controls.
Default total: 5*200 + 2*(12+2)*30 = 1,840 completed games.

The policy rules are frozen before this script runs. These are independent
simulation seeds, not students, lessons or empirical educational observations.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, statistics, time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from budget_trace import Game
from budget_engine import POLICIES
from expansion_engine import BASE_OPTIONS, ADDITIONS, CONFIG, NAMES

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'budget_results'
CORE_FILES = ('reference_engine.py','core_engine.py','engine.py','expansion_engine.py',
              'budget_engine.py','budget_trace.py')
REQUIRED = ('cash','happy','revenue','purchases','investment','tax','useful_exports',
            'production_failures','machine_gen','upgrades','uncovered_investments',
            'fallback_without_deferral','fallback_after_deferral','household_blocks')


def hashes():
    return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in CORE_FILES}


def run_one(task):
    phase,variant,seed,focal,style = task
    g = Game(seed,variant,focal=focal,style='normal' if style=='no_trade' else style,
             trade_enabled=style!='no_trade')
    result = g.run()
    for n,x in result['countries'].items():
        for k in REQUIRED:
            assert k in x and type(x[k]) in (int,float), (n,k)
    record = {'phase':phase,'variant':variant,'seed':seed,'focal':focal,'style':style,**result}
    ledger = g.cash_ledger if phase=='main' else None
    trace = g.trace() if phase=='main' and seed==22000 and variant in ('baseline','balanced') else None
    return record,ledger,trace


def flat(obj,prefix=''):
    values = {}
    for k,v in obj.items():
        key = f'{prefix}.{k}' if prefix else k
        if isinstance(v,dict):values.update(flat(v,key))
        elif type(v) in (int,float):values[key] = v
    return values


def stats(xs):
    m = statistics.mean(xs)
    se = statistics.stdev(xs)/math.sqrt(len(xs)) if len(xs)>1 else 0
    return {'n':len(xs),'mean':m,'ci95':[m-1.96*se,m+1.96*se],
            'min':min(xs),'max':max(xs)}


def grouped(rows):
    fs = [flat({'countries':r['countries'],'world':r['world']}) for r in rows]
    keys = set.intersection(*(set(f) for f in fs))
    # Some goods/count dictionaries legitimately omit zero values in v4 output;
    # only fields present in EVERY run are used here. Required fields above are
    # checked explicitly, never silently filled with zeros.
    return {'n':len(rows),'metrics':{k:stats([f[k] for f in fs]) for k in sorted(keys)}}


def pair(a,b):
    aa = {x['seed']:flat(x) for x in a}
    bb = {x['seed']:flat(x) for x in b}
    assert len(aa)==len(a) and len(bb)==len(b) and aa.keys()==bb.keys()
    seeds = sorted(aa)
    keys = set.intersection(*(set(aa[s]) & set(bb[s]) for s in seeds))
    return {k:stats([bb[s][k]-aa[s][k] for s in seeds]) for k in sorted(keys)
            if k.startswith(('countries.','world.'))}


def summarize(rows,meta):
    groups = defaultdict(list)
    for r in rows:groups[(r['phase'],r['variant'],r['focal'],r['style'])].append(r)
    agg = {':'.join(map(str,k)):grouped(rs) for k,rs in groups.items()}
    pairs = {}
    base = groups[('main','baseline',None,'normal')]
    for v in POLICIES:
        if v!='baseline':pairs['main:baseline->'+v]=pair(base,groups[('main',v,None,'normal')])
    for a,b in (('funded','living'),('living','balanced'),('living','stock_guard')):
        pairs[f'main:{a}->{b}']=pair(groups[('main',a,None,'normal')],groups[('main',b,None,'normal')])
    for v in ('baseline','balanced'):
        ctr = groups[('stress',v,None,'normal')]
        for focal in NAMES:
            for style in ('cheap','idle'):
                experimental = groups[('stress',v,focal,style)]
                p = pair(ctr,experimental)
                c = {x['seed']:x for x in ctr}
                other_deltas = []
                for x in experimental:
                    other_deltas.append(statistics.mean(x['countries'][n]['happy']-c[x['seed']]['countries'][n]['happy']
                                                       for n in NAMES if n!=focal))
                p['world.other_original_five_happy'] = stats(other_deltas)
                pairs[f'stress:{v}:{focal}:{style}'] = p
        pairs[f'stress:{v}:no_trade'] = pair(ctr,groups[('stress',v,None,'no_trade')])
    for focal,style in [(None,'normal'),(None,'no_trade')]+[(n,s) for n in NAMES for s in ('cheap','idle')]:
        pairs[f'stress:baseline->balanced:{focal}:{style}'] = pair(groups[('stress','baseline',focal,style)],
                                                                groups[('stress','balanced',focal,style)])
    return {'metadata':meta,'experiments':agg,'paired':pairs}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--n',type=int,default=200)
    p.add_argument('--stress-n',type=int,default=30)
    p.add_argument('--workers',type=int,default=4)
    a=p.parse_args()
    if a.n<2 or a.stress_n<2:p.error('use at least two seeds per group')
    OUT.mkdir(exist_ok=True)
    tasks = [('main',v,s,None,'normal') for v in POLICIES for s in range(22000,22000+a.n)]
    tasks += [('stress',v,s,n,style) for v in ('baseline','balanced') for n in NAMES
              for style in ('cheap','idle') for s in range(24000,24000+a.stress_n)]
    tasks += [('stress',v,s,None,style) for v in ('baseline','balanced')
              for style in ('normal','no_trade') for s in range(24000,24000+a.stress_n)]
    sources = hashes()
    config = {'main_seed_range':[22000,22000+a.n-1],'stress_seed_range':[24000,24000+a.stress_n-1],
              'excluded_pilot_range':[18000,18029],'planned_games':len(tasks),
              'policies':{k:asdict(v) for k,v in POLICIES.items()},'options':asdict(BASE_OPTIONS),
              'original_countries':CONFIG,'new_countries':ADDITIONS,'source_sha256':sources,
              'rounds':9,'countries':9,'post_invest_rule_scope':'all next-cycle operating resources plus separate research materials',
              'primary_checks':['no conservation violations','no uncovered balanced investments',
                                'household welfare alongside cash','absolute useful exports and technology',
                                'impact on all resource suppliers; no score-based parameter fitting'],
              'limitations':['rule-based serial agents; not a multiplayer app or a student study',
                             'cheap means 50% of reference quote; purchases and investment stay active',
                             'stock_guard is a diagnostic candidate, not an adopted game rule',
                             'confidence intervals cover seed variation within this model only']}
    (OUT/'pre_run_plan.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    tic=time.monotonic(); rows=[]; traces={}
    with ProcessPoolExecutor(max_workers=a.workers) as pool, \
         gzip.open(OUT/'runs.partial.jsonl.gz','wt') as file, \
         gzip.open(OUT/'round_ledgers.partial.jsonl.gz','wt') as ledger_file:
        for i,(record,ledger,trace) in enumerate(pool.map(run_one,tasks,chunksize=4),1):
            rows.append(record)
            file.write(json.dumps(record,ensure_ascii=False)+'\n')
            if ledger is not None:
                ledger_file.write(json.dumps({'variant':record['variant'],'seed':record['seed'],'rows':ledger},ensure_ascii=False)+'\n')
            if trace is not None:traces[record['variant']]=trace
            if i%200==0:print(f'{i}/{len(tasks)} games complete; {time.monotonic()-tic:.1f}s',flush=True)
    assert len(rows)==len(tasks)==len({(r['phase'],r['variant'],r['seed'],r['focal'],r['style']) for r in rows})
    assert sources==hashes(),'economic source changed during execution'
    assert all(r['world']['uncovered_investments']==0 for r in rows if r['variant']!='baseline')
    for name in ('runs','round_ledgers'):(OUT/f'{name}.partial.jsonl.gz').replace(OUT/f'{name}.jsonl.gz')
    meta={**config,'completed_games':len(rows),'main_games':len(POLICIES)*a.n,
          'stress_games':len(rows)-len(POLICIES)*a.n,'verification_calls':sum(r['world']['verify_calls'] for r in rows),
          'verification_failures':0,'elapsed_seconds':time.monotonic()-tic,
          'pilot_excluded':True,'trace_and_unit_test_games_excluded':True}
    summary=summarize(rows,meta)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (OUT/'run_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    with gzip.open(OUT/'first_seed_traces.json.gz','wt') as f:json.dump(traces,f,ensure_ascii=False)
    print('DONE',len(rows),'games,',round(meta['elapsed_seconds'],2),'seconds',flush=True)
    for v in POLICIES:
        m=summary['experiments'][f'main:{v}:None:normal']['metrics']
        print(v,{k:round(m['countries.Mechania.'+k]['mean'],4) for k in ('cash','happy','investment','production_failures','useful_exports','machine_gen')},flush=True)


if __name__=='__main__':main()
