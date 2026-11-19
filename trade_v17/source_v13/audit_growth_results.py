"""Independent v12 saved-result audit; no scorer or economic engine imports.

Reconstructs growth metrics from fixed initial conditions, physical traces and
saved accounting, fits the declared equal-weight calibration sample afresh,
then independently calculates the four post-game scoring views.  Frozen v11
economic/decision/price/need audits remain inherited and unmodified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

from audit_evaluation_results import Audit as EvaluationAudit, eval_identity
from audit_machinery_results import ORIGINAL, GOODS, read_json, read_lines

VIEWS=('legacy','targets','headroom','targets_headroom')
POLICIES=('normal','invest','trade')
PRICE={'banana':10,'wheat':10,'ore':20,'fuel':30,'machine':50,'electronics':80}
DURABLES=('machine','electronics')
BASES={
    'Tropia':{'banana':4,'wheat':2},'Grainia':{'wheat':3,'banana':2},
    'Oilia':{'fuel':1,'ore':1,'banana':1},'Mechania':{'machine':2,'wheat':2},
    'Mineria':{'ore':1,'fuel':1},'Technia':{'electronics':1,'machine':1,'wheat':1},
    'Novia':{'electronics':1,'wheat':1},'Agrea':{'banana':2,'fuel':1},'Ferria':{'ore':1,'wheat':2},
}
OLD_ECONOMIC=dict(zip(ORIGINAL,(250,240,140,160,140,160)))
OLD_INDUSTRIAL=dict(zip(ORIGINAL,(.90,.90,.48,.25,.48,.27)))
GOAL_METHOD={'quantile':.75,'economic_floor':50,'economic_step':5,
    'industrial_floor':.10,'industrial_step':.05,'policies':list(POLICIES),
    'equal_policy_weight':True,'original_countries_only':True,'exclude_peer_policy_observations':True}
CONFIG={'views':list(VIEWS),'headroom':{'base_target_fraction':.8,'challenge_target_multiple':2.0},
    'economic_rules_unchanged':True,'official_scores_unchanged':True,'score_feedback_to_actions':False,
    'ranked_countries':list(ORIGINAL),'v11_trade_view':'legacy','asset_definition_unchanged':True,
    'utilization_definition_unchanged':True}
IDENTITY_FIELDS=('phase','mode','scenario','seed','focal','style','behaviors')


def cap01(x):
    return max(0,min(1,x))


def growth_curve(r,extra):
    if r<=0:return 0
    if not extra:return min(r,1)
    if r<=1:return .8*r
    if r<2:return .8+.2*(r-1)
    return 1


def round_goal(value,floor,step):
    ratio=max(floor,value)/step
    nearest=round(ratio)
    if abs(ratio-nearest)<=1e-12:ratio=nearest
    return round(math.ceil(ratio)*step,10)


def original_projection(row):
    """Remove only the two explicitly post-game score additions."""
    return {**row,
        'countries':{n:{k:v for k,v in c.items() if k!='growth_evaluation'} for n,c in row['countries'].items()},
        'world':{k:v for k,v in row['world'].items() if k!='growth_evaluation_config'}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def independent_total(country,name,view,goals):
    m=country['growth_metrics'];fitted=view in ('targets','targets_headroom');extra='headroom' in view
    et=goals['economic'][name] if fitted else OLD_ECONOMIC[name]
    it=goals['industrial'][name] if fitted else OLD_INDUSTRIAL[name]
    return (20*growth_curve(m['asset_gain']/et,extra)+5*cap01(m['cash']/80)
            +15*growth_curve(m['capacity_growth']/it,extra)+10*m['used_units']/max(1,m['produced_units'])
            +country['happy']/4+country['trade'])


class Audit(EvaluationAudit):
    def __init__(self,goals=None):
        super().__init__()
        self.goals=goals
        self.goal_samples={}

    def mapping(self,actual,expected,label,context=None):
        self.equal(set(actual),set(expected),label+'_schema',context)
        for field,value in expected.items():
            if field in actual:self.equal(actual[field],value,label,(context,field))

    def run_summary(self,row):
        super().run_summary(row)
        context=eval_identity(row)
        scored='growth_evaluation_config' in row['world']
        if scored:self.equal(row['world']['growth_evaluation_config'],CONFIG,'fixed_posthoc_score_scope',context)
        for name,c in row['countries'].items():
            k=(context,name);m=c['growth_metrics'];bases=BASES[name]
            initial=sum(PRICE[g]*q for g,q in bases.items())
            final=sum(PRICE[g]*(bases.get(g,1)+(lv-1)*(2 if g in ('banana','wheat') else 1))
                      for g,lv in c['end_levels'].items() if lv>0)
            produced=sum(c['produced'].values());used=sum(c['use_by_good'].values())
            expected={'start_asset_value':c['start_asset_value'],'end_asset_value':c['end_asset_value'],
                'asset_gain':c['end_asset_value']-c['start_asset_value'],'cash':c['cash'],'tax':c['tax'],
                'investment':c['investment'],'stock_value':c['cash_plus_stock_value']-c['cash'],
                'initial_capacity':initial,'final_capacity':final,'capacity_growth':(final-initial)/initial,
                'reserve_target':80,'reserve_score':5*cap01(c['cash']/80),
                'produced_units':produced,'used_units':used,'utilization':used/max(1,produced),
                'utilization_score':10*used/max(1,produced),'wellbeing_score':c['happy']/4,'trade_score':c['trade']}
            self.equal(set(m),set(expected)|{'unused_stock_value','used_stock_value'},'growth_metrics_complete_schema',k)
            for field,value in expected.items():self.equal(m[field],value,'growth_evidence_from_accounting_and_levels',(k,field))
            for field,value in m.items():
                self.check(type(value) in (int,float) and math.isfinite(value),'growth_evidence_is_finite_number',(k,field))
            self.equal(m['unused_stock_value']+m['used_stock_value'],m['stock_value'],'stock_value_partition',k)
            self.check(m['unused_stock_value']>=0 and m['used_stock_value']>=0,'nonnegative_inventory_values',k)
            low=sum(PRICE[g]*.15*c['unused_by_good'][g] for g in GOODS)
            high=sum(PRICE[g]*.15*c['unused_by_good'][g]*(1.8 if g in DURABLES else 1) for g in GOODS)
            self.check(low-1e-8<=m['unused_stock_value']<=high+1e-8,'unused_stock_has_fixed_generation_value_bounds',k)
            self.equal(m['capacity_growth'],c['capacity_growth'],'capacity_growth_matches_legacy',k)
            self.equal(m['utilization_score'],c['industry_use_score'],'all_views_keep_actual_unique_usage',k)
            self.equal(m['trade_score'],c['evaluation']['scores']['legacy']['trade'],'growth_experiment_fixes_legacy_trade_view',k)
            start=c['start_cash']+6+sum(c['starter_raw'][g]*PRICE[g]*.15 for g in ('ore','fuel'))
            if any(g in DURABLES for g in bases):start+=7.5
            self.equal(m['start_asset_value'],start,'actual_start_grants_not_recalibrated',k)
            if not scored:
                self.check('growth_evaluation' not in c,'calibration_raw_has_no_fitted_score',k)
                continue
            self.equal(set(c['growth_evaluation']),set(VIEWS),'four_growth_views_present',k)
            if name not in ORIGINAL:
                self.equal(c['growth_evaluation'],dict.fromkeys(VIEWS),'new_countries_have_no_fitted_total',k)
                continue
            self.check(self.goals is not None,'frozen_goals_available_for_posthoc_scores',k)
            if self.goals is None:continue
            for view,actual in c['growth_evaluation'].items():
                fitted=view in ('targets','targets_headroom');extra='headroom' in view
                for field,value in actual.items():
                    self.check(type(value) in (int,float) and math.isfinite(value),'growth_score_view_is_finite_number',(k,view,field))
                et=self.goals['economic'][name] if fitted else OLD_ECONOMIC[name]
                it=self.goals['industrial'][name] if fitted else OLD_INDUSTRIAL[name]
                er=m['asset_gain']/et;ir=m['capacity_growth']/it
                eg=20*growth_curve(er,extra);cp=15*growth_curve(ir,extra)
                economic=eg+expected['reserve_score'];industry=cp+expected['utilization_score']
                calculated={'economic_target':et,'industrial_target':it,'economic_ratio':er,'industrial_ratio':ir,
                    'economic_growth':eg,'reserve':expected['reserve_score'],'economic':economic,'capacity':cp,
                    'utilization':expected['utilization_score'],'industry':industry,'wellbeing':expected['wellbeing_score'],
                    'trade':c['trade'],'score':economic+industry+c['happy']/4+c['trade'],
                    'economic_growth_at_cap':int(eg>=20-1e-9),'capacity_at_cap':int(cp>=15-1e-9),
                    'economic_growth_near_cap':int(eg>=19-1e-9),'capacity_near_cap':int(cp>=14.25-1e-9),
                    'economic_at_cap':int(economic>=25-1e-9),
                    'economic_5pct_sensitivity':20*(growth_curve(max(0,er)*1.05,extra)-growth_curve(er,extra)),
                    'capacity_5pct_sensitivity':15*(growth_curve(max(0,ir)*1.05,extra)-growth_curve(ir,extra))}
                self.mapping(actual,calculated,'independent_growth_view',(k,view))
                for field,limit in (('economic',25),('capacity',15),('utilization',10),('industry',25),('score',100)):
                    self.check(-1e-9<=actual[field]<=limit+1e-9,'unchanged_score_component_bounds',(k,view,field))
                self.check(actual['economic_5pct_sensitivity']>=-1e-9 and actual['capacity_5pct_sensitivity']>=-1e-9,
                           'nonnegative_local_growth_sensitivity',(k,view))
                if view=='legacy':
                    for field in ('economic','industry','score'):
                        self.equal(actual[field],c[field],'legacy_view_preserves_official_score_exactly',(k,field))
                    self.equal(actual['capacity'],c['industry_capacity_score'],'legacy_capacity_from_current_formula',k)
                self.counts['growth_country_score_views']+=1
            views=c['growth_evaluation']
            for soft,ordinary in (('headroom','legacy'),('targets_headroom','targets')):
                for field in ('economic_growth','capacity','economic','industry','score'):
                    self.check(views[soft][field]<=views[ordinary][field]+1e-8,'headroom_reallocates_not_adds_points',(k,soft,field))
                for field in ('reserve','utilization','wellbeing','trade'):
                    self.equal(views[soft][field],views[ordinary][field],'unchanged_complementary_score_parts',(k,soft,field))
        self.counts['growth_metric_country_records']+=len(row['countries'])

    def trace(self,trace,result,context):
        super().trace(trace,result,context)
        units={int(i):u for i,u in trace['units'].items()}
        for name,c in result['countries'].items():
            m=c['growth_metrics'];held=[u for u in units.values() if u['owner']==name]
            unused=used=0
            for u in held:
                value=PRICE[u['good']]*((1,1.4,1.8)[u['gen']-1] if u['good'] in DURABLES else 1)
                if u['used']:used+=value*(.5 if u['good'] in DURABLES else .15)
                else:unused+=value*.15
            self.equal(m['unused_stock_value'],unused,'unused_value_from_actual_ending_uids',(context,name))
            self.equal(m['used_stock_value'],used,'used_value_from_actual_ending_uids',(context,name))
            levels={g:1 for g in BASES[name]}
            for event in trace['development']:
                if event['country']==name:levels[event['industry']]=event['to_level']
            self.equal(levels,{g:lv for g,lv in c['end_levels'].items() if lv>0},
                       'capacity_levels_from_successful_development_events',(context,name))
            initial=sum(PRICE[g]*q for g,q in BASES[name].items())
            components={g:PRICE[g]*(BASES[name].get(g,1)+(lv-1)*(2 if g in ('banana','wheat') else 1))
                        for g,lv in levels.items()}
            self.equal(m['initial_capacity'],initial,'fixed_initial_capacity_from_initial_industries',(context,name))
            self.equal(m['final_capacity'],sum(components.values()),'final_capacity_uses_fixed_prices_not_market_quotes',(context,name))
            self.counts['capacity_industry_components']+=len(components)
        self.counts['growth_evidence_detailed_traces']+=1

    def audit_goals(self,records,goals):
        keys=[eval_identity(r) for r in records]
        self.equal(len(keys),len(set(keys)),'unique_calibration_trajectories')
        self.equal({k[0] for k in keys},{'calibration'},'target_fit_contains_calibration_only')
        seeds=sorted({r['seed'] for r in records if r['scenario']=='None:normal'})
        scenarios={'None:normal'}|{f'{n}:{s}' for n in ORIGINAL for s in ('invest','trade')}
        expected={('calibration',case,seed) for case in scenarios for seed in seeds}
        self.equal(set(keys),expected,'calibration_has_exactly_declared_paired_policy_grid')
        by_key={eval_identity(r):r for r in records}
        self.equal(goals['schema'],'v12-growth-targets-1','goal_schema')
        self.equal(goals['source'],'calibration_only','goal_fit_source')
        self.equal(goals['method'],GOAL_METHOD,'declared_goal_method_is_fixed')
        self.equal(goals['calibration'],{'seeds':seeds,'n_per_policy':len(seeds),'samples_per_country':3*len(seeds),
                   'unique_economic_games':len(expected)},'goal_sample_metadata')
        for category in ('economic','industrial'):
            self.equal(set(goals[category]),set(ORIGINAL),'goals_for_original_six_only',category)
            self.equal(set(goals['raw_quantiles'][category]),set(ORIGINAL),'raw_quantiles_for_original_six_only',category)
        for name in ORIGINAL:
            selected=[];policy_counts=Counter()
            for style in POLICIES:
                case='None:normal' if style=='normal' else f'{name}:{style}'
                for seed in seeds:
                    key=('calibration',case,seed)
                    if key not in by_key:continue
                    row=by_key[key];focal=None if style=='normal' else name
                    self.equal((row['focal'],row['style'],row['behaviors']),(focal,style,{} if focal is None else {name:style}),
                               'country_goal_uses_own_focal_policy_only',(name,key))
                    self.equal(row['world']['evaluation_config']['behaviors'],row['behaviors'],'learning_policy_matches_actual_execution',(name,key))
                    selected.append(row['countries'][name]['growth_metrics']);policy_counts[style]+=1
            self.equal(policy_counts,{s:len(seeds) for s in POLICIES},'equal_policy_weight_in_each_country_goal',name)
            self.equal(len(selected),3*len(seeds),'no_peer_policy_results_reused_in_target_fit',name)
            if len(selected)<2:continue
            eq=statistics.quantiles([m['asset_gain'] for m in selected],n=4,method='inclusive')[2]
            iq=statistics.quantiles([m['capacity_growth'] for m in selected],n=4,method='inclusive')[2]
            eg=round_goal(eq,50,5);ig=round_goal(iq,.1,.05)
            self.equal(goals['raw_quantiles']['economic'][name],eq,'independent_equal_weight_economic_p75',name)
            self.equal(goals['raw_quantiles']['industrial'][name],iq,'independent_equal_weight_capacity_p75',name)
            self.equal(goals['economic'][name],eg,'economic_goal_floor_and_readable_ceiling',name)
            self.equal(goals['industrial'][name],ig,'capacity_goal_floor_and_readable_ceiling',name)
            self.goal_samples[name]={'policies':dict(policy_counts),'samples':len(selected),'economic_p75':eq,
                'industrial_p75':iq,'economic_goal':eg,'industrial_goal':ig}
            self.counts['country_policy_learning_observations']+=len(selected)
        self.counts['calibration_trajectories_for_goal_fit']+=len(records)

    def audit_selection(self,records,goals,selection):
        expected_header={'schema':'v12-policy-selection-1','source':'calibration_only',
            'criterion':'own mean candidate total score','tie_order':list(POLICIES),'tie_tolerance':1e-9,
            'calibration_seeds':goals['calibration']['seeds'],
            'scope':'Each selected policy belongs to a separate focal-country world; no jointly optimized world was simulated.'}
        self.equal(set(selection),set(expected_header)|{'selections'},'policy_selection_schema')
        for key,value in expected_header.items():self.equal(selection[key],value,'policy_selection_frozen_method',key)
        self.equal(set(selection['selections']),set(VIEWS),'all_four_views_have_frozen_policy_selection')
        by_key={eval_identity(r):r for r in records};seeds=goals['calibration']['seeds']
        for view in VIEWS:
            self.equal(set(selection['selections'][view]),set(ORIGINAL),'only_original_six_policy_selections',view)
            for name in ORIGINAL:
                means={}
                for policy in POLICIES:
                    case='None:normal' if policy=='normal' else f'{name}:{policy}'
                    sample=[by_key[('calibration',case,seed)] for seed in seeds]
                    means[policy]=statistics.mean(independent_total(r['countries'][name],name,view,goals) for r in sample)
                    self.counts['calibration_policy_score_observations']+=len(sample)
                best=max(means.values());chosen=next(p for p in POLICIES if best-means[p]<=1e-9)
                expected={'policy':chosen,'scenario':'None:normal' if chosen=='normal' else f'{name}:{chosen}',
                    'calibration_mean_score':means[chosen],'calibration_n':len(seeds)}
                actual=selection['selections'][view][name];context=(view,name)
                self.equal(set(actual),set(expected)|{'policy_means'},'frozen_selection_entry_schema',context)
                for field,value in expected.items():self.equal(actual[field],value,'selected_only_on_own_calibration_score',(context,field))
                self.mapping(actual['policy_means'],means,'all_three_calibration_policy_means',context)
                self.counts['frozen_policy_selections_verified']+=1


def check_frozen_inputs(audit,folder):
    frozen=read_json(folder/'freeze_manifest.json')
    root=folder.parent
    artifacts={'protocol_sha256':'pre_run_plan.json','goals_sha256':'goals.json',
        'calibration_runs_sha256':'calibration_runs.jsonl.gz',
        'calibration_manifest_sha256':'calibration_manifest.json','tests_manifest_sha256':'tests_manifest.json',
        'selection_sha256':'frozen_selection.json','calibration_traces_sha256':'calibration_traces.json.gz'}
    for field,filename in artifacts.items():audit.equal(sha(folder/filename),frozen[field],'frozen_input_artifact_hash',filename)
    for field in ('source_sha256','test_sha256','inherited_source_sha256'):
        for filename,digest in frozen[field].items():
            audit.equal(sha(root/filename),digest,'frozen_source_or_test_hash',(field,filename))
    provenance=read_json(root/'V11_PROVENANCE.json')
    audit.equal(len(provenance['files']),69,'all_original_v11_python_files_preserved')
    audit.equal(frozen['inherited_source_sha256'],provenance['files'],'freeze_preserves_exact_v11_provenance')
    audit.equal(frozen['schema'],'v12-growth-freeze-1','freeze_schema')
    audit.equal(frozen['holdout_not_executed'],True,'freeze_declares_holdout_not_started')
    for field,value in (('calibration_games',780),('holdout_games_planned',3100),('stress_games_planned',300)):
        audit.equal(frozen[field],value,'freeze_game_counts',field)
    cal=read_json(folder/'calibration_manifest.json')
    for field,value in (('phase','calibration'),('completed_games',780),('calibration_games',780),
                        ('holdout_games',0),('stress_games',0),('representative_traces',13),('verification_failures',0)):
        audit.equal(cal[field],value,'calibration_finished_before_untouched_data',field)
    for field in ('source_sha256','test_sha256','inherited_source_sha256',*artifacts):
        if field in cal:audit.equal(cal[field],frozen[field],'calibration_manifest_matches_freeze',field)
    audit.check(datetime.fromisoformat(cal['completed_at'])<=datetime.fromisoformat(frozen['created_at']),
                'goals_and_selection_frozen_after_calibration_completion')
    tests=read_json(folder/'tests_manifest.json')
    for field in ('passed','source_unchanged','tests_unchanged','inherited_unchanged'):
        audit.equal(tests[field],True,'frozen_test_receipt',field)
    for field in ('failures','errors','skipped'):audit.equal(tests[field],0,'no_failed_or_skipped_tests',field)
    audit.equal(tests['inherited_tests'],337,'all_v11_tests_retained')
    audit.check(tests['test_count']>337,'new_growth_tests_executed')
    audit.equal(cal['tests_completed'],tests['test_count'],'calibration_used_recorded_test_suite')
    audit.equal(tests['validation_source_sha256'],frozen['source_sha256'],'tested_sources_equal_frozen_sources')
    audit.equal(tests['test_sha256'],frozen['test_sha256'],'tested_files_equal_frozen_tests')
    plan=read_json(folder/'pre_run_plan.json')
    for field,value in (('schema','v12-growth-protocol-1'),('planned_games',4180),('calibration_games',780),
        ('holdout_games',3100),('stress_games',300),('views',list(VIEWS)),('goal_method',GOAL_METHOD),
        ('score_views_are_extra_games',False),('holdout_requires_reviewed_freeze_hash',True),
        ('no_tuning_after_holdout',True),('exclude_peer_policy_observations',True)):
        audit.equal(plan[field],value,'preregistered_growth_protocol',field)
    return frozen


def compare_identity(audit,record,other,label,context):
    for field in IDENTITY_FIELDS:audit.equal(other[field],record[field],label,(context,field))


def write_report(audit,report,target):
    report.update(status='failed' if audit.errors else 'passed',audit_counts=dict(audit.counts),
                  checks_evaluated=audit.checks,errors=audit.errors,goal_samples=audit.goal_samples,
                  completed_at=datetime.now(timezone.utc).isoformat())
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,
        default=lambda v:sorted(v,key=repr) if isinstance(v,set) else repr(v)),encoding='utf-8')
    print(json.dumps({'status':report['status'],'counts':report['audit_counts'],'checks':audit.checks,
                      'errors':len(audit.errors),'report':str(target)},ensure_ascii=False))
    return int(bool(audit.errors))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=Path(__file__).parent/'growth_results')
    parser.add_argument('--stage',choices=('calibration','full'),default='full')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();folder=args.results.resolve()
    target=args.out or folder/('independent_calibration_audit.json' if args.stage=='calibration' else 'independent_audit.json')
    required=['pre_run_plan.json','calibration_runs.jsonl.gz','calibration_manifest.json','goals.json',
              'freeze_manifest.json','tests_manifest.json','frozen_selection.json','calibration_traces.json.gz']
    required+=['calibration_traces.json.gz'] if args.stage=='calibration' else [
        'runs.jsonl.gz','round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz','run_manifest.json',
        'holdout_start.json','independent_calibration_audit.json']
    missing=[f for f in required if not (folder/f).exists()]
    if missing:
        print(json.dumps({'status':'pending_final_results','stage':args.stage,'missing':missing}));return 0
    goals=read_json(folder/'goals.json');audit=Audit(goals);frozen=check_frozen_inputs(audit,folder)
    calibration=read_lines(folder/'calibration_runs.jsonl.gz')
    audit.audit_goals(calibration,goals)
    cal_manifest=read_json(folder/'calibration_manifest.json')
    audit.equal(cal_manifest['verification_calls'],sum(r['world']['verify_calls'] for r in calibration),'calibration_invariant_calls_accounted_for')
    selection=read_json(folder/'frozen_selection.json');audit.audit_selection(calibration,goals,selection)
    audit.equal(goals['calibration']['seeds'],list(range(90000,90060)),'declared_calibration_seed_range')
    audit.equal(len(calibration),780,'calibration_unique_economic_games')
    audit.equal(goals['calibration']['samples_per_country'],180,'three_policies_times_sixty_per_country')
    report={'scope':'Independent v12 saved-result audit; no scorer or economic engine imported or executed.',
        'stage':args.stage,'warnings':[],'frozen_goal_sha256':frozen['goals_sha256'],
        'frozen_selection_sha256':frozen['selection_sha256'],
        'freeze_manifest_sha256':sha(folder/'freeze_manifest.json')}
    if args.stage=='calibration':
        by_key={eval_identity(r):r for r in calibration}
        for row in calibration:audit.run_summary(row)
        trace_keys=[]
        for label,trace in read_json(folder/'calibration_traces.json.gz').items():
            key=eval_identity(trace);trace_keys.append(key)
            audit.check(key in by_key,'calibration_trace_matches_original_game',(label,key))
            if key not in by_key:continue
            compare_identity(audit,by_key[key],trace,'calibration_trace_identity',label)
            audit.equal(trace['result'],by_key[key],'raw_calibration_trace_summary_exact',key)
            audit.trace(trace,by_key[key],key)
        expected={(phase,case,90000) for phase,case,seed in by_key}
        audit.equal(set(trace_keys),expected,'first_seed_for_every_calibration_condition')
        audit.equal(len(trace_keys),13,'calibration_representative_count')
        report.update(completed_games=len(calibration),representative_traces=len(trace_keys),
            holdout_started_at_audit=(folder/'holdout_start.json').exists(),
            method_notes=['Targets use exactly180 observations per original nation:60 own normal,60 own invest,60 own trade.',
                          'The shared normal control comprises60 economic games, not360.',
                          'No holdout or stress observations are read to learn the goals.',
                          'Each of24 view/country policy choices is recomputed from own calibration scores only, with declared tie priority.',
                          'Selected policies concern separate focal-country worlds, not a world where six policies are optimized simultaneously.',
                          'This stage audits calibration and frozen inputs only; it is not a completed holdout audit.'])
        return write_report(audit,report,target)

    rows=read_lines(folder/'runs.jsonl.gz');keys=[eval_identity(r) for r in rows];by_key={eval_identity(r):r for r in rows}
    audit.equal(len(keys),len(set(keys)),'unique_physical_trajectory_identity')
    audit.equal(len(rows),4180,'complete_unique_economic_game_count')
    audit.equal(Counter(r['phase'] for r in rows),{'calibration':780,'holdout':3100,'stress':300},'phase_game_counts_not_score_views')
    for row in rows:audit.run_summary(row)
    for raw in calibration:
        key=eval_identity(raw)
        audit.check(key in by_key,'raw_calibration_survives_in_final_results',key)
        if key in by_key:audit.equal(original_projection(by_key[key]),raw,'scoring_preserves_raw_calibration_economics_exactly',key)
    holdout={eval_identity(r):r for r in rows if r['phase']=='holdout'}
    for filename,method in (('round_ledgers.jsonl.gz',audit.ledger),('raw_round_ledgers.jsonl.gz',audit.raw_ledger)):
        groups=read_lines(folder/filename);gkeys=[eval_identity(g) for g in groups]
        audit.equal(len(gkeys),len(set(gkeys)),'ledger_scenarios_do_not_alias',filename)
        audit.equal(set(gkeys),set(holdout),'every_holdout_game_has_ledger',filename)
        total=0
        for group in groups:
            key=eval_identity(group)
            compare_identity(audit,holdout[key],group,'ledger_retains_full_behavior_identity',(filename,key))
            method(group['rows'],holdout[key],key);total+=len(group['rows'])
        audit.equal(total,251100,'complete_holdout_ledger_row_count',filename)
    trace_keys=[]
    for label,trace in read_json(folder/'first_seed_traces.json.gz').items():
        key=eval_identity(trace);trace_keys.append(key)
        audit.check(key in by_key,'representative_trace_matches_final_game',(label,key))
        if key not in by_key:continue
        compare_identity(audit,by_key[key],trace,'trace_retains_full_behavior_identity',label)
        audit.equal(trace['result'],by_key[key],'trace_embedded_summary_matches_final_record_exactly',key)
        audit.trace(trace,by_key[key],key)
    audit.equal(len(trace_keys),len(set(trace_keys)),'representative_traces_are_unique')
    audit.equal(len(trace_keys),54,'all_fiftyfour_representative_conditions')
    seed_ranges={'calibration':(90000,90059),'holdout':(92000,92099),'stress':(94000,94029)}
    conditions={p:{r['scenario'] for r in rows if r['phase']==p} for p in seed_ranges}
    calibration_cases={'None:normal'}|{f'{n}:{s}' for n in ORIGINAL for s in ('invest','trade')}
    holdout_cases={'None:normal'}|{f'{n}:{s}' for n in ORIGINAL for s in ('invest','trade','cheap','minimum','idle')}
    audit.equal(conditions['calibration'],calibration_cases,'calibration_declared_policy_schedule')
    audit.equal(conditions['holdout'],holdout_cases,'holdout_declared_policy_schedule')
    stress_cases={f'{n}:minimum_passive' for n in ORIGINAL}|{
        'Mechania:idle','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum','None:no_trade'}
    audit.equal(conditions['stress'],stress_cases,'stress_declared_boundary_schedule')
    expected={(p,case,seed) for p,(lo,hi) in seed_ranges.items() for case in conditions[p] for seed in range(lo,hi+1)}
    audit.equal(set(keys),expected,'all_declared_seed_grids_complete_without_leakage')
    expected_traces={(p,case,lo) for p,(lo,hi) in seed_ranges.items() for case in conditions[p]}
    audit.equal(set(trace_keys),expected_traces,'exact_first_seed_trace_schedule')
    manifest=read_json(folder/'run_manifest.json')
    plan=read_json(folder/'pre_run_plan.json')
    for field,value in plan.items():audit.equal(manifest[field],value,'final_manifest_preserves_preregistered_plan',field)
    for phase,(lo,hi) in seed_ranges.items():
        audit.equal(plan[phase+'_seed_range'],[lo,hi],'preregistered_disjoint_seed_ranges',phase)
        specs={s['scenario']:s for s in plan[phase+'_scenarios']}
        audit.equal(set(specs),conditions[phase],'run_conditions_equal_frozen_protocol',phase)
        for row in rows:
            if row['phase']!=phase:continue
            spec=specs[row['scenario']];behaviors=dict(spec['behaviors'])
            if spec['focal'] is not None:behaviors[spec['focal']]=spec['style']
            audit.equal((row['focal'],row['style'],row['behaviors']),
                        (spec['focal'],spec['style'],behaviors),'exact_all_actor_behavior_per_scenario',eval_identity(row))
    for field,value in (('completed_games',4180),('calibration_games',780),('holdout_games',3100),('stress_games',300),
        ('representative_traces',54),('holdout_cash_ledger_rows',251100),('holdout_raw_ledger_rows',251100),
        ('verification_failures',0),('source_unchanged',True),('holdout_started_after_freeze',True),
        ('score_views_are_extra_games',False),('test_and_smoke_games_excluded',True)):
        audit.equal(manifest[field],value,'final_manifest_scope_and_integrity',field)
    audit.equal(manifest['verification_calls'],sum(r['world']['verify_calls'] for r in rows),'all_invariant_calls_accounted_for')
    for field in ('source_sha256','source_sha256_before','source_sha256_after'):
        audit.equal(manifest[field],frozen['source_sha256'],'source_unchanged_across_both_stages',field)
    for field in ('test_sha256_before','test_sha256_after'):
        audit.equal(manifest[field],frozen['test_sha256'],'tests_unchanged_across_both_stages',field)
    for field in ('inherited_source_sha256','tests_manifest_sha256','goals_sha256','selection_sha256',
                  'protocol_sha256','calibration_runs_sha256','calibration_manifest_sha256'):
        audit.equal(manifest[field],frozen[field],'final_results_retain_reviewed_freeze',field)
    audit.equal(manifest['freeze_sha256'],sha(folder/'freeze_manifest.json'),'explicitly_approved_freeze_retained')
    start=read_json(folder/'holdout_start.json')
    audit.equal(manifest['holdout_start_sha256'],sha(folder/'holdout_start.json'),'holdout_start_receipt_hash')
    audit.equal(start['approved_freeze_sha256'],sha(folder/'freeze_manifest.json'),'holdout_required_exact_reviewed_freeze')
    for field in ('goals_sha256','selection_sha256','protocol_sha256','source_sha256','test_sha256'):
        audit.equal(start[field],frozen[field],'holdout_start_uses_frozen_inputs',field)
    review=read_json(folder/'independent_calibration_audit.json')
    audit.equal(review['status'],'passed','independent_calibration_review_passed_before_holdout')
    audit.equal(review['freeze_manifest_sha256'],sha(folder/'freeze_manifest.json'),'reviewed_exact_freeze_file')
    audit.equal(review['frozen_goal_sha256'],frozen['goals_sha256'],'reviewed_exact_goal_file')
    audit.equal(review['frozen_selection_sha256'],frozen['selection_sha256'],'reviewed_exact_policy_choice_file')
    audit.equal(review['holdout_started_at_audit'],False,'independent_review_preceded_holdout')
    moments=[frozen['created_at'],review['completed_at'],start['started_at'],manifest['completed_at']]
    parsed=[datetime.fromisoformat(t) for t in moments]
    audit.equal(parsed,sorted(parsed),'calibration_review_holdout_completion_temporal_order')
    report.update(completed_runs=len(rows),groups={str(k):v for k,v in Counter((r['phase'],r['scenario']) for r in rows).items()},
                  representative_traces=len(trace_keys),legacy_score_coverage=dict(audit.score_coverage))
    report['method_notes']=[
        'All4180 economic trajectories are distinct; the four score views are not additional games.',
        'Only country growth targets and the shape of the20-point growth/15-point capacity curves vary.',
        'Official scores and all original accounting fields are preserved, including the legacy v11 trade view.',
        'The calibration subset uses each country only under its own three equally weighted policy observations.',
        'Policy selection is independently recomputed from calibration alone for each of24 view/country pairs; choices are frozen before holdout.',
        'Chosen policies belong to distinct focal-country worlds; no simultaneous six-country optimized world is inferred.',
        'The780 raw calibration records match the final calibration records after removing exactly the posthoc score fields.',
        'Inventory value, automatic income and output-sensitive utilization remain unchanged; their known incentive limitations persist.',
        'Only original-six totals are evaluated; the three additional countries keep None in all four views.',
        'Detailed physical/decision reconstruction covers54 representative traces; summary and holdout ledger checks cover their full declared datasets.',
        'Statistical target calibration and ceiling diagnostics do not establish equal human difficulty or observed learning effects.']
    return write_report(audit,report,target)


if __name__=='__main__':raise SystemExit(main())

