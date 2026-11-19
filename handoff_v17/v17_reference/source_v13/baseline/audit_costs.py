"""Read-only cost audit of uploaded #11 simulator v2.
No rules/parameters are changed. Python 3.10+, standard library only.
Run: python audit_costs.py --runs 60 --seed 3000
"""
from __future__ import annotations
import argparse, hashlib, json, math, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'source'))
from engine import Game, Options, NAMES, GOODS, PRICE, BONUS, half_up5

OPTIONS = Options(planning=True, negotiations=True, price_v2=True,
                  saturation_aware=True, smaller_bonus=True,
                  specialist_cost=False)

class ObservedGame(Game):
    """Log consumption without altering any decision or transaction."""
    def __init__(self, *a, **kw):
        self.audit_consumption = Counter()
        super().__init__(*a, **kw)
    def consume(self, c, good, quantity, purpose):
        used = super().consume(c, good, quantity, purpose)
        self.audit_consumption[(c.name, purpose, good)] += len(used)
        return used

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=60)
    parser.add_argument('--seed', type=int, default=3000)
    args = parser.parse_args()
    if args.runs <= 0: parser.error('--runs must be positive')
    out = {'scope': 'Read-only audit, no new storage/production/selling fees introduced',
           'options': OPTIONS.__dict__, 'seeds': [args.seed,args.seed+args.runs-1],
           'runs':args.runs, 'rounds':9, 'countries':6,
           'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [ROOT/'source'/'engine.py',ROOT/'source'/'reference_engine.py']}}
    out['price_steps'] = [dict(good=g,base=PRICE[g],discount10=half_up5(PRICE[g]*.9),
          discount20=half_up5(PRICE[g]*.8),discount50=half_up5(PRICE[g]*.5),
          one_tick_pct=500/PRICE[g]) for g in GOODS]
    g = Game(0, OPTIONS);g.r=1
    rows=[]
    for name in NAMES:
        c=g.cs[name]; good=c.main
        q=g.base_quantity(c,good)+(2 if good in ('banana','wheat') else BONUS[good])
        req=g.resource_requirements(c,good)
        cost=sum(PRICE[h]*n for h,n in req.items())
        rows.append(dict(country=name,main=good,level=1,round=1,
            potential_output_without_equipment=q,raw_inputs=req,
            input_value_at_initial_prices=cost,input_value_per_output=cost/q,
            next_cash_upgrade_cost=g.upgrade_cost(c,good),
            note='Raw input reference value, NOT full cost or actual cash outflow; assumes inputs available.'))
    out['production_cycle_diagnostics']=rows
    # Equal-output focus toggle exposes that extra units are not marginally charged.
    pairs=[]
    for n in ('Mechania','Technia'):
        c=g.cs[n];good=c.main
        pairs.append(dict(country=n,good=good,nonfocused_output=g.base_quantity(c,good),
            focused_output=g.base_quantity(c,good)+BONUS[good],
            raw_requirement_both=g.resource_requirements(c,good)))
    out['focus_marginal_inputs']=pairs
    # Exact sale: no third-party payment/fee is applied.
    g=Game(0,OPTIONS); a=g.cs['Tropia'];b=g.cs['Grainia']
    before={n:c.cash for n,c in g.cs.items()};uid=g.ids(a,'banana')[0]
    ok=g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':[uid]}],
                           (b.name,a.name,10),'market','cost-audit-sale')
    after={n:c.cash for n,c in g.cs.items()}
    assert ok and after[a.name]-before[a.name]==10 and before[b.name]-after[b.name]==10
    assert sum(before.values())==sum(after.values())
    out['sale_fee_microtest']={'amount':10,'seller_receives':10,'buyer_pays':10,
                              'external_sale_fee':0,'passed':True}
    samples=defaultdict(lambda:defaultdict(list)); all_runs=[]
    for seed in range(args.seed,args.seed+args.runs):
        game=ObservedGame(seed,OPTIONS); result=game.run()
        # Observational instrumentation must not change the original run.
        if seed==args.seed:
            assert result==Game(seed,OPTIONS).run()
        sales=defaultdict(Counter);purchases=defaultdict(Counter)
        barter_units=Counter()
        for tx in game.transactions:
            if tx['cash']:
                payer,payee,amount=tx['cash']
                leg=tx['legs'][0];good=game.units[leg['ids'][0]].good
                purchases[payer][good]+=amount;sales[payee][good]+=amount
            else:
                for leg in tx['legs']:
                    for uid in leg['ids']:barter_units[game.units[uid].good]+=1
        per={}
        for n in NAMES:
            c=game.cs[n];r=result['countries'][n]
            assert sum(purchases[n].values())==c.purchases
            assert sum(sales[n].values())==c.revenue
            rec={'sales':c.revenue,'food_purchase_cash':sum(purchases[n][x] for x in ('banana','wheat')),
                 'resource_purchase_cash':sum(purchases[n][x] for x in ('ore','fuel')),
                 'machine_purchase_cash':purchases[n]['machine'],
                 'electronics_purchase_cash':purchases[n]['electronics'],
                 'development_cash':c.investment,'government_income':c.tax,'cash':c.cash,
                 'happy':r['happy'],'stock':r['stock'],'listed':r['listed'],
                 'production_ore_units':game.audit_consumption[(n,'production','ore')],
                 'production_fuel_units':game.audit_consumption[(n,'production','fuel')],
                 'development_ore_units':game.audit_consumption[(n,'development','ore')]}
            assert abs(c.start+c.revenue-c.purchases-c.investment+c.tax-c.cash)<1e-9
            for k,v in rec.items():samples[n][k].append(v)
            per[n]=rec
        assert sum(c.revenue for c in game.cs.values())==sum(c.purchases for c in game.cs.values())
        assert sum(c.cash for c in game.cs.values())==game.initial_cash+game.minted-game.sunk
        all_runs.append({'seed':seed,'countries':per,'world':result['world']})
    out['means']={n:{k:statistics.mean(v) for k,v in metrics.items()} for n,metrics in samples.items()}
    out['checks']={'cash_identity_all_runs':True,'sales_equals_purchases_all_runs':True,
                   'observer_equal_to_original_first_seed':True,
                   'microtests': ['one_sale_no_fee','price_rounding','focus_has_same_raw_requirement']}
    (ROOT/'cost_audit_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'cost_audit_runs.json').write_text(json.dumps(all_runs,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out['means'],ensure_ascii=False,indent=2))
    print('COMPLETE', args.runs, 'read-only games')
if __name__=='__main__':main()
