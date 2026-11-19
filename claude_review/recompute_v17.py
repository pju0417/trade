"""Claude independent recomputation of v17 stored results.
Does NOT import engine/scoring/analyzer code. Streams validation_runs.jsonl.gz once,
writes compact per-game rows to claude_review/games_compact.json.gz for later stats.
"""
import gzip, json, math, sys, statistics as st
from pathlib import Path
from collections import defaultdict, Counter
ROOT=Path(sys.argv[1]); OUT=Path(sys.argv[2])
G=json.loads((ROOT/'SCORE_TARGETS_V15.json').read_text())
EG=G['economic_old']; IG=G['industrial_steps']; NAMES=G['names']
clip=lambda x:min(1,max(0,x))
rows=[]; bad=Counter(); n=0
with gzip.open(ROOT/'operating_results/validation_runs.jsonl.gz','rt',encoding='utf-8') as f:
    for line in f:
        r=json.loads(line); n+=1; w=r['world']
        # cash conservation (world): sum cash = initial cash + minted tax - investment sunk
        cash=sum(c['cash'] for c in r['countries'].values())
        tax=sum(c['tax'] for c in r['countries'].values()); inv=sum(c['investment'] for c in r['countries'].values())
        start=sum(c['start_cash'] for c in r['countries'].values())
        if cash!=start+tax-inv: bad['cash_conservation']+=1
        if any(c['cash']<0 for c in r['countries'].values()): bad['neg_cash']+=1
        no=w['national_operation']
        for g in ('ore','fuel'):
            if no['required'][g]!=no['consumed'][g]+no['missing'][g]: bad['op_balance']+=1
        sc={}
        for nm in NAMES:
            c=r['countries'][nm]; m=c['growth_metrics']; fe=c['fixed_evaluation']
            # recompute from raw end-state fields (not from fe)
            asset_gain=c['end_asset_value']-c['start_asset_value']
            reserve_t=m['reserve_target']
            parts={'econ':20*clip(asset_gain/EG[nm]),'reserve':5*clip(c['cash']/reserve_t),
                   'cap':15*clip(c['capacity_growth']/IG[nm]),
                   'util':10*c['all_goods_unique_used']/max(1,sum(c['produced'].values())),
                   'well':c['happy']/4,'trade':c['trade']}
            s=sum(parts.values())
            if abs(s-fe['score'])>1e-6: bad['fixed_score_mismatch']+=1
            if abs(c['score']-fe['score'])<1e-9: bad['legacy_equals_fixed']+=1
            sc[nm]={'s':s,'legacy':c['score'],**{k:round(v,4) for k,v in parts.items()},
                    'cash':c['cash'],'inv':c['investment'],'happy':c['happy'],
                    'op_short':c['national_operation']['any_shortage_rounds'],
                    'food_short':c['food_short_rounds'],'imports':c['imports'],'exports':c['exports'],
                    'useful_imports':c['useful_imports'],'tax':c['tax'],'asset_gain':asset_gain,
                    'cap_growth':c['capacity_growth'],'used':c['all_goods_unique_used'],
                    'produced':sum(c['produced'].values())}
        extra={nm:{'cash':c['cash'],'happy':c['happy'],'op_short':c['national_operation']['any_shortage_rounds']}
               for nm,c in r['countries'].items() if nm not in NAMES}
        rem=w['remaining_goods']
        rows.append({'phase':r['phase'],'mode':r['mode'],'prof':r['operating_profile'],'style':r['style'],
            'focal':r['focal'],'seed':r['seed'],'sc':sc,'extra':extra,
            'ore_end':rem.get('ore',0),'fuel_end':rem.get('fuel',0),
            'op_cons':no['consumed'],'op_req':no['required'],'op_short_sum':no['any_shortage_rounds'],
            'trade_goods':w['trade_goods'],'produced':w.get('production'),'transactions':w['transactions'],
            'barter':w['barter']})
print('games',n,'issues',dict(bad))
with gzip.open(OUT,'wt',encoding='utf-8') as f: json.dump(rows,f)
