import gzip,json,sys,statistics as st,math
from collections import defaultdict
rows=json.load(gzip.open(sys.argv[1],'rt'))
NAMES=['Tropia','Grainia','Oilia','Mechania','Mineria','Technia']
mean=st.mean
def ci(d):
    m=mean(d); se=st.stdev(d)/math.sqrt(len(d)); return m,m-1.96*se,m+1.96*se
main=[r for r in rows if r['phase']=='main']
print('== 7.2 main table ==')
for mode in ('baseline','electronics_input'):
  for p in ('none','light','regular','daily'):
    R=[r for r in main if r['mode']==mode and r['prof']==p]
    cm={n:mean(r['sc'][n]['s'] for r in R) for n in NAMES}
    print(mode,p,len(R),'ore',round(mean(r['ore_end'] for r in R),2),'fuel',round(mean(r['fuel_end'] for r in R),2),
      'opO',round(mean(r['op_cons']['ore'] for r in R),2),'opF',round(mean(r['op_cons']['fuel'] for r in R),2),
      'short',round(mean(r['op_short_sum'] for r in R),2),
      'happy6',round(mean(mean(r['sc'][n]['happy'] for n in NAMES) for r in R),2),
      'country_mean_gap',round(max(cm.values())-min(cm.values()),2),
      'per_game_gap',round(mean(max(r['sc'][n]['s'] for n in NAMES)-min(r['sc'][n]['s'] for n in NAMES) for r in R),2),
      'fuel_trade',round(mean(r['trade_goods'].get('fuel',0) for r in R),2),'ore_trade',round(mean(r['trade_goods'].get('ore',0) for r in R),2))
print('== 7.3 baseline none->light per country ==')
for mode in ('baseline','electronics_input'):
 for n in NAMES:
  a=[r for r in main if r['mode']==mode and r['prof']=='none'];b=[r for r in main if r['mode']==mode and r['prof']=='light']
  f=lambda R,k:round(mean(r['sc'][n][k] for r in R),2)
  print(mode,n,'cash',f(a,'cash'),'->',f(b,'cash'),'inv',f(a,'inv'),'->',f(b,'inv'),'score',f(a,'s'),'->',f(b,'s'))
print('== paired per-game gap change & top counts ==')
idx={(r['mode'],r['prof'],r['seed']):r for r in main}
for mode in ('baseline','electronics_input'):
  for p in ('light','regular','daily'):
    d=[];tops=defaultdict(int)
    for s in range(130000,130100):
      a=idx[(mode,'none',s)];b=idx[(mode,p,s)]
      ga=max(a['sc'][n]['s'] for n in NAMES)-min(a['sc'][n]['s'] for n in NAMES)
      gb=max(b['sc'][n]['s'] for n in NAMES)-min(b['sc'][n]['s'] for n in NAMES)
      d.append(gb-ga); tops[max(NAMES,key=lambda n:b['sc'][n]['s'])]+=1
    m,lo,hi=ci(d); print(mode,'none->',p,'gap change',round(m,3),[round(lo,3),round(hi,3)],'top',dict(tops))
  tops=defaultdict(int)
  for s in range(130000,130100): tops[max(NAMES,key=lambda n:idx[(mode,'none',s)]['sc'][n]['s'])]+=1
  print(mode,'none top',dict(tops))
print('== 7.4/7.5 behaviors (stress) ==')
stress=[r for r in rows if r['phase']=='stress']
sidx={(r['mode'],r['prof'],r['style'],r['focal'],r['seed']):r for r in stress}
for p in ('none','light','regular'):
  for style in ('minimum','minimum_passive','idle','invest','trade','cheap'):
    better=0;tot=0;dh=[];sh=0;shr=[];ds=[];absS=[];rank_last=0
    for r in stress:
      if r['prof']!=p or r['style']!=style:continue
      base=sidx[(r['mode'],p,'normal',None,r['seed'])];n=r['focal']
      tot+=1;better+=r['sc'][n]['s']>base['sc'][n]['s']+1e-9
      dh.append(r['sc'][n]['happy']-base['sc'][n]['happy']);ds.append(r['sc'][n]['s']-base['sc'][n]['s'])
      sh+=r['sc'][n]['op_short']>0;shr.append(r['sc'][n]['op_short']);absS.append(r['sc'][n]['s'])
      rank_last+= r['sc'][n]['s']<=min(r['sc'][m]['s'] for m in NAMES)+1e-9
    print(p,style,'better',better,'/',tot,'dScore',round(mean(ds),2),'absScore',round(mean(absS),2),'min',round(min(absS),2),
      'last',rank_last,'opShortCases',sh,'meanShortRounds',round(mean(shr),3),'dHappy',round(mean(dh),3))
print('== idle per-country (light) ==')
for n in NAMES:
  R=[r for r in stress if r['prof']=='light' and r['style']=='idle' and r['focal']==n]
  B=[sidx[(r['mode'],'light','normal',None,r['seed'])] for r in R]
  print(n,'idle',round(mean(r['sc'][n]['s'] for r in R),2),'normal',round(mean(b['sc'][n]['s'] for b in B),2),
    'idle parts',{k:round(mean(r['sc'][n][k] for r in R),2) for k in ('econ','reserve','cap','util','well','trade')},
    'opShortRounds',round(mean(r['sc'][n]['op_short'] for r in R),2),'foodShort',round(mean(r['sc'][n]['food_short'] for r in R),2))
print('== 7.6 no_trade light ==')
for mode in ('baseline','electronics_input'):
  for p in ('none','light'):
    R=[r for r in stress if r['prof']==p and r['style']=='no_trade' and r['mode']==mode]
    B=[sidx[(mode,p,'normal',None,r['seed'])] for r in R]
    print(mode,p,len(R),'happy6',round(mean(mean(r['sc'][n]['happy'] for n in NAMES) for r in B),3),'->',round(mean(mean(r['sc'][n]['happy'] for n in NAMES) for r in R),3),
      'foodshort',round(mean(mean(r['sc'][n]['food_short'] for n in NAMES) for r in R),3),'opshort9',round(mean(r['op_short_sum'] for r in B),2),'->',round(mean(r['op_short_sum'] for r in R),2),
      'score6',round(mean(mean(r['sc'][n]['s'] for n in NAMES) for r in B),2),'->',round(mean(mean(r['sc'][n]['s'] for n in NAMES) for r in R),2))
print('== component saturation (baseline light main) ==')
R=[r for r in main if r['mode']=='baseline' and r['prof']=='light']
for n in NAMES:
  print(n,{k:round(mean(r['sc'][n][k] for r in R),2) for k in ('econ','reserve','cap','util','well','trade','s')},
    'econ_sat',sum(r['sc'][n]['econ']>=19.999 for r in R),'cap_sat',sum(r['sc'][n]['cap']>=14.999 for r in R),
    'sd',round(st.stdev(r['sc'][n]['s'] for r in R),2))
