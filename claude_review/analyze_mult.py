import json,gzip,statistics as st,math,os,sys
# usage: python3 analyze_mult.py <claude_review dir>
R=sys.argv[1] if len(sys.argv)>1 else os.path.dirname(os.path.abspath(__file__))
W=os.path.join(R,'new_games')
rows=json.load(gzip.open(os.path.join(R,'games_compact.json.gz'),'rt'))
NAMES=['Tropia','Grainia','Oilia','Mechania','Mineria','Technia']
main={r['seed']:r for r in rows if r['phase']=='main' and r['mode']=='baseline' and r['prof']=='light'}
sn={r['seed']:r for r in rows if r['phase']=='stress' and r['mode']=='baseline' and r['prof']=='light' and r['style']=='normal'}
sidle={(r['focal'],r['seed']):r for r in rows if r['phase']=='stress' and r['mode']=='baseline' and r['prof']=='light' and r['style']=='idle'}
def ci(d):
    m=st.mean(d);se=st.stdev(d)/math.sqrt(len(d));return round(m,2),round(m-1.96*se,2),round(m+1.96*se,2)
L=lambda p:json.load(open(p))
out={}
# current level (1.0 = existing penalty only)
skip0=L(f'{W}/new_skip.json')
levels={'1.0':{'skip':skip0},'1.2':{k:L(f'{W}/mult1.2_{k}.json') for k in ('normal','skip','idle')},
        '1.5':{k:L(f'{W}/mult1.5_{k}.json') for k in ('normal','skip','idle')}}
for lv,d in levels.items():
    res={}
    if 'normal' in d:
        diffs=[st.mean(g['countries'][n]['score'] for n in NAMES)-st.mean(main[g['spec'][3]]['sc'][n]['s'] for n in NAMES) for g in d['normal']]
        maxabs=max(abs(g['countries'][n]['score']-main[g['spec'][3]]['sc'][n]['s']) for g in d['normal'] for n in NAMES)
        res['normal']={'mean_diff':round(st.mean(diffs),4),'max_abs_country_diff':round(maxabs,4),
                       'emergency_games':sum(any(g['countries'][n]['emergency'] for n in g['countries']) for g in d['normal'])}
    sk={}
    for n in NAMES:
        G=[g for g in d['skip'] if g['spec'][4]==[n]]
        dd=[g['countries'][n]['score']-sn[g['spec'][3]]['sc'][n]['s'] for g in G]
        sk[n]={'d':ci(dd),'better':sum(x>1e-9 for x in dd),'n':len(G),'fee':round(st.mean(g['countries'][n]['emergency'] for g in G),1)}
    res['skip']=sk
    idl={}
    for n in NAMES:
        if 'idle' in d:
            G=[g for g in d['idle'] if g['spec'][4]==[n]]
            sc=[g['countries'][n]['score'] for g in G]
            cur=[sidle[(n,g['spec'][3])]['sc'][n]['s'] for g in G]
            idl[n]={'score':round(st.mean(sc),2),'vs_current_idle':round(st.mean(a-b for a,b in zip(sc,cur)),2),
                    'fee':round(st.mean(g['countries'][n]['emergency'] for g in G),1),'normal':round(st.mean(sn[g['spec'][3]]['sc'][n]['s'] for g in G),2)}
        else:
            G=[r for (f,s),r in sidle.items() if f==n]
            idl[n]={'score':round(st.mean(r['sc'][n]['s'] for r in G),2)}
    res['idle']=idl
    crit1=all(sk[n]['d'][0]<0 and sk[n]['better']<=5 for n in NAMES)
    res['criteria']={'skip_loses_all_and_better<=5':crit1,
                     'normal_change<0.5':(abs(res['normal']['mean_diff'])<0.5) if 'normal' in res else True}
    out[lv]=res
print(json.dumps(out,ensure_ascii=False,indent=1))
json.dump(out,open(os.path.join(W,'mult_comparison.json'),'w'),ensure_ascii=False,indent=1)
# consistency: mult1.5_skip vs earlier new_fix
fix=L(f'{W}/new_fix.json');a={(tuple(g['spec'][4]),g['spec'][3]):g for g in fix if g['spec'][4]}
mx=max(abs(g['countries'][n]['score']-a[(tuple(g['spec'][4]),g['spec'][3])]['countries'][n]['score']) for g in levels['1.5']['skip'] for n in NAMES)
print('1.5 skip rerun vs earlier fix max diff',mx)
