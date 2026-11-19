"""Independent v17 national-operation audit. Never import or execute a game.

Schedules, physical conservation, income, score arithmetic and reported paired
statistics are reconstructed from frozen evidence using the standard library.
"""
from __future__ import annotations

import argparse
from array import array
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
from itertools import zip_longest
import json
import math
from pathlib import Path
import statistics
import time

ROOT = Path(__file__).resolve().parent
NAMES = ('Tropia','Grainia','Oilia','Mechania','Mineria','Technia')
ADDED = ('Novia','Agrea','Ferria')
ALL_NAMES = NAMES+ADDED
GOODS = ('banana','wheat','fuel','ore','machine','electronics')
RAW = ('ore','fuel')
PRICES = dict(zip(GOODS,(10,10,30,20,50,80)))
BASES = {
    'Tropia': {'banana':4,'wheat':2},
    'Grainia': {'wheat':3,'banana':2},
    'Oilia': {'fuel':1,'ore':1,'banana':1},
    'Mechania': {'machine':2,'wheat':2},
    'Mineria': {'ore':1,'fuel':1},
    'Technia': {'electronics':1,'machine':1,'wheat':1},
    'Novia': {'electronics':1,'wheat':1},
    'Agrea': {'banana':2,'fuel':1},
    'Ferria': {'ore':1,'wheat':2},
}
ECON_GOALS = dict(zip(NAMES,(305,265,245,230,185,895)))
INDUSTRY_GOALS = dict(zip(NAMES,(1/3,.4,5/6,5/12,.6,1.5)))
PROFILES = ('none','light','regular','daily')
SCHEDULES = {
    'none': {'fuel':(), 'ore':()},
    'light': {'fuel':(3,6,9),'ore':(4,8)},
    'regular': {'fuel':(2,4,6,8),'ore':(3,6,9)},
    'daily': {'fuel':tuple(range(1,10)),'ore':(3,6,9)},
}
PENALTIES = {'fuel':8,'ore':4}
MODES = ('baseline','electronics_input')
STYLES = ('minimum','idle','invest','trade','minimum_passive')
SOURCES = ('initial_own','initial_foreign','produced_own','produced_foreign')
RAW_COUNTS = ('consumed','production','research','national','imported_used')+SOURCES
BASE_FIELDS = ('cash','happy','revenue','purchases','investment','tax','exports','imports',
               'useful_exports','useful_imports','food_short_rounds','low_cash_rounds',
               'production_failures','upgrades_total','machine_gen','elec_gen','min_observed_cash')
GROWTH_FIELDS = ('asset_gain','capacity_growth','initial_capacity','final_capacity','unused_stock_value',
                 'stock_value','produced_units','used_units','utilization')
GOOD_MAPS = ('produced','use_by_good','export_used_by_good','import_goods','export_goods',
             'end_stock_by_good','unused_by_good','purchase_by_good','sale_by_good')
SCORE_FIELDS = ('score','economic_growth','reserve','capacity','utilization','wellbeing','trade','economic','industry','top')
WORLD_FIELDS = ('transactions','trade_units','happy','original_happy','original_cash','cash_total','tax',
                'investment','original_food_short','original_production_failures','inventory')
TOL = 1e-9


