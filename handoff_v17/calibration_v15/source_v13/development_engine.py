"""v9: a controlled 2x2 test of high-grade machinery supply and development.

Baseline is frozen v8 bridge. The supply experiment separates one existing
domestic support slot from the existing sales-stock target for G2/G3 only.
The gate experiment requires one reusable G2 machine on durable Lv3 entry.
No prices, cash grants, ore recipes, score formulas or artificial buyers change.
Chronological development chains are evidence of use, NOT causal output gains.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from copy import copy
from dataclasses import dataclass, asdict
import math

from raw_engine import Game as V8
from reference_engine import DURABLES, BONUS


@dataclass(frozen=True)
class DevelopmentPolicy:
    sale_buffer: bool = False
    prior_machine: bool = False


MODES = {
    'baseline': DevelopmentPolicy(),
    'supply': DevelopmentPolicy(sale_buffer=True),
    'gate': DevelopmentPolicy(prior_machine=True),
    'combined': DevelopmentPolicy(sale_buffer=True, prior_machine=True),
}
MACHINE_REFUSALS = {'no_high_machine': 2, 'no_machine': 1}
DEVELOPMENT_METRICS = (
    'upgrades', 'machine_required_upgrades', 'imported_machine_upgrades',
    'foreign_machine_upgrades', 'unique_imported_machines_development',
    'unique_foreign_machines_development', 'productive_upgrades',
    'used_output_upgrades', 'foreign_machine_productive_upgrades',
    'foreign_machine_used_output_upgrades', 'foreign_machine_output_units',
    'foreign_machine_output_used_units', 'foreign_machine_export_used_units',
    'bought_high_machines', 'bought_high_machine_unique',
    'foreign_produced_high_bought_unique', 'bought_high_machine_used_unique',
    'bought_high_machine_developed_unique', 'high_machine_purchase_cash',
    'sold_high_machines', 'high_machine_sales_cash', 'high_machine_produced',
    'high_machine_used', 'high_machine_useful_exports', 'high_machine_public_unique',
    'high_machine_ending_stock', 'high_machine_unused_stock',
    'g3_electronics_output', 'g3_electronics_used', 'g3_machine_output',
    'g3_machine_used', 'machine_condition_blocks',
)


class Game(V8):
    def __init__(self, seed=0, variant='baseline', focal=None, style='normal', trade_enabled=True):
        if variant not in MODES:
            raise ValueError('unknown development variant')
        self.development_variant = variant
        self.development_policy = MODES[variant]
        self.machine_refusal_country = focal if style in MACHINE_REFUSALS else None
        self.machine_refusal_grade = MACHINE_REFUSALS.get(style, 0)
        self.development_log = []
        self.development_output_log = []
        self.development_use_log = []
        self.development_attempt_log = []
        super().__init__(seed, variant='bridge', focal=focal,
                         style='normal' if style in MACHINE_REFUSALS else style,
                         trade_enabled=trade_enabled)
        if self.machine_refusal_grade and focal not in self.cs:
            raise ValueError('machine refusal requires a valid focal country')

    def upgrade_requirements(self, c, good):
        ore, grade = super().upgrade_requirements(c, good)
        if self.development_policy.prior_machine and good in DURABLES and c.levels.get(good, 0) == 2:
            grade = max(grade, 2)
        return ore, grade

    def machine_quantity(self, c, production_round, actual=False):
        if not self.development_policy.sale_buffer or self.tech_for(c, 'machine') < 2:
            return super().machine_quantity(c, production_round, actual)
        if 'machine' not in c.levels or production_round > 9:
            return 0
        gen = self.tech_for(c, 'machine')
        cap = self.base_quantity(c, 'machine') + (BONUS['machine'] if not actual or c.focus == 'machine' else 0)
        # Forecast reserves for any later focus choice. Never call targets/plan
        # here: those themselves forecast machine materials.
        domestic_slot = self.equip_slots(c) if actual else int(any(g not in DURABLES for g in c.levels))
        target = 1 + math.ceil(self.own_machine_sales(c, production_round, gen)) + domestic_slot
        available = self.count(c, 'machine', False, min_gen=gen)
        want = max(0, target - available)
        first = not any(u.origin == c.name and u.good == 'machine' and u.gen == gen and u.born > 0
                        for u in self.units.values())
        if first:
            want = max(1, want)
        return min(cap, want)

    def purchase_plan(self, c):
        rows = super().purchase_plan(c)
        if c.name == self.machine_refusal_country:
            return [r for r in rows if not (r['good'] == 'machine' and r['min_gen'] >= self.machine_refusal_grade)]
        return rows

    def settle_transaction(self, legs, cash, channel, action_id):
        if self.machine_refusal_country and isinstance(legs, list):
            for leg in legs:
                if isinstance(leg, dict) and leg.get('buyer') == self.machine_refusal_country:
                    ids = leg.get('ids', [])
                    if not isinstance(ids, list):
                        return False
                    if any(type(i) is int and i in self.units and self.units[i].good == 'machine'
                           and self.units[i].gen >= self.machine_refusal_grade for i in ids):
                        return False
        return super().settle_transaction(legs, cash, channel, action_id)

    def mark_use(self, c, uid, purpose):
        key = (self.r, c.name, uid, purpose)
        prior = key in self.use_episodes
        result = super().mark_use(c, uid, purpose)
        if not prior:
            u = self.units[uid]
            self.development_use_log.append({
                'round': self.r, 'country': c.name, 'uid': uid, 'good': u.good,
                'generation': u.gen, 'born': u.born, 'origin': u.origin,
                'purpose': purpose, 'import_transaction': u.last_import,
            })
        return result

    def invest(self, c, action_id=None):
        if action_id is not None and (not isinstance(action_id, str) or not action_id):
            return False
        before = c.investment
        levels = dict(c.levels)
        use_start = len(self.development_use_log)
        raw_start = len(self.raw_use_log)
        replay = action_id is not None and action_id in self.invest_actions
        eligible = not replay and (self.r, c.name) not in self.invested_rounds
        result = super().invest(c, action_id)
        if c.investment > before:
            r, good, level = c.upgrade_rounds[-1]
            old = copy(c); old.levels = levels
            ore, grade = self.upgrade_requirements(old, good)
            machines = [e for e in self.development_use_log[use_start:]
                        if e['country'] == c.name and e['good'] == 'machine' and e['purpose'] == 'development']
            assert len(machines) == int(bool(grade))
            machine = dict(machines[0]) if machines else None
            raw_ids = [e['uid'] for e in self.raw_use_log[raw_start:]
                       if e['country'] == c.name and e['good'] == 'ore' and e['purpose'] == 'development']
            self.development_log.append({
                'event_id': len(self.development_log), 'round': r, 'country': c.name,
                'industry': good, 'from_level': levels.get(good, 0), 'to_level': level,
                'cash_cost': c.investment - before, 'ore_required': ore, 'ore_ids': raw_ids,
                'machine_min_gen': grade, 'machine': machine,
            })
        if eligible and isinstance(action_id, str) and action_id:
            # Observe only an already-computed plan. No additional planning or
            # randomness is introduced by diagnostics.
            project = self.plan_cache.get((self.r, c.name))
            if project and c.investment == before:
                ore, grade = self.upgrade_requirements(c, project)
                self.development_attempt_log.append({
                    'round': self.r, 'country': c.name, 'industry': project,
                    'required_machine_grade': grade,
                    'missing_machine': bool(grade and not self.count(c, 'machine', min_gen=grade)),
                    'cash': c.cash, 'development_cost': self.upgrade_cost(c, project),
                    'ore_required': ore, 'ore_held': self.count(c, 'ore'),
                    'note': 'observed unmet condition; may coexist with cash, household or operating-input shortage',
                })
        return result

    def production(self):
        first_uid = self.uid
        trace_start = len(self.production_trace)
        repeated = self.r in self.produced_rounds
        result = super().production()
        if repeated:
            return result
        output = defaultdict(list)
        for uid in range(first_uid + 1, self.uid + 1):
            u = self.units[uid]
            output[(u.origin, u.good)].append(uid)
        for row in self.production_trace[trace_start:]:
            candidates = [e for e in self.development_log if e['country'] == row['country']
                          and e['industry'] == row['industry'] and e['round'] < self.r]
            latest = candidates[-1] if candidates else None
            self.development_output_log.append({
                'round': self.r, 'country': row['country'], 'industry': row['industry'],
                'level': row['level'], 'funded': row['funded'],
                'development_event_id': latest['event_id'] if latest else None,
                'ids': output[(row['country'], row['industry'])],
            })
        return result

    def development_chains(self):
        """Attribute each production batch to its MOST RECENT own upgrade.

        A later upgrade ends the preceding event's observation window. Every
        produced UID is assigned to at most one development, avoiding double
        credit. A funded batch may still be unused; that is reported separately.
        """
        batches = defaultdict(list)
        for row in self.development_output_log:
            if row['development_event_id'] is not None and row['funded']:
                batches[row['development_event_id']].extend(row['ids'])
        chains = []
        for event in self.development_log:
            ids = sorted(batches[event['event_id']])
            used = [i for i in ids if self.units[i].used]
            foreign_used = [i for i in ids if self.foreign_uses.get(i)]
            machine = event['machine']
            imported = bool(machine and machine['import_transaction'] is not None)
            foreign = bool(imported and machine['origin'] != event['country'])
            chains.append({**event, 'imported_machine': imported, 'foreign_machine': foreign,
                           'output_ids': ids, 'used_output_ids': used,
                           'foreign_used_output_ids': foreign_used})
        return chains

    def verify(self):
        result = super().verify()
        keys = [(e['round'], e['country'], e['uid'], e['purpose']) for e in self.development_use_log]
        assert len(keys) == len(set(keys))
        assert set(keys) == self.use_episodes
        assert [e['event_id'] for e in self.development_log] == list(range(len(self.development_log)))
        for event in self.development_log:
            assert event['to_level'] == event['from_level'] + 1
            assert len(event['ore_ids']) == event['ore_required']
            assert bool(event['machine']) == bool(event['machine_min_gen'])
            machine = event['machine']
            if machine:
                assert machine['generation'] >= event['machine_min_gen']
                assert machine['country'] == event['country'] and machine['round'] == event['round']
                assert machine['purpose'] == 'development'
            if self.development_policy.prior_machine and event['industry'] in DURABLES and event['to_level'] == 3:
                assert machine and machine['generation'] >= 2
        output_ids = []
        for row in self.development_output_log:
            for uid in row['ids']:
                u = self.units[uid]
                assert (u.origin, u.good, u.born) == (row['country'], row['industry'], row['round'])
                output_ids.append(uid)
            eid = row['development_event_id']
            if eid is not None:
                event = self.development_log[eid]
                assert event['round'] < row['round']
                assert (event['country'], event['industry'], event['to_level']) == (row['country'], row['industry'], row['level'])
        assert len(output_ids) == len(set(output_ids))
        return result

    def summary(self):
        result = super().summary()
        chains = self.development_chains()
        for name, c in self.cs.items():
            events = [e for e in chains if e['country'] == name]
            foreign = [e for e in events if e['foreign_machine']]
            bought = []; sold = []; purchase_cash = 0; sales_cash = 0
            for tx in self.transactions:
                for leg in tx['legs']:
                    ids = [i for i in leg['ids'] if self.units[i].good == 'machine' and self.units[i].gen >= 2]
                    if leg['buyer'] == name:
                        bought.extend(ids)
                        if ids and tx['cash']: purchase_cash += tx['cash'][2]
                    if leg['seller'] == name:
                        sold.extend(ids)
                        if ids and tx['cash']: sales_cash += tx['cash'][2]
            imported_uses = {e['uid'] for e in self.development_use_log if e['country'] == name
                             and e['good'] == 'machine' and e['generation'] >= 2 and e['import_transaction'] is not None}
            made = [u for u in self.units.values() if u.origin == name and u.born > 0]
            high = [u for u in made if u.good == 'machine' and u.gen >= 2]
            foreign_output = {i for e in foreign for i in e['output_ids']}
            metrics = {
                'upgrades': len(events),
                'machine_required_upgrades': sum(e['machine'] is not None for e in events),
                'imported_machine_upgrades': sum(e['imported_machine'] for e in events),
                'foreign_machine_upgrades': len(foreign),
                'unique_imported_machines_development': len({e['machine']['uid'] for e in events if e['imported_machine']}),
                'unique_foreign_machines_development': len({e['machine']['uid'] for e in foreign}),
                'productive_upgrades': sum(bool(e['output_ids']) for e in events),
                'used_output_upgrades': sum(bool(e['used_output_ids']) for e in events),
                'foreign_machine_productive_upgrades': sum(bool(e['output_ids']) for e in foreign),
                'foreign_machine_used_output_upgrades': sum(bool(e['used_output_ids']) for e in foreign),
                'foreign_machine_output_units': len(foreign_output),
                'foreign_machine_output_used_units': sum(self.units[i].used for i in foreign_output),
                'foreign_machine_export_used_units': sum(bool(self.foreign_uses.get(i)) for i in foreign_output),
                'bought_high_machines': len(bought), 'bought_high_machine_unique': len(set(bought)),
                'foreign_produced_high_bought_unique': len({i for i in bought if self.units[i].origin != name and self.units[i].born > 0}),
                'bought_high_machine_used_unique': len(set(bought) & imported_uses),
                'bought_high_machine_developed_unique': len({e['machine']['uid'] for e in events if e['imported_machine'] and e['machine']['generation'] >= 2}),
                'high_machine_purchase_cash': purchase_cash,
                'sold_high_machines': len(sold), 'high_machine_sales_cash': sales_cash,
                'high_machine_produced': len(high), 'high_machine_used': sum(u.used for u in high),
                'high_machine_useful_exports': sum(bool(self.foreign_uses.get(u.uid)) for u in high),
                'high_machine_public_unique': len({i for e in self.offer_history if e['country'] == name and e['good'] == 'machine' and e['generation'] >= 2 for i in e['ids']}),
                'high_machine_ending_stock': sum(self.units[i].good == 'machine' and self.units[i].gen >= 2 for i in c.stock),
                'high_machine_unused_stock': sum(self.units[i].good == 'machine' and self.units[i].gen >= 2 and not self.units[i].used for i in c.stock),
                'g3_electronics_output': sum(u.good == 'electronics' and u.gen == 3 for u in made),
                'g3_electronics_used': sum(u.good == 'electronics' and u.gen == 3 and u.used for u in made),
                'g3_machine_output': sum(u.good == 'machine' and u.gen == 3 for u in made),
                'g3_machine_used': sum(u.good == 'machine' and u.gen == 3 and u.used for u in made),
                'machine_condition_blocks': sum(e['country'] == name and e['missing_machine'] for e in self.development_attempt_log),
            }
            assert set(metrics) == set(DEVELOPMENT_METRICS)
            result['countries'][name]['development'] = metrics
        result['world']['development'] = {key: sum(x['development'][key] for x in result['countries'].values()) for key in DEVELOPMENT_METRICS}
        result['world']['development_policy'] = asdict(self.development_policy)
        result['world']['development_variant'] = self.development_variant
        result['world']['v9_note'] = 'Controlled supply/gate experiments; v8 bridge inputs and original diagnostic scores preserved. Chains are chronological, not incremental causal gains.'
        return result

    def trace(self):
        result = super().trace()
        result.update(development=self.development_log, development_outputs=self.development_output_log,
                      development_uses=self.development_use_log,
                      development_attempts=self.development_attempt_log,
                      development_chains=self.development_chains(),
                      development_policy=asdict(self.development_policy))
        return result
