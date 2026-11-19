"""Exploratory policy check only. Never pooled into held-out comparisons."""
from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
from pathlib import Path
import statistics, json, time
from budget_trace import Game
from budget_engine import POLICIES


def one(args):
    variant, seed = args
    g = Game(seed, variant)
    return {'variant':variant,'seed':seed,**g.run()}


def main():
    tic = time.monotonic()
    tasks = [(v,s) for v in POLICIES for s in range(18000,18030)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one,tasks,chunksize=3))
    out = Path(__file__).resolve().parent/'budget_results'
    out.mkdir(exist_ok=True)
    (out/'pilot.json').write_text(json.dumps(rows,ensure_ascii=False))
    for v in POLICIES:
        rs = [x for x in rows if x['variant']==v]
        def avg(n,k):return round(statistics.mean(x['countries'][n][k] for x in rs),3)
        print(v, 'Mech', {k:avg('Mechania',k) for k in ('cash','happy','investment','revenue','purchases','production_failures','uncovered_investments','machine_gen','useful_exports')}, flush=True)
        print('others',{n:{k:avg(n,k) for k in ('cash','happy','useful_exports')} for n in ('Mineria','Technia','Tropia')},flush=True)
        print('world', {k:round(statistics.mean(x['world'][k] for x in rs),3) for k in ('original_happy','listed','original_useful_exports','trade_units','uncovered_investments')}, flush=True)
    print('Pilot games',len(rows),'seconds',round(time.monotonic()-tic,2),flush=True)


if __name__=='__main__':main()
