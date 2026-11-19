"""Classroom session for the #11 trade game: the validated v17 engine with student-controlled countries.

The economy is exactly sim_lib.make_game(seed, fee=1.0, l3_flat=True) (confirmed rules v1).
Students replace the AI's decisions for their countries only; production, settlement,
national operation, emergency purchase, prices and the AI countries are the original engine.

Round flow (core_engine.Game.run split into teacher-advanced phases):
  start      production, verify, AI investment plans
  listing    students list / cancel / reprice goods
             -> advance: AI listings (order_actors 'listing'), demand snapshot, AI buy sweep 0
  trading    students buy from the market, make direct offers, list more
             -> advance: AI buy sweep 1, students' unsold listings return to stock,
                pending offers expire, settlement (food, electronics, operation, income)
  invest     students invest (once, R1-R7) and choose next round's focus industry
             -> advance: AI investment, focus, prices; next round or finished

With no students the call sequence is identical to core_engine.Game.run (tested).
Additions for human players (none of them changes an AI-only game):
  * A student's public listing is its consent to sell. AI countries buy it from the market
    only at or below the reference price (quote of that good and generation), and in their
    direct negotiation only at or below their negotiation ask, paying the student's price.
    AI countries never barter with a student automatically and never take unlisted stock.
  * A student's direct offer to an AI country is answered with the engine's own negotiation
    terms (seller ask = reference x (0.95 - trust concession), buyer pays at most reference,
    barter value ratio 0.75-1.33 with a real need on the AI side).
  * Students' unsold listings return to stock when trading closes each round.
  * The AI-only investment safeguards (cash reserve, household guard, next-cycle input
    check) do not block a student; the legal rules (R1-R7, once per round, cost, ore,
    machine generation, level < 4, expansion from R3) still apply.
"""
from __future__ import annotations

import dataclasses
import math
from collections import Counter

import sim_lib as L
from reference_engine import GOODS, FOOD, DURABLES, PRICE

ORIGINAL = ('Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia')
ADDED = ('Novia', 'Agrea', 'Ferria')
TARGETS = {'Tropia': 205, 'Grainia': 155, 'Oilia': 340, 'Mechania': 235, 'Mineria': 315, 'Technia': 765}
NAME_KO = {'Tropia': '트로피아', 'Grainia': '그레니아', 'Oilia': '오일리아', 'Mechania': '메카니아',
           'Mineria': '미네리아', 'Technia': '테크니아', 'Novia': '노비아', 'Agrea': '아그레아', 'Ferria': '페리아'}
GOOD_KO = {'wheat': '밀', 'banana': '바나나', 'fuel': '연료', 'ore': '광물', 'machine': '기계', 'electronics': '전자제품'}
PHASE_KO = {'listing': '판매 등록', 'trading': '거래', 'invest': '투자·주력 선택', 'finished': '게임 끝'}
MAX_PRICE = 9999
MAX_QTY = 99


def total_score(m, n):
    """Confirmed-rules total (= final_validation.total with the RULES_v1 targets)."""
    x = m[n]
    main_up = x['main_ups'] >= 1
    well_cut = min(x['happy'] / 4, x['op_short'])
    return (x['score'] - x['econ_old'] + 20 * min(1, x['useful_export_noswap'] / TARGETS[n])
            - x['cap_old'] + (15 if main_up else 0) - well_cut)


def grade(t):
    return 'A' if t >= 90 else 'B' if t >= 80 else 'C' if t >= 60 else 'D'


