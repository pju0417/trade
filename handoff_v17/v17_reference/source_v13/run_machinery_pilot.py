"""Exploratory 32000-range seeds only. Not included in held-out results."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json,statistics,time
from machinery_engine import Game,MODES


def one(task):
    mode,seed=task
    g=Game(seed,mode)
    return {'mode':mode,'seed':seed,**g.run()}


def main():
    tic=time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(one,[(v,s) for v in MODES for s in range(32000,32030)],chunksize=3))
    out=Path(__file__).resolve().parent/'machinery_results';out.mkdir(exist_ok=True)
    (out/'pilot.json').write_text(json.dumps(rows,ensure_ascii=False))
    for mode in MODES:
        rs=[r for r in rows if r['mode']==mode]
        def avg(n,k):return round(statistics.mean(r['countries'][n][k] for r in rs),3)
        print(mode,{n:{k:avg(n,k) for k in ('cash','happy','useful_exports','investment','machine_gen')} for n in ('Mechania','Mineria','Novia','Technia')},flush=True)
        print('world',{k:round(statistics.mean(r['world'][k] for r in rs),3) for k in ('happy','trade_units','listed','machine_unique_used','machine_missing_episodes','all_country_cash_gap','machine_upkeep_ore','upkeep_blocked','uncovered_investments')},flush=True)
        for field in ('produced','production_raw','export_used_by_good','end_stock_by_good'):
            print('Mech',field,{good:round(statistics.mean(r['countries']['Mechania'][field].get(good,0) for r in rs),3) for good in ('machine','ore','wheat')},flush=True)
    print('Pilot games',len(rows),'seconds',round(time.monotonic()-tic,2),flush=True)


if __name__=='__main__':main()
