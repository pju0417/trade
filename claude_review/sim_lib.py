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
    l3_flat = False  # option: level-3 investment costs the same as level 2 (no 1.5x step)

    def upgrade_cost(self, c, g):
        if not self.l3_flat or c.levels.get(g, 0) != 2:
            return super().upgrade_cost(c, g)
        from reference_engine import INVEST, half_up5
        cost = INVEST[g]
        if g == 'machine' and c.name == 'Mechania':
            cost *= .75
        if g == 'machine' and c.name == 'Technia':
            cost *= 1.25
        return half_up5(cost)

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


class LevelUpStudent(Emergency):
    """Student-like investment policy for listed countries: until `levelup_k[name]` level-ups
    are made, plan the CHEAPEST currently legal upgrade (existing industry below level 4, or the
    designated expansion industry from R3), instead of the AI's single preferred industry.
    All engine checks (cash reserve, ore, machine grade, once per round, R1-R7) still apply."""
    levelup_k = {}

    def plan(self, c):
        k = self.levelup_k.get(c.name)
        if (k is None or self._operating_initializing or c.upgrades >= k or self.r >= 8
                or c.style in ('idle', 'trade')):
            return super().plan(c)
        key = (self.r, c.name)
        if key in self.plan_cache:
            return self.plan_cache[key]
        choices = [g for g, lv in c.levels.items() if lv < 4]
        if c.expand not in c.levels and self.r >= 3:
            choices.append(c.expand)
        if not choices:
            return super().plan(c)
        pick = min(choices, key=lambda g: (self.upgrade_cost(c, g), sum(self.upgrade_requirements(c, g)),
                                           g not in c.levels, g))
        self.plan_cache[key] = pick
        return pick


class LevelUpNoReserve(LevelUpStudent):
    """Same as LevelUpStudent, but the AI-only cash reserve is not required when the focal
    country invests (students have no reserve rule; cost, ore and machine checks remain)."""
    _investing = None

    def reserve(self, c):
        if self._investing == c.name:
            return 0
        return super().reserve(c)

    def invest(self, c, *a, **kw):
        if c.name in self.levelup_k and c.upgrades < self.levelup_k[c.name]:
            self._investing = c.name
        try:
            return super().invest(c, *a, **kw)
        finally:
            self._investing = None


class MainIndustryStudent(Emergency):
    """Student-like policy for listed countries (`main_k[name]` = K): until the country's
    initial main industry has been levelled up K times, plan that industry every round
    (R1-R7) and invest without the AI-only cash reserve. Cost, ore and machine-grade checks
    are unchanged; the AI purchase planner buys the ore/machine the project needs."""
    main_k = {}
    _investing = None

    def main_ups(self, c):
        return c.levels[c.main] - 1

    def plan(self, c):
        k = self.main_k.get(c.name)
        if (k is None or self._operating_initializing or self.main_ups(c) >= k or self.r >= 8
                or c.style in ('idle', 'trade')):
            return super().plan(c)
        self.plan_cache[(self.r, c.name)] = c.main
        return c.main

    def reserve(self, c):
        if self._investing == c.name:
            return 0
        return super().reserve(c)

    def invest(self, c, *a, **kw):
        k = self.main_k.get(c.name)
        if k is not None and self.main_ups(c) < k:
            self._investing = c.name
        try:
            return super().invest(c, *a, **kw)
        finally:
            self._investing = None


def export_measures(game):
    """Per country: cash sales revenue, and 'useful export value' = for each unit it sold
    (cash or barter), min(unit price, base reference value) counted only if some other
    country actually used the unit by game end. Barter units count at reference value.
    'useful_export_noswap' additionally drops units of a good sold to a partner in a round
    in which that partner also sold the same good to this country (same-good swap rule)."""
    out = {n: {'revenue': c.revenue, 'useful_export': 0.0, 'useful_units': 0, 'barter_value': 0.0,
               'useful_export_noswap': 0.0, 'swap_excluded': 0.0}
           for n, c in game.cs.items()}
    # (round, seller, buyer, good) of every leg, for the same-good swap rule
    flows = {(t['round'], leg['seller'], leg['buyer'], game.units[uid].good)
             for t in game.transactions for leg in t['legs'] for uid in leg['ids']}
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
                    # same-good swap rule: the partner sold me the same good in the same round
                    if (t['round'], leg['buyer'], s, u.good) in flows:
                        out[s]['swap_excluded'] += v
                    else:
                        out[s]['useful_export_noswap'] += v
    return out


def make_game(seed, profile='light', mode='baseline', fee=None, focal=None, style='normal',
              behaviors=None, skip=(), wash=(), levelup=None, no_reserve=False, main_k=None,
              l3_flat=False):
    """fee=None -> original v17 engine; fee=<float> -> Emergency with that multiplier."""
    kw = dict(mode=mode, operating_profile=profile)
    if focal is not None:
        kw.update(focal=focal, style=style)
    if behaviors:
        kw['behaviors'] = dict(behaviors)
    if fee is None and not skip and not wash and not levelup and not main_k and not l3_flat:
        return engine.Game(seed, **kw)
    base = MainIndustryStudent if main_k else (LevelUpNoReserve if no_reserve else LevelUpStudent) if levelup else WashTrade if wash else (Emergency if fee is not None else Skip)
    cls = type('Variant', (base,), {'skip': tuple(skip), 'mult': fee if fee is not None else 0,
                                    'pairs': tuple(wash), 'levelup_k': dict(levelup or {}),
                                    'main_k': dict(main_k or {}), 'l3_flat': l3_flat})
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
                  'cap_old': c['fixed_evaluation']['capacity'],
                  'upgrades': game.cs[n].upgrades,
                  'upgrade_path': [list(x) for x in game.cs[n].upgrade_rounds],
                  'main_ups': game.cs[n].levels[game.cs[n].main] - 1,
                  'blocked': game.cs[n].blocked, 'attempts': game.cs[n].attempts,
                  'cash_rounds': list(game.cs[n].cash_rounds),
                  'happy': c['happy'], **ex[n]}
    return out