class ClassroomGame(L.Emergency):
    """sim_lib.make_game(seed, fee=1.0, l3_flat=True) plus student hooks."""
    mult = 1.0
    l3_flat = True
    skip = ()
    no_invest = ()
    pairs = ()
    levelup_k = {}
    main_k = {}
    students = frozenset()

    def __init__(self, seed, students=()):
        self.students = set(students)
        self.student_plan = {}
        self.student_focus = {}
        self._student_investing = None
        super().__init__(seed, mode='baseline', operating_profile='light')

    # --- student decisions replace AI decisions for student countries -------------------
    def plan(self, c):
        if c.name in self.students:
            if self._student_investing == c.name:
                key = (self.r, c.name)
                g = self.student_plan.get(key)
                self.plan_cache[key] = g
                return g
            return None
        return super().plan(c)

    def reserve(self, c):
        if self._student_investing == c.name:
            return 0
        return super().reserve(c)

    def prepare_orders(self, c):
        if c.name in self.students:
            return
        return super().prepare_orders(c)

    def buy_phase(self, c, sweep):
        if c.name in self.students:
            return
        return super().buy_phase(c, sweep)

    def invest(self, c, action_id=None):
        if c.name in self.students and self._student_investing != c.name:
            return False
        return super().invest(c, action_id)

    def choose_focus(self, c):
        if c.name in self.students:
            f = self.student_focus.get(c.name)
            if f in c.levels:
                c.focus = f
            return
        return super().choose_focus(c)

    # --- AI deals with a student only through what the student listed -----------------
    def negotiate(self, c, g, n, min_gen=1, budget=None, tag='direct'):
        # reference_engine.Game.negotiate, unchanged for AI sellers. A student seller is never
        # bartered with automatically; in the cash round its PUBLIC LISTING is its consent:
        # the AI buys listed units at the student's own price if that price is not above the
        # AI's negotiation ask (reference x (0.95 - trust concession)).
        if not self.opt.negotiations or not self.opt.trade_enabled or c.style == 'idle' or n <= 0:
            return 0
        budget = c.cash if budget is None else min(budget, c.cash)
        candidates = sorted([z for z in self.cs.values() if z is not c and z.style != 'idle'],
                            key=lambda z: self.noise(self.r, tag, c.name, g, z.name))
        for s in candidates:
            if s.name in self.students:
                continue
            supply = self.get_surplus(s, g, min_gen)
            if not supply:
                continue
            uid = supply[0]; ref = self.quote(g, self.units[uid].gen)
            for h in GOODS:
                if h == g or self.need(s, h) <= 0:
                    continue
                give = self.get_surplus(c, h)
                if not give:
                    continue
                hv = self.quote(h, self.units[give[0]].gen)
                for q in range(1, min(n, len(supply), 3) + 1):
                    k = max(1, int(math.floor(q * ref / hv + .5)))
                    if k > len(give) or k > self.need(s, h):
                        continue
                    ratio = k * hv / (q * ref)
                    if not .75 <= ratio <= 1.33:
                        continue
                    legs = [{'seller': s.name, 'buyer': c.name, 'ids': supply[:q]},
                            {'seller': c.name, 'buyer': s.name, 'ids': give[:k]}]
                    act = f'barter:{self.r}:{len(self.transactions)}'
                    if self.settle_transaction(legs, None, 'barter', act):
                        return q
        for s in candidates:
            if s.name in self.students:
                got = self._buy_student_listing(c, s, g, n, min_gen, budget)
                if got:
                    return got
                continue
            supply = self.get_surplus(s, g, min_gen)
            if not supply:
                continue
            uid = supply[0]; ref = self.quote(g, self.units[uid].gen)
            desired = self.round_price(ref * .8)  # noqa: F841 (kept from the reference)
            pair = tuple(sorted((s.name, c.name)))
            concession = .05 * min(1, self.trust[pair] / 60)
            ask = self.round_price(ref * (.95 - concession))
            self.counteroffers += 1
            qty = min(n, len(supply), budget // ask, c.cash // ask)
            if qty <= 0:
                continue
            act = f'direct:{self.r}:{len(self.transactions)}'
            if self.settle_transaction([{'seller': s.name, 'buyer': c.name, 'ids': supply[:qty]}],
                                       (c.name, s.name, qty * ask), 'direct', act):
                self.counter_accepted += 1; return qty
        return 0

    def _buy_student_listing(self, c, s, g, n, min_gen, budget):
        listed = sorted((o for o in self.orders.values() if o.seller == s.name and o.good == g and o.gen >= min_gen),
                        key=lambda o: (-o.gen, o.price, o.oid))
        pair = tuple(sorted((s.name, c.name)))
        for o in listed:
            ask = self.round_price(self.quote(g, o.gen) * (.95 - .05 * min(1, self.trust[pair] / 60)))
            if o.price > ask:
                continue
            qty = min(n, len(o.units), budget // o.price, c.cash // o.price)
            if qty <= 0:
                continue
            act = f'direct:{self.r}:{len(self.transactions)}'
            if self.settle_transaction([{'seller': s.name, 'buyer': c.name, 'ids': o.units[:qty]}],
                                       (c.name, s.name, qty * o.price), 'direct', act):
                return qty
        return 0

    def market_buy(self, c, g, n, budget, min_gen=1, tag='market'):
        # reference_engine.Game.market_buy, plus: a student's listing above the reference
        # price is not bought by an AI country (no effect when there are no students).
        if c.style == 'idle' or not self.opt.trade_enabled:
            return 0
        got = 0; spent = 0
        offers = sorted([o for o in self.orders.values() if o.good == g and o.gen >= min_gen and o.seller != c.name
                         and (o.seller not in self.students or o.price <= self.quote(g, o.gen))],
                        key=lambda o: (o.price, self.noise(self.r, tag, c.name, o.seller, o.oid)))
        for o in offers:
            if got >= n:
                break
            if o.oid not in self.orders:
                continue
            qty = min(n - got, len(o.units), c.cash // o.price, (budget - spent) // o.price)
            if qty <= 0:
                continue
            ids = o.units[:qty]; action = f'market:{self.r}:{len(self.transactions)}:{o.oid}:{c.name}'
            if self.settle_transaction([{'seller': o.seller, 'buyer': c.name, 'ids': ids}],
                                       (c.name, o.seller, qty * o.price), 'market', action):
                got += qty; spent += qty * o.price
        return got


class ActionError(Exception):
    pass


class Session:
    """One classroom game. All state changes go through apply(); the log replays exactly."""

    def __init__(self, seed, students):
        students = list(students)
        if len(set(students)) != len(students) or any(s not in ORIGINAL for s in students):
            raise ValueError('students must be distinct original countries')
        self.seed = int(seed)
        self.initial_students = list(students)
        self.g = ClassroomGame(self.seed, students)
        self.log = []
        self.offers = {}
        self.offer_seq = 0
        self.invest_seq = 0
        self.phase = None
        self.results = None
        self.tx_round_start = 0
        self._begin_round(1)

    @classmethod
    def replay(cls, seed, students, log):
        s = cls(seed, students)
        for a in log:
            s.apply(a)
        return s

    # ------------------------------------------------------------------ phases
    def _begin_round(self, r):
        g = self.g
        g.r = r; g.round_useful = Counter()
        g.production(); g.verify()
        if g.flag('budget_plans'):
            for c in g.cs.values():
                g.plan(c)
        self.tx_round_start = len(g.transactions)
        self.phase = 'listing'

    def _end_listing(self):
        g = self.g
        for c in g.order_actors('listing'):
            g.prepare_orders(c)
        g.demand_snapshot()
        for c in g.order_actors('buy0'):
            g.buy_phase(c, 0)
        self.phase = 'trading'

    def _end_trading(self):
        g = self.g
        for sweep in range(1, g.opt.round_sweeps):
            for c in g.order_actors(f'buy{sweep}'):
                g.buy_phase(c, sweep)
        g.verify()
        for o in list(g.orders.values()):
            if o.seller in g.students:
                g.remove_order_ids(list(o.units))
        for o in self.offers.values():
            if o['status'] == 'pending':
                o['status'] = 'expired'
        for c in g.cs.values():
            g.settle_round(c)
        self.phase = 'invest'

    def _end_invest(self):
        g = self.g
        r = g.r
        for c in g.order_actors('invest'):
            if c.name not in g.students:
                g.invest(c, action_id=f'invest:{r}:{c.name}')
        for c in g.cs.values():
            g.choose_focus(c); c.cash_rounds.append(c.cash)
        g.update_prices(); g.verify()
        g.round_history.append({'round': r, 'cash': {n: c.cash for n, c in g.cs.items()},
                                'listed': sum(len(o.units) for o in g.orders.values()),
                                'transactions': len(g.transactions)})
        if r == 9:
            self.phase = 'finished'
            self.results = self._results()
        else:
            self._begin_round(r + 1)

    # ------------------------------------------------------------------ actions
    def apply(self, action):
        """Apply one action dict. Returns {'ok': bool, 'msg': str, ...}. Every call is logged."""
        self.log.append(action)
        try:
            out = self._dispatch(dict(action))
            self.g.verify()
            return {'ok': True, **(out or {})}
        except ActionError as e:
            return {'ok': False, 'msg': str(e)}
        except Exception as e:  # engine invariant broken: roll back by exact replay without it
            bad = self.log.pop()
            fresh = Session.replay(self.seed, self.initial_students, self.log)
            self.__dict__.update(fresh.__dict__)
            return {'ok': False, 'msg': '처리 중 문제가 생겨 이 행동을 취소했어요.', 'error': repr(e)[:300],
                    'rejected_action': bad}

    def _dispatch(self, a):
        t = a.get('type')
        if t == 'advance':
            return self._advance()
        if t == 'set_controller':
            return self._set_controller(a.get('country'), a.get('mode'))
        if self.phase == 'finished':
            raise ActionError('게임이 끝났어요.')
        who = a.get('country')
        if who not in self.g.students:
            raise ActionError('학생이 맡은 나라가 아니에요.')
        c = self.g.cs[who]
        handler = {'list': self._list, 'cancel': self._cancel, 'reprice': self._reprice, 'buy': self._buy,
                   'offer': self._offer, 'respond': self._respond, 'withdraw': self._withdraw,
                   'invest': self._invest, 'focus': self._focus}.get(t)
        if handler is None:
            raise ActionError('알 수 없는 행동이에요.')
        return handler(c, a)

    def _advance(self):
        if self.phase == 'listing':
            self._end_listing()
        elif self.phase == 'trading':
            self._end_trading()
        elif self.phase == 'invest':
            self._end_invest()
        else:
            raise ActionError('게임이 끝났어요.')
        return {'msg': f'{self.g.r}라운드 {PHASE_KO[self.phase]} 단계', 'phase': self.phase, 'round': self.g.r}

    def _set_controller(self, country, mode):
        if country not in ORIGINAL or mode not in ('ai', 'student'):
            raise ActionError('나라 또는 방식이 올바르지 않아요.')
        if mode == 'ai':
            self.g.students.discard(country)
            for o in self.offers.values():
                if o['status'] == 'pending' and country in (o['from'], o['to']):
                    o['status'] = 'cancelled'
        else:
            self.g.students.add(country)
        return {'msg': f'{NAME_KO[country]}: {"AI" if mode == "ai" else "학생"}'}

    # helpers
    @staticmethod
    def _int(v, lo, hi, what):
        if type(v) is not int or not lo <= v <= hi:
            raise ActionError(f'{what}은(는) {lo}~{hi} 사이 정수여야 해요.')
        return v

    @staticmethod
    def _good(v):
        if v not in GOODS:
            raise ActionError('물건 종류가 올바르지 않아요.')
        return v

    def _gen(self, good, v):
        gen = 1 if v is None else v
        if good not in DURABLES and gen != 1:
            raise ActionError('기계·전자제품만 세대가 있어요.')
        return self._int(gen, 1, 3, '세대')

    def _free_ids(self, c, good, gen):
        return [i for i in self.g.ids(c, good) if self.g.units[i].gen == gen]

    def _need_phase(self, *phases):
        if self.phase not in phases:
            raise ActionError(f'지금은 {PHASE_KO[self.phase]} 단계라서 할 수 없어요.')

    # market
    def _list(self, c, a):
        self._need_phase('listing', 'trading')
        good = self._good(a.get('good')); gen = self._gen(good, a.get('gen'))
        qty = self._int(a.get('qty'), 1, MAX_QTY, '수량')
        price = self._int(a.get('price'), 1, MAX_PRICE, '가격')
        ids = self._free_ids(c, good, gen)
        if len(ids) < qty:
            raise ActionError(f'창고에 내놓을 수 있는 {GOOD_KO[good]}이(가) {len(ids)}개뿐이에요.')
        oid = self.g.make_order(c, ids[:qty], price)
        return {'msg': f'{GOOD_KO[good]} {qty}개를 개당 {price}G에 내놓았어요.', 'oid': oid}

    def _own_order(self, c, a):
        o = self.g.orders.get(a.get('oid'))
        if o is None or o.seller != c.name:
            raise ActionError('내 판매 목록에 없는 물건이에요.')
        return o

    def _cancel(self, c, a):
        self._need_phase('listing', 'trading')
        o = self._own_order(c, a)
        n = len(o.units); good = o.good
        self.g.remove_order_ids(list(o.units))
        return {'msg': f'{GOOD_KO[good]} {n}개를 창고로 되돌렸어요.'}

    def _reprice(self, c, a):
        self._need_phase('listing', 'trading')
        o = self._own_order(c, a)
        o.price = self._int(a.get('price'), 1, MAX_PRICE, '가격')
        return {'msg': f'{GOOD_KO[o.good]} 가격을 {o.price}G로 바꿨어요.'}

    def _buy(self, c, a):
        self._need_phase('trading')
        o = self.g.orders.get(a.get('oid'))
        if o is None:
            raise ActionError('이미 팔렸거나 없는 물건이에요.')
        if o.seller == c.name:
            raise ActionError('내 물건은 살 수 없어요.')
        qty = self._int(a.get('qty'), 1, MAX_QTY, '수량')
        if qty > len(o.units):
            raise ActionError(f'{len(o.units)}개만 남아 있어요.')
        cost = qty * o.price
        if c.cash < cost:
            raise ActionError(f'돈이 모자라요. {cost}G가 필요해요.')
        good, seller, price = o.good, o.seller, o.price
        act = f'smarket:{self.g.r}:{len(self.g.transactions)}:{o.oid}:{c.name}'
        if not self.g.settle_transaction([{'seller': seller, 'buyer': c.name, 'ids': o.units[:qty]}],
                                         (c.name, seller, cost), 'market', act):
            raise ActionError('거래가 처리되지 않았어요.')
        return {'msg': f'{NAME_KO[seller]}에서 {GOOD_KO[good]} {qty}개를 {cost}G에 샀어요.'}

    # direct offers
    def _side(self, v, label):
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ActionError(f'{label} 물건 정보가 올바르지 않아요.')
        good = self._good(v.get('good'))
        return {'good': good, 'gen': self._gen(good, v.get('gen')),
                'qty': self._int(v.get('qty'), 1, MAX_QTY, '수량')}

    def _offer(self, c, a):
        self._need_phase('trading')
        to = a.get('to')
        if to not in self.g.cs or to == c.name:
            raise ActionError('거래할 나라를 다시 골라 주세요.')
        kind = a.get('kind')
        give = self._side(a.get('give'), '줄')
        get = self._side(a.get('get'), '받을')
        cash = a.get('cash')
        if kind == 'sell':
            if give is None or get is not None:
                raise ActionError('팔 물건만 정해 주세요.')
            cash = self._int(cash, 1, MAX_PRICE * MAX_QTY, '금액')
        elif kind == 'buy':
            if get is None or give is not None:
                raise ActionError('살 물건만 정해 주세요.')
            cash = self._int(cash, 1, MAX_PRICE * MAX_QTY, '금액')
        elif kind == 'barter':
            if give is None or get is None:
                raise ActionError('주고받을 물건을 모두 정해 주세요.')
            if give['good'] == get['good']:
                raise ActionError('같은 물건끼리는 바꿀 수 없어요.')
            cash = 0
        else:
            raise ActionError('거래 종류가 올바르지 않아요.')
        self.offer_seq += 1
        oid = self.offer_seq
        offer = {'id': oid, 'round': self.g.r, 'from': c.name, 'to': to, 'kind': kind,
                 'give': give, 'get': get, 'cash': cash, 'status': 'pending', 'note': ''}
        self._check_offer(offer, before=True)
        self.offers[oid] = offer
        if to in self.g.students:
            return {'msg': f'{NAME_KO[to]}에 제안을 보냈어요.', 'offer': oid}
        ok, note = self._ai_answer(offer)
        offer['note'] = note
        if not ok:
            offer['status'] = 'rejected'
            return {'msg': f'{NAME_KO[to]}: {note}', 'offer': oid, 'accepted': False}
        self._execute(offer)
        return {'msg': f'{NAME_KO[to]}이(가) 제안을 받아들였어요.', 'offer': oid, 'accepted': True}

    def _legs(self, o):
        """Units are chosen at execution time from each giver's free (unlisted) stock."""
        g = self.g
        a, b = g.cs[o['from']], g.cs[o['to']]
        legs = []
        if o['give']:
            ids = self._free_ids(a, o['give']['good'], o['give']['gen'])[:o['give']['qty']]
            legs.append({'seller': a.name, 'buyer': b.name, 'ids': ids})
        if o['get']:
            ids = self._free_ids(b, o['get']['good'], o['get']['gen'])[:o['get']['qty']]
            legs.append({'seller': b.name, 'buyer': a.name, 'ids': ids})
        return legs

    def _check_offer(self, o, before=False):
        g = self.g
        a, b = g.cs[o['from']], g.cs[o['to']]
        if o['give']:
            have = len(self._free_ids(a, o['give']['good'], o['give']['gen']))
            if have < o['give']['qty']:
                who = '내' if before else NAME_KO[a.name]
                raise ActionError(f'{who} 창고에 {GOOD_KO[o["give"]["good"]]}이(가) {have}개뿐이에요(판매 중인 물건 제외).')
        if o['get'] and b.name in g.students:
            have = len(self._free_ids(b, o['get']['good'], o['get']['gen']))
            if have < o['get']['qty']:
                raise ActionError(f'{NAME_KO[b.name]} 창고에 {GOOD_KO[o["get"]["good"]]}이(가) {have}개뿐이에요.')
        payer = a if o['kind'] == 'buy' else b if o['kind'] == 'sell' else None
        if payer is not None and payer.name in g.students and payer.cash < o['cash']:
            raise ActionError(f'{NAME_KO[payer.name]}의 돈이 모자라요({o["cash"]}G 필요).')

    def _execute(self, o):
        g = self.g
        legs = self._legs(o)
        if o['kind'] == 'barter':
            cash, channel = None, 'barter'
        else:
            leg = legs[0]
            cash, channel = (leg['buyer'], leg['seller'], o['cash']), 'direct'
        act = f'offer:{g.r}:{o["id"]}'
        if not g.settle_transaction(legs, cash, channel, act):
            raise ActionError('거래가 처리되지 않았어요. 물건이나 돈이 모자랄 수 있어요.')
        o['status'] = 'accepted'

    def _ai_answer(self, o):
        """AI country answers a student's offer with the engine's own negotiation terms."""
        g = self.g
        s = g.cs[o['to']]; c = g.cs[o['from']]
        pair = tuple(sorted((s.name, c.name)))
        if o['kind'] in ('buy', 'barter'):
            want = o['get']
            supply = [i for i in g.get_surplus(s, want['good'], want['gen']) if g.units[i].gen == want['gen']]
            if len(supply) < want['qty']:
                return False, f'{GOOD_KO[want["good"]]}은(는) {len(supply)}개까지만 내줄 수 있어요.'
        if o['kind'] == 'buy':
            ref = g.quote(want['good'], want['gen'])
            concession = .05 * min(1, g.trust.get(pair, 0) / 60)
            ask = g.round_price(ref * (.95 - concession))
            if o['cash'] < ask * want['qty']:
                return False, f'개당 {ask}G 이상이면 팔게요(모두 {ask * want["qty"]}G).'
            return True, ''
        if o['kind'] == 'sell':
            give = o['give']
            need = g.need(s, give['good'])
            if need < give['qty']:
                return False, (f'{GOOD_KO[give["good"]]}이(가) 지금은 필요 없어요.' if need <= 0
                               else f'{GOOD_KO[give["good"]]}은(는) {need}개만 필요해요.')
            ref = g.quote(give['good'], give['gen'])
            if o['cash'] > ref * give['qty']:
                return False, f'개당 {ref}G 이하면 살게요(모두 {ref * give["qty"]}G).'
            essentials = sum(max(0, g.food_need() - g.count(s, f)) * g.quote(f) for f in FOOD if f != give['good'])
            keep = essentials + (0 if give['good'] in FOOD else 15)
            if o['cash'] > max(0, s.cash - keep):
                return False, '지금은 돈이 부족해요.'
            return True, ''
        # barter
        give = o['give']
        need = g.need(s, give['good'])
        if need < give['qty']:
            return False, (f'{GOOD_KO[give["good"]]}이(가) 지금은 필요 없어요.' if need <= 0
                           else f'{GOOD_KO[give["good"]]}은(는) {need}개만 필요해요.')
        hv = g.quote(give['good'], give['gen']); ref = g.quote(want['good'], want['gen'])
        ratio = give['qty'] * hv / (want['qty'] * ref)
        if ratio < .75:
            return False, '내가 주는 물건의 가치가 너무 적어요.'
        if ratio > 1.33:
            return False, '내가 주는 물건이 너무 많아요. 조금 줄여도 돼요.'
        return True, ''

    def _pending(self, a, who, field):
        o = self.offers.get(a.get('offer'))
        if o is None or o[field] != who.name:
            raise ActionError('해당 제안이 없어요.')
        if o['status'] != 'pending':
            raise ActionError('이미 끝난 제안이에요.')
        return o

    def _respond(self, c, a):
        self._need_phase('trading')
        o = self._pending(a, c, 'to')
        if not a.get('accept'):
            o['status'] = 'rejected'
            return {'msg': '제안을 거절했어요.'}
        self._check_offer(o)
        self._execute(o)
        return {'msg': f'{NAME_KO[o["from"]]}의 제안을 받아들였어요.'}

    def _withdraw(self, c, a):
        self._need_phase('trading')
        o = self._pending(a, c, 'from')
        o['status'] = 'cancelled'
        return {'msg': '제안을 취소했어요.'}

    # investment and focus
    def invest_options(self, c):
        g = self.g
        out = []
        cands = [x for x, lv in c.levels.items() if lv < 4]
        if c.expand not in c.levels:
            cands.append(c.expand)
        for x in cands:
            lv = c.levels.get(x, 0)
            cost = g.upgrade_cost(c, x)
            ore, mg = g.upgrade_requirements(c, x)
            reasons = []
            if self.phase != 'invest':
                reasons.append('투자 단계가 아니에요')
            if g.r >= 8:
                reasons.append('투자는 7라운드까지만 할 수 있어요')
            if (g.r, c.name) in g.invested_rounds:
                reasons.append('이번 라운드에 이미 투자했어요')
            if x not in c.levels and g.r < 3:
                reasons.append('새 산업은 3라운드부터 시작할 수 있어요')
            if c.cash < cost:
                reasons.append(f'돈이 {cost - c.cash}G 모자라요')
            have_ore = g.count(c, 'ore')
            if have_ore < ore:
                reasons.append(f'광물이 {ore - have_ore}개 모자라요')
            if mg and not g.ids(c, 'machine', min_gen=mg):
                reasons.append(f'{mg}세대 이상 기계가 필요해요')
            out.append({'good': x, 'label': GOOD_KO[x], 'level': lv, 'next_level': lv + 1,
                        'new_industry': x not in c.levels, 'main': x == c.main, 'cost': cost,
                        'ore': ore, 'machine_gen': mg, 'ok': not reasons, 'reasons': reasons})
        return out

    def _invest(self, c, a):
        self._need_phase('invest')
        good = self._good(a.get('good'))
        opt = next((o for o in self.invest_options(c) if o['good'] == good), None)
        if opt is None:
            raise ActionError(f'{GOOD_KO[good]}에는 투자할 수 없어요.')
        if not opt['ok']:
            raise ActionError(' / '.join(opt['reasons']))
        g = self.g
        key = (g.r, c.name)
        g.student_plan[key] = good
        old_policy = g.policy
        self.invest_seq += 1
        g._student_investing = c.name
        g.policy = dataclasses.replace(old_policy, funded_development=False)
        try:
            ok = g.invest(c, action_id=f'sinvest:{g.r}:{c.name}:{self.invest_seq}')
        finally:
            g.policy = old_policy
            g._student_investing = None
        if not ok:
            raise ActionError('투자가 처리되지 않았어요.')
        lv = c.levels[good]
        return {'msg': f'{GOOD_KO[good]} 산업을 레벨 {lv}(으)로 올렸어요({opt["cost"]}G).'}

    def _focus(self, c, a):
        self._need_phase('invest')
        good = self._good(a.get('good'))
        if good not in c.levels:
            raise ActionError('우리 나라가 생산하는 산업만 주력으로 고를 수 있어요.')
        self.g.student_focus[c.name] = good
        return {'msg': f'다음 라운드 주력 산업: {GOOD_KO[good]}'}

    # ------------------------------------------------------------------ views
    def _stock(self, c):
        g = self.g
        rows = {}
        for i in sorted(c.stock):
            u = g.units[i]
            k = (u.good, u.gen)
            r = rows.setdefault(k, {'good': u.good, 'label': GOOD_KO[u.good], 'gen': u.gen,
                                    'free': 0, 'listed': 0, 'own_made': 0, 'imported': 0})
            r['listed' if u.order is not None else 'free'] += 1
            r['own_made' if u.origin == c.name else 'imported'] += 1
        return sorted(rows.values(), key=lambda r: (GOODS.index(r['good']), r['gen']))

    def _order_view(self, o):
        return {'oid': o.oid, 'seller': o.seller, 'seller_label': NAME_KO[o.seller],
                'seller_is_student': o.seller in self.g.students, 'good': o.good,
                'label': GOOD_KO[o.good], 'gen': o.gen, 'qty': len(o.units), 'price': o.price,
                'reference': self.g.quote(o.good, o.gen)}

    def _tx_view(self, t, me):
        g = self.g
        legs = []
        for leg in t['legs']:
            u = g.units[leg['ids'][0]]
            legs.append({'seller': leg['seller'], 'buyer': leg['buyer'], 'good': u.good, 'label': GOOD_KO[u.good],
                         'gen': u.gen, 'qty': len(leg['ids'])})
        cash = None
        if t['cash']:
            cash = {'payer': t['cash'][0], 'payee': t['cash'][1], 'amount': t['cash'][2]}
        return {'round': t['round'], 'channel': t['channel'], 'legs': legs, 'cash': cash}

    def _operating_schedule(self):
        p = self.g.operating_policy
        return {'fuel': list(p.fuel_rounds), 'ore': list(p.ore_rounds)}

    def settlement_preview(self, c):
        """What this round's settlement will need, from free (unlisted) stock."""
        g = self.g
        rows = []
        settled = (g.r, c.name) in g.settled
        for f in FOOD:
            rows.append({'good': f, 'label': GOOD_KO[f], 'need': g.food_need(), 'have': g.count(c, f),
                         'purpose': '식량'})
        rows.append({'good': 'electronics', 'label': GOOD_KO['electronics'], 'need': math.ceil(g.pop() / 2),
                     'have': g.count(c, 'electronics'), 'purpose': '생활(쓰고 없어지지 않음)'})
        due = {'fuel': int(g.r in g.operating_policy.fuel_rounds), 'ore': int(g.r in g.operating_policy.ore_rounds)}
        for h in ('fuel', 'ore'):
            if due[h]:
                rows.append({'good': h, 'label': GOOD_KO[h], 'need': due[h], 'have': g.count(c, h),
                             'purpose': f'국가 운영(없으면 {L.BASE[h]}G 긴급 조달, 생활 점수 −1)'})
        for r in rows:
            r['short'] = max(0, r['need'] - r['have'])
        return {'settled': settled, 'rows': rows}

    def progress(self, n):
        g = self.g
        c = g.cs[n]
        ex = L.export_measures(g)[n]
        led = [x for x in g.operating_ledger if x['country'] == n]
        short = sum(1 for x in led if any(x['missing'].values()))
        return {'export_value': ex['useful_export_noswap'], 'export_target': TARGETS.get(n),
                'main_levelled': c.levels[c.main] >= 2, 'avg_happy': (sum(c.happiness) / len(c.happiness)) if c.happiness else None,
                'operating_short_days': short, 'emergency_paid': getattr(g, 'emergency', {}).get(n, 0)}

    def _common(self):
        g = self.g
        return {'round': g.r, 'phase': self.phase, 'phase_label': PHASE_KO[self.phase],
                'students': sorted(g.students), 'countries': list(g.cs),
                'names': {n: NAME_KO[n] for n in g.cs}, 'goods': {k: GOOD_KO[k] for k in GOODS},
                'base_prices': dict(PRICE), 'prices': {k: round(v, 2) for k, v in g.prices.items()},
                'quotes': {k: {gen: g.quote(k, gen) for gen in ((1, 2, 3) if k in DURABLES else (1,))} for k in GOODS},
                'population': g.pop(), 'food_need': g.food_need(),
                'operating_schedule': self._operating_schedule(),
                'market': [self._order_view(o) for o in sorted(g.orders.values(), key=lambda o: (o.good, o.gen, o.price, o.oid))]}

    def view(self, n):
        """Everything one student's screen needs."""
        g = self.g
        c = g.cs[n]
        mine = lambda o: n in (o['from'], o['to'])
        v = self._common()
        v.update({
            'country': n, 'label': NAME_KO[n], 'is_student': n in g.students,
            'cash': c.cash, 'main': c.main, 'expand': c.expand, 'focus': c.focus,
            'next_focus': g.student_focus.get(n, c.focus), 'levels': dict(c.levels),
            'machine_gen': c.machine_tech, 'electronics_gen': c.elec_tech,
            'happiness': list(c.happiness), 'cash_by_round': list(c.cash_rounds),
            'stock': self._stock(c),
            'my_orders': [self._order_view(o) for o in g.orders.values() if o.seller == n],
            'settlement': self.settlement_preview(c),
            'invest_options': self.invest_options(c),
            'invested_this_round': (g.r, n) in g.invested_rounds,
            'upgrades': [{'round': r, 'good': x, 'label': GOOD_KO[x], 'level': lv} for r, x, lv in c.upgrade_rounds],
            'offers': [dict(o) for o in self.offers.values() if mine(o)],
            'transactions_this_round': [self._tx_view(t, n) for t in g.transactions[self.tx_round_start:]
                                        if any(n in (l['seller'], l['buyer']) for l in t['legs'])],
            'trust': {m: g.trust.get(tuple(sorted((n, m))), 0) for m in g.cs if m != n},
            'progress': self.progress(n),
            'results': self.results,
        })
        return v

    def teacher_view(self):
        g = self.g
        v = self._common()
        rows = []
        for n, c in g.cs.items():
            rows.append({'country': n, 'label': NAME_KO[n], 'student': n in g.students, 'evaluated': n in ORIGINAL,
                         'cash': c.cash, 'levels': dict(c.levels), 'focus': c.focus,
                         'happy': c.happiness[-1] if c.happiness else None,
                         'stock': {k: g.count(c, k, False) for k in GOODS},
                         'invested_this_round': (g.r, n) in g.invested_rounds,
                         'listed': sum(len(o.units) for o in g.orders.values() if o.seller == n),
                         'progress': self.progress(n) if n in ORIGINAL else None})
        v.update({'seed': self.seed, 'nations': rows, 'log_length': len(self.log),
                  'pending_offers': sum(o['status'] == 'pending' for o in self.offers.values()),
                  'transactions_this_round': len(g.transactions) - self.tx_round_start,
                  'results': self.results})
        return v

    def _results(self):
        m = L.run_metrics(self.g)
        out = {}
        for n in ORIGINAL:
            x = m[n]
            t = total_score(m, n)
            well = x['well_pts'] - min(x['happy'] / 4, x['op_short'])
            out[n] = {'label': NAME_KO[n], 'student': n in self.g.students, 'total': t, 'grade': grade(t),
                      'parts': {'export': 20 * min(1, x['useful_export_noswap'] / TARGETS[n]),
                                'industry': 15 if x['main_ups'] >= 1 else 0, 'living': well,
                                'trade': x['trade_pts'], 'utilization': x['util_pts'], 'cash': x['reserve_pts']},
                      'export_value': x['useful_export_noswap'], 'export_target': TARGETS[n],
                      'operating_short_days': x['op_short'], 'emergency_paid': x['emergency'],
                      'final_cash': x['cash'], 'avg_happy': x['happy']}
        return out
