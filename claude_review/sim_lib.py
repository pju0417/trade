"""Shared helpers for Claude's v17 experiments. Original v17/v13 sources are not modified.

Engine variants are subclasses of the v17 operating engine:
- Skip:      listed countries ignore national-operation needs when buying/protecting stock
             (settlement still charges the real need).
- Emergency: an unmet operating bundle is charged `mult` x base price (fuel 30G, ore 20G)
             as a deduction from national income; if fully paid, the satisfaction penalty
             is waived. No goods are created.
"""
from __future__ import annotations

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'trade_v17')


def load(src=SRC):
    for p in (os.path.join(src, 'source_v13'), src):
        if p not in sys.path:
            sys.path.insert(0, p)
    import run_operating_validation as R
    engine, old, growth, goals = R.runtime()
    return R, engine, growth, goals


R, engine, growth, GOALS = load()
NAMES = ('Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia')
RAW = ('ore', 'fuel')
BASE = {'fuel': 30, 'ore': 20}


class Skip(engine.Game):
    skip = ()

    def settle_round(self, c):
        self._in_settle = True
        try:
            return super().settle_round(c)
        finally:
            self._in_settle = False

    def operating_required(self, c, r=None, unsettled=True):
        if (c.name in self.skip and not getattr(self, '_in_settle', False)
                and not self._operating_initializing):
            return {'ore': 0, 'fuel': 0}
        return super().operating_required(c, r, unsettled)


class Emergency(Skip):
    mult = 1.0

    def settle_round(self, c):
        before = len(self.operating_ledger)
        ok = super().settle_round(c)
        if ok and len(self.operating_ledger) > before:
            row = self.operating_ledger[-1]
            fee = sum(int(round(self.mult * BASE[g])) * row['missing'][g] for g in RAW)
            pay = min(fee, c.cash)
            if pay:
                c.cash -= pay; c.tax -= pay; self.minted -= pay
                self.emergency = getattr(self, 'emergency', {})
                self.emergency[c.name] = self.emergency.get(c.name, 0) + pay
                if pay == fee and row['penalty'] > 0:
                    diff = (10 + int(math.floor(row['base_happy'] / 10 + .5))) - row['round_income']
                    c.happy = row['base_happy']; c.happiness[-1] = row['base_happy']
                    c.tax += diff; c.cash += diff; self.minted += diff
                    row['penalty'] = 0; row['happy'] = row['base_happy']
                    row['round_income'] += diff; row['tax_effect'] += diff
        return ok


class WashTrade(Emergency):
    """Diagnostic exploit: each listed pair sells one surplus unit to each other every
    round at a fixed high price, right before settlement (round-trip 'wash' trade)."""
    pairs = ()
    wash_price = 100

    def settle_round(self, c):
        if getattr(self, '_washed', None) != self.r:
            self._washed = self.r
            for a, b in self.pairs:
                for s, t in ((a, b), (b, a)):
                    S, T = self.cs[s], self.cs[t]
                    for g in ('banana', 'wheat', 'fuel', 'ore', 'machine', 'electronics'):
                        ids = [i for i in self.get_surplus(S, g) if self.units[i].origin == s]
                        if ids and T.cash >= self.wash_price:
                            act = f'wash:{self.r}:{s}:{t}:{len(self.transactions)}'
                            if self.settle_transaction([{'seller': s, 'buyer': t, 'ids': ids[:1]}],
                                                       (t, s, self.wash_price), 'direct', act):
                                self.wash_count = getattr(self, 'wash_count', 0) + 1
                                break
        return super().settle_round(c)


def export_measures(game):
    """Per country: cash sales revenue, and 'useful export value' = for each unit it sold
    (cash or barter), min(unit price, base reference value) counted only if some other
    country actually used the unit by game end. Barter units count at reference value."""
    out = {n: {'revenue': c.revenue, 'useful_export': 0.0, 'useful_units': 0, 'barter_value': 0.0}
           for n, c in game.cs.items()}
    for t in game.transactions:
        for leg in t['legs']:
            s = leg['seller']
            per = (t['cash'][2] / len(leg['ids'])) if t['cash'] else None
            for uid in leg['ids']:
                u = game.units[uid]
                ref = game.unit_ref(u)
                if u.used and u.use_country not in (None, s):
                    v = ref if per is None else min(per, ref)
                    out[s]['useful_export'] += v; out[s]['useful_units'] += 1
                    if per is None:
                        out[s]['barter_value'] += v
    return out


def make_game(seed, profile='light', mode='baseline', fee=None, focal=None, style='normal',
              behaviors=None, skip=(), wash=()):
    """fee=None -> original v17 engine; fee=<float> -> Emergency with that multiplier."""
    kw = dict(mode=mode, operating_profile=profile)
    if focal is not None:
        kw.update(focal=focal, style=style)
    if behaviors:
        kw['behaviors'] = dict(behaviors)
    if fee is None and not skip and not wash:
        return engine.Game(seed, **kw)
    base = WashTrade if wash else (Emergency if fee is not None else Skip)
    cls = type('Variant', (base,), {'skip': tuple(skip), 'mult': fee if fee is not None else 0,
                                    'pairs': tuple(wash)})
    return cls(seed, **kw)


def run_metrics(game):
    """Run a game; return per-country growth metrics plus fixed (v15 steps) score."""
    result = R.normalize_extended(game.run())
    rec = {'countries': result['countries'], 'world': result['world']}
    R.attach_fixed_scores(game, rec, growth, GOALS)
    out = {}
    ex = export_measures(game)
    for n in NAMES:
        c = rec['countries'][n]
        m = c['growth_metrics']
        out[n] = {'asset_gain': m['asset_gain'], 'capacity_growth': m['capacity_growth'],
                  'investment': m['investment'], 'tax': m['tax'], 'cash': m['cash'],
                  'score': c['fixed_evaluation']['score'],
                  'op_short': c['national_operation']['any_shortage_rounds'],
                  'emergency': getattr(game, 'emergency', {}).get(n, 0),
                  'econ_old': c['fixed_evaluation']['economic_growth'],
                  'happy': c['happy'], **ex[n]}
    return out
