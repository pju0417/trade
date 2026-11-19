"""v10: goal-preserving AI detours on the frozen v9 combined economy.

Only automatically selected development plans and optional focus choices change. Existing investment
permissions/costs, living/raw guards, production, pricing and scores remain.
The new router sees own state and public offers, never rival hidden state.
Public supply at an unaffordable price is NOT treated as supply absence.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

from development_engine import Game as V9


@dataclass(frozen=True)
class RoutePolicy:
    wait_rounds: int = 0
    expansion_wait_extra: int = 0
    launch_grace: bool = False
    supplier_focus: bool = False


MODES = {'baseline': RoutePolicy(0), 'quick': RoutePolicy(1), 'patient': RoutePolicy(2),
         'market_first': RoutePolicy(2, 1, True, True)}
ROUTING_METRICS = (
    'routes_started', 'routes_completed', 'routes_unfinished',
    'routes_with_used_goal_output', 'routes_with_own_machine_goal',
    'routes_with_foreign_machine_goal', 'intermediate_investments',
    'intermediate_spend', 'unfinished_intermediate_spend',
    'alternate_plan_rounds', 'wait_output_rounds', 'market_resume_rounds',
    'owned_resume_rounds', 'horizon_block_rounds', 'redundant_investments_cancelled',
    'market_launch_wait_rounds', 'supplier_focus_rounds',
    'g3_electronics_produced', 'g3_electronics_used',
    'first_g3_electronics_production_round', 'first_g3_electronics_use_round',
    'high_machine_producer',
)


class Game(V9):
    def __init__(self, seed=0, variant='baseline', focal=None, style='normal', trade_enabled=True):
        if variant not in MODES:
            raise ValueError('unknown routing variant')
        self.routing_variant = variant
        self.routing_policy = MODES[variant]
        self.routing_initializing = True
        self.routing_log = []
        self.routing_seen = set()
        self.route_records = []
        self.active_routes = {}
        self.route_actions = []
        self.route_cancelled = set()
        self.route_focus_log = []
        super().__init__(seed, variant='combined', focal=focal, style=style, trade_enabled=trade_enabled)
        self.routing_initializing = False

    def routing_advice(self, c, goal, target_level=None, active=False):
        """Pure decision helper: own state + past/current PUBLIC offers only.

        It does not invoke the inherited planner, inspect rival inventories,
        change histories, or issue any economic command.
        """
        target = target_level if target_level is not None else c.levels.get(goal, 0) + 1 if goal else 0
        grade = self.upgrade_requirements(c, goal)[1] if goal else 0
        held = self.ids(c, 'machine', False, min_gen=grade or 1) if grade else []
        offers = sorted(o.oid for o in self.orders.values() if o.good == 'machine' and
                        o.gen >= (grade or 1) and o.seller != c.name and o.units)
        level = c.levels.get('machine', 0)
        wait = self.routing_policy.wait_rounds + (self.routing_policy.expansion_wait_extra if level == 0 else 0)
        prior = list(range(self.r-wait, self.r))
        failures = [e['round'] for e in self.development_attempt_log
                    if e['country'] == c.name and e['industry'] == goal and
                    e['missing_machine'] and e['required_machine_grade'] >= grade and e['round'] in prior]
        public_rounds = sorted({e['round'] for e in self.offer_history if e['country'] != c.name and
                                e['good'] == 'machine' and e['generation'] >= (grade or 1) and
                                e['ids'] and e['round'] in prior})
        last_public = any(e['country'] != c.name and e['good'] == 'machine' and
                          e['generation'] >= (grade or 1) and e['ids'] and e['round'] == self.r-1
                          for e in self.offer_history)
        launches = [dict(e) for e in self.launch_events if e['good']=='machine' and
                    e['generation'] >= (grade or 1) and e['round']==self.r]
        steps = max(0, 2-level)
        earliest = self.r + (steps if steps else int(not held))
        legal = 'machine' in c.levels or (c.expand == 'machine' and self.r >= 3)
        row = {'round': self.r, 'country': c.name, 'goal': goal, 'target_level': target,
               'active_route': bool(active), 'machine_min_gen': grade,
               'own_levels': dict(c.levels), 'own_expand': c.expand, 'own_style': c.style,
               'own_machine_level': level, 'own_qualified_machine_ids': list(held),
               'public_offer_ids': offers, 'public_offer_prices': [self.orders[i].price for i in offers],
               'public_offers': [{'oid':i, 'seller':self.orders[i].seller, 'generation':self.orders[i].gen,
                                  'price':self.orders[i].price, 'ids':list(self.orders[i].units)} for i in offers],
               'prior_rounds': prior, 'failed_rounds': sorted(set(failures)),
               'public_history_rounds': public_rounds, 'last_round_public_supply': bool(last_public),
               'effective_wait_rounds':wait, 'public_generation_launches':launches,
               'remaining_machine_steps': steps, 'earliest_goal_round': earliest,
               'legal_machine_path': legal, 'selected': goal, 'reason': 'original_goal'}
        def decide(selected, reason):
            return {**row, 'selected': selected, 'reason': reason}
        if c.style in ('idle', 'trade') or self.r >= 8:
            return decide(None, 'investment_disabled')
        if not goal:
            return decide(None, 'no_goal')
        if c.levels.get(goal, 0) >= target:
            return decide(None, 'goal_already_satisfied')
        if not grade:
            return decide(goal, 'no_machine_condition')
        if held:
            return decide(goal, 'owned_machine_ready')
        if offers or (active and last_public):
            return decide(goal, 'public_supply_present')
        if self.routing_policy.launch_grace and launches:
            return decide(goal, 'new_generation_market_chance')
        if not self.routing_policy.wait_rounds:
            return decide(goal, 'router_disabled')
        if not active:
            if not prior or prior[0] < 1 or set(failures) != set(prior):
                return decide(goal, 'waiting_for_completed_attempts')
            if public_rounds:
                return decide(goal, 'recent_public_supply')
        if not legal:
            return decide(goal, 'no_legal_machine_path')
        if earliest > 7:
            return decide(goal, 'too_late_for_self_production')
        if level >= 2:
            return decide(None, 'await_actual_machine')
        return decide('machine', 'continue_route' if active else 'start_route')

    def plan(self, c):
        if self.routing_initializing:
            return super().plan(c)
        key = (self.r, c.name)
        if key in self.routing_seen:
            return self.plan_cache.get(key) if key in self.plan_cache else super().plan(c)
        base = super().plan(c)
        self.routing_seen.add(key)
        if not self.routing_policy.wait_rounds:
            self.routing_log.append({'round':self.r, 'country':c.name, 'base_plan':base,
                                     'selected':base, 'reason':'baseline', 'route_id':None})
            return base
        route_id = self.active_routes.get(c.name)
        route = self.route_records[route_id] if route_id is not None else None
        goal = route['goal'] if route else base
        target = route['target_level'] if route else None
        row = self.routing_advice(c, goal, target, active=bool(route))
        if row['reason'] == 'start_route':
            route_id = len(self.route_records)
            route = {'route_id':route_id, 'country':c.name, 'goal':goal,
                     'target_level':row['target_level'], 'start_round':self.r,
                     'starting_machine_level':c.levels.get('machine',0),
                     'status':'active', 'end_round':None, 'goal_event_id':None,
                     'intermediate_event_ids':[]}
            self.route_records.append(route)
            self.active_routes[c.name] = route_id
        if row['reason'] == 'goal_already_satisfied' and route:
            route.update(status='already_satisfied', end_round=self.r)
            self.active_routes.pop(c.name, None)
            row['selected'] = base
        self.plan_cache[key] = row['selected']
        self.routing_log.append({**row, 'base_plan':base, 'route_id':route_id})
        return row['selected']

    def invest(self, c, action_id=None):
        if action_id is not None and (not isinstance(action_id,str) or not action_id):
            return False
        if (action_id is not None and action_id in self.invest_actions) or (self.r,c.name) in self.invested_rounds:
            return super().invest(c, action_id)
        if not self.routing_policy.wait_rounds:
            return super().invest(c, action_id)
        selected = self.plan(c)
        route_id = self.active_routes.get(c.name)
        route = self.route_records[route_id] if route_id is not None else None
        if route and selected == 'machine' and route['goal'] != 'machine' and c.levels.get('machine',0) < 2:
            grade = self.upgrade_requirements(c, route['goal'])[1]
            if grade and self.count(c, 'machine', False, min_gen=grade):
                # Keep the round's selected plan/budget stable. A newly acquired
                # machine makes the intermediate spend unnecessary; resume the
                # original goal in the next round, never perform a second plan.
                key=(self.r,c.name)
                if key not in self.route_cancelled:
                    self.route_cancelled.add(key)
                    self.route_actions.append({'round':self.r, 'country':c.name, 'route_id':route_id,
                        'selected':selected, 'status':'redundant_cancelled', 'event_id':None, 'cash_cost':0})
                if action_id is not None:
                    self.invest_actions[action_id]=False
                    self.invest_payloads[action_id]=key
                return False
        before = len(self.development_log)
        result = super().invest(c, action_id)
        if route and len(self.development_log) > before:
            event = self.development_log[-1]
            completed = event['industry'] == route['goal'] and event['to_level'] >= route['target_level']
            if completed:
                route.update(status='completed', end_round=self.r, goal_event_id=event['event_id'])
                self.active_routes.pop(c.name,None)
            elif event['industry'] == 'machine':
                assert event['to_level'] <= 2
                route['intermediate_event_ids'].append(event['event_id'])
            self.route_actions.append({'round':self.r, 'country':c.name, 'route_id':route_id,
                'selected':selected, 'status':'goal_completed' if completed else 'intermediate_completed',
                'event_id':event['event_id'], 'cash_cost':event['cash_cost']})
        return result

    def update_prices(self):
        result=super().update_prices()
        if self.r == 9:
            for route_id in self.active_routes.values():
                self.route_records[route_id].update(status='unfinished',end_round=9)
            self.active_routes.clear()
        return result

    def choose_focus(self, c):
        result=super().choose_focus(c)
        if not self.routing_policy.supplier_focus or self.r >= 9 or c.style in ('idle','trade'):
            return result
        route_id=self.active_routes.get(c.name)
        if route_id is None:
            return result
        route=self.route_records[route_id]
        events=[self.development_log[i] for i in route['intermediate_event_ids']
                if self.development_log[i]['round']==self.r and self.development_log[i]['to_level']==2]
        if not events or self.count(c,'machine',False,min_gen=2):
            return result
        # Use an already legal focus choice for ONE launch cycle. The inherited
        # v9 physical stock target already separates this domestic support slot
        # from sale stock. No new output, material discount, or buyer is added.
        from reference_engine import DURABLES
        choices=[g for g in c.levels if g not in DURABLES]
        if not choices:
            return result
        previous=c.focus
        chosen=max(choices,key=lambda g:(self.quote(g)*self.actual_bonus(c,g)/(1+.3*self.count(c,g,False)),g))
        c.focus=chosen
        # Repeated inspection in one round must not count a second launch cycle.
        # Keep the first decision snapshot while preserving the legal focus above.
        if any(e['round']==self.r and e['country']==c.name for e in self.route_focus_log):
            return result
        self.route_focus_log.append({'round':self.r,'country':c.name,'route_id':route_id,
            'previous_focus':previous,'selected_focus':chosen,'own_levels':dict(c.levels),
            'supporting_event_id':events[-1]['event_id'],
            'forecast_quantity':self.machine_quantity(c,self.r+1),
            'actual_focus_quantity':self.machine_quantity(c,self.r+1,actual=True)})
        return result

    def verify(self):
        result=super().verify()
        assert len(self.routing_log) == len({(e['round'],e['country']) for e in self.routing_log})
        assert len(self.route_focus_log) == len({(e['round'],e['country']) for e in self.route_focus_log})
        for row in self.routing_log:
            if (row['round'],row['country']) in self.plan_cache:
                assert row['selected'] == self.plan_cache[(row['round'],row['country'])]
            if row['reason'] in ('start_route','continue_route'):
                assert row['selected']=='machine' and row['legal_machine_path']
                assert row['own_machine_level']<2 and row['earliest_goal_round']<=7
                assert not row['own_qualified_machine_ids'] and not row['public_offer_ids']
            if row['reason']=='start_route':
                assert row['failed_rounds']==row['prior_rounds'] and not row['public_history_rounds']
        for i,route in enumerate(self.route_records):
            assert route['route_id']==i
            for eid in route['intermediate_event_ids']:
                event=self.development_log[eid]
                assert event['country']==route['country'] and event['industry']=='machine' and event['to_level']<=2
            if route['status']=='completed':
                event=self.development_log[route['goal_event_id']]
                assert (event['country'],event['industry'])==(route['country'],route['goal'])
                assert event['to_level']>=route['target_level'] and event['round']<=7
        for row in self.route_focus_log:
            assert row['selected_focus'] in row['own_levels'] and row['selected_focus'] not in ('machine','electronics')
            assert row['actual_focus_quantity'] <= row['forecast_quantity']
            event=self.development_log[row['supporting_event_id']]
            assert (event['round'],event['country'],event['industry'],event['to_level']) == (row['round'],row['country'],'machine',2)
        return result

    def summary(self):
        result=super().summary()
        chains={e['event_id']:e for e in self.development_chains()}
        for name,c in self.cs.items():
            routes=[e for e in self.route_records if e['country']==name]
            completed=[e for e in routes if e['status']=='completed']
            goal_events=[chains[e['goal_event_id']] for e in completed]
            intermediate=[eid for e in routes for eid in e['intermediate_event_ids']]
            unfinished=[eid for e in routes if e['status']!='completed' for eid in e['intermediate_event_ids']]
            decisions=[e for e in self.routing_log if e['country']==name]
            g3=[u for u in self.units.values() if u.origin==name and u.born>0 and u.good=='electronics' and u.gen==3]
            metrics={
                'routes_started':len(routes), 'routes_completed':len(completed),
                'routes_unfinished':sum(e['status']!='completed' for e in routes),
                'routes_with_used_goal_output':sum(bool(e['used_output_ids']) for e in goal_events),
                'routes_with_own_machine_goal':sum(e['machine'] is not None and e['machine']['origin']==name for e in goal_events),
                'routes_with_foreign_machine_goal':sum(e['foreign_machine'] for e in goal_events),
                'intermediate_investments':len(intermediate),
                'intermediate_spend':sum(self.development_log[i]['cash_cost'] for i in intermediate),
                'unfinished_intermediate_spend':sum(self.development_log[i]['cash_cost'] for i in unfinished),
                'alternate_plan_rounds':sum(e['reason'] in ('start_route','continue_route') for e in decisions),
                'wait_output_rounds':sum(e['reason']=='await_actual_machine' for e in decisions),
                'market_resume_rounds':sum(e.get('active_route',False) and e['reason']=='public_supply_present' for e in decisions),
                'owned_resume_rounds':sum(e.get('active_route',False) and e['reason']=='owned_machine_ready' for e in decisions),
                'horizon_block_rounds':sum(e['reason']=='too_late_for_self_production' for e in decisions),
                'redundant_investments_cancelled':sum(n==name for r,n in self.route_cancelled),
                'market_launch_wait_rounds':sum(e['reason']=='new_generation_market_chance' for e in decisions),
                'supplier_focus_rounds':sum(e['country']==name for e in self.route_focus_log),
                'g3_electronics_produced':int(bool(g3)), 'g3_electronics_used':int(any(u.used for u in g3)),
                'first_g3_electronics_production_round':min((u.born for u in g3),default=10),
                'first_g3_electronics_use_round':min((u.use_round for u in g3 if u.used),default=10),
                'high_machine_producer':int(any(u.origin==name and u.born>0 and u.good=='machine' and u.gen>=2 for u in self.units.values())),
            }
            assert set(metrics)==set(ROUTING_METRICS)
            result['countries'][name]['routing']=metrics
        # First-round sentinel metrics are intentionally not summed globally.
        summed=[k for k in ROUTING_METRICS if not k.startswith('first_')]
        result['world']['routing']={key:sum(c['routing'][key] for c in result['countries'].values()) for key in summed}
        for label,field in (('both_electronics_produced','g3_electronics_produced'),('both_electronics_used','g3_electronics_used')):
            result['world']['routing'][label]=int(all(result['countries'][n]['routing'][field] for n in ('Technia','Novia')))
        result['world']['routing_policy']=asdict(self.routing_policy)
        result['world']['routing_variant']=self.routing_variant
        result['world']['v10_note']='Automatic development choice and market_first launch focus only; v9 combined physical rules/scoring retained. No assertion that legacy planner has no private aggregate inputs.'
        return result

    def trace(self):
        result=super().trace()
        result.update(routing_decisions=self.routing_log, routing_routes=self.route_records,
                      routing_actions=self.route_actions, routing_focus=self.route_focus_log,
                      routing_public_launches=[dict(e) for e in self.launch_events],
                      routing_policy=asdict(self.routing_policy))
        return result
