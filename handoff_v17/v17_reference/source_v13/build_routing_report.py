"""Build the Korean v10 report from completed, audited saved results only.

The inherited report utilities are formatting/file readers only. This module
does not import game engines, run simulations or use pilot values as evidence.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
from html import escape
import json
from pathlib import Path
import statistics

from build_development_report import read_json, read_lines, need, get, f as plain_f, ci as plain_ci

ROOT=Path(__file__).resolve().parent
DEFAULT_RESULTS=ROOT/'routing_results'
COUNTRIES={'Tropia':'트로피아','Grainia':'그레니아','Oilia':'오일리아','Mechania':'메카니아',
           'Mineria':'미네리아','Technia':'테크니아','Novia':'노비아','Agrea':'아그레아','Ferria':'페리아'}
ORIGINAL=tuple(COUNTRIES)[:6]
GOODS={'banana':'바나나','wheat':'밀','ore':'광물','fuel':'연료','machine':'기계','electronics':'전자제품'}
MODES={'baseline':'기존안','quick':'1회 대기','patient':'2회 대기','market_first':'무역 유지형'}
WAIT_ROUNDS={'baseline':0,'quick':1,'patient':2,'market_first':2}
POLICIES={m:{'wait_rounds':wait,'expansion_wait_extra':int(m=='market_first'),
             'launch_grace':m=='market_first','supplier_focus':m=='market_first'} for m,wait in WAIT_ROUNDS.items()}
COHORTS=((None,'normal'),('Mechania','idle'))
REFUSALS=tuple((n,s) for n in ('Mechania','Technia','Novia') for s in ('no_high_machine','no_raw'))
SCENARIOS=tuple((n,s) for n in ORIGINAL for s in ('cheap','idle'))+((None,'normal'),(None,'no_trade'))+REFUSALS
MAIN_SEEDS=range(68000,68200)
STRESS_SEEDS=range(70000,70030)


class Cell(str):
    """Displayed text with an independent saved-result locator for numeric QA."""
    def __new__(cls,text,qa):
        obj=str.__new__(cls,text);obj.qa=qa;return obj
    @staticmethod
    def parts(value):
        if isinstance(value,Cell):
            return value.qa['parts'] if value.qa['kind']=='concat' else [value.qa]
        return [{'kind':'literal','text':str(value)}]
    def __add__(self,other):
        return Cell(str(self)+str(other),{'kind':'concat','parts':self.parts(self)+self.parts(other)})
    def __radd__(self,other):
        return Cell(str(other)+str(self),{'kind':'concat','parts':self.parts(other)+self.parts(self)})


class Metric(float):
    def __new__(cls,value,qa):
        obj=float.__new__(cls,value);obj.qa=qa;return obj


class PairedValues(list):
    def __init__(self,values,qa):super().__init__(values);self.qa=qa


def f(value,digits=2):
    text=plain_f(value,digits)
    return Cell(text,{**value.qa,'digits':digits}) if isinstance(value,Metric) else text


def ci(values,digits=2):
    text=plain_ci(values,digits)
    return Cell(text,{**values.qa,'digits':digits}) if isinstance(values,PairedValues) else text


def table(headers,rows):
    klass=' class="two-columns"' if len(headers)==2 else ''
    out='<div class="table-wrap"><table'+klass+'><thead><tr>'+''.join('<th scope="col">'+escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'
    for row in rows:
        out+='<tr>'
        for i,value in enumerate(row):
            tag='th' if i==0 else 'td';attributes=' scope="row"' if i==0 else ''
            if isinstance(value,Cell):attributes+=' data-qa="'+escape(json.dumps(value.qa,ensure_ascii=False,separators=(',',':')),quote=True)+'"'
            out+='<'+tag+attributes+'>'+escape(str(value))+'</'+tag+'>'
        out+='</tr>'
    return out+'</tbody></table></div>'


def load_completed(folder):
    files=('pre_run_plan.json','run_manifest.json','summary.json','runs.jsonl.gz','round_ledgers.jsonl.gz',
           'raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz','tests_manifest.json','independent_audit.json')
    need(all((folder/n).is_file() for n in files),'Complete formal results, tests and independent audit required.')
    meta=read_json(folder/'run_manifest.json');summary=read_json(folder/'summary.json')
    need(summary['metadata']==meta,'Summary and completed manifest differ.')
    need(meta['completed_games']==4000 and meta['main_games']==1600 and meta['stress_games']==2400,'Formal contract is 4,000 games.')
    need(meta['main_seed_range']==[68000,68199] and meta['stress_seed_range']==[70000,70029],'Unexpected formal seeds.')
    need(meta['rounds']==9 and meta['countries']==9 and meta['source_unchanged'] is True and meta['pilot_excluded'] is True,'Frozen nine-country, nine-round results required.')
    need(meta['modes']==POLICIES,'Routing policy definitions differ.')
    tests=read_json(folder/'tests_manifest.json')
    need(tests['passed'] is True and tests['test_count']==meta['tests_completed'] and tests['test_count']>260,'Inherited and new tests must pass.')
    need(hashlib.sha256((folder/'tests_manifest.json').read_bytes()).hexdigest()==meta['tests_manifest_sha256'],'Test record hash mismatch.')
    audit=read_json(folder/'independent_audit.json')
    need(audit['status']=='passed' and not audit['errors'] and not audit.get('warnings'),'Independent audit must pass.')
    rows=read_lines(folder/'runs.jsonl.gz')
    expected={('main',m,s,n,st) for m in MODES for s in MAIN_SEEDS for n,st in COHORTS}
    expected.update(('stress',m,s,n,st) for m in MODES for s in STRESS_SEEDS for n,st in SCENARIOS)
    keys=[(r['phase'],r['mode'],r['seed'],r['focal'],r['style']) for r in rows]
    need(len(keys)==len(set(keys))==4000 and set(keys)==expected,'Saved runs differ from the complete unique schedule.')
    groups=defaultdict(list)
    for r in rows:
        need(set(r['countries'])==set(COUNTRIES),'Unexpected country set.')
        need(r['world']['routing_policy']==meta['modes'][r['mode']],'Saved route policy differs.')
        need(r['world']['development_policy']=={'sale_buffer':True,'prior_machine':True},'All variants must retain v9 combined.')
        need(r['world']['raw_policy']=={'machine_credits':2,'starter':'two_cycles'},'All variants must retain v8 bridge raw rules.')
        groups[(r['phase'],r['mode'],r['focal'],r['style'])].append(r)
    ledger_keys={(m,s,n,st) for m in MODES for s in MAIN_SEEDS for n,st in COHORTS}
    cells={(n,r) for n in COUNTRIES for r in range(1,10)}
    for filename in ('round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz'):
        rr=read_lines(folder/filename)
        need(len(rr)==1600 and {(r['mode'],r['seed'],r['focal'],r['style']) for r in rr}==ledger_keys,'Incomplete main ledger: '+filename)
        for r in rr:need(len(r['rows'])==81 and {(x['country'],x['round']) for x in r['rows']}==cells,'Incomplete country-round ledger.')
    traces=read_json(folder/'first_seed_traces.json.gz')
    trace_keys={':'.join(map(str,('main',m,68000,n,st))) for m in MODES for n,st in COHORTS}
    trace_keys.update(':'.join(map(str,('stress',m,70000,n,st))) for m in MODES for n,st in REFUSALS)
    need(len(traces)==32 and set(traces)==trace_keys,'All 32 representative traces required.')
    return meta,tests,audit,rows,groups,traces


def build(folder,report):
    meta,tests,audit,rows,groups,traces=load_completed(folder)

    @lru_cache(maxsize=None)
    def mean(mode,path,phase='main',focal=None,style='normal'):
        return Metric(statistics.mean(get(r,path) for r in groups[(phase,mode,focal,style)]),
                      {'kind':'mean','experiment':f'{phase}:{mode}:{focal}:{style}','metric':path})
    def values(mode,path,phase='main',focal=None,style='normal'):
        return {r['seed']:get(r,path) for r in groups[(phase,mode,focal,style)]}
    def diff(a,b,path,focal=None,style='normal',phase='main'):
        x=values(a,path,phase,focal,style);y=values(b,path,phase,focal,style)
        need(x.keys()==y.keys(),'Unpaired seeds.')
        return PairedValues([y[s]-x[s] for s in sorted(x)],
                            {'kind':'ci','pair':f'{phase}:{a}->{b}:{focal}:{style}','metric':path})
    def stressdiff(mode,name,style,path):
        x=values(mode,path,'stress');y=values(mode,path,'stress',name,style)
        need(x.keys()==y.keys(),'Unpaired stress seeds.')
        suffix='no_trade' if style=='no_trade' else f'{name}:{style}'
        return PairedValues([y[s]-x[s] for s in sorted(x)],
                            {'kind':'ci','pair':f'stress:{mode}:{suffix}','metric':path})
    def count(mode,path,phase='main',focal=None,style='normal'):
        v=values(mode,path,phase,focal,style)
        return Cell(f'{sum(x>0 for x in v.values())}/{len(v)}',
                    {'kind':'count','experiment':f'{phase}:{mode}:{focal}:{style}','metric':path})
    def count_either(mode,key,phase='main',focal=None,style='normal'):
        rr=groups[(phase,mode,focal,style)]
        return Cell(f"{sum(any(r['countries'][n]['routing'][key] for n in ('Technia','Novia')) for r in rr)}/{len(rr)}",
                    {'kind':'anycount','experiment':f'{phase}:{mode}:{focal}:{style}',
                     'metrics':[f'countries.{n}.routing.{key}' for n in ('Technia','Novia')]})
    def economic_equal_count(a,b):
        left={r['seed']:r for r in groups[('main',a,None,'normal')]}
        right={r['seed']:r for r in groups[('main',b,None,'normal')]}
        need(left.keys()==right.keys(),'Economic identity comparison must use paired seeds.')
        def comparable(r):
            return {'countries':{n:{k:v for k,v in x.items() if k!='routing'} for n,x in r['countries'].items()},
                    'world':{k:v for k,v in r['world'].items() if k not in ('routing','routing_policy','routing_variant','v10_note')}}
        equal=sum(comparable(left[s])==comparable(right[s]) for s in left)
        return Cell(f'{equal}/{len(left)}',{'kind':'economic_equal_count',
                    'left_experiment':f'main:{a}:None:normal','right_experiment':f'main:{b}:None:normal'})
    def c(mode,n,key,focal=None,style='normal'):return mean(mode,'countries.'+n+'.'+key,'main',focal,style)
    def w(mode,key,focal=None,style='normal'):return mean(mode,'world.'+key,'main',focal,style)
    def world_table(fields,focal=None,style='normal'):
        return table(['지표·단위']+[MODES[m] for m in MODES],[(label,)+tuple(f(w(m,path,focal,style)) for m in MODES) for label,path in fields])
    parts=[]
    def add(x):parts.append(x)
    def p(s,cls=''):add('<p class="'+cls+'">'+escape(s)+'</p>')
    def h(i,s):add(f'<section id="s{i}"><h2>{i}. {escape(s)}</h2>')
    def end():add('</section>')

    add('<header><div class="eyebrow">아이디어 노트 · #11 무역 게임 · v10</div><h1>공급국이 참여하지 않아도<br>다른 발전 방법을 찾을 수 있을까</h1><p class="lead">9개국·9라운드 · 기존안과 세 가지 자동 대안 선택 · 실제 4,000회 비교</p><div class="badge">경제 모형 검증 · 규칙 확정 및 실제 학습 효과 검증 아님</div></header>')
    add('<nav>'+''.join(f'<a href="#s{i}">{escape(t)}</a>' for i,t in ((1,'판단 범위'),(2,'변경 규칙'),(3,'정상 공급'),(4,'공급국 무행동'),(5,'국가별 영향'),(6,'대안 경로'),(7,'거부·플레이 전략'),(8,'점수·학습'),(9,'검증·재현'),(10,'세부 표')) )+'</nav>')

    h(1,'이번에 확인한 것')
    add('<div class="callout"><strong>검증 판단: 무역 유지형을 후속 후보로 남긴다. 공급 중단의 영향은 줄었지만 두 나라의 발전을 모두 회복시키지는 못했다.</strong>')
    p('정상 공급에서는 기존안과 무역 유지형의 경제 요약이 같은 시드 '+economic_equal_count('baseline','market_first')+'게임에서 일치했다. 메카니아 무행동에서는 자국산 G3의 실제 사용이 테크니아 '+count('market_first','countries.Technia.routing.g3_electronics_used','main','Mechania','idle')+', 노비아 '+count('market_first','countries.Novia.routing.g3_electronics_used','main','Mechania','idle')+'게임으로 회복됐다. 두 나라 모두 성공은 '+count('market_first','world.routing.both_electronics_used','main','Mechania','idle')+', 한 나라 이상 성공은 '+count_either('market_first','g3_electronics_used','main','Mechania','idle')+'게임이다.')
    p('즉 83%는 “두 나라 중 한 나라 이상 회복”의 비율이고, 두 나라 동시 회복은 10%다. 노비아의 낮은 회복률과 미완료 중간 투자, 만족도 하락, 반값 판매의 점수 민감도가 남아 있다. 이번 결과를 최종 경제 균형이나 모든 학생의 발전 기회 보장으로 확정하지 않는다.')
    add('</div>')
    p('v9 결합안에서는 고급 기계가 연구와 실제 상품 사용으로 이어졌지만, 메카니아가 거래·투자를 하지 않으면 테크니아와 노비아의 G3 발전이 멈췄다. 이번에는 물리적 생산·비용·기술 조건·점수를 그대로 두고, 컴퓨터 국가가 원래 목표를 기억한 채 허용된 다른 산업을 먼저 개발하는 판단을 비교한다. 무역 유지형 안은 임시 주력 선택까지 포함한 AI 정책 묶음이다.')
    p('정상 공급과 메카니아 무행동을 각각 200개의 같은 시드로 비교한다. 발전이 막힌 경우의 회복과 정상적인 기계 무역의 보존은 서로 다른 질문이다. 자국 기계를 써서 발전하면 외국산 기계 연구 연결이 줄 수 있으므로, 이를 단독 성공·실패 지표로 사용하지 않는다.')
    p('이 보고서의 “국가별 G3 실제 사용 성공”은 그 나라가 생산한 G3 상품이 자국 또는 외국에서 한 번 이상 사용됐다는 뜻이다. 다른 나라의 G3 상품을 수입해 소비한 것만으로 이 생산국 성공 지표가 1이 되지는 않는다. 생활 만족도는 별도 지표로 확인한다.','note')
    p('v10 기존안은 v9 combined다. v9 기존안과 이름이 같지만 다른 정책이며, v9 보고서의 서로 다른 시드 평균을 직접 차감하지 않는다. 보고서는 정식 저장 결과만 읽고 예비 실행을 섞지 않는다.','note')
    end()

    h(2,'자동 투자와 주력 선택의 변경 범위')
    add(table(['안','대안 검토를 시작하는 조건'],[
        ('기존안','v9 combined의 기존 투자 판단'),
        ('1회 대기','같은 목표가 기계 부족 상태로 한 라운드를 마쳤고 그 라운드에 적격 공개 판매 기록이 없을 때'),
        ('2회 대기','위 상태가 연속 두 완료 라운드에 걸쳐 이어졌을 때'),
        ('무역 유지형','기계 산업이 있으면 2라운드, 없으면 3라운드를 확인; 신세대 공개 시 구매 기회를 한 번 더 주고 임시 주력 선택도 조정'),
    ]))
    p('계획 시점에 주문이 없다는 이유만으로 즉시 자급으로 바꾸지 않는다. 라운드는 생산 → 투자 계획 고정 → 판매 등록 → 거래 → 생활 정산 → 투자 순서로 진행되므로, 계획 이후에 그 라운드의 새 기계가 시장에 나올 수 있다. 새 판단은 완료된 라운드의 자기 투자 미달과 공개 판매 기록을 함께 확인한다.')
    add(table(['대안 경로 단계','동작'],[
        ('원래 목표 보관','개발하려던 산업과 목표 단계를 기억한다.'),
        ('허용된 기계 산업 확보','기존 기계 산업을 올리거나, 국가에 원래 허용된 기계 확장 경로를 사용한다.'),
        ('기계 산업 2단계까지만 우회','원래 비용과 생활·원료 확보 조건을 적용한다. 가상의 현금·원료를 추가하지 않는다.'),
        ('실물 G2 생산 기다리기','산업 단계만 오른 것으로 만족하지 않고 적격 기계 실물이 있어야 원래 개발로 돌아간다.'),
        ('공급 재개 시 원래 목표로','적격 공개 공급이나 자국 보유 기계가 생기면 원래 목표를 다시 선택한다.'),
        ('중복 투자 피하기','그 라운드 거래 중 적격 기계를 얻으면 불필요한 중간 투자는 취소한다. 원래 목표 선택은 다음 라운드에 한다.'),
        ('남은 시간 확인','기계 개발·생산 뒤 원래 개발이 7라운드까지 가능할 것으로 예상되는 경로만 시작한다.'),
    ]))
    p('G2 이상 기계가 공개 판매 중이면 비싸거나 예산이 부족하더라도 “공급 없음”으로 보지 않는다. 이번 수정은 공급 부재에 대한 대응이며 높은 가격·구매력 부족의 해결책은 아니다. 경로의 예상 소요 시간도 실제 투자 성공이나 원료 조달을 보장하지 않는다.')
    p('무역 유지형 안은 기계 산업 2단계에 도달했지만 아직 첫 G2를 생산하지 않은 우회 경로에서, 다음 한 번의 생산 주력을 기존 비내구재 산업으로 선택한다. 이로써 기존 생산식의 국내 지원 자리와 판매 재고 목표가 함께 적용되어 판매할 G2를 마련할 수 있게 한다. 생산 능력·재고 목표 공식·원료비를 새로 바꾸거나 무료 구매자를 만들지 않는다. 기다리는 횟수, 신세대 공개 후 구매 유예, 임시 주력 변경을 함께 비교하므로 결과를 대기 횟수 하나의 효과라고 해석하지 않는다.')
    p('새 경로 판단은 자기 상태와 현재·과거 공개 판매, 공개된 신세대 출시 정보를 사용한다. 기존 투자 후보 선정에는 집계 수요·부족 플래그가 남아 있어, 전체 AI가 모든 비공개 정보를 전혀 쓰지 않는다고 주장하지 않는다. 새 판단에서 경쟁국 비공개 현금·재고·미래 행동을 추가로 읽지는 않는다.','note')
    p('국가·라운드·시작 조건, v8 bridge 원료, v9 고급 기계 공급 분리와 G2 연구 조건, 생산량·원료 소비·개발비·기계 재사용, 가격 산정·협상·만족도·점수식은 유지한다. 수요·공급과 행동이 달라지므로 실제 거래 가격·생산·투자 결과는 달라질 수 있다.')
    end()

    h(3,'정상 공급에서 무역을 유지하는가')
    add(table(['정상 공급에서 같은 시드 경제 요약 비교','일치 게임 수'],[
        ('기존안 ↔ 무역 유지형',economic_equal_count('baseline','market_first'))]))
    p('동일성 비교는 저장된 국가·세계 요약에서 새 경로 진단값과 정책 설명만 제외하고 나머지 값을 모두 비교한다. 평균 몇 개만 같은지를 확인한 것이 아니다. 다만 전체 거래 상세 이력이 같거나 앞으로 모든 시드에서 같다는 보장은 아니며, 이번 정상 공급 본 비교의 저장 요약 범위다.','note')
    add(table(['정상 공급 · 자국산 G3가 실제 사용된 게임']+[MODES[m] for m in MODES],
        [(COUNTRIES[n],)+tuple(count(m,f'countries.{n}.routing.g3_electronics_used') for m in MODES) for n in ('Technia','Novia')]
        +[('두 국가 모두',)+tuple(count(m,'world.routing.both_electronics_used') for m in MODES),
          ('두 국가 중 한 나라 이상',)+tuple(count_either(m,'g3_electronics_used') for m in MODES)]))
    p('1회 대기는 정상적인 기계 공급이 생기기 전에 자급 투자로 돌아서면서 거래와 두 나라의 G3 사용 기회를 줄였다. 2회 대기도 일부 불필요한 우회가 남았다. 무역 유지형은 이번 정상 시드에서 경제 결과를 보존했지만, 세 가지 판단을 함께 묶은 안이므로 어느 한 요소만의 효과로 분리하지 않는다.')
    add(world_table([
        ('고급 기계 국경 거래(대)','development.bought_high_machines'),
        ('고급 기계 실사용 수출품(고유 실물)','development.high_machine_useful_exports'),
        ('외국산 기계 이용 개발(건)','development.foreign_machine_upgrades'),
        ('외국산 기계 개발 후 생산품 사용 연결(건)','development.foreign_machine_used_output_upgrades'),
        ('광물 국경 거래(묶음)','trade_goods.ore'),('연료 국경 거래(묶음)','trade_goods.fuel'),
        ('대안 경로 시작(건)','routing.routes_started'),('대안 완료(건)','routing.routes_completed'),
        ('G3 전자제품 실제 사용(고유 실물)','development.g3_electronics_used'),
        ('전체 평균 만족도','happy'),('종료 재고(개)','inventory'),
        ('고급 기계 미사용 종료 재고(대)','development.high_machine_unused_stock'),
        ('9개국 종료 현금 격차(G)','all_country_cash_gap'),
    ]))
    add(table(['핵심 지표']+['기존→'+MODES[m]+' 차이 [95% 구간]' for m in ('quick','patient','market_first')],[
        (label,)+tuple(ci(diff('baseline',m,path)) for m in ('quick','patient','market_first')) for label,path in (
            ('고급 기계 거래','world.development.bought_high_machines'),('외국산 기계 개발','world.development.foreign_machine_upgrades'),
            ('G3 전자제품 사용','world.development.g3_electronics_used'),('만족도','world.happy'),('종료 재고','world.inventory'),
            ('메카니아 종료 현금','countries.Mechania.cash'),('9개국 현금 격차','world.all_country_cash_gap'))]))
    p('95% 구간은 같은 시드 차이의 평균 ± 1.96 × 표준오차다. 0을 포함한다고 두 안이 동등하다고 증명한 것은 아니며, 포함하지 않는다고 학생의 학습 효과를 입증한 것도 아니다. 여러 지표를 함께 보는 게임 모형의 탐색적 비교다.','note')
    end()

    h(4,'메카니아가 행동하지 않을 때 발전이 회복되는가')
    p('여기서 무행동은 메카니아의 거래와 투자가 없는 조건이다. 자동 생산과 만족도 연계 운영수입은 계속된다. 다른 8개국은 정상적으로 행동한다. 각 안의 200게임을 같은 시드로 비교했다.')
    add(table(['국가·관측']+[MODES[m] for m in MODES],[
        (COUNTRIES[n]+' · '+label,)+tuple(count(m,f'countries.{n}.routing.{key}','main','Mechania','idle') for m in MODES)
        for n in ('Technia','Novia') for label,key in (('G3 상품 실제 생산','g3_electronics_produced'),('G3 상품 실제 사용','g3_electronics_used'))
    ]+[(label,)+tuple(count(m,'world.routing.'+key,'main','Mechania','idle') for m in MODES) for label,key in
        (('두 전자제품 국가 모두 G3 생산','both_electronics_produced'),('두 국가 모두 G3 상품 사용','both_electronics_used'))]
      +[(label,)+tuple(count_either(m,key,'main','Mechania','idle') for m in MODES) for label,key in
        (('두 국가 중 한 나라 이상 G3 생산','g3_electronics_produced'),('두 국가 중 한 나라 이상 G3 상품 사용','g3_electronics_used'))]))
    add(world_table([
        ('대안 경로 시작(건)','routing.routes_started'),('시작한 대안의 원래 목표 완료(건)','routing.routes_completed'),
        ('목표 개발 뒤 상품 사용(건)','routing.routes_with_used_goal_output'),
        ('자국 기계로 목표 완료(건)','routing.routes_with_own_machine_goal'),
        ('외국산 기계로 목표 완료(건)','routing.routes_with_foreign_machine_goal'),
        ('끝내지 못한 경로의 중간 투자(G)','routing.unfinished_intermediate_spend'),
        ('고급 기계 생산국 수','routing.high_machine_producer'),
        ('고급 기계 국경 거래(대)','development.bought_high_machines'),
        ('광물 거래(묶음)','trade_goods.ore'),('연료 거래(묶음)','trade_goods.fuel'),
        ('평균 만족도','happy'),('종료 재고','inventory'),('고급 기계 미사용 종료 재고','development.high_machine_unused_stock'),
    ],'Mechania','idle'))
    add(table(['메카니아 무행동의 핵심 변화']+['기존→'+MODES[m]+' 차이 [95% 구간]' for m in ('quick','patient','market_first')],[
        (label,)+tuple(ci(diff('baseline',m,path,'Mechania','idle')) for m in ('quick','patient','market_first')) for label,path in (
            ('테크니아 G3 실제 생산 비율','countries.Technia.routing.g3_electronics_produced'),
            ('노비아 G3 실제 생산 비율','countries.Novia.routing.g3_electronics_produced'),
            ('두 국가 모두 G3 사용 비율','world.routing.both_electronics_used'),
            ('만족도','world.happy'),('종료 재고','world.inventory'),('고급 기계 거래','world.development.bought_high_machines'))]))
    p('위 비율의 차이는 0~1 단위다. 예를 들어 0.20은 20%포인트다. G3 기술에 도달했는지와 G3 상품을 실제 생산·사용했는지를 구분한다. 처음 생산·사용한 라운드 지표의 10은 10라운드가 아니라 9라운드 안에 발생하지 않았다는 뜻이다.')
    p('“한 나라 이상”에는 두 나라 모두 성공한 게임도 포함한다. 한 나라의 회복, 두 나라의 동시 회복, 어느 한 나라라도 회복한 경우는 서로 다른 결과다. 한 나라 이상 회복률만으로 모든 학생의 발전 기회가 보장됐다고 말하지 않는다.')
    p('무역 유지형에서도 34/200게임은 두 나라 모두 자국산 G3 사용이 없었다. 미완료 경로의 중간 투자는 게임당 평균 '+f(w('market_first','routing.unfinished_intermediate_spend','Mechania','idle'))+'G다. 이는 전부 폐기 손실이라는 뜻은 아니지만, 투자 지출이 원래 목표의 완수로 이어지지 못한 부담을 보여 준다.')
    p('전체 만족도는 기존 '+f(w('baseline','happy','Mechania','idle'))+'점에서 무역 유지형 '+f(w('market_first','happy','Mechania','idle'))+'점으로 낮아졌다. 새 세대 출시가 구형 상품 평가를 바꾸는 규칙은 가능한 설명 중 하나다. 이 원인별 효과를 따로 분해한 실험은 아니므로 원료·가격·생활 구매 변화와 구분해 확정하지 않는다.','note')
    end()

    h(5,'국가별 경제 영향')
    for focal,style in COHORTS:
        add('<h3>'+('정상 공급' if focal is None else '메카니아 무행동')+' · 기존안 → 무역 유지형</h3>')
        add(table(['국가','종료 현금(G)','만족도','판매수입(G)','투자(G)','실사용 수출품'],[
            (COUNTRIES[n],)+tuple(f(c('baseline',n,k,focal,style))+' → '+f(c('market_first',n,k,focal,style)) for k in
                ('cash','happy','revenue','investment','useful_exports')) for n in COUNTRIES]))
    p('현금이 남은 이유가 투자 포기인지, 투자가 늘었어도 실제 사용이 없었는지를 함께 본다. 전체 실사용 수출품에는 모든 품목이 포함된다. 원료 거래량 증가가 특정 원료 생산국의 순이익 증가를 뜻하지는 않는다. 이 표의 무역 유지형 안 제시는 비교 편의이며 최종 채택 표시가 아니다.')
    p('메카니아 무행동에서 테크니아의 현금 감소는 투자 '+f(c('baseline','Technia','investment','Mechania','idle'))+'G → '+f(c('market_first','Technia','investment','Mechania','idle'))+'G 증가와 함께 나타난다. 노비아도 투자가 '+f(c('baseline','Novia','investment','Mechania','idle'))+'G → '+f(c('market_first','Novia','investment','Mechania','idle'))+'G로 늘었다. 종료 현금만 낮아졌다는 이유로 경제가 악화됐다고 판단하지 않는다. 반대로 현금 격차 축소만으로 공정성이 해결됐다고 말하지 않는다.')
    end()

    h(6,'경로 선택과 실제 완료는 다른 지표다')
    labels=(('시작','routes_started'),('완료','routes_completed'),('미완료','routes_unfinished'),
            ('완료 후 사용','routes_with_used_goal_output'),('중간 투자(G)','intermediate_spend'),
            ('미완료 중간 투자(G)','unfinished_intermediate_spend'),('기계 생산 대기 라운드','wait_output_rounds'),
            ('시간 부족 판단 라운드','horizon_block_rounds'),('공급 재개 후 복귀 판단','market_resume_rounds'),
            ('실물 확보 후 복귀 판단','owned_resume_rounds'),('중복 투자 취소','redundant_investments_cancelled'),
            ('신세대 공개 후 구매 기회','market_launch_wait_rounds'),('대체 공급용 주력 선택','supplier_focus_rounds'))
    for focal,style in COHORTS:
        add('<details><summary>'+('정상 공급' if focal is None else '메카니아 무행동')+' · 테크니아·노비아 경로 진단</summary>')
        add(table(['국가·안']+[x[0] for x in labels],[(COUNTRIES[n]+' · '+MODES[m],)+tuple(f(c(m,n,'routing.'+key,focal,style)) for _,key in labels) for n in ('Technia','Novia') for m in MODES]))
        add('</details>')
    p('경로 완료는 원래 목표 산업·단계의 투자가 성공한 경우다. 그 이후 생산품이 사용됐는지는 별도 지표다. 중간 투자비는 기계 산업 투자에 실제 지출한 현금으로, 연구 원료·기계 거래·기회비용을 모두 포함한 경로 총비용은 아니다. 끝내지 못한 중간 투자도 기계 생산 능력이나 실제 이용 가치가 남을 수 있어 전부 손실이라고 단정하지 않는다.')
    p('경로 시작·완료 지표는 자국의 우회 경로를 실제 시작한 나라만 센다. 다른 나라가 마련한 기계를 곧바로 수입해 원래 개발에 성공하면 우회 경로 완료 수에는 들어가지 않을 수 있다. 따라서 회복의 주된 판단은 테크니아·노비아 각각의 G3 실제 생산·사용으로 한다.')
    p('테크니아는 시작 기계 산업이 있지만 노비아는 기계 산업을 새로 확장해야 하므로 같은 회복률을 기대할 수 없다. 새 AI는 원래 국가별 확장 경로를 따르며, 모든 국가에 임의의 새 산업을 열어 주지 않는다.')
    add('<h3>첫 정식 시드의 대안 경로 기록</h3>')
    sample_rows=[]
    for mode in ('quick','patient','market_first'):
        trace=traces[f'main:{mode}:68000:Mechania:idle']
        for route in trace['routing_routes']:
            sample_rows.append((MODES[mode],COUNTRIES[route['country']],route['start_round'],route['starting_machine_level'],
                               GOODS[route['goal']]+' '+str(route['target_level'])+'단계',len(route['intermediate_event_ids']),{'completed':'완료','unfinished':'미완료','already_satisfied':'이미 충족','active':'진행 중'}[route['status']],route['end_round']))
    add(table(['안','국가','시작 라운드','시작 기계 단계','원래 목표','중간 투자 건수','종료 상태','종료 라운드'],sample_rows))
    p('첫 시드 사례는 전체 평균을 대신하지 않는다. 대안 경로가 없었던 나라를 실패나 성공으로 임의 분류하지 않는다. 이후 정상 생산은 최근 개발 1건에만 연결하며, 그 개발 덕분에 추가된 인과적 순증 생산량을 뜻하지 않는다. 고유 기계 수와 재사용 개발 횟수도 구별한다.')
    end()

    h(7,'다른 플레이 전략과 거부 조건')
    p('반값 판매는 공개 가격을 기준 가격의 50%로 두고 구매·투자를 계속한다. 무행동은 거래·투자 없이 자동 생산과 운영수입을 유지한다. 각 스트레스 조건은 같은 30개 시드의 정상 운영과 비교한다. 이 표의 무역 유지형 안은 검토 대상이며 최종 규칙 확정이 아니다.')
    p('50%는 가격 추천의 하한이지 게임에서 허용하는 최저 판매가라는 뜻이 아니다. 따라서 이번 반값 판매 실험으로 실제 허용 최저가를 매번 선택하는 모든 행동을 검증했다고 말할 수 없다. 실제 허용 최저가 반복 판매는 별도 스트레스 검증 과제이며, 의욕이 낮은 학생이나 저가 반복 행동의 문제가 모두 해결됐다고 판단하지 않는다.','note')
    add(table(['반값 판매 국가','기존 점수 차이','무역 유지형 점수 차이','무역 유지형 판매수입 차이(G)','무역 유지형 투자 차이(G)','무역 유지형 실제 사용품 차이'],[
        (COUNTRIES[n],ci(stressdiff('baseline',n,'cheap',f'countries.{n}.score')),ci(stressdiff('market_first',n,'cheap',f'countries.{n}.score')),ci(stressdiff('market_first',n,'cheap',f'countries.{n}.revenue')),ci(stressdiff('market_first',n,'cheap',f'countries.{n}.investment')),ci(stressdiff('market_first',n,'cheap',f'countries.{n}.all_goods_unique_used'))) for n in ORIGINAL]))
    p('테크니아 반값 판매의 종합 점수는 정상보다 '+ci(stressdiff('market_first','Technia','cheap','countries.Technia.score'))+'점 높았다. 실제 사용된 자국 생산품도 늘었으므로 점수 상승을 모두 허점으로 볼 수는 없다. 판매수입 감소와 점수 상한·활용 비율의 영향을 나누어 보는 후속 평가 검토가 필요하다. 테크니아 투자 감소의 95% 구간은 0을 포함하므로 이번 표본에서 그 감소를 확정적으로 해석하지 않는다.')
    add(table(['테크니아가 반값 판매할 때','정상 자국산 G3 사용 게임','반값 판매 조건의 자국산 G3 사용 게임','투자 차이(G)'],[
        (COUNTRIES[n],count('market_first',f'countries.{n}.routing.g3_electronics_used','stress'),count('market_first',f'countries.{n}.routing.g3_electronics_used','stress','Technia','cheap'),ci(stressdiff('market_first','Technia','cheap',f'countries.{n}.investment'))) for n in ('Technia','Novia')]))
    p('한 나라의 낮은 가격은 상대 국가의 발전에도 영향을 준다. 위 표는 테크니아의 행동을 바꾼 같은 게임에서 노비아에 생긴 변화를 함께 보여 준다. 공급 자체가 없는 문제와 가격·구매력·수익성 문제를 나누어 검토해야 한다.')
    add(table(['무행동 국가','무역 유지형 현금 차이','만족도 차이','점수 차이','전체 만족도 차이'],[
        (COUNTRIES[n],ci(stressdiff('market_first',n,'idle',f'countries.{n}.cash')),ci(stressdiff('market_first',n,'idle',f'countries.{n}.happy')),ci(stressdiff('market_first',n,'idle',f'countries.{n}.score')),ci(stressdiff('market_first',n,'idle','world.happy'))) for n in ORIGINAL]))
    p('이번 기존 6개국의 무행동 비교에서는 모두 자기 정상 운영보다 종합 점수가 낮았다. 현금이 쌓이는 경우를 더 좋은 게임 성과로 보지는 않는다. 이는 현재 규칙 기반 행동 표본의 결과이며 실제 소극적 학생의 참여·학습을 확인한 결과는 아니다.')
    add(table(['거부 안·국가·조건','G3 상품 생산 게임','G3 상품 사용 게임','원래 목표 완료 평균','생산 원료 부족 평균','투자 차이(G)'],[
        (MODES[m]+' · '+COUNTRIES[n]+' · '+('G2 이상 기계 수입 거부' if st=='no_high_machine' else '광물·연료 수입 거부'),count(m,f'countries.{n}.routing.g3_electronics_produced','stress',n,st),count(m,f'countries.{n}.routing.g3_electronics_used','stress',n,st),f(mean(m,f'countries.{n}.routing.routes_completed','stress',n,st)),f(mean(m,f'countries.{n}.production_failures','stress',n,st)),ci(stressdiff(m,n,st,f'countries.{n}.investment'))) for m in MODES for n,st in REFUSALS]))
    p('기계 수입 거부는 G2 이상 기계의 현금·물물교환 수입을 지정 국가가 거부하는 조건이다. 공개 공급이 존재하면 새 AI는 이를 공급 부재로 오인하지 않는다. 거부 규칙을 우회해 기계를 사도록 만들지 않는다. 자국 생산과 수출은 허용되지만, 자국 생산 여부도 기존 비용·원료·시간에 달려 있다.')
    add(table(['전체 무역 금지','평균 만족도 정상→금지','원래 목표 완료 정상→금지','고급 기계 거래 정상→금지'],[
        (MODES[m],f(mean(m,'world.happy','stress'))+' → '+f(mean(m,'world.happy','stress',None,'no_trade')),f(mean(m,'world.routing.routes_completed','stress'))+' → '+f(mean(m,'world.routing.routes_completed','stress',None,'no_trade')),f(mean(m,'world.development.bought_high_machines','stress'))+' → '+f(mean(m,'world.development.bought_high_machines','stress',None,'no_trade'))) for m in MODES]))
    end()

    h(8,'점수와 학습 효과의 판단 범위')
    p('점수식은 바꾸지 않았다. 경제력·생산 능력 점수의 상한, 산업 활용 점수의 생산량 분모, 개발용 기계 수요가 기존 필요량·충족량 원장에 별도 기록되지 않는 문제는 남아 있다. 사용량 증가와 분모 감소가 동시에 있을 수 있어 반값 판매 점수 상승을 전부 허점으로 보거나 전부 성공으로 보지 않는다.')
    add(table(['기존 6개국 · 정상 공급','종합 기존→무역 유지형','경제력 기존→무역 유지형','생산 능력 점수','활용 점수','무역 점수'],[
        (COUNTRIES[n],)+tuple(f(c('baseline',n,k))+' → '+f(c('market_first',n,k)) for k in ('score','economic','industry_capacity_score','industry_use_score','trade')) for n in ORIGINAL]))
    p('추가 3개국의 경제력·산업·종합 목표가 보정되지 않아 9개국 순위를 만들지 않는다. 산업의 자급 경로가 존재하는 것과 무역이 필요하지 않은 것은 다르다. 고급 기계 구매가 줄어도 광물·연료·생활 상품을 계속 수입하는지 확인한다.')
    add('<blockquote>“필요한 기계를 파는 나라가 없다면, 우리나라에서 할 수 있는 다른 발전 방법을 찾아볼 수 있어요. 시간이 더 걸리고 돈과 원료도 필요해요. 다시 살 수 있게 되면 원래 계획으로 돌아갈 수 있어요.”</blockquote>')
    add(table(['학습 의도','교실에서 확인할 행동'],[
        ('무역과 자국 생산 비교','사는 것과 직접 만들기의 돈·시간·원료 차이를 말하는가'),
        ('공급과 구매력 구분','판매자가 없음과 돈이 부족함을 구별하는가'),
        ('계획 수정 경험','원래 목표를 기억하면서 다른 선택을 시도하는가'),
        ('상호 의존 이해','기계를 직접 만들어도 필요한 원료·생활 상품 교역이 남는다는 점을 발견하는가'),
        ('소극적 학생이 있는 수업','한 학생의 무행동이 다른 학생의 모든 발전 기회를 막지 않는가'),
    ]))
    p('위 문구는 학생 화면의 설명 예시다. 내부 대기 횟수·경로 예측식을 학생에게 암기시키지 않는다. 모든 실행에서는 규칙 기반 자동 국가가 행동했다. 테크니아·노비아를 학생이 맡는다면 대안 경로를 선택 가능한 안내로 보여 주고, 투자·주력 결정은 학생의 선택으로 남기는 설계가 필요하다. 학생이 이 안내를 따를지는 이번 계산으로 확인하지 않았다.')
    p('학생 3명과 컴퓨터 6개국이 실제로 상호작용할 때의 발전 회복·이해·흥미·협상, 40분+40분 수업 속도, 개별 접속·동시 거래 웹앱은 아직 검증하지 않았다. 임시 주력 조정은 이번 자동 국가 실험의 선택 알고리즘이며 학생의 자금 지출이나 주력을 자동으로 바꾸는 학생용 기능을 추가한 것은 아니다.')
    end()

    h(9,'실행·검사 범위와 재현')
    add(table(['항목','기록'],[
        ('본 비교','4안 × 정상/메카니아 무행동 × 200시드 = 1,600게임; 68000~68199'),
        ('스트레스','4안 × 20조건 × 30시드 = 2,400게임; 70000~70029'),
        ('전체 게임',f"{meta['completed_games']:,}"),('통과 테스트',f"{tests['test_count']:,}; 기존 260개 및 신규 검증"),
        ('상태 불변식 호출',f"{meta['verification_calls']:,}; 보고된 실패 {meta['verification_failures']}"),
        ('본 비교 원장','현금 129,600행, 원료 129,600행'),
        ('대표 상세 추적','8개 본 비교 + 24개 수입 거부 = 32게임'),
        ('계산 시간',f(meta['elapsed_seconds'])+'초; 교실 진행 시간이 아님'),('독립 감사',audit['status']),
    ]))
    p('예비 실행·단위 테스트 시드와 정식 시드를 분리했다. 실제 코드·테스트·실행기 해시를 고정하고 완료 전후 일치를 확인했다. 모든 게임의 내부 불변식 검사를 실시했으며, 저장된 상세 경로를 재구성하는 독립 검사는 대표 32게임의 추적 범위를 포함한다. 전체 게임의 모든 상세 경로를 독립 재실행했다고 표현하지 않는다.')
    add('<pre>python3 -m unittest test_previous test_fixes test_costs test_expansion test_budget test_machinery test_recommendation test_raw_resources test_development test_routing\npython3 run_routing_validation.py --n 200 --stress-n 30 --workers 4 --output-dir reproduced_routing_results\npython3 audit_routing_results.py --results reproduced_routing_results\npython3 build_routing_report.py --results reproduced_routing_results --report REPRODUCED_V10_KO.html</pre>')
    p('Python 표준 라이브러리로 계산하며 이번 환경은 Python 3.12다. 기존 결과를 보존하도록 새 출력 폴더를 지정한다. 코드를 바꾸었다면 실제 테스트와 시뮬레이션을 다시 수행한다. 보고서 생성기는 정식 전체 결과·감사 통과·원장·대표 추적이 완성되지 않으면 보고서를 쓰지 않는다.')
    end()

    h(10,'네 가지 안의 국가별 상세 평균')
    for focal,style in COHORTS:
        for mode in MODES:
            add('<details><summary>'+('정상 공급' if focal is None else '메카니아 무행동')+' · '+MODES[mode]+'</summary>')
            add(table(['국가','현금','만족도','투자','고급 기계 수입','광물 수입','연료 수입','경로 시작','경로 완료','G3 전자 생산 게임','종합'],[
                (COUNTRIES[n],)+tuple(f(c(mode,n,k,focal,style)) for k in ('cash','happy','investment','development.bought_high_machines','import_goods.ore','import_goods.fuel','routing.routes_started','routing.routes_completed'))+(count(mode,f'countries.{n}.routing.g3_electronics_produced','main',focal,style),f(c(mode,n,'score',focal,style)) if n in ORIGINAL else '—') for n in COUNTRIES]))
            add('</details>')
    p('압축 파일에는 코드·테스트·전체 게임 요약·조건별 평균·같은 시드 차이·현금 및 원료 원장·대표 상세 추적·독립 감사 기록이 들어 있다. 이 HTML은 인터넷 없이 읽는 정적 결과 보고서이며 플레이 가능한 웹앱이 아니다.')
    end()

    css='''*{box-sizing:border-box}body{margin:0;background:#eef2f5;color:#1e2e3e;font:16px/1.7 system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:28px}header{background:#173f4e;color:#fff;border-radius:18px;padding:40px 44px}.eyebrow{font-size:14px;color:#b5dce2}h1{font-size:38px;line-height:1.25;margin:14px 0}header p{color:#e0edf0}.badge{display:inline-block;padding:7px 14px;background:#2d5b6b;border-radius:8px;font-size:14px}nav{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}nav a{background:#fff;border:1px solid #d4e0e5;border-radius:8px;padding:7px 12px;color:#184e63;text-decoration:none}section{background:white;border:1px solid #dce4e9;border-radius:14px;padding:26px 30px;margin:22px 0}h2{font-size:25px;line-height:1.35;margin:0 0 18px;color:#143e50}h3{font-size:19px;margin:24px 0 10px}.table-wrap{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid #dbe4e9;padding:10px 12px;text-align:right;vertical-align:top;white-space:nowrap}th:first-child,td:first-child{text-align:left;min-width:130px;white-space:normal}thead th{background:#e8f1f5;color:#164356}tbody th{font-weight:500}tbody tr:nth-child(even){background:#f8fafb}.note{border-left:3px solid #88aab8;padding-left:14px;color:#586c7b;font-size:14px}.callout{background:#edf5f7;border-left:4px solid #447a8c;border-radius:8px;padding:18px 22px}blockquote{background:#f2f6ed;border-left:4px solid #77925d;padding:20px 24px;margin:20px 0;font-size:18px}details{border:1px solid #d8e3e8;border-radius:8px;padding:13px 16px;margin:14px 0}summary{cursor:pointer;color:#205265;font-weight:600}pre{background:#162c38;color:#e0eef3;white-space:pre-wrap;word-break:break-word;font-size:13px;padding:18px;border-radius:8px}footer{color:#637786;font-size:13px;text-align:center;padding:20px}@media(max-width:700px){main{padding:12px}header{padding:26px 22px}h1{font-size:29px}section{padding:22px 16px}}@media print{body{background:white}main{max-width:none;padding:0}nav{display:none}section{border:0;padding:15px 0}.table-wrap{overflow:visible}th,td{white-space:normal;padding:5px}table{font-size:10px}pre{background:#eee;color:#111}}'''
    css+='table.two-columns th:first-child{width:28%}table.two-columns th:last-child,table.two-columns td:last-child{text-align:left;white-space:normal;min-width:0;overflow-wrap:anywhere}'
    html='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>#11 무역 게임 v10 · 대안 발전 경로 검증</title><style>'+css+'</style></head><body><main>'+''.join(parts)+'<footer>#11 무역 게임 · v10 대안 투자 판단 · 정적 결과 보고서</footer></main></body></html>'
    report.write_text(html,encoding='utf-8')
    return {'report':str(report),'bytes':report.stat().st_size,'tables':html.count('<table'),'games':len(rows),'sha256':hashlib.sha256(report.read_bytes()).hexdigest()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=DEFAULT_RESULTS)
    p.add_argument('--report',type=Path,default=ROOT/'TRADE_ROUTING_REVIEW_V10_KO.html');args=p.parse_args()
    print(json.dumps(build(args.results.resolve(),args.report.resolve()),ensure_ascii=False))


if __name__=='__main__':main()
