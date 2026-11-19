"""Exploratory v11 comparisons; seeds and counts excluded from formal evidence."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import statistics
import time
from evaluation_engine import Game, SCORING_MODES
from reference_engine import NAMES

ROOT=Path(__file__).resolve().parent


def run(task):
    seed,focal,style,overrides=task
    game=Game(seed,focal=focal,style=style,behaviors=overrides)
    result=game.run()
    return {'seed':seed,'focal':focal,'style':style,'behaviors':overrides or {},**result}


def main():
    scenarios=[(None,'normal',None)]+[(n,s,None) for n in NAMES for s in ('cheap','minimum','idle','minimum_passive')]
    scenarios += [('Technia','minimum',{'Mechania':'idle'}),('Novia','minimum',{'Mechania':'idle'})]
    tasks=[(seed,n,s,b) for n,s,b in scenarios for seed in range(74000,74010)]
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(run,tasks))
    result={'exploratory_only':True,'formal_games_included':0,'seed_range':[74000,74009],
            'completed_games':len(rows),'elapsed_seconds':time.monotonic()-started,'runs':rows}
    out=ROOT/'evaluation_results';out.mkdir(exist_ok=True)
    (out/'pilot.json').write_text(json.dumps(result,ensure_ascii=False))
    normal={r['seed']:r for r in rows if r['focal'] is None}
    for name in NAMES:
        for style in ('cheap','minimum','idle','minimum_passive'):
            selected=[r for r in rows if r['focal']==name and r['style']==style and not r['behaviors']]
            x={k:statistics.mean(r['countries'][name][k] for r in selected)
               for k in ('cash','revenue','purchases','investment','happy','trade','score','useful_exports')}
            x['score_deltas']={m:statistics.mean(r['countries'][name]['evaluation']['scores'][m]['score']-
                       normal[r['seed']]['countries'][name]['evaluation']['scores'][m]['score'] for r in selected)
                       for m in SCORING_MODES}
            x['machine_ready_unfulfilled']=statistics.mean(r['countries'][name]['evaluation']['ready_unfulfilled'] for r in selected)
            print(name,style,json.dumps(x),flush=True)
    print('DONE',len(rows),round(result['elapsed_seconds'],2),flush=True)


if __name__=='__main__':main()
