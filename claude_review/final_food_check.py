"""Direct food-shortage check for V1 of final_validation.py (Claude, 2026-11-19).
final_validation.py judged V1 food shortages through a satisfaction proxy (>= 75), which cannot
rule out partial food shortages. This re-runs the same 100 all-AI normal games (final economy,
seeds 130000-130099) and reads food_short_rounds directly. Criterion unchanged: no food-shortage
rounds for the six original countries."""
import json, os, sys
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sim_lib as L

def f(seed):
    g = L.make_game(seed, fee=1.0, l3_flat=True)
    r = L.R.normalize_extended(g.run())
    return {n: r['countries'][n]['food_short_rounds'] for n in L.NAMES}

if __name__ == '__main__':
    with Pool(2) as p:
        rows = p.map(f, range(130000, 130100))
    total = {n: sum(r[n] for r in rows) for n in L.NAMES}
    res = {'games': len(rows), 'food_short_rounds_total': total, 'pass': all(v == 0 for v in total.values())}
    json.dump(res, open(os.path.join(HERE, 'new_games', 'final_food_check.json'), 'w'), indent=1)
    print(res)