class Audit:
    def __init__(self):
        self.counts=Counter();self.errors=[]
    def require(self, condition, check, detail=None):
        self.counts[check]+=1
        if not condition:
            error={'check':check,'detail':detail};self.errors.append(error)
            raise AssertionError(error)
    def close(self, actual, expected, check, detail=None):
        self.require(type(actual) in (int,float) and math.isfinite(actual)
                     and math.isclose(actual,expected,rel_tol=1e-11,abs_tol=1e-8),
                     check,detail if detail is not None else [actual,expected])
    def same(self, actual, expected, check, path=''):
        if isinstance(expected,dict):
            self.require(isinstance(actual,dict) and set(actual)==set(expected),check+'.keys',path)
            for key,value in expected.items():self.same(actual[key],value,check,path+'.'+str(key))
        elif isinstance(expected,(list,tuple)):
            self.require(isinstance(actual,(list,tuple)) and len(actual)==len(expected),check+'.length',path)
            for index,(a,b) in enumerate(zip(actual,expected)):self.same(a,b,check,path+'.'+str(index))
        elif type(expected) in (int,float):self.close(actual,expected,check+'.numeric',path)
        else:self.require(actual==expected,check+'.value',path)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def json_lines(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f:yield json.loads(line)


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def value_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def object_items(path):
    """Stream a potentially large gzip JSON object of full physical traces."""
    decoder=json.JSONDecoder()
    with gzip.open(path,'rt',encoding='utf-8') as f:
        buffer='';eof=False
        def more():
            nonlocal buffer,eof
            text=f.read(1048576);buffer+=text;eof=not text
        def white():
            nonlocal buffer
            buffer=buffer.lstrip()
            while not buffer and not eof:more();buffer=buffer.lstrip()
        def token():
            nonlocal buffer
            while True:
                white()
                try:
                    value,end=decoder.raw_decode(buffer);buffer=buffer[end:];return value
                except json.JSONDecodeError:
                    if eof:raise
                    more()
        more();white()
        if not buffer.startswith('{'):raise ValueError('Trace object required')
        buffer=buffer[1:]
        while True:
            white()
            if buffer.startswith('}'):
                buffer=buffer[1:];white()
                if buffer:raise ValueError('Trailing JSON')
                return
            key=token();white()
            if not isinstance(key,str) or not buffer.startswith(':'):raise ValueError('Invalid object member')
            buffer=buffer[1:];yield key,token();white()
            if buffer.startswith(','):buffer=buffer[1:]
            elif not buffer.startswith('}'):raise ValueError('Invalid object separator')


def clip(value):return min(1.,max(0.,value))


def potential_capacity(name,levels):
    return sum(PRICES[g]*(BASES[name].get(g,1)+(lv-1)*(2 if g in ('banana','wheat') else 1))
               for g,lv in levels.items() if lv>0)


def expected_score(c,name):
    if name not in NAMES:return None
    m=c['growth_metrics'];used=sum(c['use_by_good'].values());produced=sum(c['produced'].values())
    e=20*clip(m['asset_gain']/ECON_GOALS[name]);reserve=5*clip(c['cash']/m['reserve_target'])
    cap=15*clip(m['capacity_growth']/INDUSTRY_GOALS[name]);use=10*used/max(1,produced)
    wellbeing=c['happy']/4;trade=c['trade']
    return {'economic_growth':e,'reserve':reserve,'capacity':cap,'utilization':use,
            'wellbeing':wellbeing,'trade':trade,'economic':e+reserve,'industry':cap+use,
            'score':e+reserve+cap+use+wellbeing+trade}


def expected_schedule():
    cases=[(None,'normal')]+[(n,s) for n in NAMES for s in STYLES]+[('Technia','cheap'),(None,'no_trade')]
    expected={('main',m,p,'None:normal',seed) for p in PROFILES for m in MODES for seed in range(130000,130100)}
    expected|={('stress',m,p,f'{n}:{s}',seed) for p in PROFILES[:3] for m in MODES
               for n,s in cases for seed in range(132000,132030)}
    assert len(expected)==6740
    return expected


def identity(row):
    return tuple(row[k] for k in ('phase','mode','operating_profile','scenario','seed'))


def stats(values,paired=False):
    values=list(values);n=len(values)
    if not n:raise ValueError('No observations')
    mean=statistics.mean(values);width=1.96*statistics.stdev(values)/math.sqrt(n) if n>1 else 0
    result={'n':n,'mean':mean,'ci95':[mean-width,mean+width],'min':min(values),'max':max(values)}
    if paired:result.update(up=sum(x>TOL for x in values),down=sum(x<-TOL for x in values),tie=sum(abs(x)<=TOL for x in values))
    return result


def nonnegative_int(audit,value,check,detail=None):
    audit.require(type(value) is int and value>=0,check,detail)


def verify_growth(audit,c,name):
    m=c['growth_metrics'];produced=sum(c['produced'].values());used=sum(c['use_by_good'].values())
    audit.close(m['produced_units'],produced,'produced_count')
    audit.close(m['used_units'],used,'used_count')
    audit.require(0<=used<=produced,'used_bound')
    for good in GOODS:
        audit.require(0<=c['use_by_good'].get(good,0)<=c['produced'].get(good,0),'per_good_used_bound')
    initial=potential_capacity(name,{g:1 for g in BASES[name]});final=potential_capacity(name,c['end_levels'])
    audit.close(m['initial_capacity'],initial,'initial_capacity')
    audit.close(m['final_capacity'],final,'final_capacity')
    audit.close(m['capacity_growth'],(final-initial)/initial,'capacity_growth')
    audit.close(m['asset_gain'],m['end_asset_value']-m['start_asset_value'],'asset_gain')
    audit.close(m['end_asset_value'],c['cash']+m['stock_value']+.45*c['investment'],'end_assets')
    audit.close(m['utilization'],used/max(1,produced),'use_ratio')
    audit.close(m['utilization_score'],10*used/max(1,produced),'use_points')
    audit.close(m['wellbeing_score'],c['happy']/4,'wellbeing_points')
    audit.close(m['trade_score'],c['trade'],'trade_points')
    audit.close(c['cash']-c['start_cash'],c['revenue']-c['purchases']-c['investment']+c['tax'],'whole_game_cash')


def verify_money_raw(audit,record,cash_rows,raw_rows):
    expected={(r,n) for r in range(1,10) for n in ALL_NAMES}
    cash={(r['round'],r['country']):r for r in cash_rows}
    raw={(r['round'],r['country']):r for r in raw_rows}
    audit.require(len(cash_rows)==len(raw_rows)==81 and set(cash)==set(raw)==expected,
                  'complete_cash_raw_rounds')
    countries=record['countries'];world=record['world']
    for n,c in countries.items():
        rows=[cash[r,n] for r in range(1,10)]
        previous=c['start_cash']
        for row in rows:
            audit.close(row['cash_start'],previous,'cash_continuity')
            audit.close(row['cash_end'],row['cash_start']+row['sales']-row['purchases']
                        -row['investment']+row['operating_income'],'round_cash_conservation')
            audit.require(row['cash_end']>=0,'nonnegative_cash')
            audit.close(row['operating_income'],10+math.floor(row['happy']/10+.5),'satisfaction_income')
            audit.close(sum(row['purchase_by_good'].values()),row['purchases'],'purchases_by_good')
            audit.close(sum(row['sale_by_good'].values()),row['sales'],'sales_by_good')
            previous=row['cash_end']
        audit.close(previous,c['cash'],'cash_final')
        for field,source in (('revenue','sales'),('purchases','purchases'),('investment','investment'),('tax','operating_income')):
            audit.close(c[field],sum(r[source] for r in rows),'cash_summary_'+field)
        audit.close(c['happy'],statistics.mean(r['happy'] for r in rows),'mean_satisfaction')
        for g in RAW:
            previous=c['starter_raw'][g]
            for r in range(1,10):
                row=raw[r,n];x=row['goods'][g];money=cash[r,n]
                audit.close(row['cash'],money['cash_end'],'raw_cash_connection')
                audit.close(row['happy'],money['happy'],'raw_happy_connection')
                for field in RAW_COUNTS:
                    nonnegative_int(audit,x.get(field,0),'raw_count_integer',[n,r,g,field])
                audit.close(x['opening_stock'],previous,'raw_stock_continuity')
                audit.close(x['stock'],x['opening_stock']+x['produced']+x['imports']-x['exports']-x['consumed'],
                            'raw_physical_conservation')
                audit.close(x['consumed'],x['production']+x['research']+x.get('national',0),'raw_purpose_partition')
                audit.close(x['consumed'],sum(x[s] for s in SOURCES),'raw_source_partition')
                audit.require(x['imported_used']<=x['consumed'],'raw_import_use_bound')
                audit.close(x['purchases'],money['purchase_by_good'][g],'raw_purchase_connection')
                audit.close(x['sales'],money['sale_by_good'][g],'raw_sales_connection')
                for value in x['machine_credits_by_grade'].values():
                    audit.require(type(value) is int and 0<=value<2,'machine_credit_bound')
                previous=x['stock']
            audit.close(previous,c['end_stock_by_good'][g],'raw_final_stock')
            for field in RAW_COUNTS:
                total=sum(raw[r,n]['goods'][g].get(field,0) for r in range(1,10))
                audit.close(c['raw_use'][g].get(field,0),total,'raw_summary_'+field)
            for source,target in (('imports','import_goods'),('exports','export_goods'),('purchases','purchase_by_good'),('sales','sale_by_good'),('produced','produced')):
                audit.close(c[target][g],sum(raw[r,n]['goods'][g][source] for r in range(1,10)),'raw_flow_summary_'+source)
            audit.close(c['production_raw'][g],c['raw_use'][g]['production'],'production_raw_summary')
            audit.close(c['research_raw'][g],c['raw_use'][g]['research'],'research_raw_summary')
            audit.close(c['raw_unmet_production'][g],sum(raw[r,n]['goods'][g]['unmet_production'] for r in range(1,10)),
                        'unmet_production_summary')
    for r in range(1,10):
        audit.close(sum(cash[r,n]['sales'] for n in ALL_NAMES),sum(cash[r,n]['purchases'] for n in ALL_NAMES),'round_cash_trade_conservation')
        for g in RAW:
            audit.close(sum(raw[r,n]['goods'][g]['imports'] for n in ALL_NAMES),sum(raw[r,n]['goods'][g]['exports'] for n in ALL_NAMES),'round_raw_trade_conservation')
    audit.close(world['cash_total'],sum(c['cash'] for c in countries.values()),'world_cash_total')
    audit.close(world['cash_total'],world['initial_cash']+world['tax']-world['investment'],'world_cash_conservation')
    audit.close(world['tax'],sum(c['tax'] for c in countries.values()),'world_income')
    audit.close(world['investment'],sum(c['investment'] for c in countries.values()),'world_investment')
    for g in RAW:
        for field in RAW_COUNTS:
            audit.close(world['raw_use'][g].get(field,0),sum(c['raw_use'][g].get(field,0) for c in countries.values()),'world_raw_'+field)
        audit.close(world['remaining_goods'][g],sum(c['end_stock_by_good'][g] for c in countries.values()),'world_remaining_raw')
        audit.close(world['production'][g],sum(c['produced'][g] for c in countries.values()),'world_produced_raw')
        audit.close(world['consumed'][g],world['raw_use'][g]['consumed'],'world_consumed_raw')
    return cash,raw


def numeric_leaves(obj,prefix=''):
    answer={}
    if isinstance(obj,dict):
        for k,v in obj.items():answer.update(numeric_leaves(v,prefix+'.'+k if prefix else k))
    elif type(obj) in (int,float):answer[prefix]=obj
    return answer


def analytical_fields(row):
    """Rebuild declared numerical analysis inputs, independently from its code."""
    out={}
    for n in ALL_NAMES:
        c=row['countries'][n];prefix='countries.'+n+'.'
        for field in BASE_FIELDS:out[prefix+field]=c[field]
        for field in GROWTH_FIELDS:out[prefix+'growth_metrics.'+field]=c['growth_metrics'][field]
        for field in GOOD_MAPS:
            for good in GOODS:out[prefix+field+'.'+good]=c[field][good]
        for good in RAW:
            for field in ('consumed','production','research','national','imported_used'):
                out[prefix+'raw_use.'+good+'.'+field]=c['raw_use'][good].get(field,0)
            out[prefix+'raw_unmet_production.'+good]=c['raw_unmet_production'][good]
            out[prefix+'own_produced_never_used.'+good]=c['produced'][good]-c['use_by_good'][good]
            out[prefix+'national_operation_origin_used.'+good]=c['national_operation_origin_used'][good]
        out.update(numeric_leaves(c['national_operation'],prefix+'national_operation'))
        if n in NAMES:
            for field in SCORE_FIELDS:out[prefix+'fixed_evaluation.'+field]=c['fixed_evaluation'][field]
    w=row['world']
    for field in WORLD_FIELDS:out['world.'+field]=w[field]
    for field in ('production','consumed','trade_goods','remaining_goods','aged_unused_goods','end_prices'):
        for good in GOODS:out['world.'+field+'.'+good]=w[field][good]
    for good in RAW:
        for field in ('consumed','production','research','national','imported_used'):
            out['world.raw_use.'+good+'.'+field]=w['raw_use'][good].get(field,0)
        out['world.raw_unmet_production.'+good]=w['raw_unmet_production'][good]
        out['world.own_produced_never_used.'+good]=sum(c['produced'][good]-c['use_by_good'][good] for c in row['countries'].values())
        out['world.national_operation_origin_used.'+good]=sum(c['national_operation_origin_used'][good] for c in row['countries'].values())
    out.update(numeric_leaves(w['national_operation'],'world.national_operation'))
    out['world.fixed_evaluation.score_spread']=w['fixed_evaluation']['score_spread']
    return out


def verify_national(audit,record,rows,cash,raw):
    profile=record['operating_profile'];expected={(r,n) for r in range(1,10) for n in ALL_NAMES}
    keyed={(x['round'],x['country']):x for x in rows}
    audit.require(len(rows)==81 and set(keyed)==expected,'national_round_schedule')
    seen_ids=set();origin_used=Counter();evidence_by_uid={}
    for key,x in keyed.items():
        r,n=key
        audit.require(x['profile']==profile,'national_profile')
        required={g:int(r in SCHEDULES[profile][g]) for g in RAW}
        audit.same(x['required'],required,'national_required',str(key))
        for g in RAW:
            actual=min(required[g],x['available_before'][g]);missing=required[g]-actual
            audit.close(x['consumed'][g],actual,'national_consumed_available')
            audit.close(x['missing'][g],missing,'national_missing')
            audit.close(x['stock_after'][g],x['stock_before'][g]-actual,'national_physical_stock')
            audit.require(0<=x['available_before'][g]<=x['stock_before'][g],'national_free_stock_bound')
            audit.require(0<=x['own_origin_before'][g]<=x['stock_before'][g],'national_own_stock_bound')
            audit.close(raw[r,n]['goods'][g].get('national',0),actual,'national_raw_ledger_connection')
            ids=x['used_ids'][g];evidence=x['used_unit_evidence'][g]
            audit.require(len(ids)==actual==len(evidence) and len(set(ids))==len(ids),'national_physical_count')
            audit.require(ids==[v['uid'] for v in evidence],'national_evidence_identity')
            for unit in evidence:
                uid=unit['uid']
                audit.require(type(uid) is int and uid>0,'national_physical_uid_type')
                audit.require(uid not in seen_ids,'national_unique_consumed_uid')
                seen_ids.add(uid);evidence_by_uid[uid]=(r,n,g,unit)
                audit.require(unit['good']==g and unit['origin'] in ALL_NAMES,'national_unit_kind')
                audit.require(unit['owner_before']==n and unit['order_before'] is None,'national_owned_unlisted')
                audit.require(type(unit['born']) is int and 0<=unit['born']<=r,'national_unit_birth')
                if unit['born']>0:origin_used[unit['origin'],g]+=1
        penalty=sum(PENALTIES[g]*x['missing'][g]/required[g] for g in RAW if required[g])
        happy=round(max(0,x['base_happy']-penalty),6)
        base_tax=10+math.floor(x['base_happy']/10+.5)
        tax=10+math.floor(happy/10+.5)
        audit.close(x['penalty'],penalty,'national_penalty')
        audit.close(x['happy'],happy,'national_final_happy')
        audit.close(x['base_tax'],base_tax,'national_base_income')
        audit.close(x['round_income'],tax,'national_final_income')
        audit.close(x['tax_effect'],tax-base_tax,'national_income_effect')
        for before,after in (('cash_before','cash_after'),('tax_before','tax_after'),('minted_before','minted_after')):
            audit.close(x[after]-x[before],tax,'national_single_income_update')
        pop=2+int(r>=5)+int(r>=8);food=1+int(r>=5)+int(r>=8)
        audit.close(x['need_slots_after']-x['need_slots_before'],2*food+math.ceil(pop/2)+sum(required.values()),
                    'national_need_slots_once')
        audit.close(cash[r,n]['happy'],happy,'national_cash_happy_connection')
        audit.close(cash[r,n]['operating_income'],tax,'national_cash_income_connection')
    for n,c in record['countries'].items():
        selected=[keyed[r,n] for r in range(1,10)]
        totals={key:{g:sum(x[key][g] for x in selected) for g in RAW} for key in ('required','consumed','missing')}
        totals.update(shortage_rounds={g:sum(x['missing'][g]>0 for x in selected) for g in RAW},
                      any_shortage_rounds=sum(any(x['missing'].values()) for x in selected),
                      penalty_total=sum(x['penalty'] for x in selected),
                      penalty_mean=statistics.mean(x['penalty'] for x in selected),
                      base_happy_mean=statistics.mean(x['base_happy'] for x in selected),
                      final_happy_mean=statistics.mean(x['happy'] for x in selected),
                      tax_effect=sum(x['tax_effect'] for x in selected))
        audit.same(c['national_operation'],totals,'national_country_summary',n)
        audit.same(c['national_operation_origin_used'],{g:origin_used[n,g] for g in RAW},'national_producer_credit',n)
    totals={key:{g:sum(c['national_operation'][key][g] for c in record['countries'].values()) for g in RAW}
            for key in ('required','consumed','missing','shortage_rounds')}
    totals.update({key:sum(c['national_operation'][key] for c in record['countries'].values())
                   for key in ('any_shortage_rounds','penalty_total','tax_effect')})
    totals['profile']=profile
    audit.same(record['world']['national_operation'],totals,'national_world_summary')
    for g in RAW:
        audit.close(totals['required'][g],9*len(SCHEDULES[profile][g]),'national_fixed_world_obligations')
    return keyed,evidence_by_uid


def group_name(key):return ':'.join(map(str,key[:4]))


def verify_statistics(audit,summary,data,paths):
    groups=defaultdict(dict)
    for key,values in data.items():groups[key[:4]][key[4]]=values
    audit.require(len(groups)==206 and set(summary['groups'])=={group_name(k) for k in groups},'statistics_group_set')
    index={p:i for i,p in enumerate(paths)}
    def value(a,p):return a[index[p]]
    for key,seeds in groups.items():
        name=group_name(key);actual=summary['groups'][name]
        audit.require(actual['n']==len(seeds)==(100 if key[0]=='main' else 30),'statistics_group_n')
        audit.require(set(actual['stats'])==set(paths),'statistics_metric_set')
        for p in paths:
            audit.same(actual['stats'][p],stats(value(v,p) for v in seeds.values()),'group_statistics',name+':'+p)
        means={n:statistics.mean(value(v,f'countries.{n}.fixed_evaluation.score') for v in seeds.values()) for n in NAMES}
        top={n:sum(value(v,f'countries.{n}.fixed_evaluation.top') for v in seeds.values()) for n in NAMES}
        expected={'country_mean_score_range':max(means.values())-min(means.values()),
                  'mean_within_game_score_range':statistics.mean(value(v,'world.fixed_evaluation.score_spread') for v in seeds.values()),
                  'top_counts_including_ties':top,
                  'highest_mean_countries':[n for n in NAMES if means[n]>=max(means.values())-TOL],
                  'lowest_mean_countries':[n for n in NAMES if means[n]<=min(means.values())+TOL],
                  'tie_games':sum(sum(value(v,f'countries.{n}.fixed_evaluation.top') for n in NAMES)>1 for v in seeds.values())}
        audit.same(actual['score_diagnostics'],expected,'group_rank_diagnostics',name)
    contrasts={}
    all_cases=['None:normal']+[f'{n}:{s}' for n in NAMES for s in STYLES]+['Technia:cheap','None:no_trade']
    for phase in ('main','stress'):
        profiles=PROFILES if phase=='main' else PROFILES[:3]
        cases=['None:normal'] if phase=='main' else all_cases
        for mode in MODES:
            for case in cases:
                for profile in profiles[1:]:
                    contrasts[('profile_comparisons',f'profile:{phase}:{mode}:{case}:none->{profile}')]=(
                        (phase,mode,'none',case),(phase,mode,profile,case))
        for profile in profiles:
            for case in cases:
                contrasts[('economic_comparisons',f'economy:{phase}:{profile}:{case}:baseline->electronics_input')]=(
                    (phase,'baseline',profile,case),(phase,'electronics_input',profile,case))
    for mode in MODES:
        for profile in PROFILES[:3]:
            for case in all_cases[1:]:
                contrasts[('behavior_comparisons',f'behavior:{mode}:{profile}:{case}')]=(
                    ('stress',mode,profile,'None:normal'),('stress',mode,profile,case))
    for section,count in (('profile_comparisons',138),('economic_comparisons',103),('behavior_comparisons',192)):
        wanted={k for s,k in contrasts if s==section}
        audit.require(len(wanted)==count and set(summary[section])==wanted,'paired_comparison_set',section)
    for (section,name),(a,b) in contrasts.items():
        before,after=groups[a],groups[b]
        audit.require(set(before)==set(after),'paired_seed_set',name)
        actual=summary[section][name]
        audit.require(actual['n']==len(before) and set(actual['stats'])==set(paths),'paired_metric_schedule',name)
        for p in paths:
            differences=(value(after[seed],p)-value(before[seed],p) for seed in sorted(before))
            audit.same(actual['stats'][p],stats(differences,True),'paired_statistics',name+':'+p)
    return groups,index


def verify_physical_traces(audit,results,metadata):
    expected={key for key in metadata if key[0]=='main' or key[-1]==132000}
    seen=set();unit_total=0;plan_total=0
    for _,t in object_items(results/'representative_traces.json.gz'):
        key=identity(t)
        audit.require(key in expected and key not in seen,'trace_identity',key);seen.add(key)
        audit.require(value_hash(t['result'])==metadata[key]['record_sha256'],'trace_result_connection')
        audit.require(value_hash(t['operating_ledger'])==metadata[key]['national_sha256'],'trace_national_connection')
        audit.require(value_hash(t['cash_ledger'])==metadata[key]['cash_sha256'],'trace_cash_connection')
        audit.require(value_hash(t['raw_ledger'])==metadata[key]['raw_sha256'],'trace_raw_connection')
        units={int(k):v for k,v in t['units'].items()};unit_total+=len(units)
        episodes=t['development_uses'];episode_keys=[(x['round'],x['country'],x['uid'],x['purpose']) for x in episodes]
        audit.require(len(episode_keys)==len(set(episode_keys)),'physical_unique_use_episodes')
        used_ids={x['uid'] for x in episodes}
        for uid,u in units.items():
            audit.require(uid==u['uid'] and u['origin'] in ALL_NAMES and u['good'] in GOODS,'physical_uid_identity')
            audit.require(type(u['born']) is int and 0<=u['born']<=9,'physical_uid_birth')
            audit.require(bool(u['used'])==(uid in used_ids),'physical_used_has_episode')
            if u['used']:audit.require(u['born']<=u['use_round']<=9,'physical_use_after_birth')
        national={(x['round'],x['country'],g):(x,g) for x in t['operating_ledger'] for g in RAW if x['required'][g]}
        needs={}
        for x in t['needs_ledger']:
            audit.require(0<=x['fulfilled']<=x['external']<=x['needed'],'physical_need_bounds')
            if x['purpose']=='national':
                nk=(x['round'],x['country'],x['good'])
                audit.require(nk not in needs,'physical_national_need_unique');needs[nk]=x
        audit.require(set(needs)==set(national),'physical_national_need_schedule')
        national_ids=set()
        for nk,(row,g) in national.items():
            need=needs[nk];r,n,_=nk
            audit.close(need['needed'],row['required'][g],'physical_national_requested')
            audit.same(need['used_ids'],row['used_ids'][g],'physical_national_need_uses')
            external=max(0,row['required'][g]-row['own_origin_before'][g])
            imported=sum(x['origin']!=n and x['last_import'] is not None for x in row['used_unit_evidence'][g])
            audit.close(need['external'],external,'physical_national_external')
            audit.close(need['fulfilled'],min(external,imported),'physical_national_fulfilled')
            for proof in row['used_unit_evidence'][g]:
                uid=proof['uid'];u=units[uid];national_ids.add(uid)
                audit.require(u['owner'] is None and u['used'] and u['order'] is None,'physical_national_destroyed')
                audit.require((u['use_country'],u['use_round'],u['use_purpose'])==(n,r,'national'),'physical_national_first_use')
                audit.require((u['good'],u['origin'],u['born'])==(g,proof['origin'],proof['born']),'physical_national_evidence')
                if proof['last_import'] is not None:
                    tx=t['transactions'][proof['last_import']]
                    audit.require(tx['round']<=r and any(z['buyer']==n and uid in z['ids'] for z in tx['legs']),
                                  'physical_national_import_provenance')
        raw_use=t['raw_use'];raw_ids=[x['uid'] for x in raw_use]
        audit.require(len(raw_ids)==len(set(raw_ids)),'physical_unique_raw_consumption')
        raw_counts=defaultdict(Counter)
        for x in raw_use:
            u=units[x['uid']]
            audit.require(u['owner'] is None and u['used'] and u['good']==x['good'],'physical_raw_destroyed')
            audit.require((u['use_country'],u['use_round'],u['use_purpose'])==(x['country'],x['round'],x['purpose']),
                          'physical_raw_purpose')
            source=('initial_' if u['born']==0 else 'produced_')+('own' if u['origin']==x['country'] else 'foreign')
            audit.require(x['source']==source and x['born']==u['born'] and x['origin']==u['origin'],'physical_raw_source')
            audit.require(x['purpose'] in ('production','development','national'),'physical_raw_allowed_purposes')
            counted=raw_counts[x['round'],x['country'],x['good']]
            counted['consumed']+=1;counted[source]+=1
            counted[{'production':'production','development':'research','national':'national'}[x['purpose']]]+=1
            counted['imported_used']+=int(x['import_transaction'] is not None)
        for row in t['raw_ledger']:
            for g in RAW:
                for field in RAW_COUNTS:
                    audit.close(row['goods'][g].get(field,0),raw_counts[row['round'],row['country'],g][field],
                                'physical_raw_ledger_from_uid')
        audit.require(national_ids=={x['uid'] for x in raw_use if x['purpose']=='national'},'physical_national_raw_log')
        audit.same(t['operating_use'],[x for x in raw_use if x['purpose']=='national'],'physical_national_log_filter')
        # Rebuild meaningful foreign uses from real use episodes and their actual
        # import transactions; repeated use of a durable never multiplies units.
        first_foreign={};import_partners=defaultdict(set)
        for e in sorted(episodes,key=lambda x:(x['round'],x['country'],x['uid'],x['purpose'])):
            uid=e['uid'];n=e['country'];u=units[uid]
            if u['origin']!=n and e['import_transaction'] is not None:
                pair=(uid,n)
                if pair not in first_foreign:
                    first_foreign[pair]=e['round']
                    tx=t['transactions'][e['import_transaction']]
                    legs=[x for x in tx['legs'] if uid in x['ids'] and x['buyer']==n]
                    audit.require(len(legs)==1 and tx['round']<=e['round'],'physical_foreign_use_import')
                    import_partners[n].add(legs[0]['seller'])
        foreign_ids={uid for uid,_ in first_foreign}
        flows=defaultdict(Counter);payments=defaultdict(Counter)
        for tx in t['transactions']:
            r=tx['round']
            for leg in tx['legs']:
                audit.require(leg['seller']!=leg['buyer'] and len(leg['ids'])==len(set(leg['ids'])),
                              'physical_trade_leg_unique_ids')
                for uid in leg['ids']:
                    u=units[uid]
                    audit.require(u['born']<=r,'physical_trade_after_production')
                    flows[r,leg['seller'],u['good']]['exports']+=1
                    flows[r,leg['buyer'],u['good']]['imports']+=1
            if tx['cash']:
                payer,payee,amount=tx['cash']
                audit.require(amount>=0 and payer!=payee,'physical_trade_cash_leg')
                payments[r,payer]['purchases']+=amount;payments[r,payee]['sales']+=amount
        born=Counter((u['born'],u['origin'],u['good']) for u in units.values())
        destroyed=Counter((u['use_round'],u['use_country'],u['good']) for u in units.values() if u['owner'] is None)
        stock=Counter((u['origin'],u['good']) for u in units.values() if u['born']==0)
        for row in sorted(t['cash_ledger'],key=lambda x:(x['round'],x['country'])):
            r,n=row['round'],row['country']
            for field in ('purchases','sales'):audit.close(row[field],payments[r,n][field],'physical_transaction_cash')
            for g in GOODS:
                stock[n,g]+=born[r,n,g]+flows[r,n,g]['imports']-flows[r,n,g]['exports']-destroyed[r,n,g]
                audit.close(row['stock'].get(g,0),stock[n,g],'physical_all_goods_round_stock')
                audit.require(stock[n,g]>=0,'physical_nonnegative_stock')
        for n,c in t['result']['countries'].items():
            own=[u for u in units.values() if u['origin']==n and u['born']>0]
            used=[u for u in own if u['used']]
            audit.close(len(own),c['growth_metrics']['produced_units'],'physical_produced_count')
            audit.close(len(used),c['growth_metrics']['used_units'],'physical_used_count')
            owned=[u for u in units.values() if u['owner']==n]
            def nominal(u):return PRICES[u['good']]*({1:1,2:1.4,3:1.8}[u['gen']] if u['good'] in ('machine','electronics') else 1)
            unused_value=sum(nominal(u)*.15 for u in owned if not u['used'])
            used_value=sum(nominal(u)*(.5 if u['good'] in ('machine','electronics') else .15) for u in owned if u['used'])
            audit.close(c['growth_metrics']['unused_stock_value'],unused_value,'physical_unused_stock_valuation')
            audit.close(c['growth_metrics']['used_stock_value'],used_value,'physical_used_stock_valuation')
            audit.close(c['growth_metrics']['stock_value'],unused_value+used_value,'physical_total_stock_valuation')
            initial_value=sum(nominal(u)*.15 for u in units.values() if u['born']==0 and u['origin']==n)
            audit.close(c['growth_metrics']['start_asset_value'],c['start_cash']+initial_value,'physical_initial_asset_valuation')
            for g in GOODS:
                audit.close(sum(u['good']==g for u in own),c['produced'][g],'physical_produced_good')
                audit.close(sum(u['good']==g for u in used),c['use_by_good'][g],'physical_used_good')
                audit.close(sum(u['good']==g for u in owned),c['end_stock_by_good'][g],'physical_end_stock')
                audit.close(sum(u['good']==g and not u['used'] for u in owned),c['unused_by_good'][g],'physical_unused_stock')
            exported={u['uid'] for u in own if u['uid'] in foreign_ids}
            er={r for (uid,_),r in first_foreign.items() if uid in exported}
            partners=import_partners[n] | {buyer for uid,buyer in first_foreign if uid in exported}
            cr=[x for x in t['needs_ledger'] if x['country']==n]
            ext=sum(x['external'] for x in cr);filled=sum(x['fulfilled'] for x in cr)
            erounds={x['round'] for x in cr if x['external']};frounds={x['round'] for x in cr if x['fulfilled']}
            trade=9*min(1,len(er)/6)+(8*filled/ext if ext else 0)+4*min(1,len(partners)/3)+(4*len(frounds)/len(erounds) if erounds else 0)
            audit.close(c['trade'],trade,'physical_trade_score')
            audit.close(c['useful_exports'],len(exported),'physical_useful_exports')
            audit.close(c['useful_imports'],len({uid for uid,buyer in first_foreign if buyer==n}),'physical_useful_imports')
            audit.close(c['useful_partners'],len(partners),'physical_useful_partners')
            for g in GOODS:
                audit.close(c['export_goods'][g],sum(flows[r,n,g]['exports'] for r in range(1,10)),'physical_export_units')
                audit.close(c['import_goods'][g],sum(flows[r,n,g]['imports'] for r in range(1,10)),'physical_import_units')
        # Household base satisfaction reconstructed before the new penalties.
        household={(x['round'],x['country'],x['good']):x for x in t['needs_ledger'] if x['purpose'] in ('food','living')}
        for x in t['operating_ledger']:
            r,n=x['round'],x['country'];food_need=1+int(r>=5)+int(r>=8);pop=2+int(r>=5)+int(r>=8)
            food=sum(len(household[r,n,g]['used_ids'])/food_need for g in ('wheat','banana'))/2
            global_gen=max((u['gen'] for u in units.values() if u['good']=='electronics' and u['born']<=r),default=1)
            ids=household[r,n,'electronics']['used_ids']
            efficiency=sum((1,.8,.6)[min(2,max(0,global_gen-units[i]['gen']))] for i in ids)
            base_happy=round(35+40*food+25*min(1,efficiency/math.ceil(pop/2)),6)
            audit.close(x['base_happy'],base_happy,'physical_household_base_happy')
        for plan in t['operating_plans']:
            plan_total+=1;due={g:int(plan['round'] in SCHEDULES[key[2]][g]) for g in RAW}
            audit.same(plan['due'],due,'physical_plan_due')
            audit.require(plan['profile']==key[2] and any(due.values()),'physical_plan_profile')
            for g in GOODS:
                audit.close(plan['target'][g],plan['legacy_target'][g]+due.get(g,0),'physical_target_adds_once')
            ordinary=[x for x in plan['rows'] if x['kind']!='replacement']
            audit.require(len(ordinary)==len({x['good'] for x in ordinary}),'physical_plan_single_good_row')
            audit.require(sum(x['budget'] for x in plan['rows'])<=plan['cash'],'physical_plan_affordable')
            for row in plan['rows']:
                audit.require(0<=row['quantity']<=row['want'],'physical_plan_quantity')
                audit.close(row['budget'],row['quantity']*row['unit_price'],'physical_plan_budget')
                for field in ('want','quantity','budget'):
                    audit.close(row[field],sum(p[field] for p in row['budget_parts']),'physical_plan_parts')
                if row['good'] in RAW:
                    audit.close(row['want'],max(0,plan['target'][row['good']]-plan['available'][row['good']]),'physical_plan_raw_no_duplicate')
            for g in RAW:
                requested=sum(p['want'] for x in plan['rows'] if x['good']==g for p in x['budget_parts'] if p['purpose']=='national')
                audit.close(requested,max(0,due[g]-plan['available'][g]),'physical_plan_national_request')
    audit.require(seen==expected and len(seen)==998,'physical_trace_schedule')
    return {'physical_traces':len(seen),'physical_units':unit_total,'national_purchase_plan_records':plan_total}


def make_behavior_case(before,after,name,paths,index):
    prefix=f'countries.{name}.'
    selected=[p for p in paths if p.startswith(prefix)]
    b={p[len(prefix):]:before[index[p]] for p in selected}
    a={p[len(prefix):]:after[index[p]] for p in selected}
    d={p:a[p]-b[p] for p in b}
    score=d['fixed_evaluation.score'];used=d['growth_metrics.used_units'];investment=d['investment']
    no_better=(used<=TOL and d['happy']<=TOL and d['useful_exports']<=TOL and d['useful_imports']<=TOL and d['growth_metrics.asset_gain']<=TOL)
    signals={'total_up':score>TOL,'total_down':score<-TOL,'total_tie':abs(score)<=TOL,
             'investment_up_used_not_up_score_up':investment>TOL and used<=TOL and score>TOL,
             'investment_up_selected_outcomes_not_up_score_up':investment>TOL and no_better and score>TOL,
             'ratio_up_used_not_up_score_up':used<=TOL and d['growth_metrics.utilization']>TOL and score>TOL}
    return {'country':name,'before':b,'after':a,'delta':d,'signals':signals}


def verify_behavior_records(audit,results,summary,groups,index,paths):
    diagnostics={p:{} for p in PROFILES[:3]};by_country={};exceptions=[]
    count={'pairs':0,'countries':0}
    def expected_rows():
        for mode in MODES:
            for profile in PROFILES[:3]:
                base=groups['stress',mode,profile,'None:normal']
                for focal,style in [(n,s) for n in NAMES for s in STYLES]+[('Technia','cheap'),(None,'no_trade')]:
                    scenario=f'{focal}:{style}';after=groups['stress',mode,profile,scenario]
                    for seed in sorted(base):
                        names=NAMES if focal is None else (focal,)
                        cases=[make_behavior_case(base[seed],after[seed],n,paths,index) for n in names]
                        row={'schema':'v17-behavior-pair-1','mode':mode,'operating_profile':profile,
                             'scenario':scenario,'focal':focal,'style':style,'seed':seed,'countries':cases}
                        count['pairs']+=1
                        for case in cases:
                            count['countries']+=1
                            diagnostic=diagnostics[profile].setdefault(style,Counter());diagnostic['n']+=1
                            key=f'{mode}:{profile}:{case["country"]}:{style}'
                            local=by_country.setdefault(key,Counter());local['n']+=1
                            for field,flag in case['signals'].items():diagnostic[field]+=int(flag);local[field]+=int(flag)
                            if style in ('minimum','minimum_passive','idle') and case['signals']['total_up']:
                                exceptions.append({k:v for k,v in row.items() if k not in ('countries','schema')}|case)
                        yield row
    for wanted,actual in zip_longest(expected_rows(),json_lines(results/'behavior_cases.jsonl.gz')):
        audit.require(wanted is not None and actual is not None,'behavior_record_count')
        audit.same(actual,wanted,'complete_behavior_record')
    audit.require(count['pairs']==5760 and count['countries']==6660,'behavior_scope')
    audit.same(summary['diagnostics'],diagnostics,'behavior_diagnostics')
    audit.same(summary['diagnostics_by_country'],by_country,'behavior_diagnostics_by_country')
    audit.same(summary['positive_price_or_idle_exceptions'],exceptions,'complete_positive_exceptions')
    return {'behavior_pair_records':count['pairs'],'behavior_country_comparisons':count['countries'],'positive_exception_records':len(exceptions)}


def verify_records(audit,results):
    expected=expected_schedule();seen=set();metadata={};data={};paths=None
    initial_by_condition={};phase_counts=Counter();profile_counts=Counter();behavior_counts=Counter()
    files=('validation_runs.jsonl.gz','round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz','operating_round_ledgers.jsonl.gz')
    identity_fields=('phase','mode','operating_profile','scenario','seed','focal','style','behaviors')
    national_units=0
    for i,items in enumerate(zip_longest(*(json_lines(results/f) for f in files)),1):
        audit.require(all(x is not None for x in items),'record_ledger_stream_length')
        record,*ledgers=items;key=identity(record)
        audit.require(key in expected and key not in seen,'record_identity_schedule',key);seen.add(key)
        phase,mode,profile,scenario,seed=key
        focal,style=scenario.split(':');focal=None if focal=='None' else focal
        behavior={} if focal is None else {focal:style}
        audit.require(record['focal']==focal and record['style']==style and record['behaviors']==behavior,'record_scenario_policy')
        audit.require(record['schema']=='v17-operating-execution-row-1','record_schema')
        for ledger in ledgers:
            audit.same({f:ledger[f] for f in identity_fields},{f:record[f] for f in identity_fields},'ledger_identity')
        cash_rows,raw_rows,national_rows=[x['rows'] for x in ledgers]
        audit.require(set(record['countries'])==set(ALL_NAMES),'record_country_set')
        world=record['world']
        audit.require(world['national_operation_scope']['physical_rule_changed']==(profile!='none'),'record_changed_rule_scope')
        scope=world['national_operation_scope']
        for flag,wanted in {'population_scaled':False,'new_score_feedback':False,'extra_starting_grants':False,
                            'daily_profile_stress_tested':False,'whole_bundle_scheduled_settlement':True}.items():
            audit.require(scope[flag] is wanted,'record_scope_flags',flag)
        audit.same(scope['policy'],{'fuel_rounds':list(SCHEDULES[profile]['fuel']),
                                   'ore_rounds':list(SCHEDULES[profile]['ore']),
                                   'fuel_penalty':8,'ore_penalty':4},'record_policy')
        audit.require(record['v17_evidence']['score_feedback_to_actions'] is False,'record_no_score_feedback')
        for field in ('offer_price_mismatches','listing_plan_violations','protected_offer_violations','uncovered_investments'):
            audit.close(world[field],0,'record_execution_invariant',field)
        for n,c in record['countries'].items():
            verify_growth(audit,c,n)
            if n in NAMES:
                expected_parts=expected_score(c,n)
                for f,v in expected_parts.items():audit.close(c['fixed_evaluation'][f],v,'fixed_score_'+f,n)
                audit.close(c['fixed_evaluation']['economic_target'],ECON_GOALS[n],'fixed_economic_goal')
                audit.close(c['fixed_evaluation']['industrial_target'],INDUSTRY_GOALS[n],'fixed_industrial_goal')
                audit.require(0<=c['fixed_evaluation']['score']<=100+TOL,'fixed_score_bounds')
            else:audit.require(c['fixed_evaluation'] is None,'additional_countries_unranked')
        scores={n:record['countries'][n]['fixed_evaluation']['score'] for n in NAMES}
        best=max(scores.values());top=[n for n in NAMES if scores[n]>=best-TOL]
        for n in NAMES:audit.close(record['countries'][n]['fixed_evaluation']['top'],int(n in top),'fixed_top_indicator')
        audit.same(world['fixed_evaluation'],{'score_spread':best-min(scores.values()),'top_countries':top,
            'score_feedback_to_actions':False,'goals_refitted':False,'reference':'v15 steps'},'fixed_world_evaluation')
        if style=='no_trade':audit.close(world['transactions'],0,'trade_disabled_transactions')
        for n,b in behavior.items():
            c=record['countries'][n]
            if b=='idle':
                for f in ('imports','exports','investment'):audit.close(c[f],0,'idle_no_discretionary_action')
            if b in ('trade','minimum_passive','idle'):
                audit.close(c['investment'],0,'passive_no_investment')
                audit.close(c['routing']['routes_started'],0,'passive_no_route')
        cash,raw=verify_money_raw(audit,record,cash_rows,raw_rows)
        _,used=verify_national(audit,record,national_rows,cash,raw);national_units+=len(used)
        initial={'world_cash':world['initial_cash'],'countries':{n:{
            'cash':c['start_cash'],'raw':c['starter_raw'],
            'assets':c['growth_metrics']['start_asset_value'],
            'capacity':c['growth_metrics']['initial_capacity']}
            for n,c in record['countries'].items()}}
        condition=(phase,mode,scenario,seed)
        if condition in initial_by_condition:audit.same(initial,initial_by_condition[condition],'same_profile_initial_conditions')
        else:initial_by_condition[condition]=initial
        flat=analytical_fields(record)
        if paths is None:paths=tuple(sorted(flat))
        audit.require(set(flat)==set(paths),'flat_metric_consistency')
        audit.require(all(type(x) in (int,float) and math.isfinite(x) for x in flat.values()),'finite_analysis_metrics')
        data[key]=array('d',(flat[p] for p in paths))
        metadata[key]={'record_sha256':value_hash(record),'cash_sha256':value_hash(cash_rows),
                       'raw_sha256':value_hash(raw_rows),'national_sha256':value_hash(national_rows)}
        phase_counts[phase]+=1;profile_counts[profile]+=1;behavior_counts[style]+=1
        if i%500==0 or i==6740:print(f'AUDIT records {i}/6740',flush=True)
    audit.require(seen==expected and len(seen)==6740,'complete_formal_schedule')
    audit.require(len(paths)==1125,'flat_metric_count')
    for condition in initial_by_condition:
        profiles=PROFILES if condition[0]=='main' else PROFILES[:3]
        audit.require(all((condition[0],condition[1],p,condition[2],condition[3]) in seen for p in profiles),
                      'complete_matched_profile_conditions')
    counts={'formal_games':len(seen),'country_game_records':len(seen)*9,
            'cash_round_rows':len(seen)*81,'raw_round_rows':len(seen)*81,'national_round_rows':len(seen)*81,
            'national_consumed_units_with_preuse_evidence':national_units,'metrics_per_group':len(paths),
            'phase_counts':dict(phase_counts),'profile_counts':dict(profile_counts),'behavior_counts':dict(behavior_counts)}
    return data,paths,metadata,counts


def source_snapshot():
    inherited={str(p.relative_to(ROOT/'source_v13')):digest(p) for p in sorted((ROOT/'source_v13').rglob('*.py'))}
    files=[ROOT/n for n in ('OPERATING_PROTOCOL_V17.json','SCORE_TARGETS_V15.json','INPUT_PROVENANCE_V17.json',
                            'operating_engine.py','run_operating_validation.py','analyze_operating_validation.py')]
    files+=sorted(ROOT.glob('test_*.py'))
    return {'inherited_source_sha256':inherited,'new_source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in files}}


def verify_sources_and_manifests(audit,results,analysis_dir):
    snapshot=source_snapshot();provenance=load(ROOT/'INPUT_PROVENANCE_V17.json')
    protocol=load(ROOT/'OPERATING_PROTOCOL_V17.json');goals=load(ROOT/'SCORE_TARGETS_V15.json')
    frozen=load(results/'freeze_manifest.json');run=load(results/'run_manifest.json')
    smoke=load(results/'smoke/smoke_manifest.json');analysis=load(analysis_dir/'analysis_manifest.json')
    audit.require(len(snapshot['inherited_source_sha256'])==85,'inherited_source_count')
    audit.same(snapshot['inherited_source_sha256'],provenance['source_python_sha256'],'inherited_source_unchanged')
    audit.require(digest(ROOT/'SCORE_TARGETS_V15.json')=='4a88b018c4adb9b21774b45e7f7b90fa4af1149aff76e29b126a3887b7d53ca3','fixed_goal_source_hash')
    audit.same(goals['economic_old'],ECON_GOALS,'declared_economic_goals')
    audit.same(goals['industrial_steps'],INDUSTRY_GOALS,'declared_industry_goals')
    audit.require(protocol['status']=='FIXED_BEFORE_NEW_GAMES','protocol_predeclared_status')
    audit.require(protocol['quantity_per_due']==1 and protocol['population_scaled'] is False,'protocol_physical_quantity')
    for p in PROFILES:
        for g in RAW:audit.same(protocol['profiles'][p][g+'_rounds'],list(SCHEDULES[p][g]),'protocol_schedule')
    execution=protocol['execution']
    for f,v in {'country_count':9,'rounds':9,'formal_games':6740,'main_games':800,'stress_games':5940,
                'smoke_games':24,'formal_ledger_rows_per_kind':545940,'formal_traces':998}.items():
        audit.close(execution[f],v,'protocol_scope')
    for f,v in {'modes':list(MODES),'main_profiles':list(PROFILES),'stress_profiles':list(PROFILES[:3]),
                'ranked_countries':list(NAMES),'unranked_countries':list(ADDED)}.items():audit.same(execution[f],v,'protocol_scope_lists')
    audit.require(frozen['status']=='PASS' and frozen['formal_not_executed'] is True,'freeze_status')
    audit.same(frozen['execution_plan'],execution,'freeze_execution_plan')
    audit.same(frozen['source_snapshot'],snapshot,'freeze_sources')
    audit.require(run['status']=='PASS' and not run['errors'] and run['source_unchanged'] is True,'formal_run_pass')
    audit.same(run['source_before'],snapshot,'formal_sources_before')
    audit.same(run['source_after'],snapshot,'formal_sources_after')
    audit.require(run['stage']=='formal' and run['planned_games']==run['completed_games']==run['new_economic_games']==6740,'formal_game_count')
    audit.require(run['representative_traces']==998 and not run['partial_sha256'],'formal_trace_and_completion')
    audit.require(run['score_feedback_to_actions'] is False and run['preserved_python_sources']==85,'formal_fixed_design')
    audit.same(run['ranked_countries'],list(NAMES),'formal_ranked')
    audit.same(run['unranked_countries'],list(ADDED),'formal_unranked')
    audit.same(run['ledger_rows'],{f:545940 for f in ('round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz','operating_round_ledgers.jsonl.gz')},'formal_ledger_counts')
    audit.require(smoke['status']=='PASS' and not smoke['errors'] and smoke['completed_games']==smoke['new_economic_games']==24,
                  'smoke_pass_scope')
    audit.require(smoke['representative_traces']==24 and not smoke['partial_sha256'],'smoke_trace_scope')
    audit.same(smoke['source_before'],snapshot,'smoke_sources_before')
    audit.same(smoke['source_after'],snapshot,'smoke_sources_after')
    audit.require(frozen['smoke_manifest_sha256']==digest(results/'smoke/smoke_manifest.json'),'freeze_smoke_hash')
    receipt=ROOT/frozen['test_receipt'];test=load(receipt)
    audit.require(digest(receipt)==frozen['test_receipt_sha256'],'freeze_semantic_hash')
    audit.require(test['status']=='PASS' and not test['errors'] and not test['failures'],'semantic_pass')
    audit.require(test['new_economic_games']==test['completed_economic_games']==test['economic_execution_attempts']==12,
                  'semantic_actual_game_count')
    audit.require(test['backcompat_pairs']==6 and len(test['matched_pairs'])==6 and all(x['matched'] for x in test['matched_pairs']),
                  'semantic_backward_compatibility_receipt')
    audit.require(len(test['executions'])==12 and all(x['completed'] for x in test['executions']), 'semantic_completed_games')
    audit.require(test['fixtures_are_completed_games'] is False,'semantic_fixture_scope')
    for field,file in (('engine_sha256','operating_engine.py'),('engine_after_sha256','operating_engine.py'),
                       ('test_sha256','test_operating_engine.py'),('protocol_sha256','OPERATING_PROTOCOL_V17.json')):
        audit.require(test[field]==digest(ROOT/file),'semantic_source_hash')
    times=[protocol['created_at'],test['completed_at'],smoke['started_at'],smoke['completed_at'],frozen['created_at'],run['started_at'],run['completed_at']]
    parsed=[datetime.fromisoformat(t) for t in times]
    audit.require(parsed==sorted(parsed),'freeze_chronology')
    audit.require(analysis['status']=='PASS' and not analysis['errors'],'analysis_pass')
    audit.require(analysis['formal_economic_games_analyzed']==6740 and analysis['new_economic_games']==0,'analysis_game_scope')
    audit.require(analysis['source_sha256']==digest(results/'validation_runs.jsonl.gz'),'analysis_raw_hash')
    audit.require(analysis['run_manifest_sha256']==digest(results/'run_manifest.json'),'analysis_manifest_hash')
    audit.require(analysis['analysis_source_sha256']==digest(ROOT/'analyze_operating_validation.py'),'analysis_code_hash')
    for directory,manifest in ((results,run),(results/'smoke',smoke),(analysis_dir,analysis)):
        wanted={'summary.json','behavior_cases.jsonl.gz'} if directory==analysis_dir and manifest is analysis else {
            'validation_runs.jsonl.gz','round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz',
            'operating_round_ledgers.jsonl.gz','representative_traces.json.gz'}
        audit.require(set(manifest['output_sha256'])==wanted,'manifest_output_file_set')
        for f,sha in manifest['output_sha256'].items():
            audit.require(digest(directory/f)==sha,'evidence_file_hash',str(directory/f))
    return snapshot,run,analysis,{'semantic_tests':test['tests'],'semantic_completed_games':12,
           'semantic_backcompat_pairs':6,'isolated_fixture_instances':test['isolated_fixture_instances'],
           'smoke_completed_games':24,'formal_completed_games':6740,'total_completed_economic_games':6776}


def verify_analysis_metadata(audit,summary,analysis,results,analysis_dir,counts,paths):
    expected={'formal_economic_games':6740,'main_games':800,'stress_games':5940,'new_analysis_games':0,
              'main_per_condition':100,'stress_per_condition':30,'group_count':206,'profile_contrasts':138,
              'economic_contrasts':103,'behavior_contrasts':192,'behavior_pair_records':5760,
              'behavior_country_comparisons':6660,'metrics_per_group':len(paths)}
    for k,v in expected.items():audit.close(summary['metadata'][k],v,'summary_metadata')
    for k in ('group_count','profile_contrasts','economic_contrasts','behavior_contrasts','behavior_pair_records',
              'behavior_country_comparisons','metrics_per_group'):
        audit.close(analysis[k],expected[k],'analysis_manifest_counts')
    for k,v in {'modes':list(MODES),'profiles':list(PROFILES),'stress_profiles':list(PROFILES[:3])}.items():
        audit.same(summary['metadata'][k],v,'summary_metadata_lists')
    for k,p in (('source_sha256',results/'validation_runs.jsonl.gz'),('run_manifest_sha256',results/'run_manifest.json'),
                ('freeze_sha256',results/'freeze_manifest.json')):
        audit.require(summary['metadata'][k]==digest(p),'summary_metadata_hashes')
    audit.same(summary['all_positive_and_negative_behavior_records'],{'path':'behavior_cases.jsonl.gz','records':5760,
               'country_comparisons':6660,'sha256':digest(analysis_dir/'behavior_cases.jsonl.gz')},'summary_behavior_evidence')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=ROOT/'operating_results')
    p.add_argument('--analysis',type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args();results=args.results.resolve();analysis_dir=(args.analysis or results).resolve()
    output=(args.output or results/'independent_audit.json').resolve()
    if output.exists():raise RuntimeError('Preserve the previous audit receipt before another run')
    audit=Audit();clock=time.monotonic();started=datetime.now(timezone.utc).isoformat();statistics_out={};error=None
    try:
        source_before,run,analysis,execution=verify_sources_and_manifests(audit,results,analysis_dir)
        print('AUDIT frozen inputs and manifests verified',flush=True)
        data,paths,metadata,statistics_out=verify_records(audit,results)
        for field in ('phase_counts','profile_counts','behavior_counts'):
            audit.same(run[field],statistics_out[field],'run_manifest_actual_counts')
        statistics_out.update(verify_physical_traces(audit,results,metadata))
        print('AUDIT 998 physical traces verified',flush=True)
        del metadata
        summary=load(analysis_dir/'summary.json')
        verify_analysis_metadata(audit,summary,analysis,results,analysis_dir,statistics_out,paths)
        groups,index=verify_statistics(audit,summary,data,paths)
        print('AUDIT grouped and paired statistics verified',flush=True)
        statistics_out.update(verify_behavior_records(audit,analysis_dir,summary,groups,index,paths))
        statistics_out.update(group_count=206,profile_contrasts=138,economic_contrasts=103,behavior_contrasts=192)
        audit.close(analysis['positive_exception_records'],statistics_out['positive_exception_records'],'analysis_exception_count')
        audit.same(source_snapshot(),source_before,'audit_sources_unchanged')
        statistics_out['execution_accounting']=execution
    except BaseException as exc:
        error=exc
        if not audit.errors:audit.errors.append({'check':'unexpected_exception','type':type(exc).__name__,'message':str(exc)})
    receipt={'schema':'v17-independent-operating-audit-1','status':'PASS' if error is None else 'FAIL',
             'started_at':started,'completed_at':datetime.now(timezone.utc).isoformat(),
             'elapsed_seconds':time.monotonic()-clock,'new_economic_games':0,
             'imports_engine_or_scorer':False,'auditor_sha256':digest(__file__),
             'check_count':sum(audit.counts.values()),'check_categories':dict(sorted(audit.counts.items())),
             'statistics':statistics_out,'errors':audit.errors,
             'scope':'All 6740 games: fixed score arithmetic, 81 cash/raw/national rows, national UID preuse ownership evidence, physical accounting, grouped and matched seed statistics. 998 full traces: complete UID/use/need/transaction/household/plan links. Backwards compatibility is verified by the separately frozen semantic-test receipt; no additional games are executed.',
             'limitations':['Full historical UID traces cover all 800 main games and 198 first-seed stress games, not every stress trajectory.',
                            'Deterministic automated policies and seed variation do not validate human learning, classroom timing, or universal strategy optimality.']}
    with output.open('x',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':receipt['status'],'check_count':receipt['check_count'],'statistics':statistics_out,
                      'elapsed_seconds':receipt['elapsed_seconds'],'errors':receipt['errors']},ensure_ascii=False),flush=True)
    if error is not None:raise error


if __name__=='__main__':main()
