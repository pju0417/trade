"""Frozen split: pilot 0-29; training 100-299; validation 2000+, no tuning on holdout.
python run_validation.py --n 300 --stress-n 60 --workers 4
"""
from __future__ import annotations
import argparse,concurrent.futures,dataclasses,gzip,hashlib,json,math,statistics,time
from pathlib import Path
from collections import defaultdict
from engine import Game,Options,NAMES
import reference_engine as ref
from scoring import make_goals,apply
ROOT=Path(__file__).resolve().parent
BASE=dict(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True)
VARIANTS={
 'previous_supply':(ref.Game,ref.Options(**BASE)),
 'previous_combined':(ref.Game,ref.Options(**BASE,specialist_cost=True)),
 'core_only':(Game,Options(**BASE,budget_plans=False,adaptive_expansion=False,upgrade_living_goods=False)),
 'budget_only':(Game,Options(**BASE,adaptive_expansion=False,upgrade_living_goods=False)),
 'revised':(Game,Options(**BASE)),
 'research_discount':(Game,Options(**BASE,specialist_cost=True))}

def job(task):
    variant,seed,focal,style=task
    v='revised' if variant in ('train','no_trade','all_idle') else variant
    cls,opt=VARIANTS[v]
    if variant=='no_trade':opt=dataclasses.replace(opt,trade_enabled=False)
    g=cls(seed,opt,focal=focal,style=style,all_style='idle' if variant=='all_idle' else None)
    if variant=='train':
        # Every nation receives each strategy equally. No idle or cheap players
        # in goal-setting; held-out stress players do not define their own goals.
        for i,n in enumerate(NAMES):g.cs[n].style=('normal','normal','invest','trade')[(seed+i)%4]
    result=g.run()
    return {'variant':variant,'seed':seed,'focal':focal,'style':style,**result}

def flat(d,p=''):
    ans={}
    for k,v in d.items():
        key=p+'.'+str(k) if p else str(k)
        if isinstance(v,dict):ans.update(flat(v,key))
        elif isinstance(v,(float,int)):ans[key]=v
    return ans

def stats(v):
    m=statistics.mean(v);se=statistics.stdev(v)/math.sqrt(len(v)) if len(v)>1 else 0
    return {'mean':m,'ci95':[m-1.96*se,m+1.96*se],'min':min(v),'max':max(v)}

def aggregate(rows):
    fs=[flat({'countries':r['countries'],'world':r['world']}) for r in rows]
    keys=set().union(*(f.keys() for f in fs))
    out={'n':len(rows),'metrics':{k:stats([f.get(k,0) for f in fs]) for k in sorted(keys)}}
    for sk in ('score','previous_score','score_v3'):
        if sk not in rows[0]['countries'][NAMES[0]]:continue
        wins=dict.fromkeys(NAMES,0.)
        for r in rows:
            hi=max(r['countries'][n][sk] for n in NAMES)
            ns=[n for n in NAMES if abs(r['countries'][n][sk]-hi)<1e-9]
            for n in ns:wins[n]+=100/len(rows)/len(ns)
        out['wins_'+sk]=wins
        means=[out['metrics'][f'countries.{n}.{sk}']['mean'] for n in NAMES]
        out['gap_'+sk]=max(means)-min(means)
    out['barter_games_pct']=100*sum(r['world']['barter']>0 for r in rows)/len(rows)
    return out

def paired(a,b,paths):
    aa={r['seed']:flat(r) for r in a};bb={r['seed']:flat(r) for r in b};seeds=sorted(set(aa)&set(bb))
    return {p:stats([bb[s].get(p,0)-aa[s].get(p,0) for s in seeds]) for p in paths}

def main():
    p=argparse.ArgumentParser();p.add_argument('--n',type=int,default=300);p.add_argument('--stress-n',type=int,default=60);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    out=ROOT/'results';out.mkdir(exist_ok=True);t=time.time();allrows=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
        training=list(pool.map(job,[('train',s,None,'normal') for s in range(100,300)],chunksize=10))
        goals=make_goals(training);goals['training_seeds']=[100,299]
        (out/'goals_candidate.json').write_text(json.dumps(goals,indent=2))
        print('Frozen goals:',goals,flush=True)
        jobs=[]
        for v in VARIANTS:jobs += [(v,s,None,'normal') for s in range(2000,2000+a.n)]
        for v in ('previous_supply','revised'):
            for n in NAMES:
                for st in ('cheap','idle','invest','trade'):
                    jobs += [(v,s,n,st) for s in range(2000,2000+a.stress_n)]
        jobs += [(v,s,None,'normal') for v in ('no_trade','all_idle') for s in range(2000,2000+a.stress_n)]
        with gzip.open(out/'runs.jsonl.gz','wt',encoding='utf-8') as f:
            for r in training:
                apply(r,goals);allrows.append(r);f.write(json.dumps(r)+'\n')
            for i,r in enumerate(pool.map(job,jobs,chunksize=10),1):
                if 'evaluated_progress' in r['countries'][NAMES[0]]:apply(r,goals)
                allrows.append(r);f.write(json.dumps(r)+'\n')
                if i%300==0:print(i,'/',len(jobs),'time',round(time.time()-t,1),flush=True)
    groups=defaultdict(list)
    for r in allrows:groups[(r['variant'],r['focal'],r['style'])].append(r)
    summary={'metadata':{'n_training':200,'n_validation':len(jobs),'n_total':len(allrows),'main_repetitions':a.n,'stress_repetitions':a.stress_n,'validation_seeds':[2000,2000+a.n-1],'pilot_seeds':[0,29],
      'engine_sha256':hashlib.sha256((ROOT/'engine.py').read_bytes()).hexdigest(),'reference_sha256':hashlib.sha256((ROOT/'reference_engine.py').read_bytes()).hexdigest(),'goals':goals,
      'variants':{n:dataclasses.asdict(o) for n,(_,o) in VARIANTS.items()}},
      'experiments':{':'.join(str(x) for x in k):aggregate(rs) for k,rs in groups.items()}}
    paths=['world.listed','world.inventory','world.trade_units','world.barter','world.counter_accepted','world.electronics_expansions']
    paths += [f'countries.{n}.{k}' for n in NAMES for k in ('cash','happy','score','trade','upgrades','electronics_expanded')]
    changes={}
    for va,vb in [('previous_supply','core_only'),('core_only','budget_only'),('budget_only','revised'),('previous_supply','revised'),('revised','research_discount')]:
        changes[va+'->'+vb]=paired(groups[(va,None,'normal')],groups[(vb,None,'normal')],paths)
    for v in ('previous_supply','revised'):
        for n in NAMES:
            for st in ('cheap','idle','invest','trade'):
                changes[v+':'+n+':'+st]=paired(groups[(v,None,'normal')],groups[(v,n,st)],paths)
    summary['paired']=changes;summary['metadata']['elapsed_seconds']=time.time()-t
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    # Detailed examples, not just aggregate summaries.
    for focal in (None,'Technia'):
        g=Game(2000,VARIANTS['revised'][1],focal=focal,style='idle' if focal else 'normal')
        result=g.run();trace={'result':result,'rounds':g.round_history,'transactions':g.transactions,'needs':g.needs_ledger,'launches':g.launch_events,
        'upgrades':{n:g.cs[n].upgrade_rounds for n in NAMES},'units':[dataclasses.asdict(u) for u in g.units.values()]}
        (out/f'trace_2000_{focal or "normal"}.json').write_text(json.dumps(trace,indent=2))
    print('COMPLETE',len(allrows),'games',round(time.time()-t,1),'seconds',flush=True)
if __name__=='__main__':main()
