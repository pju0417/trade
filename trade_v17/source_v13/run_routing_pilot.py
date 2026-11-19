"""Exploratory v10 pilot, excluded from all formal validation counts."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import json,statistics,time
from routing_engine import Game,MODES

ROOT=Path(__file__).resolve().parent

def one(task):
    mode,style,seed=task
    g=Game(seed,mode,focal='Mechania' if style=='idle' else None,style=style)
    return {'mode':mode,'style':style,'seed':seed,**g.run()}

def main():
    tasks=[(m,st,s) for m in MODES for st in ('normal','idle') for s in range(64000,64030)]
    start=time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,tasks,chunksize=2))
    means={}
    for m in MODES:
        for st in ('normal','idle'):
            rs=[r for r in rows if r['mode']==m and r['style']==st]
            out={k:statistics.mean(r['world'][k] for r in rs) for k in ('happy','inventory','trade_units','all_country_cash_gap')}
            out.update({k:statistics.mean(r['world']['routing'][k] for r in rs) for k in ('routes_started','routes_completed','routes_with_used_goal_output','intermediate_spend','unfinished_intermediate_spend','both_electronics_used')})
            out.update({k:statistics.mean(r['world']['development'][k] for r in rs) for k in ('bought_high_machines','foreign_machine_upgrades','g3_electronics_output','g3_electronics_used')})
            for n in ('Mechania','Technia','Novia'):
                out[n]={k:statistics.mean(r['countries'][n][k] for r in rs) for k in ('cash','investment','happy','electronics_g3')}
                out[n].update({k:statistics.mean(r['countries'][n]['routing'][k] for r in rs) for k in ('g3_electronics_used','routes_completed','routes_unfinished','intermediate_spend')})
            means[f'{m}:{st}']=out;print(m,st,json.dumps(out),flush=True)
    out=ROOT/'routing_results';out.mkdir(exist_ok=True)
    (out/'pilot.json').write_text(json.dumps({'note':'Exploratory repeated-seed pilot, not formal outcomes','runs':rows,'means':means,'seconds':time.monotonic()-start},ensure_ascii=False,indent=2)+'\n')
    print('DONE',len(rows),round(time.monotonic()-start,2),flush=True)

if __name__=='__main__':main()
