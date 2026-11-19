"""Korean v12 report from completed and independently audited saved records.

This is a reader/formatter. It never imports the game or scoring engine,
chooses target values, simulates games, or substitutes calibration for holdout.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from functools import lru_cache
import gzip
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import statistics

from build_routing_report import read_json,read_lines,need,get,f,ci,table,Metric,PairedValues,Cell

ROOT=Path(__file__).resolve().parent
DEFAULT_RESULTS=ROOT/'growth_results'
COUNTRIES={'Tropia':'트로피아','Grainia':'그레니아','Oilia':'오일리아','Mechania':'메카니아',
           'Mineria':'미네리아','Technia':'테크니아','Novia':'노비아','Agrea':'아그레아','Ferria':'페리아'}
ORIGINAL=tuple(COUNTRIES)[:6]
VIEWS={'legacy':'기존 평가','targets':'목표 조정','headroom':'기본·도전 상한','targets_headroom':'목표 조정+기본·도전'}
BEHAVIORS={'normal':'정상','invest':'투자 중심','trade':'무역 중심','cheap':'반값 공개 판매',
           'minimum':'1G 공개 판매','minimum_passive':'1G+투자 중단','idle':'무행동'}
CALIBRATION_CASES=('None:normal',)+tuple(f'{n}:{s}' for n in ORIGINAL for s in ('invest','trade'))
HOLDOUT_CASES=('None:normal',)+tuple(f'{n}:{s}' for n in ORIGINAL for s in ('invest','trade','cheap','minimum','idle'))
STRESS_CASES=tuple(f'{n}:minimum_passive' for n in ORIGINAL)+(
    'Mechania:idle','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum','None:no_trade')
PHASES={'calibration':(CALIBRATION_CASES,range(90000,90060)),
        'holdout':(HOLDOUT_CASES,range(92000,92100)),
        'stress':(STRESS_CASES,range(94000,94030))}


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.anchors=[];self.external=[];self.qa=[]
        self.tables=0;self.rows=0;self.width=None;self.cells=None;self.errors=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a' and a.get('href','').startswith('#'):self.anchors.append(a['href'][1:])
        if any(a.get(k,'').startswith(('http:','https:','//')) for k in ('href','src')):self.external.append(a)
        if 'data-qa' in a:self.qa.append(json.loads(a['data-qa']))
        if tag=='table':self.tables+=1;self.width=None
        if tag=='tr':self.rows+=1;self.cells=0
        if tag in ('td','th') and self.cells is not None:self.cells+=1
    def handle_endtag(self,tag):
        if tag=='tr':
            if self.width is None:self.width=self.cells
            elif self.width!=self.cells:self.errors.append(f'Table {self.tables}: row cell count differs.')
            self.cells=None


def check_structure(html,report,folder):
    p=StructureParser();p.feed(html);p.close()
    need(not p.errors,'; '.join(p.errors))
    need(len(p.ids)==len(set(p.ids)) and set(p.ids)=={f's{i}' for i in range(1,12)},'Unique complete section IDs required.')
    need(set(p.anchors)==set(p.ids),'Every section must be reachable from navigation.')
    need(not p.external,'Report must be self-contained.')
    need(len(p.qa)>=150,'Independently locatable numeric cells required.')
    result={'status':'passed','report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),
            'sections':len(p.ids),'tables':p.tables,'rows':p.rows,'numeric_cells':len(p.qa),
            'external_assets':len(p.external),'errors':[],
            'scope':'HTML structure and numeric locator syntax; no browser screenshot validation.'}
    (folder/'report_structure_qa.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


class SavedResults:
    def __init__(self,folder):
        self.folder=folder
        required=('run_manifest.json','summary.json','runs.jsonl.gz','goals.json','frozen_selection.json',
                  'tests_manifest.json','independent_audit.json','independent_calibration_audit.json','freeze_manifest.json','holdout_start.json',
                  'calibration_manifest.json','calibration_runs.jsonl.gz','calibration_traces.json.gz',
                  'pre_run_plan.json','round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz')
        need(all((folder/name).is_file() for name in required),'Completed formal records, frozen goals, tests and audit required.')
        self.meta=read_json(folder/'run_manifest.json')
        summary=read_json(folder/'summary.json')
        need(summary['metadata']==self.meta,'Summary and completed manifest differ.')
        del summary
        m=self.meta
        need((m['completed_games'],m['calibration_games'],m['holdout_games'],m['stress_games'])==(4180,780,3100,300),'Unexpected completed game counts.')
        need(m['rounds']==m['countries']==9 and m['ranked_countries']==list(ORIGINAL),'Unexpected economic/ranking scope.')
        need(m['views']==list(VIEWS) and m['source_unchanged'] is True and m['verification_failures']==0,'Frozen verified score views required.')
        need(m['holdout_started_after_freeze'] is True and m['score_views_are_extra_games'] is False,'Separate frozen-target holdout required.')
        for phase,(cases,seeds) in PHASES.items():
            need(m[phase+'_seed_range']==[seeds.start,seeds.stop-1],'Unexpected phase seed band.')
        self.freeze=read_json(folder/'freeze_manifest.json');self.holdout_start=read_json(folder/'holdout_start.json')
        need(self.freeze['holdout_not_executed'] is True,'Freeze must precede holdout.')
        need(hashlib.sha256((folder/'freeze_manifest.json').read_bytes()).hexdigest()==m['freeze_sha256']==self.holdout_start['approved_freeze_sha256'],'Freeze hash mismatch.')
        for key,name in (('goals_sha256','goals.json'),('selection_sha256','frozen_selection.json'),('protocol_sha256','pre_run_plan.json'),
                         ('calibration_runs_sha256','calibration_runs.jsonl.gz'),('calibration_manifest_sha256','calibration_manifest.json'),
                         ('tests_manifest_sha256','tests_manifest.json')):
            need(hashlib.sha256((folder/name).read_bytes()).hexdigest()==m[key]==self.freeze[key],'Frozen evidence hash differs: '+name)
        self.goals=read_json(folder/'goals.json')
        need(self.goals['source']=='calibration_only','Targets must use calibration only.')
        need(self.goals['calibration']['seeds']==list(range(90000,90060)),'Unexpected calibration seeds.')
        need(self.goals['calibration']['samples_per_country']==180 and self.goals['calibration']['unique_economic_games']==780,'Incorrect equal-policy calibration scope.')
        self.selection=read_json(folder/'frozen_selection.json')
        need(self.selection['source']=='calibration_only' and self.selection['schema']=='v12-policy-selection-1','Selection must use only calibration.')
        need(self.selection['calibration_seeds']==list(range(90000,90060)) and self.selection['tie_order']==['normal','invest','trade'],'Incorrect frozen selection cohort/order.')
        self.tests=read_json(folder/'tests_manifest.json')
        need(self.tests['passed'] is True and self.tests['test_count']>337 and self.tests['test_count']==m['tests_completed'],'Inherited and new tests must pass.')
        need(self.tests['errors']==self.tests['failures']==self.tests['skipped']==0,'Tests must not fail or skip.')
        self.audit=read_json(folder/'independent_audit.json')
        need(self.audit['status']=='passed' and not self.audit['errors'],'Independent audit must pass.')
        self.calibration_audit=read_json(folder/'independent_calibration_audit.json')
        need(self.calibration_audit['status']=='passed' and not self.calibration_audit['errors'] and self.calibration_audit['holdout_started_at_audit'] is False,'Calibration review must precede holdout.')
        need(self.calibration_audit['freeze_manifest_sha256']==m['freeze_sha256'],'Calibration review must cover the exact frozen inputs.')
        self.rows=read_lines(folder/'runs.jsonl.gz');self.groups=defaultdict(list)
        expected={(phase,case,seed) for phase,(cases,seeds) in PHASES.items() for case in cases for seed in seeds}
        keys=[(r['phase'],r['scenario'],r['seed']) for r in self.rows]
        need(len(keys)==len(set(keys))==4180 and set(keys)==expected,'Saved records differ from the declared unique schedule.')
        for r in self.rows:
            need(r['mode']=='market_first' and set(r['countries'])==set(COUNTRIES),'Frozen nine-country economy required.')
            config=r['world']['growth_evaluation_config']
            need(config['economic_rules_unchanged'] is True and config['official_scores_unchanged'] is True and config['score_feedback_to_actions'] is False,'Views must not affect economy or official scores.')
            need(config['v11_trade_view']=='legacy' and config['views']==list(VIEWS),'Unexpected trade or score view.')
            for n,country in r['countries'].items():
                views=country['growth_evaluation']
                need(set(views)==set(VIEWS),'Every score view must be explicit.')
                if n in ORIGINAL:
                    need(views['legacy']['score']==country['score'],'Original score changed.')
                else:need(all(v is None for v in views.values()),'Uncalibrated countries must remain unranked.')
            self.groups[(r['phase'],r['scenario'])].append(r)
        ledger_keys={(case,seed) for case in HOLDOUT_CASES for seed in PHASES['holdout'][1]}
        cells={(n,r) for n in COUNTRIES for r in range(1,10)}
        for filename in ('round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz'):
            observed=set()
            with gzip.open(folder/filename,'rt',encoding='utf-8') as stream:
                for line in stream:
                    r=json.loads(line);key=(r['scenario'],r['seed'])
                    need(r['phase']=='holdout' and key not in observed,'Incorrect or duplicate ledger identity.')
                    observed.add(key)
                    need(len(r['rows'])==81 and {(x['country'],x['round']) for x in r['rows']}==cells,'Incomplete country-round ledger.')
            need(observed==ledger_keys,'Incomplete holdout ledgers.')
        self.traces=read_json(folder/'first_seed_traces.json.gz')
        trace_keys={(phase,case,seeds.start) for phase,(cases,seeds) in PHASES.items() for case in cases}
        need(len(self.traces)==54 and {(t['phase'],t['scenario'],t['seed']) for t in self.traces.values()}==trace_keys,'All 54 representatives are required.')
        for view in VIEWS:
            for n in ORIGINAL:
                choice=self.selection['selections'][view][n]
                policy=choice['policy'];case=choice['scenario']
                need(policy in ('normal','invest','trade') and case==('None:normal' if policy=='normal' else f'{n}:{policy}'),'Frozen selected policy identity differs.')
                observed=statistics.mean(r['countries'][n]['growth_evaluation'][view]['score'] for r in self.groups[('calibration',case)])
                need(choice['calibration_n']==60 and abs(observed-choice['calibration_mean_score'])<1e-9,'Frozen selected calibration mean differs.')

    @lru_cache(maxsize=None)
    def mean(self,case,path,phase='holdout'):
        value=statistics.mean(get(r,path) for r in self.groups[(phase,case)])
        return Metric(value,{'kind':'mean','experiment':f'{phase}:market_first:{case}','metric':path})
    def values(self,case,path,phase='holdout'):
        return {r['seed']:get(r,path) for r in self.groups[(phase,case)]}
    def diff(self,case,path,phase='holdout',control='None:normal'):
        left=self.values(control,path,phase);right=self.values(case,path,phase)
        need(left.keys()==right.keys(),'Paired comparisons require identical seeds.')
        pair=f'{phase}:market_first:{case}' if control=='None:normal' else f'{phase}:market_first:{control}->{case}'
        return PairedValues([right[s]-left[s] for s in sorted(left)],{'kind':'ci','pair':pair,'metric':path})
    def count(self,case,path,phase='holdout'):
        vals=self.values(case,path,phase)
        return Cell(f'{sum(x>0 for x in vals.values())}/{len(vals)}',{'kind':'count','experiment':f'{phase}:market_first:{case}','metric':path})
    def higher(self,case,path,phase='holdout',control='None:normal'):
        left=self.values(control,path,phase);right=self.values(case,path,phase)
        need(left.keys()==right.keys(),'Paired frequencies require identical seeds.')
        return Cell(f'{sum(right[s]>left[s]+1e-9 for s in left)}/{len(left)}',
                    {'kind':'paired_greater_count','experiment':f'{phase}:market_first:{case}',
                     'control':f'{phase}:market_first:{control}','metric':path})
    def highest(self,case,name,view='legacy',phase='holdout'):
        rr=self.groups[(phase,case)];path=f'countries.{name}.growth_evaluation.{view}.score'
        paths=[f'countries.{n}.growth_evaluation.{view}.score' for n in ORIGINAL]
        return Cell(f'{sum(get(r,path)>=max(get(r,k) for k in paths)-1e-9 for r in rr)}/{len(rr)}',
                    {'kind':'top_count','experiment':f'{phase}:market_first:{case}','metric':path,'metrics':paths})
    def either_g3(self,case,phase='stress'):
        rr=self.groups[(phase,case)];paths=[f'countries.{n}.routing.g3_electronics_used' for n in ('Technia','Novia')]
        return Cell(f'{sum(any(get(r,k)>0 for k in paths) for r in rr)}/{len(rr)}',
                    {'kind':'anycount','experiment':f'{phase}:market_first:{case}','metrics':paths})
    def country(self,case,name,path,phase='holdout'):return self.mean(case,f'countries.{name}.{path}',phase)
    def world(self,case,path,phase='holdout'):return self.mean(case,'world.'+path,phase)
    def score(self,case,name,view='legacy',field='score',phase='holdout'):
        return self.country(case,name,f'growth_evaluation.{view}.{field}',phase)
    def goal(self,path):return Metric(get(self.goals,path),{'kind':'goal','metric':path})
    def score_spread(self,case,view,phase='holdout'):
        values=[]
        for r in self.groups[(phase,case)]:
            scores=[r['countries'][n]['growth_evaluation'][view]['score'] for n in ORIGINAL]
            values.append(max(scores)-min(scores))
        return Metric(statistics.mean(values),{'kind':'diagnostic','experiment':f'{phase}:market_first:{case}',
                      'view':view,'metric':'original_score_spread'})
    def spread_diff(self,case,view,phase='holdout'):
        values=[]
        for r in self.groups[(phase,case)]:
            before=[r['countries'][n]['growth_evaluation']['legacy']['score'] for n in ORIGINAL]
            after=[r['countries'][n]['growth_evaluation'][view]['score'] for n in ORIGINAL]
            values.append((max(after)-min(after))-(max(before)-min(before)))
        return PairedValues(values,{'kind':'view_ci','experiment':f'{phase}:market_first:{case}',
                            'comparison':'legacy->'+view,'metric':'world.original_score_spread'})


def build(folder,report):
    data=SavedResults(folder);meta=data.meta;tests=data.tests;audit=data.audit
    c=data.country;w=data.world;s=data.score
    parts=[]
    def add(text):parts.append(text)
    def p(text,cls=''):add('<p class="'+cls+'">'+escape(text)+'</p>')
    def h(number,text):add(f'<section id="s{number}"><h2>{number}. {escape(text)}</h2>')
    def end():add('</section>')
    def pt(headers,rows):return '<div class="prose-table">'+table(headers,rows)+'</div>'
    def cp(name,field):return f'countries.{name}.{field}'
    def sp(name,view,field='score'):return cp(name,f'growth_evaluation.{view}.{field}')
    def mp(name,field):return cp(name,'growth_metrics.'+field)

    add('<header><div class="eyebrow">아이디어 노트 · #11 무역 게임 · v12</div><h1>나라별 성장 목표와<br>점수 상한을 다시 비교하다</h1><p>9개국·9라운드 · 목표 조정과 상한의 2×2 비교</p><div class="badge">목표 조정 780게임 · 별도 검증 3,100게임 · 추가 조건 300게임</div></header>')
    titles=((1,'검토 범위'),(2,'네 가지 평가'),(3,'목표 동결'),(4,'나라별 점수'),(5,'상한과 변별'),(6,'전략 비교'),(7,'남은 문제'),(8,'추가 조건'),(9,'학생 경험'),(10,'검증·재현'),(11,'상세 평균'))
    add('<nav>'+''.join(f'<a href="#s{i}">{escape(t)}</a>' for i,t in titles)+'</nav>')

    h(1,'이번에는 경제 행동과 평가 변경을 분리했다')
    add('<div class="callout"><h3>검토 결론</h3><p>기존 목표를 둔 채 상한만 바꾸는 안은 이번 표본에서 지지되지 않았다. 테크니아에 최고점이 더 몰렸고 게임 안의 점수 차이도 커졌다. 국가별 목표 조정은 최고점 편중을 줄였으며, 목표와 상한을 함께 바꾼 안은 같은 정상 경제 경로에서 게임별 점수 범위도 줄였다.</p><p>목표 조정 두 후보의 장단점은 다르다. 단순한 계산 구조를 우선하면 목표 조정만, 공통 정상 정책의 격차 완화를 우선하면 결합안이 검토 후보가 된다. 어느 쪽도 국가별 공정성이 완성됐다고 확정하지 않는다. 공식 점수는 유지하며, 사전 선택 정책의 기회와 경제 성장 지표의 남은 한계를 함께 확인한다.</p></div>')
    add(table(['같은 정상 경로의 핵심 결과','기존 평가','목표 조정','기본·도전 상한','목표 조정+기본·도전'],[
        ('게임별6국 점수 범위 평균',)+tuple(f(data.score_spread('None:normal',v)) for v in VIEWS),
        ('테크니아 최고점 빈도',)+tuple(data.highest('None:normal','Technia',v) for v in VIEWS),
        ('메카니아 최고점 빈도',)+tuple(data.highest('None:normal','Mechania',v) for v in VIEWS),
    ]))
    p('v11에서 테크니아의 점수가 자주 높았고, 실제 발전 정도가 달라도 산업 능력 15점 상한에 함께 도달했다. 이번 검증은 국가별 목표를 다시 정하는 효과와 기본·도전 목표로 상한을 바꾸는 효과를 따로 비교한다. 특정 국가나 가격 전략을 반드시 이기거나 지게 만드는 목표를 전제로 하지 않는다.')
    p('고유 경제 궤적은 4,180개다. 목표를 정하는 780개, 그 뒤 고정된 목표로 확인하는 별도 본 검증 3,100개, 추가 조건 300개를 구별한다. 네 가지 사후 점수는 같은 경제 기록에 적용하며, 네 배의 독립 경제 실험으로 세지 않는다.')
    p('돈·가격·거래·투자·생산·만족도는 평가 보기에 따라 바뀌지 않는다. 공식 점수도 유지한다. 달라지는 것은 경제 성장 20점과 산업 능력 15점의 목표값·상한 처리뿐이며, 예비자금 5점·산업 활용 10점·무역 25점·만족도 25점은 그대로다.','callout')
    p('조정 표본의 평균을 나라별로 비슷하게 만드는 것은 공정성 증명이 아니다. 별도 시드의 결과, 다양한 전략, 최고점 빈도, 상한 도달, 무행동과 투자·재고의 영향을 함께 읽어야 한다. 추가 3개국의 종합 목표는 미보정 상태이므로 종합 점수와 최고점 비교는 기존 6개국에 한정한다.','note')
    end()

    h(2,'목표 교체와 상한 변경을 2×2로 나누었다')
    add(pt(['보기','국가별 목표','점수 상한'],[
        ('기존 평가','기존 목표','목표에서 해당 성장 부분 100%'),
        ('목표 조정','별도 조정 자료의 고정 목표','목표에서 해당 성장 부분 100%'),
        ('기본·도전 상한','기존 목표','기본 목표80%, 목표의2배에서100%'),
        ('목표 조정+기본·도전','별도 조정 자료의 고정 목표','기본 목표80%, 목표의2배에서100%'),
    ]))
    p('실제 성장량÷그 나라의 목표를 r이라고 할 때, 기존은 L(r)=clip(r,0,1), 기본·도전은 H(r)=0.8×clip(r,0,1)+0.2×clip(r−1,0,1)이다. clip은 0~1 범위로 제한하는 계산이다.')
    add(table(['목표 대비 실제 성장','기존 경제 성장 /20','기본·도전 경제 성장 /20','기존 능력 /15','기본·도전 능력 /15'],[
        ('0%',0,0,0,0),('50%',10,8,7.5,6),('100%',20,16,15,12),('150%',20,18,15,13.5),('200%',20,20,15,15)]))
    p('기본 목표의 80%는 경제 성장 20점과 능력 15점 부분을 뜻한다. 예비자금 5점과 활용 10점은 그대로 더한다. 국가 전체 총점이 기본 목표에서 80점이 된다는 뜻은 아니다.')
    p('이 곡선은 상한에 닿은 경우만 바꾸지 않는다. 목표보다 낮은 구간의 점수 증가 기울기도 기존의80%로 바뀐다. 따라서 만점에 이르지 않은 국가 사이에서도 평가 차이가 달라질 수 있다.')
    p('경제 성장은 기존 평가자산의 순증가, 산업 능력은 고정 기준가격으로 가중한 기본 생산량의 증가 비율이다. 산업 활용은 실제 사용된 자국 생산 실물÷전체 자국 생산 실물의 비율을 유지한다. v11의 ready_once 무역 평가를 공식으로 채택한 비교가 아니며 기존 무역 점수를 사용한다.')
    end()

    h(3,'목표는 별도 780게임으로 정하고 고정했다')
    p('조정 시드 90000~90059에서 정상 1조건, 기존 6개국 각각 투자 중심·무역 중심의 12조건을 실행했다. 각 나라의 목표에는 자기 정상·자기 투자 중심·자기 무역 중심을 동일 비중으로 넣어 180개 관측을 사용했다. 다른 나라의 행동을 바꾼 결과를 그 나라 자신의 전략 표본으로 추가하지 않는다.')
    add(table(['국가','기존 경제 목표 G','경제 성장 P75 G','새 경제 목표 G','기존 능력 목표','능력 증가 P75','새 능력 목표'],[
        (COUNTRIES[n],f(s('None:normal',n,'legacy','economic_target')),f(data.goal('raw_quantiles.economic.'+n)),
         f(s('None:normal',n,'targets','economic_target')),f(s('None:normal',n,'legacy','industrial_target'),3),
         f(data.goal('raw_quantiles.industrial.'+n),3),f(s('None:normal',n,'targets','industrial_target'),3)) for n in ORIGINAL]))
    p('P75는 75백분위수다. 경제 목표는 최소 50G를 적용한 뒤 5G 단위로 올리고, 능력 목표는 최소 0.10을 적용한 뒤 0.05 단위로 올린다. 능력 증가 0.10은 시작 능력보다 10% 증가했다는 뜻이다.')
    p('정상 게임 하나는 6개국 모두의 기준 자료로 쓰이지만 독립 경제 게임 6개로 세지 않는다. P75·하한·올림 단위는 이번 후보를 정의하는 선택이며 교육적으로 검증된 상수는 아니다. 목표가 검증 표본의 결과를 보고 다시 움직이지 않도록 조정 시드와 본 검증 시드를 분리했다.','note')
    end()

    h(4,'정상 운영: 같은 경제 결과를 네 방식으로 평가')
    p('모두에게 정상 AI를 적용한 표는 공통 정책의 기준선이다. 나라의 생산 구조에 따라 투자 중심·무역 중심이 더 유리할 수 있으므로, 정상 정책에서 낮은 점수만으로 그 나라 역할이 불공정하다고 단정하지 않는다. 아래에는 조정 자료에서 미리 선택한 정책의 별도 검증도 구분해 제시한다.')
    add(table(['국가']+list(VIEWS.values()),[(COUNTRIES[n],)+tuple(f(s('None:normal',n,v)) for v in VIEWS) for n in ORIGINAL]))
    add('<h3>기존 6개국 중 최고점 빈도 · 동점 포함</h3>')
    add(table(['국가']+list(VIEWS.values()),[(COUNTRIES[n],)+tuple(data.highest('None:normal',n,v) for v in VIEWS) for n in ORIGINAL]))
    p('분모는 별도 본 검증 100시드다. 동점도 최고점으로 세므로 빈도의 합이 100을 넘을 수 있다. 이 값은 기존 6개국에 대한 자동 전략 진단이며, 9개국 전체 순위·학생 승률·수업 평가의 공정성 증명은 아니다.')
    add(table(['평가 보기','한 게임의6국 최대−최소 평균','기존 대비 범위 차이 [95% 구간]'],[
        (VIEWS[v],f(data.score_spread('None:normal',v)),'기준' if v=='legacy' else ci(data.spread_diff('None:normal',v))) for v in VIEWS]))
    p('범위는 각 게임 안의 최고점−최저점을 먼저 계산한 뒤100게임의 평균을 낸 것이다. 나라별 평균끼리 뺀 값과는 다르다. 점수 범위의 축소는 계산식의 압축으로도 생길 수 있으므로 단독으로 공정성이 개선됐다는 증거로 삼지 않는다.')
    p('목표 조정만 적용한 범위 차이는 평균 +0.44점이며95% 구간에0이 들어간다. 상한만 바꾸면 +3.55점으로 커지고, 목표와 상한을 결합하면 −2.26점으로 줄었다. 목표 조정의 최고점 편중 완화와 매 게임의 점수 차이 개선은 같은 결과가 아니다. 점수의 수준이 내려가도 실제 경제가 후퇴한 것은 아니다.','note')
    add('<h3>조정 자료에서 미리 선택한 정책의 별도 검증</h3>')
    selection_rows=[]
    for view in VIEWS:
        for n in ORIGINAL:
            choice=data.selection['selections'][view][n];case=choice['scenario']
            selection_rows.append((COUNTRIES[n]+' · '+VIEWS[view],BEHAVIORS[choice['policy']],
                f(s(case,n,view,phase='calibration')),f(s(case,n,view)),
                f(c(case,n,'happy')),f(c(case,n,'growth_metrics.used_units'))))
    add(table(['국가·보기','사전 선택 정책','조정60시드 평균 총점','별도100시드 평균 총점','별도 검증 만족도','별도 검증 실사용량'],selection_rows))
    p('각 보기·국가마다 조정 자료의 정상·투자 중심·무역 중심 중 자기 평균 총점이 높은 정책을 먼저 고정했다. 동점은 정상→투자 중심→무역 중심 순서이며 허용 오차는10⁻⁹점이다. 본 검증에서 가장 높게 나온 정책을 나중에 골라 보여 준 것이 아니다.')
    p('보기마다 선택된 정책이 다를 수 있어 이 표의 성적 차이에는 점수식과 정책 선택의 차이가 함께 들어간다. 점수식 자체의 효과는 같은 정상 경제 경로에 네 보기를 적용한 위 표에서 판단하고, 사전 선택 표는 각 안에서 활용할 수 있는 세 정책의 기회를 확인하는 자료로 읽는다.')
    p('이 표는 세 정책 중 사전 선택 결과다. 일반적으로 최적인 전략을 찾았다는 뜻이 아니다. 각 나라의 성적은 자국만 해당 정책으로 바뀐 별도 세계에서 나왔으므로, 여섯 나라가 동시에 맞춤 정책으로 겨룬 세계의 순위·승률로 합쳐 읽으면 안 된다.','note')
    selected_ranges={}
    for v in VIEWS:
        chosen=[float(s(data.selection['selections'][v][n]['scenario'],n,v)) for n in ORIGINAL]
        selected_ranges[v]=max(chosen)-min(chosen)
    p('국가별 사전 선택 정책의 평균 총점끼리 계산한 범위는 '+', '.join(VIEWS[v]+' '+f(selected_ranges[v])+'점' for v in VIEWS)+'이다. 이는 앞의 게임별6국 범위 평균과 다른 지표다. 조정 자료에서 무역 중심은 선택되지 않았지만, 제한된 세 자동 정책의 결과일 뿐 무역 전략 일반이나 학생의 선택이 열등하다는 뜻은 아니다.')
    add('<details><summary>경제력·산업 능력·활용 점수 분해</summary>')
    for n in ORIGINAL:
        add(table([COUNTRIES[n]]+list(VIEWS.values()),[
            (label,)+tuple(f(s('None:normal',n,v,key)) for v in VIEWS) for label,key in
            (('경제 성장 /20','economic_growth'),('예비자금 /5','reserve'),('경제력 /25','economic'),
             ('산업 능력 /15','capacity'),('실제 활용 /10','utilization'),('산업 발전 /25','industry'),
             ('만족도 /25','wellbeing'),('무역 /25','trade'),('총점 /100','score'))]))
    add('</details>');end()

    h(5,'상한이 줄었는지와 성장 차이를 구별하는지')
    add(table(['국가·보기','경제 성장20 만점','능력15 만점','경제 성장19 이상','능력14.25 이상','경제 성장량+5%의 점수 증가','능력 증가량+5%의 점수 증가'],[
        (COUNTRIES[n]+' · '+VIEWS[v],)+tuple(data.count('None:normal',sp(n,v,k)) for k in
            ('economic_growth_at_cap','capacity_at_cap','economic_growth_near_cap','capacity_near_cap'))+
        tuple(f(s('None:normal',n,v,k),3) for k in ('economic_5pct_sensitivity','capacity_5pct_sensitivity')) for n in ORIGINAL for v in VIEWS]))
    p('상한 근처는 해당 부분의 95% 이상으로 정의했다. 마지막 두 열은 목표를 5% 바꾼 값이 아니다. 목표·다른 조건을 그대로 두고 양수인 실제 성장량만 5% 늘렸을 때 해당 부분 점수가 얼마나 오르는지 계산한 민감도다. 성장량이 0이면 이 검사에서도 0이다.')
    p('만점 국가가 줄었다는 사실만으로 공정해졌다고 판단하지 않는다. 도전 목표가 너무 멀면 학생이 발전해도 성취를 느끼기 어렵고, 반대로 쉬우면 다시 상한에 몰린다. 어떤 전략·나라에 변화가 집중됐는지 다음 표와 함께 확인한다.')
    p('기존 목표에서는 정상 테크니아가100시드 모두 경제 성장과 산업 능력의 만점이었다. 상한만 바꿔도 이미 목표의2배를 넘은 성과에는 같은 만점이 유지되어, 다른 나라의 점수 하락과 함께 최고점 편중이 커졌다. 목표와 상한을 결합한 정상 조건에서는 기존6개국 모두 두 성장 부분의 만점이0/100이었다. 포화가 풀린 것과 도전 목표의 적절한 난이도가 확인된 것은 구별해야 한다.')
    end()

    h(6,'투자·무역·가격·무행동 전략을 같은 시드에서 비교')
    p('각 행은 해당 나라의 행동만 바꾼 게임과 그 나라 정상 운영을 같은 본 검증 시드에서 짝지은 총점 차이다. 원래6개국×다섯 행동의 30조건을 공통 정상 조건과 비교한다.')
    p('투자 중심과 무역 중심은 기존 자동 국가의 행동 방식이다. 투자 중심은 정상 정책의 생활 물량·유보 현금 확인보다 투자를 우선하고, 무역 중심은 자발적 투자를 하지 않으며 구매·판매는 이어 간다. 반값과1G는 공개 판매 가격을 바꾸고 직접 협상·물물교환은 기존 규칙을 유지한다. 무행동도 자동 생산과 만족도에 따른 운영수입은 남는다. 행동 이름으로 학생의 의욕이나 심리를 측정한 것은 아니다.')
    for behavior in ('invest','trade','cheap','minimum','idle'):
        add('<h3>'+BEHAVIORS[behavior]+' − 정상</h3>')
        add(table(['국가']+[VIEWS[v]+' 차이 [95% 구간]' for v in VIEWS],[
            (COUNTRIES[n],)+tuple(ci(data.diff(f'{n}:{behavior}',sp(n,v))) for v in VIEWS) for n in ORIGINAL]))
    p('구간은 같은 시드 차이의 평균 ±1.96×표준오차다. 실제 학생 모집단의 신뢰구간이 아니며 여러 지표를 보는 탐색적 모형 분석이다. 정상 평균을 기준으로 삼지만 정상 AI가 모든 유효한 전략보다 항상 높은 점수를 받아야 한다는 기준은 두지 않는다.','note')
    add('<h3>테크니아의 실제 성과: 평가 보기와 무관한 기록</h3>')
    tech_cases=('None:normal','Technia:invest','Technia:trade','Technia:cheap','Technia:minimum','Technia:idle')
    add(table(['행동','현금','투자','평가자산 증가','능력 증가 비율','생산 실물','사용된 실물','활용 /10'],[
        (BEHAVIORS[case.split(':')[-1]],)+tuple(f(c(case,'Technia','growth_metrics.'+k)) for k in
            ('cash','investment','asset_gain','capacity_growth','produced_units','used_units','utilization_score')) for case in tech_cases]))
    p('반값 행동에서 실제 사용이 늘거나 필요 없는 생산이 줄었다면 유효한 가격 전략의 성과일 수 있다. 점수를 낮춰 정상보다 지게 만드는 것을 목표로 하지 않는다. 생산 능력·투자·현금과 실제 사용의 여러 차이를 한 지표로 모두 설명하지 않는다.')
    p('테크니아 반값의 정상 대비 평균 총점 차이는 기존 +0.92점, 목표 조정 −4.76점, 상한만 +0.92점, 결합 −3.78점이었다. 같은 반값 경제 기록을 다르게 평가한 결과다. 반값 전략이 본질적으로 잘못됐거나 새 가격 행동 때문에 경제가 바뀌었다는 뜻은 아니다.')
    p('1G 공개 판매와 무행동은 모든 나라·보기에서 기존6개국 최고점이0/100이었다. 그러나 “1G는 항상 자기 정상보다 낮다”는 결론은 유지되지 않았다. 미네리아에서 새 세 보기는 각각1/100 게임이 자기 정상 총점을 넘었고 기존 평가는0/100이었다. 평균적인 열세와 개별 게임의 예외를 구별한다.')
    normal_exception=next(r['countries']['Mineria'] for r in data.groups[('holdout','None:normal')] if r['seed']==92036)
    minimum_exception=next(r['countries']['Mineria'] for r in data.groups[('holdout','Mineria:minimum')] if r['seed']==92036)
    before=normal_exception['growth_metrics'];after=minimum_exception['growth_metrics']
    p(f"그 예외인 시드92036은 두 행동 모두 투자와 능력 증가가0이었다. 생산량은 둘 다 {f(before['produced_units'],0)}개였고, 실제 사용으로 기록된 생산품은 {f(before['used_units'],0)}개에서 {f(after['used_units'],0)}개로 늘었다. 미사용 재고 평가액은 {f(before['unused_stock_value'])}G에서 {f(after['unused_stock_value'])}G, 평가자산 증가는 {f(before['asset_gain'])}G에서 {f(after['asset_gain'])}G로 줄었다. 활용·무역 성과의 증가와 경제 성장 점수 열세의 완화가 함께 작용해 순서가 바뀌었다. 두 행동 모두 목표 아래였으므로 상한에서만 생긴 효과가 아니다.")
    p('이 사례의1G−정상 총점 차이는 '+', '.join(VIEWS[v]+' '+f(minimum_exception['growth_evaluation'][v]['score']-normal_exception['growth_evaluation'][v]['score'])+'점' for v in VIEWS)+'이었다. 해당1G 국가의 순위는 네 보기 모두 기존6개국 중6위였다. 이 설명은 저장된 요약의 분해이며 새로운 게임을 실행하거나 해당 시드의 개별 실물 이력을 추가로 재구성한 결과는 아니다.','note')
    end()

    h(7,'목표와 상한만으로 해결되지 않는 문제')
    add('<h3>무행동의 평가자산 증가와 경제 점수</h3>')
    add(table(['국가','자산 증가 정상→무행동','운영수입 정상→무행동','미사용 재고평가 정상→무행동','무행동 자산 증가가 정상보다 큰 게임'],[
        (COUNTRIES[n],)+tuple(f(c('None:normal',n,'growth_metrics.'+k))+' → '+f(c(f'{n}:idle',n,'growth_metrics.'+k)) for k in
            ('asset_gain','tax','unused_stock_value'))+(data.higher(f'{n}:idle',mp(n,'asset_gain')),) for n in ORIGINAL]))
    add(table(['무행동 경제력>정상']+list(VIEWS.values()),[
        (COUNTRIES[n],)+tuple(data.higher(f'{n}:idle',sp(n,v,'economic')) for v in VIEWS) for n in ORIGINAL]))
    add(table(['무행동 총점>정상']+list(VIEWS.values()),[
        (COUNTRIES[n],)+tuple(data.higher(f'{n}:idle',sp(n,v)) for v in VIEWS) for n in ORIGINAL]))
    p('기존 경제 성장량에는 자동 운영수입과 재고 평가가 포함된다. 무행동이 현금을 쌓았을 때 경제 성장량이 정상보다 클 수 있다. 양의 목표로 나눈 뒤 단조적인 점수 함수를 적용하는 것만으로 이 원래 순서를 뒤집을 수는 없다. 상한에서 동점이 될 수는 있고 예비자금 및 다른 구성점수는 별도로 작용한다. 따라서 경제력 한 항목과 종합 점수는 구별한다.')
    p('미네리아는 무행동의 평가자산 증가가 정상보다 큰 경우가97/100이었다. 경제력이 더 높은 경우는 기존39/100에서 결합97/100으로 늘었다. 기존 상한에 가려졌던 자산 순서가 더 드러난 결과이며, 새 경제 활동이나 수입을 만들어 낸 변화가 아니다. 무행동 총점이 정상보다 높은 경우는 여섯 나라·네 보기 모두0/100이었다.')
    add('<h3>투자 중심 전략의 생산과 실제 쓰임</h3>')
    add(table(['국가','투자 정상→투자 중심','자산 증가 정상→투자 중심','생산 실물 정상→투자 중심','사용 실물 정상→투자 중심','미사용 재고평가 정상→투자 중심'],[
        (COUNTRIES[n],)+tuple(f(c('None:normal',n,'growth_metrics.'+k))+' → '+f(c(f'{n}:invest',n,'growth_metrics.'+k)) for k in
            ('investment','asset_gain','produced_units','used_units','unused_stock_value')) for n in ORIGINAL]))
    p('투자100G는 현금을100G 줄이고 기존 평가자산에는45G만 더하므로, 투자 지출 자체가 경제 자산을 늘리는 구조는 아니다. 다만 능력 점수 상승이 경제 손실·실제 활용 변화를 넘어서는지는 전체 구성으로 확인해야 한다. 같은 시드의 전략 비교는 여러 후속 행동도 달라지므로 한 번의 투자만을 바꾼 인과 실험으로 표현하지 않는다.')
    p('생산된 실물이 많다는 사실과 사용된 실물이 많다는 사실은 다르다. 사용되지 않는 생산·설비의 증가를 발전으로 과도하게 보상하는지 검토하면서, 적은 생산으로 많은 수요를 채운 효율도 인정해야 한다. 이번에는 이 기초 지표의 정의를 바꾸지 않았으므로 목표 조정의 효과와 지표 자체의 한계를 구별한다.')
    end()

    h(8,'추가 30시드 조건은 별도 진단으로 읽는다')
    p('추가 시드94000~94029에는 정상 대조와 단독1G 조건이 없다. 따라서 1G+투자 중단이나 전체 무역 금지를 본 검증 평균과 짝지어진 정상 대비 차이처럼 제시하지 않는다.')
    add(table(['1G+투자 중단 국가','현금','만족도','실제 투자']+list(VIEWS.values()),[
        (COUNTRIES[n],)+tuple(f(c(f'{n}:minimum_passive',n,k,'stress')) for k in ('cash','happy','investment'))+
        tuple(f(s(f'{n}:minimum_passive',n,v,phase='stress')) for v in VIEWS) for n in ORIGINAL]))
    combos=('Mechania:idle','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum')
    labels={'Mechania:idle':'메카니아 무행동','Mechania:idle+Technia:minimum':'메카니아 무행동+테크니아1G','Mechania:idle+Novia:minimum':'메카니아 무행동+노비아1G'}
    add(table(['공급국 비참여 조건','테크니아 자국산G3 사용','노비아 자국산G3 사용','두 나라 모두','한 나라 이상','세계 만족도'],[
        (labels[case],data.count(case,cp('Technia','routing.g3_electronics_used'),'stress'),
         data.count(case,cp('Novia','routing.g3_electronics_used'),'stress'),data.count(case,'world.routing.both_electronics_used','stress'),
         data.either_g3(case),f(w(case,'happy','stress'))) for case in combos]))
    add(table(['메카니아 무행동에 더한 조건']+[VIEWS[v]+' 테크니아 총점 차이' for v in VIEWS],[
        (labels[case],)+tuple(ci(data.diff(case,sp('Technia',v),'stress','Mechania:idle')) for v in VIEWS) for case in combos[1:]]))
    p('자국산 G3 사용은 해당 국가가 생산한 G3 상품이 자국 또는 외국에서 실제 사용된 경우다. 수입 상품만 소비한 것은 생산국 성공으로 세지 않는다. 점수 보기만 바꾸어 이 성공률이 달라진 것은 아니다.')
    add('<details><summary>전체 무역 금지의 단독 진단</summary>')
    add(table(['국가','현금','만족도']+list(VIEWS.values()),[
        (COUNTRIES[n],f(c('None:no_trade',n,'cash','stress')),f(c('None:no_trade',n,'happy','stress')))+
        tuple(f(s('None:no_trade',n,v,phase='stress')) for v in VIEWS) for n in ORIGINAL]))
    add('</details>');end()

    h(9,'학생에게 보일 규칙은 단순해야 한다')
    add('<blockquote>“우리나라의 성장 목표를 보세요. 더 큰 생산 능력을 갖추는 것과 만든 물건이 실제로 쓰이는 것을 함께 살펴봅니다. 필요한 물건을 살 돈도 남겨야 해요.”</blockquote>')
    add(table(['상태','의미'],[
        ('유지한 것','9개국·9라운드 경제 규칙과 기존 공식 점수. 추가3개국 종합 목표는 미보정 상태.'),
        ('이번에 비교한 후보','국가별 목표 교체, 기본 목표80%·2배 도전100% 상한, 두 변경의 결합.'),
        ('학생 화면 제안','자기 나라의 고정 목표와 진행 막대를 간단히 제시. 기본·도전 상한을 선택한다면 두 표시로 구별.'),
        ('이번 계산으로 확인하지 않은 것','실제 학생의 이해·흥미·협상·새 평가에 대한 전략 반응과 3학생+AI6개국 수업 속도.'),
    ]))
    p('학생에게 백분위수나 통계 조정을 계산하도록 요구할 필요는 없다. 다만 눈에 보이는 실제 성과와 점수의 연결은 설명할 수 있어야 한다. 현금이 늘었는데 무역을 하지 않은 나라, 많이 투자했지만 사용되지 않는 재고가 늘어난 나라, 싸게 팔아 상대 수요를 채운 나라를 각각 같은 이유로 평가하지 않는다.')
    p('현재 제안은 상한만 바꾸는 안을 다음 기준으로 삼지 않고, 목표 조정 두 후보의 장단점과 남은 경제 지표 문제를 보존하는 것이다. 정상 정책에서 저평가된 나라의 사전 선택 정책 성과도 함께 확인했다. 점수식의 공식 교체나 추가3개국까지의 공정한 종합 순위가 완료된 상태는 아니다.')
    p('모든 실행은 규칙 기반 자동 국가다. 교실의 3명 학생이 어떤 국가를 선택하고 어떤 협상을 하는지, 40분+40분에 규칙을 이해하고 끝낼 수 있는지, 개별 접속 웹앱의 동시 거래가 가능한지는 별도 검증이다. 이 보고서의 수치로 학습 목표 달성을 확정하지 않는다.')
    end()

    h(10,'실행·검증·재현 범위')
    add(table(['항목','완료 기록'],[
        ('목표 조정','13조건×60 = 780게임; 90000~90059'),
        ('별도 본 검증','31조건×100 = 3,100게임; 92000~92099'),
        ('추가 조건','10조건×30 = 300게임; 94000~94029'),
        ('고유 경제 궤적',f"{len(data.rows):,}"),('통과 테스트',f"{tests['test_count']:,}"),
        ('불변식 호출',f"{meta['verification_calls']:,}; 보고된 실패 {meta['verification_failures']}"),
        ('본 검증 현금·원료 원장',f"각 {meta['holdout_cash_ledger_rows']:,} 국가·라운드 행"),
        ('대표 상세 경로',f"{meta['representative_traces']}개: 조정13+본 검증31+추가10"),
        ('독립 감사',audit['status']),('독립 대조 횟수',f"{audit['checks_evaluated']:,}; 오류 {len(audit['errors'])}"),
        ('본 검증 전 조정자료 감사',f"{data.calibration_audit['checks_evaluated']:,}회; 본 검증 시작 전에 통과"),
        ('계산 시간',f(meta['calibration_elapsed_seconds'])+'초(조정) + '+f(meta['holdout_stress_elapsed_seconds'])+'초(본 검증·추가); 수업 시간 아님'),
    ]))
    p('전체 4,180개 요약과 본 검증의 현금·원료 원장 각251,100행을 검사한다. 실물·가격·개발·정책 결정의 상세 독립 재구성은 저장된 대표54경로의 범위다. 조정 자료만으로 목표와 사전 정책 선택을 다시 계산하고 고정 기록과 비교한다. 별도 검증 자료로 목표를 다시 맞추지 않으며, 네 보기에서 공식 경제·점수가 보존되는지와 구성 점수의 합도 확인한다.')
    p('자료는 growth_scoring.py의 정의, goals.json의 고정 목표, runs.jsonl.gz의 실제 기록, summary.json의 통계, 테스트·감사 기록으로 추적할 수 있다. 보고서 생성기는 게임이나 점수 엔진을 실행하지 않고 저장된 완료 자료를 읽는다.')
    add('<pre>python3 run_growth_validation.py --stage calibrate --workers 4 --output-dir reproduced_growth_results\npython3 audit_growth_results.py --stage calibration --results reproduced_growth_results\n# 목표·사전 정책 선택을 확인하고, 이번 실행에서 출력된 FREEZE_SHA256 값을 아래에 입력\npython3 run_growth_validation.py --stage holdout --workers 4 --output-dir reproduced_growth_results --approve-freeze 검토한_SHA256_값\npython3 audit_growth_results.py --stage full --results reproduced_growth_results\npython3 build_growth_report.py --results reproduced_growth_results --report REPRODUCED_V12_KO.html\npython3 validate_growth_report.py --results reproduced_growth_results --report REPRODUCED_V12_KO.html --output reproduced_growth_results/report_numeric_qa.json</pre>')
    p('새 폴더에서 재현하면 생성 시각 때문에 동결 파일의 해시는 새 값이 된다. 이전 실행의 해시를 복사하지 않고 새 실행에서 출력된 값을 사용한다. 기존 완료 결과를 보존하고 새 폴더에 실행하며, 조정·동결·별도 검증의 순서를 유지한다.')
    end()

    h(11,'나라별 행동과 점수 상세 평균')
    for n in ORIGINAL:
        add('<details><summary>'+COUNTRIES[n]+' · 본 검증100시드</summary>')
        cases=('None:normal',)+tuple(f'{n}:{b}' for b in ('invest','trade','cheap','minimum','idle'))
        add(table(['행동','현금','만족도','투자','생산량','실사용량']+list(VIEWS.values()),[
            (BEHAVIORS[case.split(':')[-1]],f(c(case,n,'cash')),f(c(case,n,'happy')),f(c(case,n,'investment')),
             f(c(case,n,'growth_metrics.produced_units')),f(c(case,n,'growth_metrics.used_units')))+tuple(f(s(case,n,v)) for v in VIEWS) for case in cases]))
        add(table(['행동·보기','자국 정상 총점보다 큼','기존6개국 최고점'],[
            (BEHAVIORS[case.split(':')[-1]]+' · '+VIEWS[v],data.higher(case,sp(n,v)),data.highest(case,n,v)) for case in cases[1:] for v in VIEWS]))
        add('</details>')
    p('빈도는 동점 허용 10⁻⁹점을 기준으로 최고점을 세고, 자국 정상보다 큰 경우는 그 오차를 넘는 엄격한 증가만 센다. 각 나라의 행동을 바꾼 세계가 서로 다르므로 여러 행동·국가 칸을 합쳐 하나의 순위 분포로 해석하지 않는다.')
    p('이 파일은 결과 검토용 정적 HTML이다. 압축 자료에는 계산·검증 코드와 원시 결과, 고정 목표, 통계와 추적 근거가 포함되며, 플레이 가능한 학생 화면이나 수업 실증 결과를 대신하지 않는다.')
    end()

    css='''*{box-sizing:border-box}body{margin:0;background:#f0f3f6;color:#233140;font:16px/1.7 system-ui,sans-serif}main{max-width:1320px;margin:auto;padding:28px}header{background:#283d58;color:white;border-radius:18px;padding:40px 44px}.eyebrow{color:#c7d8eb;font-size:14px}h1{font-size:38px;line-height:1.25;margin:14px 0}.badge{display:inline-block;background:#3f5570;border-radius:8px;padding:8px 14px;font-size:14px}nav{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0}nav a{background:white;border:1px solid #d5e0e9;border-radius:8px;padding:7px 12px;color:#284964;text-decoration:none}section{background:white;border:1px solid #dce5eb;border-radius:14px;padding:26px 30px;margin:22px 0}h2{font-size:25px;line-height:1.35;color:#263e58;margin:0 0 18px}h3{font-size:19px;margin:24px 0 10px}.table-wrap{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid #dce5eb;padding:10px 12px;text-align:right;vertical-align:top;white-space:nowrap}th:first-child,td:first-child{text-align:left;min-width:130px;white-space:normal}thead th{background:#edf2f8;color:#263e58}tbody th{font-weight:500}tbody tr:nth-child(even){background:#f8fafc}table.two-columns th:first-child{width:27%}table.two-columns th:last-child,table.two-columns td:last-child{text-align:left;white-space:normal;min-width:0;overflow-wrap:anywhere}.prose-table th,.prose-table td{white-space:normal;text-align:left;min-width:0}.prose-table th:first-child{width:25%}.note{border-left:3px solid #a3b5c7;padding-left:14px;font-size:14px;color:#536a7f}.callout{background:#edf4f8;border-left:4px solid #5f819b;border-radius:8px;padding:18px 22px}blockquote{background:#f3f6ed;border-left:4px solid #829767;padding:20px 24px;margin:20px 0;font-size:18px}details{border:1px solid #dce5eb;border-radius:8px;padding:14px 16px;margin:14px 0}summary{cursor:pointer;color:#294c68;font-weight:600}pre{background:#1d3046;color:#e2ebf3;padding:18px;border-radius:8px;font-size:13px;white-space:pre-wrap;word-break:break-word}footer{color:#627786;font-size:13px;text-align:center;padding:20px}@media(max-width:700px){main{padding:12px}header{padding:26px 22px}h1{font-size:29px}section{padding:22px 16px}}@media print{body{background:white}main{padding:0;max-width:none}nav{display:none}section{border:0;padding:15px 0}.table-wrap{overflow:visible}th,td{white-space:normal;padding:5px}table{font-size:10px}pre{background:#eee;color:#111}}'''
    html='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>#11 무역 게임 v12 · 성장 목표와 상한 검증</title><style>'+css+'</style></head><body><main>'+''.join(parts)+'<footer>#11 무역 게임 · v12 국가별 성장 목표와 상한 비교</footer></main></body></html>'
    report.write_text(html,encoding='utf-8');structure=check_structure(html,report,folder)
    return {'report':str(report),'bytes':report.stat().st_size,'tables':structure['tables'],'numeric_cells':structure['numeric_cells'],'games':len(data.rows),'sha256':structure['report_sha256']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=DEFAULT_RESULTS)
    p.add_argument('--report',type=Path,default=ROOT/'TRADE_GROWTH_SCORE_REVIEW_V12_KO.html');args=p.parse_args()
    print(json.dumps(build(args.results.resolve(),args.report.resolve()),ensure_ascii=False))


if __name__=='__main__':main()
