"""Run the fixed validation in short, independently saved batches.
python run_staged.py train
python run_staged.py chunk --index 0  # through 5
python run_staged.py aggregate
"""
import argparse,concurrent.futures,gzip,hashlib,json,time,dataclasses
from pathlib import Path
from collections import defaultdict
from run_validation import job,VARIANTS,aggregate,paired
from engine import Game,NAMES
from scoring import make_goals,apply
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'

def tasks():
    jobs=[]
    for v in VARIANTS:jobs.extend((v,s,None,'normal') for s in range(2000,2300))
    for v in ('previous_supply','revised'):
        for n in NAMES:
            for st in ('cheap','idle','invest','trade'):jobs.extend((v,s,n,st) for s in range(2000,2060))
    for v in ('no_trade','all_idle'):jobs.extend((v,s,None,'normal') for s in range(2000,2060))
    assert len(jobs)==4800
    return jobs

def save_rows(path,rows):
    with gzip.open(path,'wt',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['train','chunk','aggregate']);p.add_argument('--index',type=int,default=0);a=p.parse_args();t=time.time();OUT.mkdir(exist_ok=True)
    if a.phase=='train':
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(job,[('train',s,None,'normal') for s in range(100,300)],chunksize=10))
        goals=make_goals(rows);goals['training_seeds']=[100,299]
        (OUT/'goals_candidate.json').write_text(json.dumps(goals,indent=2))
        save_rows(OUT/'train.jsonl.gz',[apply(r,goals) for r in rows]);print(goals)
    elif a.phase=='chunk':
        assert 0<=a.index<6
        jobs=tasks()[a.index*800:(a.index+1)*800];goals=json.loads((OUT/'goals_candidate.json').read_text())
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(job,jobs,chunksize=10))
        for r in rows:
            if 'evaluated_progress' in r['countries'][NAMES[0]]:apply(r,goals)
        save_rows(OUT/f'chunk_{a.index}.jsonl.gz',rows)
        print('completed chunk',a.index,len(rows),'games')
    else:
        paths=[OUT/'train.jsonl.gz']+[OUT/f'chunk_{i}.jsonl.gz' for i in range(6)]
        rows=[]
        for f in paths:
            with gzip.open(f,'rt') as z:rows.extend(json.loads(line) for line in z)
        assert len(rows)==5000
        keys=[(r['variant'],r['seed'],r['focal'],r['style']) for r in rows]
        assert len(set(keys))==5000
        save_rows(OUT/'runs.jsonl.gz',rows)
        groups=defaultdict(list)
        for r in rows:groups[(r['variant'],r['focal'],r['style'])].append(r)
        goals=json.loads((OUT/'goals_candidate.json').read_text())
        summary={'metadata':{'n_training':200,'n_validation':4800,'n_total':5000,'main_repetitions':300,'stress_repetitions':60,'validation_seeds':[2000,2299],'pilot_seeds':[0,29],
          'engine_sha256':hashlib.sha256((ROOT/'engine.py').read_bytes()).hexdigest(),'reference_sha256':hashlib.sha256((ROOT/'reference_engine.py').read_bytes()).hexdigest(),'goals':goals,
          'variants':{n:dataclasses.asdict(o) for n,(_,o) in VARIANTS.items()}},
          'experiments':{':'.join(str(x) for x in k):aggregate(rs) for k,rs in groups.items()}}
        mets=['world.listed','world.inventory','world.trade_units','world.barter','world.counter_accepted','world.electronics_expansions']
        mets += [f'countries.{n}.{k}' for n in NAMES for k in ('cash','happy','score','trade','upgrades','electronics_expanded')]
        changes={}
        for va,vb in [('previous_supply','core_only'),('core_only','budget_only'),('budget_only','revised'),('previous_supply','revised'),('revised','research_discount')]:changes[va+'->'+vb]=paired(groups[(va,None,'normal')],groups[(vb,None,'normal')],mets)
        for v in ('previous_supply','revised'):
            for n in NAMES:
                for st in ('cheap','idle','invest','trade'):changes[v+':'+n+':'+st]=paired(groups[(v,None,'normal')],groups[(v,n,st)],mets)
        summary['paired']=changes
        (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
        for focal in (None,'Technia'):
            g=Game(2000,VARIANTS['revised'][1],focal=focal,style='idle' if focal else 'normal');result=g.run()
            trace={'result':result,'rounds':g.round_history,'transactions':g.transactions,'needs':g.needs_ledger,'launches':g.launch_events,
             'upgrades':{n:g.cs[n].upgrade_rounds for n in NAMES},'units':[dataclasses.asdict(u) for u in g.units.values()]}
            (OUT/f'trace_2000_{focal or "normal"}.json').write_text(json.dumps(trace,indent=2))
        print('all 5000 unique games verified, aggregated, written')
    elapsed=round(time.time()-t,3);print('elapsed',elapsed)
    with (OUT/'staged_log.jsonl').open('a') as f:f.write(json.dumps({'phase':a.phase,'index':a.index if a.phase=='chunk' else None,'elapsed_seconds':elapsed})+'\n')
if __name__=='__main__':main()
