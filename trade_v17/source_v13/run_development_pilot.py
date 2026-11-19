"""Exploratory pilot only; seeds58000..58029 never enter formal statistics."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json, statistics, time
from development_engine import Game, MODES

OUT = Path(__file__).resolve().parent/'development_results'


def run(task):
    mode, seed = task
    game = Game(seed, variant=mode)
    result = game.run()
    return {'mode': mode, 'seed': seed, 'result': result}


def avg(rows, path):
    values=[]
    for row in rows:
        x=row['result']
        for key in path.split('.'):
            x=x[key]
        if x is not None: values.append(x)
    return statistics.mean(values) if values else None


def main():
    OUT.mkdir(exist_ok=True)
    tasks=[(mode, seed) for mode in MODES for seed in range(58000,58030)]
    start=time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(run,tasks,chunksize=2))
    summaries={}
    for mode in MODES:
        selected=[r for r in rows if r['mode']==mode]
        keys=['world.happy','world.inventory','world.aged_unused','world.all_country_cash_gap',
              'world.development.bought_high_machines','world.development.foreign_machine_upgrades',
              'world.development.foreign_machine_used_output_upgrades',
              'world.development.high_machine_produced','world.development.high_machine_unused_stock',
              'world.development.g3_electronics_output','world.development.g3_electronics_used']
        for n in rows[0]['result']['countries']:
            keys += [f'countries.{n}.{k}' for k in ('cash','happy','investment','score','electronics_g3','production_failures')]
        summaries[mode]={key:avg(selected,key) for key in keys}
        print(mode,json.dumps(summaries[mode],ensure_ascii=False),flush=True)
    out={'note':'Exploratory, excludes four smoke games and ten audit diagnostic games reusing these seeds; not formal evidence',
         'seeds':list(range(58000,58030)),'runs':rows,'means':summaries,'seconds':time.monotonic()-start}
    (OUT/'pilot.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print('pilot completed',len(rows),round(out['seconds'],2),flush=True)


if __name__=='__main__':main()
