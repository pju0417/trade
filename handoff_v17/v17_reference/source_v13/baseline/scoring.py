"""Candidate scoring v3; changes accounting goals, never the game's cash ledger.
Goals are learned on separate train seeds, then frozen for validation.
Not a claim of equal human difficulty or validated educational assessment.
"""
import statistics
from engine import NAMES,clip

def percentile(values,q):
    x=sorted(values);i=(len(x)-1)*q;k=int(i);f=i-k
    return x[k]*(1-f)+x[min(k+1,len(x)-1)]*f

def make_goals(rows):
    return {
      'method':'75th percentile, mixed normal/invest/trade policies; independent training seeds',
      'n_training_games':len(rows),
      'economic':{n:round(max(50,percentile([r['countries'][n]['evaluated_progress'] for r in rows],.75)),6) for n in NAMES},
      'industrial':{n:round(max(.10,percentile([r['countries'][n]['growth'] for r in rows],.75)),6) for n in NAMES}}

def apply(result,goals):
    for n,x in result['countries'].items():
        # No credit for unlimited unused stock or the guaranteed basic 10G transfer.
        e=20*clip(x['evaluated_progress']/goals['economic'][n],0,1)+x['reserve_cash_score']
        i=15*clip(x['growth']/goals['industrial'][n],0,1)+10*x['utilization']
        x['score_v3']=e+x['wellbeing']+x['trade']+i
        x['economic_v3']=e;x['industry_v3']=i
    return result
