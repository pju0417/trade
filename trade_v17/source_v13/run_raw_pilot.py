"""Exploratory seeds only; never counted as frozen formal validation."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import hashlib
from dataclasses import asdict

from raw_engine import Game, RAW_MODES
from run_recommendation_validation import normalize_and_validate, grouped


def one(task):
    mode,seed = task
    g = Game(seed=seed,variant=mode)
    result = normalize_and_validate(g.run())
    return {'mode':mode,'seed':seed,**result}


def main():
    root = Path(__file__).resolve().parent
    tasks = [(m,s) for m in RAW_MODES for s in range(52000,52030)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one,tasks))
    output = {'exploratory':True,'excluded_from_formal':True,'games':len(rows),
              'seeds':[52000,52029], 'policies':{m:asdict(p) for m,p in RAW_MODES.items()},
              'source_sha256':hashlib.sha256((root/'raw_engine.py').read_bytes()).hexdigest(),
              'groups':{m:grouped([r for r in rows if r['mode']==m]) for m in RAW_MODES}}
    (root/'raw_results'/'pilot.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    for mode,group in output['groups'].items():
        keys=['world.happy','world.inventory','world.trade_units','world.all_country_cash_gap',
              'world.first_two_happy','world.first_two_food_short','world.first_two_production_failures',
              'world.raw_use.ore.imported_used','world.raw_use.fuel.imported_used',
              'countries.Mechania.raw_importing.ore','countries.Mechania.machine_g2']
        print(json.dumps({'mode':mode,**{k:round(group['metrics'][k]['mean'],4) for k in keys}},ensure_ascii=False))


if __name__=='__main__':main()
