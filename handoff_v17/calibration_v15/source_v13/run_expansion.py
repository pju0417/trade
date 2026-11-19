"""Reproduce the modest 6 -> 9 expansion. Standard library Python only.
Holdout seeds fixed before results: normal 10000+, stress 12000+.
Pilot/debug seeds 8000+; no parameters selected by holdout wins.
"""
import argparse,concurrent.futures,gzip,hashlib,json,math,statistics,time
from pathlib import Path
from collections import defaultdict
from expansion_engine import Game,NAMES,ADDITIONS,BASE_OPTIONS,COMBINATIONS
from dataclasses import asdict
ROOT=Path(__file__).resolve().parent
CONDITIONS={'legacy6':('six',False),'fixed6':('six',True),
            'clone9':('clones',True),'role9':('roles',True)}

def task(t):
    condition,seed,focal,style=t
    scenario,fixes=CONDITIONS[condition]
    g=Game(seed,scenario,focal=focal,style=style if style!='no_trade' else 'normal',
           fixes=fixes,trade_enabled=style!='no_trade')
    r=g.run()
    return {'condition':condition,'seed':seed,'focal':focal,'style':style,**r}

def flatten(x,prefix=''):
    out={}
    for k,v in x.items():
        key=f'{prefix}.{k}' if prefix else k
        if isinstance(v,dict):out.update(flatten(v,key))
        elif type(v) in (int,float):out[key]=v
    return out

def stat(vals):
    m=statistics.mean(vals);se=statistics.stdev(vals)/math.sqrt(len(vals)) if len(vals)>1 else 0
    return {'mean':m,'ci95':[m-1.96*se,m+1.96*se],'min':min(vals),'max':max(vals)}

def aggregate(rows):
    flats=[flatten({'countries':x['countries'],'world':x['world']}) for x in rows]
    keys=set().union(*(v.keys() for v in flats))
    out={'n':len(rows),'metrics':{k:stat([v.get(k,0) for v in flats]) for k in sorted(keys)}}
    wins={n:0 for n in NAMES}
    for row in rows:
        best=max(row['countries'][n]['score'] for n in NAMES)
        tied=[n for n in NAMES if abs(row['countries'][n]['score']-best)<1e-8]
        for n in tied:wins[n]+=100/len(rows)/len(tied)
    out['diagnostic_top_original_six_pct']=wins
    out['no_barter_pct']=100*sum(r['world']['barter']==0 for r in rows)/len(rows)
    out['score_warning']='Original six only, unchanged tentative goals; not 9-country win probability.'
    return out

def paired(rowsA,rowsB):
    a={r['seed']:flatten(r) for r in rowsA};b={r['seed']:flatten(r) for r in rowsB}
    seeds=sorted(a.keys()&b.keys());keys=set().union(*(a[s].keys()&b[s].keys() for s in seeds))
    return {k:stat([b[s].get(k,0)-a[s].get(k,0) for s in seeds]) for k in sorted(keys) if k.startswith(('world.','countries.'))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--n',type=int,default=200)
    p.add_argument('--stress-n',type=int,default=30);p.add_argument('--workers',type=int,default=4)
    args=p.parse_args()
    if args.n<20 or args.n%20:p.error('n must be a positive multiple of 20 for clone balance')
    if args.stress_n<1:p.error('stress-n must be positive')
    out=ROOT/'results';out.mkdir(exist_ok=True)
    tasks=[(v,s,None,'normal') for v in CONDITIONS for s in range(10000,10000+args.n)]
    tasks += [(v,s,n,style) for v in ('fixed6','role9') for n in NAMES for style in ('cheap','idle')
              for s in range(12000,12000+args.stress_n)]
    tasks += [(v,s,None,style) for v in ('fixed6','role9') for style in ('normal','no_trade')
              for s in range(12000,12000+args.stress_n)]
    tic=time.monotonic();rows=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as ex, gzip.open(out/'runs.jsonl.gz','wt') as f:
        for i,r in enumerate(ex.map(task,tasks,chunksize=8),1):
            rows.append(r);f.write(json.dumps(r,ensure_ascii=False)+'\n')
            if i%200==0:print(f'{i}/{len(tasks)} finished, {time.monotonic()-tic:.1f}s',flush=True)
    assert len(rows)==len(tasks)==len(set((r['condition'],r['seed'],r['focal'],r['style']) for r in rows))
    groups=defaultdict(list)
    for r in rows:
        phase='normal' if r['seed']<12000 else 'stress'
        groups[(phase,r['condition'],r['focal'],r['style'])].append(r)
    agg={':'.join(str(x) for x in k):aggregate(v) for k,v in groups.items()}
    pairs={}
    for va,vb in [('legacy6','fixed6'),('fixed6','clone9'),('fixed6','role9'),('clone9','role9')]:
        pairs[va+'->'+vb]=paired(groups[('normal',va,None,'normal')],groups[('normal',vb,None,'normal')])
    for v in ('fixed6','role9'):
        controls=groups[('stress',v,None,'normal')]
        for focal in NAMES:
            for style in ('cheap','idle'):
                rs=groups[('stress',v,focal,style)]
                # Compare harm to the OTHER five original countries, not additional
                # AI countries diluting the reported harm merely by denominator.
                for row in rs+controls:
                    row['world']['other_original_happy']=statistics.mean(row['countries'][n]['happy'] for n in NAMES if n!=focal)
                pairs[f'{v}:{focal}:{style}']=paired(controls,rs)
        pairs[v+':no_trade']=paired(controls,groups[('stress',v,None,'no_trade')])
    meta={'primary_games':len(rows),'main_games':4*args.n,'stress_games':len(rows)-4*args.n,
      'main_seed_range':[10000,10000+args.n-1],'stress_seed_range':[12000,12000+args.stress_n-1],
      'rounds':9,'options':asdict(BASE_OPTIONS),'new_country_parameters':ADDITIONS,
      'clone_combinations':COMBINATIONS,'verification_calls':sum(r['world']['verify_calls'] for r in rows),
      'verification_failures':0,'elapsed_seconds':time.monotonic()-tic,
      'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')},
      'upstream_zip_sha256':json.loads((ROOT/'UPSTREAM_PROVENANCE.json').read_text())['sha256'],
      'new_countries_no_score_targets':True,'no_web_or_generative_api':True}
    (out/'summary.json').write_text(json.dumps({'metadata':meta,'experiments':agg,'paired':pairs},ensure_ascii=False,indent=2))
    (out/'run_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    print('DONE',len(rows),round(time.monotonic()-tic,1),'seconds',flush=True)
    for v in CONDITIONS:
        m=agg[f'normal:{v}:None:normal']['metrics']
        print(v,{k:round(m['world.'+k]['mean'],3) for k in ['trade_units','trade_units_per_country','original_happy','original_useful_exports','original_coverage','aged_unused_per_country','listed']},flush=True)
if __name__=='__main__':main()
