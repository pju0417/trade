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


def make_game(seed, profile='light', mode='baseline', fee=None, focal=None, style='normal',
              behaviors=None, skip=()):
    """fee=None -> original v17 engine; fee=<float> -> Emergency with that multiplier."""
    kw = dict(mode=mode, operating_profile=profile)
    if focal is not None:
        kw.update(focal=focal, style=style)
    if behaviors:
        kw['behaviors'] = dict(behaviors)
    if fee is None and not skip:
        return engine.Game(seed, **kw)
    cls = type('Variant', (Emergency if fee is not None else Skip,),
               {'skip': tuple(skip), 'mult': fee if fee is not None else 0})
    return cls(seed, **kw)


def run_metrics(game):
    """Run a game; return per-country growth metrics plus fixed (v15 steps) score."""
    result = R.normalize_extended(game.run())
    rec = {'countries': result['countries'], 'world': result['world']}
    R.attach_fixed_scores(game, rec, growth, GOALS)
    out = {}
    for n in NAMES:
        c = rec['countries'][n]
        m = c['growth_metrics']
        out[n] = {'asset_gain': m['asset_gain'], 'capacity_growth': m['capacity_growth'],
                  'investment': m['investment'], 'tax': m['tax'], 'cash': m['cash'],
                  'score': c['fixed_evaluation']['score'],
                  'op_short': c['national_operation']['any_shortage_rounds'],
                  'emergency': getattr(game, 'emergency', {}).get(n, 0)}
    return out
