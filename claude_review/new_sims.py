"""Claude new-game experiments on a COPY of v17 code (source unchanged).
Usage: python3 new_sims.py <v17_copy_dir> <experiment> <out.json>
Scores use the original attach_fixed_scores path (v15 steps, 45% capital).
"""
import sys, json, math, os
from multiprocessing import Pool
SRC=sys.argv[1]; EXP=sys.argv[2]; OUT=sys.argv[3]
sys.path.insert(0,SRC); sys.path.insert(0,os.path.join(SRC,'source_v13'))
import run_operating_validation as R
engine,old,growth,goals=R.runtime()
NAMES=('Tropia','Grainia','Oilia','Mechania','Mineria','Technia')
RAW=('ore','fuel')

class Skip(engine.Game):
    """Focal countries ignore national-operation needs when planning purchases
    and protecting stock; settlement still charges the real need."""
    skip=()
    def settle_round(self,c):
        self._in_settle=True
        try:return super().settle_round(c)
        finally:self._in_settle=False
    def operating_required(self,c,r=None,unsettled=True):
        if c.name in self.skip and not getattr(self,'_in_settle',False) and not self._operating_initializing:
            return {'ore':0,'fuel':0}
        return super().operating_required(c,r,unsettled)

class Emergency(Skip):
    mult=1.5
    """Candidate fix (one factor): an unmet operating bundle is covered by an
    automatic emergency purchase costing 1.5x the base price, paid from cash
    (booked as a deduction from national income; cash sink; no goods created). Happiness penalty only if cash is insufficient."""
    def settle_round(self,c):
        before=len(self.operating_ledger)
        ok=super().settle_round(c)
        if ok and len(self.operating_ledger)>before:
            row=self.operating_ledger[-1]
            fee=0
            for g in RAW:
                if row['missing'][g]:
                    fee+=int(round(self.mult*(30 if g=='fuel' else 20)))*row['missing'][g]
            pay=min(fee,c.cash)
            if pay:
                c.cash-=pay;c.tax-=pay;self.minted-=pay;self.emergency=getattr(self,'emergency',{});self.emergency[c.name]=self.emergency.get(c.name,0)+pay
                # if fully paid, restore the happiness/income penalty for this round
                if pay==fee and row['penalty']>0:
                    diff=(10+int(math.floor(row['base_happy']/10+.5)))-row['round_income']
                    c.happy=row['base_happy'];c.happiness[-1]=row['base_happy']
                    c.tax+=diff;c.cash+=diff;self.minted+=diff
                    row['penalty']=0;row['happy']=row['base_happy'];row['round_income']+=diff
                    row['tax_effect']+=diff
        return ok

def score_game(game):
    result=R.normalize_extended(game.run())
    rec={'countries':result['countries'],'world':result['world']}
    R.attach_fixed_scores(game,rec,growth,goals)
    out={}
    for n,c in rec['countries'].items():
        fe=c['fixed_evaluation']
        out[n]={'score':fe['score'] if fe else None,
                'parts':{k:fe[k] for k in ('economic_growth','reserve','capacity','utilization','wellbeing','trade')} if fe else None,
                'cash':c['cash'],'inv':c['investment'],'happy':c['happy'],
                'op_short':c['national_operation']['any_shortage_rounds'],
                'op_missing':c['national_operation']['missing'],'food_short':c['food_short_rounds'],
                'imports':c['imports'],'exports':c['exports'],
                'emergency':getattr(game,'emergency',{}).get(n,0)}
    w=result['world']
    return {'countries':out,'op_short_sum':w['national_operation']['any_shortage_rounds'],
            'trade_goods':w['trade_goods'],'ore_end':w['remaining_goods'].get('ore',0),'fuel_end':w['remaining_goods'].get('fuel',0)}

def task(spec):
    kind,mode,prof,seed,arg=spec
    if kind=='normal':
        g=engine.Game(seed,mode=mode,operating_profile=prof)
    elif kind=='behaviors':   # several countries with inherited behaviors at once
        g=engine.Game(seed,mode=mode,operating_profile=prof,behaviors=dict(arg))
    elif kind=='skip':
        g=Skip.__new__(Skip);Skip.skip=tuple(arg);Skip.__init__(g,seed,mode=mode,operating_profile=prof)
    elif kind=='emergency':
        g=Emergency.__new__(Emergency);Emergency.skip=tuple(arg);Emergency.__init__(g,seed,mode=mode,operating_profile=prof)
    elif kind=='emerg_idle':
        g=Emergency.__new__(Emergency);Emergency.skip=();Emergency.__init__(g,seed,mode=mode,operating_profile=prof,behaviors={arg[0]:'idle'})
    try:
        res=score_game(g);res['ok']=True
    except Exception as e:
        res={'ok':False,'error':repr(e)[:300]}
    res['spec']=[kind,mode,prof,seed,list(arg) if not isinstance(arg,dict) else arg];res['mult']=Emergency.mult
    return res

SEEDS=range(132000,132030)
specs=[]
if EXP=='repro':
    specs=[('normal',m,'light',s,()) for m in ('baseline','electronics_input') for s in SEEDS]
elif EXP=='skip':
    specs=[('skip','baseline','light',s,(n,)) for n in NAMES for s in SEEDS]
elif EXP in ('class3','class3_cheap'):
    # three human-run nations behave alike at once; others are AI
    trio=('Tropia','Oilia','Technia')
    for b in (('idle','minimum') if EXP=='class3' else ('cheap',)):
        specs+=[('behaviors','baseline','light',s,tuple((n,b) for n in trio)) for s in SEEDS]
    if EXP=='class3':specs+=[('skip','baseline','light',s,trio) for s in SEEDS]
elif EXP=='fix':
    specs=[('emergency','baseline','light',s,()) for s in SEEDS]
    specs+=[('emergency','baseline','light',s,(n,)) for n in NAMES for s in SEEDS]
elif EXP.startswith('mult'):
    # mult<factor>_<part>: e.g. mult1.2_normal, mult1.2_skip, mult1.2_idle
    factor,part=EXP[4:].split('_');Emergency.mult=float(factor)
    if part=='normal':specs=[('emergency','baseline','light',s,()) for s in range(130000,130100)]
    elif part=='skip':specs=[('emergency','baseline','light',s,(n,)) for n in NAMES for s in SEEDS]
    elif part=='idle':specs=[('emerg_idle','baseline','light',s,(n,)) for n in NAMES for s in SEEDS]
    for i,x in enumerate(specs):specs[i]=x[:4]+(x[4],)
with Pool(2) as p: rows=p.map(task,specs,chunksize=4)
json.dump(rows,open(OUT,'w'))
print(EXP,'games',len(rows),'ok',sum(r['ok'] for r in rows),'fail',[r for r in rows if not r['ok']][:2])
