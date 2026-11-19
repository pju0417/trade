"""Read-only instrumentation of v4/v5 decisions, cash and physical use.

No decision plans, state mutations or random draws are invoked by instrumentation. Per-country
round ledgers are reconciled against authoritative nation totals.
"""
from __future__ import annotations
from collections import Counter
from budget_engine import Game as BudgetGame
from reference_engine import GOODS, DURABLES


class Game(BudgetGame):
    def __init__(self,*args,**kwargs):
        self.cash_ledger = []
        self.production_trace = []
        self.investment_trace = []
        self.last_cash_state = {}
        self.phase_min_cash = {}
        self.last_transaction = 0
        super().__init__(*args,**kwargs)
        self.last_cash_state = {n:self._money(c) for n,c in self.cs.items()}
        self.phase_min_cash = {n:c.cash for n,c in self.cs.items()}

    @staticmethod
    def _money(c):
        return {k:getattr(c,k) for k in ('cash','revenue','purchases','investment','tax')}

    def _observe_cash(self):
        for n,c in self.cs.items():
            if n in self.phase_min_cash:
                self.phase_min_cash[n] = min(self.phase_min_cash[n],c.cash)

    def settle_transaction(self,*args,**kwargs):
        result = super().settle_transaction(*args,**kwargs)
        self._observe_cash()
        return result

    def production(self):
        if self.r in self.produced_rounds:
            return super().production()
        for n,c in self.cs.items():
            free = Counter({g:self.count(c,g) for g in GOODS})
            for good in c.levels:
                req = self.resource_requirements(c,good)
                enough = all(free[g]>=q for g,q in req.items())
                self.production_trace.append({'round':self.r,'country':n,'industry':good,
                    'level':c.levels[good],'tech':self.tech_for(c,good),'required':dict(req),
                    'available_before':dict(free),'funded':enough,
                    'following_input_deferral':(self.r-1,n,good) in self.input_deferrals})
                if enough:
                    free.subtract(req)
        return super().production()

    def invest(self,c,action_id=None):
        before = c.investment
        result = super().invest(c,action_id)
        if c.investment > before:
            r,good,level = c.upgrade_rounds[-1]
            post = self.projected_resources(c)
            self.investment_trace.append({'round':r,'country':c.name,'industry':good,
                'new_level':level,'cash_cost':c.investment-before,
                'post_next_resources':dict(post),
                'post_free_raw':{g:self.count(c,g) for g in ('ore','fuel')},
                'next_cycle_covered':all(self.count(c,g)>=q for g,q in post.items())})
        self._observe_cash()
        return result

    def update_prices(self):
        result = super().update_prices()
        transactions = self.transactions[self.last_transaction:]
        for n,c in self.cs.items():
            previous = self.last_cash_state[n]
            now = self._money(c)
            purchases = Counter({g:0 for g in GOODS})
            sales = Counter({g:0 for g in GOODS})
            for tx in transactions:
                if not tx['cash']:
                    continue
                payer,payee,amount = tx['cash']
                good = self.units[tx['legs'][0]['ids'][0]].good
                if payer == n:purchases[good] += amount
                if payee == n:sales[good] += amount
            row = {'round':self.r,'country':n,'cash_start':previous['cash'],
                'cash_end':now['cash'],'sales':now['revenue']-previous['revenue'],
                'purchases':now['purchases']-previous['purchases'],
                'investment':now['investment']-previous['investment'],
                'operating_income':now['tax']-previous['tax'],
                'purchase_by_good':dict(purchases),'sale_by_good':dict(sales),
                'happy':c.happy,'levels':dict(c.levels),'next_focus':c.focus,
                'stock':{g:self.count(c,g,False) for g in GOODS}}
            assert row['cash_end'] == (row['cash_start']+row['sales']-row['purchases']
                                      -row['investment']+row['operating_income'])
            assert sum(purchases.values()) == row['purchases']
            assert sum(sales.values()) == row['sales']
            self.cash_ledger.append(row)
            self.last_cash_state[n] = now
        self.last_transaction = len(self.transactions)
        return result

    def summary(self):
        result = super().summary()
        for n,c in self.cs.items():
            x = result['countries'][n]
            rows = [r for r in self.cash_ledger if r['country']==n]
            assert len(rows) == 9
            assert sum(r['sales'] for r in rows)==c.revenue
            assert sum(r['purchases'] for r in rows)==c.purchases
            assert sum(r['investment'] for r in rows)==c.investment
            assert sum(r['operating_income'] for r in rows)==c.tax
            x['purchase_by_good'] = {g:sum(r['purchase_by_good'][g] for r in rows) for g in GOODS}
            x['sale_by_good'] = {g:sum(r['sale_by_good'][g] for r in rows) for g in GOODS}
            x['use_by_good'] = {g:sum(u.origin==n and u.born>0 and u.good==g and u.used
                                          for u in self.units.values()) for g in GOODS}
            x['export_used_by_good'] = {g:sum(u.origin==n and u.born>0 and u.good==g
                                                 and bool(self.foreign_uses.get(u.uid))
                                                 for u in self.units.values()) for g in GOODS}
            x['end_stock_by_good'] = {g:self.count(c,g,False) for g in GOODS}
            x['unused_by_good'] = {g:sum(self.units[i].good==g and not self.units[i].used
                                           for i in c.stock) for g in GOODS}
            x['production_raw'] = {g:self.operation_inputs[(n,'production',g)] for g in ('ore','fuel')}
            x['research_raw'] = {g:self.operation_inputs[(n,'development',g)] for g in ('ore','fuel')}
            x['min_observed_cash'] = self.phase_min_cash[n]
            x['funding_blocks'] = sum(b['country']==n for b in self.funding_blocks)
            x['household_blocks'] = sum(b['country']==n for b in self.household_blocks)
            x['input_deferral_rounds'] = len({r for r,k,g in self.input_deferrals if k==n})
            relevant = [p for p in self.production_trace if p['country']==n and p['required']]
            x['fallback_after_deferral'] = sum(not p['funded'] and p['following_input_deferral'] for p in relevant)
            x['fallback_without_deferral'] = sum(not p['funded'] and not p['following_input_deferral'] for p in relevant)
            assert x['fallback_after_deferral']+x['fallback_without_deferral']==c.production_failures
            upgrades = [v for v in self.investment_trace if v['country']==n]
            x['uncovered_investments'] = sum(not v['next_cycle_covered'] for v in upgrades)
            # This follows actual bought units' recorded use, not notional prices.
            first = [r for r,k,i,p in self.use_episodes if k==n and p=='living']
            x['first_electronics_use_round'] = min(first,default=10)
            x['end_levels'] = dict(c.levels)
        result['world']['input_deferral_rounds'] = sum(x['input_deferral_rounds'] for x in result['countries'].values())
        result['world']['uncovered_investments'] = sum(x['uncovered_investments'] for x in result['countries'].values())
        return result

    def trace(self):
        return {'cash_ledger':self.cash_ledger,'production':self.production_trace,
                'investments':self.investment_trace,'funding_blocks':self.funding_blocks,
                'household_blocks':self.household_blocks,
                'input_deferrals':sorted(self.input_deferrals),'transactions':self.transactions,
                'needs_ledger':self.needs_ledger,'prices':self.price_history}
