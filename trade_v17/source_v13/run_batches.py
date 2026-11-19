"""Short, restart-safe batches for execution environments with command timeouts.
python run_batches.py --batch 0  # 0 through 8, each writes a closed checkpoint
python run_batches.py --summary
"""
import argparse,concurrent.futures,gzip,hashlib,json,time,statistics
from pathlib import Path
from collections import defaultdict
from dataclasses import asdict
from run_expansion import task,aggregate,paired,CONDITIONS
from expansion_engine import NAMES,ADDITIONS,BASE_OPTIONS,COMBINATIONS
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results';OUT.mkdir(exist_ok=True)

def all_tasks():
    tasks=[(v,s,None,'normal') for v in CONDITIONS for s in range(10000,10200)]
    tasks += [(v,s,n,style) for v in ('fixed6','role9') for n in NAMES for style in ('cheap','idle') for s in range(12000,12030)]
    tasks += [(v,s,None,style) for v in ('fixed6','role9') for style in ('normal','no_trade') for s in range(12000,12030)]
    return tasks

def run_batch(i):
    tasks=all_tasks()[i*200:(i+1)*200]
    if not tasks:raise ValueError('batch must be 0..8')
    tic=time.monotonic();temp=OUT/f'batch_{i:02}.tmp.gz';final=OUT/f'batch_{i:02}.jsonl.gz'
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as ex,gzip.open(temp,'wt') as f:
        for row in ex.map(task,tasks,chunksize=4):f.write(json.dumps(row,ensure_ascii=False)+'\n')
    temp.replace(final)
    print('Completed batch',i,'games',len(tasks),'seconds',round(time.monotonic()-tic,2),flush=True)

def summarize():
    rows=[]
    for i in range(9):
        with gzip.open(OUT/f'batch_{i:02}.jsonl.gz','rt') as f:rows.extend(json.loads(line) for line in f)
    assert len(rows)==1640
    assert len({(r['condition'],r['seed'],r['focal'],r['style']) for r in rows})==1640
    groups=defaultdict(list)
    for r in rows:groups[('normal' if r['seed']<12000 else 'stress',r['condition'],r['focal'],r['style'])].append(r)
    aggregates={':'.join(str(x) for x in k):aggregate(v) for k,v in groups.items()}
    print('Aggregated',len(groups),'groups',flush=True)
    pairs={}
    for a,b in [('legacy6','fixed6'),('fixed6','clone9'),('fixed6','role9'),('clone9','role9')]:
        pairs[a+'->'+b]=paired(groups[('normal',a,None,'normal')],groups[('normal',b,None,'normal')])
    for v in ('fixed6','role9'):
        ctr=groups[('stress',v,None,'normal')]
        for n in NAMES:
            for style in ('cheap','idle'):
                rs=groups[('stress',v,n,style)]
                for row in rs+ctr:row['world']['other_original_happy']=statistics.mean(row['countries'][k]['happy'] for k in NAMES if k!=n)
                pairs[f'{v}:{n}:{style}']=paired(ctr,rs)
        pairs[f'{v}:no_trade']=paired(ctr,groups[('stress',v,None,'no_trade')])
    meta={'primary_games':1640,'main_games':800,'stress_and_controls':840,
          'main_seed_range':[10000,10199],'stress_seed_range':[12000,12029],
          'rounds':9,'options':asdict(BASE_OPTIONS),'new_country_parameters':ADDITIONS,
          'clone_combinations':COMBINATIONS,
          'verification_calls':sum(r['world']['verify_calls'] for r in rows),'verification_failures':0,
          'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')},
          'upstream_zip_sha256':json.loads((ROOT/'UPSTREAM_PROVENANCE.json').read_text())['sha256'],
          'new_countries_no_score_targets':True,'new_scores_note':'Original six only; unchanged diagnostic goals.',
          'excluded':'Pilot runs, regression tests, trace reruns, and interrupted uncheckpointed executions are not in 1640.',
          'checkpoints':[f'batch_{i:02}.jsonl.gz' for i in range(9)]}
    (OUT/'summary.json').write_text(json.dumps({'metadata':meta,'experiments':aggregates,'paired':pairs},ensure_ascii=False,indent=2))
    (OUT/'run_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    print('Completed verified total:',1640,flush=True)
    for v in CONDITIONS:
        m=aggregates[f'normal:{v}:None:normal']['metrics']
        print(v,{k:round(m['world.'+k]['mean'],3) for k in ['trade_units','trade_units_per_country','original_happy','original_useful_exports','original_coverage','aged_unused_per_country','listed']},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',type=int);p.add_argument('--summary',action='store_true');a=p.parse_args()
    if a.summary:summarize()
    elif a.batch is not None:run_batch(a.batch)
    else:p.error('choose --batch 0..8 or --summary')
