import json,gzip,sys,statistics as st,math
from collections import defaultdict
rows=json.load(gzip.open(sys.argv[1],'rt'))
idx={(r['mode'],r['prof'],r['seed']):r for r in rows if r['phase']=='stress' and r['style']=='normal'}
NAMES=['Tropia','Grainia','Oilia','Mechania','Mineria','Technia']
def ci(d):
    m=st.mean(d);se=st.stdev(d)/math.sqrt(len(d)) if len(d)>1 else 0;return round(m,2),round(m-1.96*se,2),round(m+1.96*se,2)
for path in sys.argv[2:]:
    new=json.load(open(path));print('###',path,len(new))
    groups=defaultdict(list)
    for g in new:
        k,mode,prof,seed,arg=g['spec']
        focal=[a[0] if isinstance(a,list) else a for a in arg] if arg else []
        k=k+(':'+arg[0][1] if arg and isinstance(arg[0],list) else '')
        groups[(k,tuple(focal) if not isinstance(arg,dict) else str(arg))].append(g)
    for key,G in groups.items():
        k,focal=key
        foc=[f for f in focal if f in NAMES]
        line=[k,focal,'n',len(G)]
        if foc:
            for f in foc:
                d=[g['countries'][f]['score']-idx[(g['spec'][1],g['spec'][2],g['spec'][3])]['sc'][f]['s'] for g in G]
                better=sum(x>1e-9 for x in d)
                parts=defaultdict(list)
                for g in G:
                    o=idx[(g['spec'][1],g['spec'][2],g['spec'][3])]['sc'][f]
                    p=g['countries'][f]['parts']
                    for a,b in (('economic_growth','econ'),('wellbeing','well'),('trade','trade'),('capacity','cap'),('utilization','util'),('reserve','reserve')):
                        parts[b].append(p[a]-o[b])
                print('  ',f,'dScore',ci(d),'better',better,'/',len(G),
                      {a:round(st.mean(v),2) for a,v in parts.items()},
                      'opShortRounds',round(st.mean(g['countries'][f]['op_short'] for g in G),2),
                      'emergencyG',round(st.mean(g['countries'][f]['emergency'] for g in G),1),
                      'dCash',round(st.mean(g['countries'][f]['cash']-idx[(g['spec'][1],g['spec'][2],g['spec'][3])]['sc'][f]['cash'] for g in G),1))
            others=[n for n in NAMES if n not in foc]
            d=[st.mean(g['countries'][n]['score'] for n in others)-st.mean(idx[(g['spec'][1],g['spec'][2],g['spec'][3])]['sc'][n]['s'] for n in others) for g in G]
            print('   others(AI) dScore',ci(d),'op_short_sum',round(st.mean(g['op_short_sum'] for g in G),2),
                  'fuel_trade',round(st.mean(g['trade_goods'].get('fuel',0) for g in G),2))
        else:
            d=[st.mean(g['countries'][n]['score'] for n in NAMES)-st.mean(idx[(g['spec'][1],g['spec'][2],g['spec'][3])]['sc'][n]['s'] for n in NAMES) for g in G]
            print('  all6 dScore',ci(d),'op_short_sum',round(st.mean(g['op_short_sum'] for g in G),2),
              {n:round(st.mean(g['countries'][n]['score']-idx[(g['spec'][1],g['spec'][2],g['spec'][3])]['sc'][n]['s'] for g in G),2) for n in NAMES})
