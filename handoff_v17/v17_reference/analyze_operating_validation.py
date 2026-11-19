"""Read-only paired analysis of frozen v17 national-operation games."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
try:
    import resource
except ImportError:  # Standard Windows Python has no resource module.
    resource=None
import statistics
import time

ROOT=Path(__file__).resolve().parent
NAMES=('Tropia','Grainia','Oilia','Mechania','Mineria','Technia')
ADDED=('Novia','Agrea','Ferria')
MODES=('baseline','electronics_input')
PROFILES=('none','light','regular','daily')
STRESS_PROFILES=PROFILES[:3]
STYLES=('minimum','idle','invest','trade','minimum_passive')
GOODS=('wheat','banana','ore','fuel','machine','electronics')
BASE=('cash','happy','revenue','purchases','investment','tax','exports','imports',
      'useful_exports','useful_imports','food_short_rounds','low_cash_rounds',
      'production_failures','upgrades_total','machine_gen','elec_gen','min_observed_cash')
GROWTH=('asset_gain','capacity_growth','initial_capacity','final_capacity','unused_stock_value',
        'stock_value','produced_units','used_units','utilization')
GOOD_MAPS=('produced','use_by_good','export_used_by_good','import_goods','export_goods',
           'end_stock_by_good','unused_by_good','purchase_by_good','sale_by_good')
SCORE=('score','economic_growth','reserve','capacity','utilization','wellbeing','trade','economic','industry','top')
WORLD=('transactions','trade_units','happy','original_happy','original_cash','cash_total','tax',
       'investment','original_food_short','original_production_failures','inventory')
TOL=1e-9


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1048576),b''):h.update(part)
    return h.hexdigest()


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')


def stats(values,paired=False):
    values=list(values);n=len(values)
    assert n and all(type(v) in (int,float) and math.isfinite(v) for v in values)
    mean=statistics.fmean(values);error=1.96*statistics.stdev(values)/math.sqrt(n) if n>1 else 0
    out={'n':n,'mean':mean,'ci95':[mean-error,mean+error],'min':min(values),'max':max(values)}
    if paired:out.update(up=sum(v>TOL for v in values),down=sum(v<-TOL for v in values),tie=sum(abs(v)<=TOL for v in values))
    return out


def recursive_numeric(obj,prefix,target):
    for key,value in obj.items():
        path=prefix+'.'+key
        if isinstance(value,dict):recursive_numeric(value,path,target)
        elif type(value) in (int,float):
            assert math.isfinite(value),path;target[path]=value


def flattened(row):
    out={}
    for n in NAMES+ADDED:
        c=row['countries'][n];prefix='countries.'+n+'.'
        for k in BASE:out[prefix+k]=c[k]
        for k in GROWTH:out[prefix+'growth_metrics.'+k]=c['growth_metrics'][k]
        for k in GOOD_MAPS:
            for g in GOODS:out[prefix+k+'.'+g]=c[k][g]
        for g in ('ore','fuel'):
            for k in ('consumed','production','research','national','imported_used'):
                out[prefix+'raw_use.'+g+'.'+k]=c['raw_use'][g].get(k,0)
            out[prefix+'raw_unmet_production.'+g]=c['raw_unmet_production'][g]
            out[prefix+'own_produced_never_used.'+g]=c['produced'][g]-c['use_by_good'][g]
            out[prefix+'national_operation_origin_used.'+g]=c['national_operation_origin_used'][g]
        assert 'national_operation' in c
        recursive_numeric(c['national_operation'],prefix[:-1]+'.national_operation',out)
        if n in NAMES:
            for k in SCORE:out[prefix+'fixed_evaluation.'+k]=c['fixed_evaluation'][k]
    w=row['world']
    for k in WORLD:out['world.'+k]=w[k]
    for k in ('production','consumed','trade_goods','remaining_goods','aged_unused_goods','end_prices'):
        for g in GOODS:out['world.'+k+'.'+g]=w[k][g]
    for g in ('ore','fuel'):
        for k in ('consumed','production','research','national','imported_used'):
            out['world.raw_use.'+g+'.'+k]=w['raw_use'][g].get(k,0)
        out['world.raw_unmet_production.'+g]=w['raw_unmet_production'][g]
        out['world.own_produced_never_used.'+g]=sum(out[f'countries.{n}.own_produced_never_used.{g}'] for n in NAMES+ADDED)
        out['world.national_operation_origin_used.'+g]=sum(out[f'countries.{n}.national_operation_origin_used.{g}'] for n in NAMES+ADDED)
    recursive_numeric(w['national_operation'],'world.national_operation',out)
    out['world.fixed_evaluation.score_spread']=w['fixed_evaluation']['score_spread']
    assert all(type(v) in (int,float) and math.isfinite(v) for v in out.values())
    return out


def identity(r):return tuple(r[k] for k in ('phase','mode','operating_profile','scenario','seed'))


def group_key(phase,mode,profile,scenario):return f'{phase}:{mode}:{profile}:{scenario}'


def expected_schedule():
    cases=['None:normal']+[f'{n}:{s}' for n in NAMES for s in STYLES]+['Technia:cheap','None:no_trade']
    expected={('main',m,p,'None:normal',s) for m in MODES for p in PROFILES for s in range(130000,130100)}
    expected|={('stress',m,p,c,s) for m in MODES for p in STRESS_PROFILES for c in cases for s in range(132000,132030)}
    assert len(expected)==6740
    return expected


def paired(before,after):
    assert set(before)==set(after)
    seeds=sorted(before);fields=before[seeds[0]].keys()
    assert all(before[s].keys()==after[s].keys()==fields for s in seeds)
    return {'n':len(seeds),'stats':{k:stats((after[s][k]-before[s][k] for s in seeds),True) for k in fields}}


def country_case(before,after,name):
    prefix='countries.'+name+'.'
    fields=[k for k in before if k.startswith(prefix)]
    b={k[len(prefix):]:before[k] for k in fields};a={k[len(prefix):]:after[k] for k in fields}
    delta={k:a[k]-b[k] for k in b}
    assert math.isclose(delta['fixed_evaluation.score'],sum(delta['fixed_evaluation.'+k] for k in
                       ('economic_growth','reserve','capacity','utilization','wellbeing','trade')),abs_tol=1e-8)
    score=delta['fixed_evaluation.score'];invest=delta['investment'];used=delta['growth_metrics.used_units']
    selected_not_better=(used<=TOL and delta['happy']<=TOL and delta['useful_exports']<=TOL
                         and delta['useful_imports']<=TOL and delta['growth_metrics.asset_gain']<=TOL)
    signal={'total_up':score>TOL,'total_down':score<-TOL,'total_tie':abs(score)<=TOL,
            'investment_up_used_not_up_score_up':invest>TOL and used<=TOL and score>TOL,
            'investment_up_selected_outcomes_not_up_score_up':invest>TOL and selected_not_better and score>TOL,
            'ratio_up_used_not_up_score_up':used<=TOL and delta['growth_metrics.utilization']>TOL and score>TOL}
    return {'country':name,'before':b,'after':a,'delta':delta,'signals':signal}


def save_pairs(path,pairs):
    with Path(path).open('xb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0) as gz:
            with io.TextIOWrapper(gz,encoding='utf-8') as text:
                for row in pairs:text.write(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=ROOT/'operating_results')
    p.add_argument('--output-dir',type=Path)
    a=p.parse_args();results=a.results.resolve();out=(a.output_dir or results).resolve()
    out.mkdir(parents=True,exist_ok=True)
    assert not (out/'summary.json').exists() and not (out/'analysis_manifest.json').exists()
    started=time.monotonic();manifest=json.loads((results/'run_manifest.json').read_text())
    frozen=json.loads((results/'freeze_manifest.json').read_text())
    assert manifest['status']=='PASS' and manifest['completed_games']==manifest['new_economic_games']==6740
    assert not manifest['errors'] and manifest['source_before']==manifest['source_after']==frozen['source_snapshot']
    for rel,sha in frozen['source_snapshot']['new_source_sha256'].items():assert digest(ROOT/rel)==sha,rel
    for rel,sha in frozen['source_snapshot']['inherited_source_sha256'].items():assert digest(ROOT/'source_v13'/rel)==sha,rel
    raw=results/'validation_runs.jsonl.gz';assert digest(raw)==manifest['output_sha256'][raw.name]
    grouped=defaultdict(dict);seen=set();field_names=None;canonical_fields=None
    with gzip.open(raw,'rt') as f:
        for line in f:
            r=json.loads(line);key=identity(r)
            assert key not in seen;seen.add(key)
            x=flattened(r)
            if field_names is None:
                field_names=set(x);canonical_fields={k:k for k in x}
            assert set(x)==field_names,('Inconsistent evidence schema',key,field_names^set(x))
            # Every trajectory has the same paths. Reuse their string objects
            # instead of retaining several million duplicate long field names.
            x={canonical_fields[k]:v for k,v in x.items()}
            grouped[group_key(*key[:4])][key[4]]=x
    assert seen==expected_schedule()
    groups={}
    for key,samples in sorted(grouped.items()):
        assert len(samples)==(100 if key.startswith('main:') else 30)
        g={'n':len(samples),'stats':{k:stats(x[k] for x in samples.values()) for k in sorted(field_names)}}
        means={n:g['stats'][f'countries.{n}.fixed_evaluation.score']['mean'] for n in NAMES}
        tops={n:sum(x[f'countries.{n}.fixed_evaluation.top'] for x in samples.values()) for n in NAMES}
        g['score_diagnostics']={'country_mean_score_range':max(means.values())-min(means.values()),
          'mean_within_game_score_range':g['stats']['world.fixed_evaluation.score_spread']['mean'],
          'top_counts_including_ties':tops,
          'highest_mean_countries':[n for n in NAMES if means[n]>=max(means.values())-TOL],
          'lowest_mean_countries':[n for n in NAMES if means[n]<=min(means.values())+TOL],
          'tie_games':sum(sum(x[f'countries.{n}.fixed_evaluation.top'] for n in NAMES)>1 for x in samples.values())}
        groups[key]=g
    assert len(groups)==206
    profile_pairs={};economic_pairs={};behavior_pairs={}
    for phase in ('main','stress'):
        profiles=PROFILES if phase=='main' else STRESS_PROFILES
        cases=['None:normal'] if phase=='main' else ['None:normal']+[f'{n}:{s}' for n in NAMES for s in STYLES]+['Technia:cheap','None:no_trade']
        for mode in MODES:
            for case in cases:
                base=grouped[group_key(phase,mode,'none',case)]
                for profile in profiles[1:]:
                    profile_pairs[f'profile:{phase}:{mode}:{case}:none->{profile}']=paired(base,grouped[group_key(phase,mode,profile,case)])
        for profile in profiles:
            for case in cases:
                economic_pairs[f'economy:{phase}:{profile}:{case}:baseline->electronics_input']=paired(
                    grouped[group_key(phase,'baseline',profile,case)],grouped[group_key(phase,'electronics_input',profile,case)])
    assert len(profile_pairs)==138 and len(economic_pairs)==103
    diagnostics={p:{} for p in STRESS_PROFILES};by_country={};exceptions=[];pair_counts=Counter()
    def detailed_pairs():
        # Persist complete favorable and unfavorable cases as a stream. Only
        # the comparatively small positive-price/idle subset stays in memory.
        for mode in MODES:
            for profile in STRESS_PROFILES:
                base=grouped[group_key('stress',mode,profile,'None:normal')]
                for focal,style in [(n,s) for n in NAMES for s in STYLES]+[('Technia','cheap'),(None,'no_trade')]:
                    case=f'{focal}:{style}';target=grouped[group_key('stress',mode,profile,case)]
                    behavior_pairs[f'behavior:{mode}:{profile}:{case}']=paired(base,target)
                    for seed in sorted(base):
                        names=NAMES if focal is None else (focal,)
                        cc=[country_case(base[seed],target[seed],n) for n in names]
                        row={'schema':'v17-behavior-pair-1','mode':mode,'operating_profile':profile,
                             'scenario':case,'focal':focal,'style':style,'seed':seed,'countries':cc}
                        pair_counts['records']+=1
                        for c in cc:
                            pair_counts['countries']+=1
                            d=diagnostics[profile].setdefault(style,Counter());d['n']+=1
                            key=f'{mode}:{profile}:{c["country"]}:{style}'
                            z=by_country.setdefault(key,Counter());z['n']+=1
                            for k,v in c['signals'].items():d[k]+=int(v);z[k]+=int(v)
                            if style in ('minimum','minimum_passive','idle') and c['signals']['total_up']:
                                exceptions.append({k:v for k,v in row.items() if k not in ('countries','schema')}|c)
                        yield row
    pairs_path=out/'behavior_cases.jsonl.gz';save_pairs(pairs_path,detailed_pairs())
    assert len(behavior_pairs)==192 and pair_counts['records']==5760 and pair_counts['countries']==6660
    for profile in STRESS_PROFILES:
        for style in STYLES:assert diagnostics[profile][style]['n']==360
        assert diagnostics[profile]['cheap']['n']==60 and diagnostics[profile]['no_trade']['n']==360
    summary={'schema':'v17-operating-summary-1','metadata':{
       'formal_economic_games':6740,'main_games':800,'stress_games':5940,'new_analysis_games':0,
       'main_per_condition':100,'stress_per_condition':30,'group_count':206,
       'profile_contrasts':138,'economic_contrasts':103,'behavior_contrasts':192,
       'behavior_pair_records':5760,'behavior_country_comparisons':6660,
       'metrics_per_group':len(field_names),'modes':list(MODES),'profiles':list(PROFILES),
       'stress_profiles':list(STRESS_PROFILES),'source_sha256':digest(raw),
       'run_manifest_sha256':digest(results/'run_manifest.json'),'freeze_sha256':digest(results/'freeze_manifest.json'),
       'daily_scope':'Main only; no stress behavior inference for daily.',
       'interval':'mean +/-1.96*sample SD/sqrt(n); descriptive seed variation, not human outcome probabilities',
       'score_reference':'Frozen v15 steps; no score-target fitting or score-aware policy optimization'},
       'groups':groups,'profile_comparisons':profile_pairs,'economic_comparisons':economic_pairs,
       'behavior_comparisons':behavior_pairs,'diagnostics':diagnostics,'diagnostics_by_country':by_country,
       'positive_price_or_idle_exceptions':exceptions,
       'all_positive_and_negative_behavior_records':{'path':pairs_path.name,'records':pair_counts['records'],
          'country_comparisons':pair_counts['countries'],'sha256':digest(pairs_path)}}
    write_new(out/'summary.json',summary)
    analysis={'schema':'v17-analysis-manifest-1','status':'PASS','completed_at':datetime.now(timezone.utc).isoformat(),
       'elapsed_seconds':time.monotonic()-started,'formal_economic_games_analyzed':6740,'new_economic_games':0,
       'group_count':206,'profile_contrasts':138,'economic_contrasts':103,'behavior_contrasts':192,
       'behavior_pair_records':5760,'behavior_country_comparisons':6660,'metrics_per_group':len(field_names),
       'positive_exception_records':len(exceptions),'source_sha256':digest(raw),
       'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None,
       'full_game_records_retained':False,'detailed_cases_streamed':True,
       'run_manifest_sha256':digest(results/'run_manifest.json'),'analysis_source_sha256':digest(__file__),
       'output_sha256':{n:digest(out/n) for n in ('summary.json','behavior_cases.jsonl.gz')},'errors':[]}
    write_new(out/'analysis_manifest.json',analysis)
    print(json.dumps({k:v for k,v in analysis.items() if k not in ('output_sha256','errors')},ensure_ascii=False))


if __name__=='__main__':main()
