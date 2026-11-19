"""Korean v11 report from completed, audited saved results only.

Formatting helpers do not import engines. No simulation, price selection,
score fitting or pilot fallback occurs while generating this report.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
import gzip
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import statistics

from build_routing_report import read_json,read_lines,need,get,f,ci,table,Metric,PairedValues,Cell

ROOT=Path(__file__).resolve().parent
DEFAULT_RESULTS=ROOT/'evaluation_results'
COUNTRIES={'Tropia':'트로피아','Grainia':'그레니아','Oilia':'오일리아','Mechania':'메카니아',
           'Mineria':'미네리아','Technia':'테크니아','Novia':'노비아','Agrea':'아그레아','Ferria':'페리아'}
ORIGINAL=tuple(COUNTRIES)[:6]
VIEWS={'legacy':'기존 평가','success_only':'성공한 개발만','ready':'준비된 기회 전체','ready_once':'기존 충족과 중복 제한'}
BEHAVIORS={'normal':'정상','cheap':'반값 공개 판매','minimum':'1G 공개 판매','minimum_passive':'1G 공개 판매+투자 중단','idle':'무행동'}
MAIN_CASES=('None:normal',)+tuple(f'{n}:{s}' for n in ORIGINAL for s in ('cheap','minimum','idle'))
STRESS_CASES=('None:normal',)+tuple(f'{n}:{s}' for n in ORIGINAL for s in ('minimum','minimum_passive'))+(
    'Mechania:idle','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum',
    'Technia:no_high_machine','Novia:no_high_machine','Technia:no_raw','None:no_trade')
MAIN_SEEDS=range(78000,78200)
STRESS_SEEDS=range(80000,80030)


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.anchors=[];self.external=[]
        self.qa=[];self.tables=0;self.rows=0;self.width=None;self.cells=None
        self.errors=[]
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
    parsed=StructureParser();parsed.feed(html);parsed.close()
    need(not parsed.errors,'; '.join(parsed.errors))
    need(len(parsed.ids)==len(set(parsed.ids)) and set(parsed.ids)=={f's{i}' for i in range(1,12)},'Section anchors must be unique and complete.')
    need(set(parsed.anchors)==set(parsed.ids),'Navigation must point to every report section.')
    need(not parsed.external,'Static report must not depend on external links or assets.')
    need(len(parsed.qa)>=150,'Insufficient independently locatable numeric cells.')
    receipt={'status':'passed','report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),
             'sections':len(parsed.ids),'tables':parsed.tables,'rows':parsed.rows,
             'numeric_cells':len(parsed.qa),'external_assets':len(parsed.external),'errors':[],
             'scope':'HTML structure and numeric-locator syntax only; no browser rendering or screenshot validation.'}
    (folder/'report_structure_qa.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt


def load_completed(folder):
    files=('pre_run_plan.json','run_manifest.json','summary.json','runs.jsonl.gz','round_ledgers.jsonl.gz',
           'raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz','tests_manifest.json','independent_audit.json')
    need(all((folder/n).is_file() for n in files),'Complete formal results, tests and independent audit required.')
    meta=read_json(folder/'run_manifest.json');summary=read_json(folder/'summary.json')
    need(summary['metadata']==meta,'Summary and completed manifest differ.')
    del summary
    need(meta['completed_games']==4400 and meta['main_games']==3800 and meta['stress_games']==600,'Formal contract is 4,400 unique economic games.')
    need(meta['main_seed_range']==[78000,78199] and meta['stress_seed_range']==[80000,80029],'Unexpected formal seeds.')
    need(meta['rounds']==9 and meta['countries']==9 and meta['source_unchanged'] is True and meta['pilot_excluded'] is True,'Frozen nine-country, nine-round execution required.')
    tests=read_json(folder/'tests_manifest.json')
    need(tests['passed'] is True and tests['test_count']==meta['tests_completed'] and tests['test_count']>298,'Inherited and new tests must pass.')
    need(hashlib.sha256((folder/'tests_manifest.json').read_bytes()).hexdigest()==meta['tests_manifest_sha256'],'Test record hash mismatch.')
    audit=read_json(folder/'independent_audit.json')
    need(audit['status']=='passed' and not audit['errors'] and not audit.get('warnings'),'Independent audit must pass.')
    rows=read_lines(folder/'runs.jsonl.gz')
    expected={('main',case,s) for case in MAIN_CASES for s in MAIN_SEEDS}
    expected.update(('stress',case,s) for case in STRESS_CASES for s in STRESS_SEEDS)
    keys=[(r['phase'],r['scenario'],r['seed']) for r in rows]
    need(len(keys)==len(set(keys))==4400 and set(keys)==expected,'Saved runs differ from the exact unique schedule.')
    groups=defaultdict(list)
    for r in rows:
        need(r['mode']=='market_first' and set(r['countries'])==set(COUNTRIES),'Unexpected physical policy/country set.')
        conf=r['world']['evaluation_config']
        need(conf['baseline']=='v10 market_first' and conf['legal_public_minimum']==1 and conf['public_prices_only'] is True,'Minimum-public-price contract differs.')
        need(conf['scoring_modes']==list(VIEWS) and conf['original_scores_unchanged'] is True and conf['shadow_scores_do_not_affect_actions'] is True,'Score views must preserve the original economy and scores.')
        for name,x in r['countries'].items():
            need(set(x['evaluation']['scores'])==set(VIEWS),'Missing score view.')
            need(abs(x['evaluation']['scores']['legacy']['trade']-x['trade'])<1e-9,'Legacy trade changed.')
        groups[(r['phase'],r['scenario'])].append(r)
    ledger_keys={(case,s) for case in MAIN_CASES for s in MAIN_SEEDS}
    cells={(n,r) for n in COUNTRIES for r in range(1,10)}
    for filename in ('round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz'):
        observed=set()
        with gzip.open(folder/filename,'rt',encoding='utf-8') as stream:
            for line in stream:
                r=json.loads(line);key=(r['scenario'],r['seed'])
                need(r['phase']=='main' and key not in observed,'Duplicate/non-main ledger identity.')
                observed.add(key)
                need(len(r['rows'])==81 and {(x['country'],x['round']) for x in r['rows']}==cells,'Incomplete country-round ledger.')
        need(observed==ledger_keys,'Incomplete main ledger: '+filename)
    traces=read_json(folder/'first_seed_traces.json.gz')
    trace_keys={('main',case,78000) for case in MAIN_CASES}|{('stress',case,80000) for case in STRESS_CASES}
    need(len(traces)==39 and {(t['phase'],t['scenario'],t['seed']) for t in traces.values()}==trace_keys,'All 39 representative traces required.')
    return meta,tests,audit,rows,groups,traces


def build(folder,report):
    meta,tests,audit,rows,groups,traces=load_completed(folder)
    supplemental=read_json(folder/'supplemental_overlap_audit.json') if (folder/'supplemental_overlap_audit.json').exists() else None
    if supplemental is not None:
        need(supplemental['status']=='passed' and not supplemental['errors'] and supplemental['summary_exact_match'] is True,'Supplemental replay must pass and match the original formal record.')
        need(supplemental['additional_unique_trajectories']==0,'Supplemental replay is not an extra unique game.')
    @lru_cache(maxsize=None)
    def mean(case,path,phase='main'):
        return Metric(statistics.mean(get(r,path) for r in groups[(phase,case)]),
                      {'kind':'mean','experiment':f'{phase}:market_first:{case}','metric':path})
    def values(case,path,phase='main'):
        return {r['seed']:get(r,path) for r in groups[(phase,case)]}
    def diff(case,path,phase='main',control='None:normal'):
        x=values(control,path,phase);y=values(case,path,phase);need(x.keys()==y.keys(),'Unpaired seeds.')
        if control=='None:normal':key=f'{phase}:market_first:{case}'
        elif phase=='main' and control.endswith(':cheap') and case==control[:-5]+'minimum':
            key=f'{phase}:market_first:{case[:-7]}cheap->minimum'
        else:key=f'{phase}:market_first:{control}->{case}'
        return PairedValues([y[s]-x[s] for s in sorted(x)],{'kind':'ci','pair':key,'metric':path})
    def count(case,path,phase='main'):
        v=values(case,path,phase)
        return Cell(f'{sum(x>0 for x in v.values())}/{len(v)}',{'kind':'count','experiment':f'{phase}:market_first:{case}','metric':path})
    def either(case,phase='main'):
        rr=groups[(phase,case)]
        keys=[f'countries.{n}.routing.g3_electronics_used' for n in ('Technia','Novia')]
        return Cell(f'{sum(any(get(r,k) for k in keys) for r in rr)}/{len(rr)}',
                    {'kind':'anycount','experiment':f'{phase}:market_first:{case}','metrics':keys})
    def higher(case,name,view='legacy',phase='main',control='None:normal'):
        path=f'countries.{name}.evaluation.scores.{view}.score'
        x=values(control,path,phase);y=values(case,path,phase)
        need(x.keys()==y.keys(),'Score frequency comparison must use paired seeds.')
        return Cell(f'{sum(y[s]>x[s]+1e-9 for s in x)}/{len(x)}',
                    {'kind':'paired_greater_count','experiment':f'{phase}:market_first:{case}',
                     'control':f'{phase}:market_first:{control}','metric':path})
    def highest(case,name,view='legacy',phase='main'):
        rr=groups[(phase,case)];path=f'countries.{name}.evaluation.scores.{view}.score'
        keys=[f'countries.{n}.evaluation.scores.{view}.score' for n in ORIGINAL]
        return Cell(f'{sum(get(r,path)>=max(get(r,k) for k in keys)-1e-9 for r in rr)}/{len(rr)}',
                    {'kind':'top_count','experiment':f'{phase}:market_first:{case}',
                     'metric':path,'metrics':keys})
    def c(case,name,key,phase='main'):return mean(case,'countries.'+name+'.'+key,phase)
    def scaled(value,factor):return Metric(float(value)*factor,{**value.qa,'factor':factor})
    def w(case,key,phase='main'):return mean(case,'world.'+key,phase)
    def score(case,name,view='legacy',phase='main',field='score'):
        return c(case,name,f'evaluation.scores.{view}.{field}',phase)
    def cdiff(case,name,key,phase='main',control='None:normal'):
        return diff(case,'countries.'+name+'.'+key,phase,control)
    parts=[]
    def add(x):parts.append(x)
    def p(s,cls=''):add('<p class="'+cls+'">'+escape(s)+'</p>')
    def h(i,s):add(f'<section id="s{i}"><h2>{i}. {escape(s)}</h2>')
    def end():add('</section>')
    def prose_table(headers,rows):
        return '<div class="prose-table">'+table(headers,rows)+'</div>'

    add('<header><div class="eyebrow">아이디어 노트 · #11 무역 게임 · v11</div><h1>실제 1G 판매와<br>개발용 기계의 평가를 점검하다</h1><p class="lead">9개국·9라운드 · 4,400개 경제 궤적 · 동일 궤적의 사후 평가 4가지</p><div class="badge">기존 공식 점수 유지 · 결과 검토와 수정 후보 비교</div></header>')
    add('<nav>'+''.join(f'<a href="#s{i}">{escape(t)}</a>' for i,t in ((1,'검증 범위'),(2,'가격 행동'),(3,'1G 판매 결과'),(4,'주변 국가'),(5,'25점의 구조'),(6,'평가 보기'),(7,'전략 간 공정성'),(8,'복합 행동'),(9,'교실 해석'),(10,'검증·재현'),(11,'전체 표')) )+'</nav>')

    h(1,'이번 검증의 두 질문')
    add('<div class="callout"><h3>검토 결론</h3><p>이번 표본에서 1G 공개 판매를 반복한 국가는 여섯 나라 모두 자기 정상 운영보다 총점이 낮았고, 기존 6개국 중 최고점을 얻은 경우도 없었다. 그러나 테크니아의 반값 판매는 높은 점수와 결합했다. 최저가 반복에 대한 우려와 국가별 평가 공정성 문제를 구별해야 한다.</p><p>개발용 기계의 실제 사용·준비된 미충족·중복 추적은 기록 개선으로 반영할 수 있는 상태다. 점수 공식의 자동 교체는 보류하는 편을 제안한다. 중복 제한 보기는 테크니아 반값 행동의 정상 대비 점수 차이를 오히려 키웠고, 국가 배정의 공정성도 해결하지 못했다. 기존 공식 점수는 변경하지 않았다.</p></div>')
    add(table(['핵심 진단','기존 평가','중복 제한 보기'],[
        ('테크니아 반값의 정상 대비 총점 차이',ci(cdiff('Technia:cheap','Technia','evaluation.scores.legacy.score')),ci(cdiff('Technia:cheap','Technia','evaluation.scores.ready_once.score'))),
        ('정상 운영 테크니아 최고점 빈도',highest('None:normal','Technia'),highest('None:normal','Technia','ready_once')),
        ('테크니아 반값 최고점 빈도',highest('Technia:cheap','Technia'),highest('Technia:cheap','Technia','ready_once')),
    ]))
    p('첫째, 학생이 공개 판매 가격을 매번 실제 최저값으로 고르면 어떤 일이 생기는가? 둘째, 개발에 사용한 기계가 무역 점수의 필요·충족 원장에 빠진 부분을 보완하면 평가가 더 정확하고 공정해지는가? 두 질문을 분리해 계산했다.')
    p('모든 경제 실행은 v10 무역 유지형을 기준으로 한다. 가격·참여 행동을 바꾼 고유 게임은 4,400회다. 각 게임이 끝난 뒤 네 가지 평가를 적용했으며, 이를 17,600개의 독립 경제 시뮬레이션으로 세지 않는다. 평가 보기만 바꿀 때 가격·거래·투자·생산·국민 만족도와 기존 공식 점수는 달라지지 않는다.')
    p('원장에 빠진 증거를 채우는 정확성과 평가의 공정성은 별개다. 준비가 잘 된 국가의 미충족 기회를 추가하는 규칙이, 준비가 안 된 국가보다 더 큰 점수 부담을 만들 수도 있다. 중복을 제한한 보기라고 해서 채택을 미리 확정하지 않는다.','note')
    end()

    h(2,'50% 추천 가격과 실제 최저 주문 가격')
    add(prose_table(['행동','바뀌는 부분','계속되는 부분'],[
        ('정상','없음','기존 v10 무역 유지형'),
        ('반값 공개 판매','공개 가격을 기준 가격의 50%로 설정','보호 재고·구매·투자·협상·물물교환'),
        ('1G 공개 판매','공개 가격을 1G/개로 설정','보호 재고·구매·투자·협상·물물교환'),
        ('1G 공개 판매+투자 중단','공개 가격 1G/개, 투자 중단','구매·자동 생산·기존 비투자 행동'),
        ('무행동','거래·투자 중단','자동 생산·만족도 연계 운영수입'),
    ]))
    p('현재 공개 주문은 가격 단위가 1G이고 주문 단가가 그 단위 이상이어야 하므로 최저값은 1G/개다. 50%는 추천 가격의 하한이며 가격 단위에 맞춰 반올림한다. 이번 최소 가격 실험은 허용 가격 규칙을 새로 바꾸지 않고 해당 국가의 가격 선택만 바꾼다.')
    p('직접 현금 협상과 물물교환은 기존 규칙을 유지한다. 따라서 “공개 판매가가 1G”와 “모든 채널의 거래가 1G”를 구별한다. 가격 외의 자동 행동을 유지한 minimum과 투자까지 중단한 minimum_passive도 서로 다른 조건이다.')
    p('직접 현금 협상의 명령은 양의 정수 총액을 허용한다. 여러 개를 묶어 총 1G에 넘기는 별도의 행동까지 이번 공개 시장 최저가 실험으로 검증한 것은 아니다.','note')
    add(table(['가격 정책 검사','결과'],[
        ('전체 정식 실행의 공개 최저가 위반 관측 합계',str(sum(r['world']['evaluation']['public_minimum_violations'] for r in rows))),
        ('기존 공식 점수','모든 보기에서 보존'),
        ('새 사후 평가의 행동 피드백','주문·예산·투자 선택에 사용하지 않음'),
    ]))
    p('공개 등록이 없었던 경우에도 위반 수는 0일 수 있다. 아래 채널별 실제 거래량·현금을 함께 확인한다.','note')
    end()

    h(3,'실제 1G 공개 판매의 자국 결과')
    add(table(['국가','종료 현금 정상→1G','만족도 정상→1G','판매수입 정상→1G','투자 정상→1G','실사용 수출품 정상→1G','기존 총점 정상→1G'],[
        (COUNTRIES[n],)+tuple(f(c('None:normal',n,k))+' → '+f(c(f'{n}:minimum',n,k)) for k in
            ('cash','happy','revenue','investment','useful_exports','score')) for n in ORIGINAL]))
    add(table(['국가','1G의 정상 대비 기존 총점 차이 [95% 구간]','반값 대비 1G 총점 차이 [95% 구간]','현금 무역수지 정상→1G'],[
        (COUNTRIES[n],ci(cdiff(f'{n}:minimum',n,'score')),ci(cdiff(f'{n}:minimum',n,'score',control=f'{n}:cheap')),
         f(c('None:normal',n,'evaluation.cash_trade_balance'))+' → '+f(c(f'{n}:minimum',n,'evaluation.cash_trade_balance'))) for n in ORIGINAL]))
    add(table(['국가','식량 부족 라운드 정상→1G','생산 실패 정상→1G','생산 광물 부족량 정상→1G','생산 연료 부족량 정상→1G'],[
        (COUNTRIES[n],)+tuple(f(c('None:normal',n,k))+' → '+f(c(f'{n}:minimum',n,k)) for k in
            ('food_short_rounds','production_failures','raw_unmet_production.ore','raw_unmet_production.fuel')) for n in ORIGINAL]))
    p('현금 무역수지는 현금 판매수입−구매지출이다. 투자와 운영수입을 포함한 순이익이 아니며, 수입으로 생활·생산 능력을 얻는 가치는 이 수치만으로 판단하지 않는다. 물물교환은 현금으로 임의 환산하지 않는다.')
    add('<h3>1G 정책 국가의 실제 거래 채널</h3>')
    add(table(['국가','공개 시장 판매수량','공개 시장 판매현금','직접 협상 판매수량','직접 협상 판매현금','물물교환 수출수량','기존 무역 점수'],[
        (COUNTRIES[n],)+tuple(f(c(f'{n}:minimum',n,k)) for k in ('channel_stats.market.sold_units','channel_stats.market.sales_cash','channel_stats.direct.sold_units','channel_stats.direct.sales_cash','channel_stats.barter.sold_units','trade')) for n in ORIGINAL]))
    p('판매량이 늘거나 실제로 쓰인 수출품이 많아지는 것은 무역의 유효한 성과일 수 있다. 낮은 가격 자체를 감점하지 않는다. 그 성과를 유지할 현금·원료·생활 물량·개발 여력이 남는지 함께 봐야 한다.')
    p('실제 결과에서 여섯 나라 모두 1G 판매의 실사용 수출품은 늘었지만 현금 판매수입과 총점은 줄었다. 테크니아의 1G 판매는 평균 투자 0G이면서 무역 점수는 25점이었다. 실제 수출 사용과 필수 수입 충족이 인정되는 구조이므로 25점 자체를 오류로 단정하지 않는다. 경제력·산업 점수까지 합친 국가 운영 결과는 별도로 낮아졌다.')
    p('식량 부족·생산 실패가 반드시 늘지는 않았다. 보호 재고·자동 구매·기본 운영수입 등이 남아 있는 조건이므로, 낮은 가격을 선택하면 즉시 국가가 붕괴한다는 모형도 아니다. 임의로 모든 재고를 처분하는 행동과는 범위가 다르다.')
    add('<h3>평균과 별도로, 1G 행동이 더 높은 점수를 받은 경우</h3>')
    add(table(['국가','기존 평가: 1G가 자국 정상보다 높음','중복 제한: 1G가 자국 정상보다 높음'],[
        (COUNTRIES[n],higher(f'{n}:minimum',n),higher(f'{n}:minimum',n,'ready_once')) for n in ORIGINAL]))
    p('분모는 각 200개 동일 시드다. 점수가 정상보다 엄격히 큰 경우를 센다. 평균 점수가 낮더라도 일부 시드에서 유리할 수 있으므로 평균 차이와 이 횟수를 함께 확인한다. 수치 오차 허용값은 10⁻⁹점이다.')
    add('<h3>기존 6개국 중 최고점 빈도 · 동점 포함</h3>')
    for view in ('legacy','ready_once'):
        add(table([VIEWS[view],'정상','해당국 반값','해당국 1G','해당국 무행동'],[
            (COUNTRIES[n],)+tuple(highest(case,n,view) for case in ('None:normal',f'{n}:cheap',f'{n}:minimum',f'{n}:idle')) for n in ORIGINAL]))
    p('각 칸은 해당 조건의 세계에서 대상 국가가 기존 6개국 최고점과 같거나 높은 게임 수다. 동점도 포함한다. 추가 3개국은 종합 성장 목표가 보정되지 않아 제외했다. 각 행에서 가격·참여를 바꾸는 나라가 다르므로 이 표의 칸을 합쳐 하나의 순위 분포로 해석하지 않는다. 제한된 자동 전략 비교이며 학생의 승률이나 공정성이 확정된 대회의 우승률은 아니다.')
    p('차이 구간은 같은 시드 차이의 평균 ± 1.96×표준오차다. 여러 지표를 보는 게임 모형의 탐색적 통계이며, 실제 학생 모집단을 대표하지 않는다. 구간에 0이 들어가면 증가·감소를 단정하지 않는다.','note')
    end()

    h(4,'한 나라의 낮은 가격이 주변에 미치는 영향')
    add(table(['1G 판매 국가','세계 만족도 차이','전체 거래량 차이','미사용 오래된 재고 차이','노비아 투자 차이','노비아 자국산 G3 사용 게임'],[
        (COUNTRIES[n],ci(diff(f'{n}:minimum','world.happy')),ci(diff(f'{n}:minimum','world.trade_units')),ci(diff(f'{n}:minimum','world.aged_unused')),ci(cdiff(f'{n}:minimum','Novia','investment')),count(f'{n}:minimum','countries.Novia.routing.g3_electronics_used')) for n in ORIGINAL]))
    p('같은 최저가라도 어떤 품목·국가가 실행하느냐에 따라 수입국의 부담과 다른 공급국의 수입이 다르게 바뀐다. 세계 평균 만족도 상승이나 거래량 증가를 그 판매국의 재정 성공 또는 모든 국가의 개선과 같은 뜻으로 보지 않는다.')
    add('<h3>테크니아의 가격 행동: 정상·반값·1G</h3>')
    tech_fields=(('종료 현금','cash'),('판매수입','revenue'),('구매지출','purchases'),('투자','investment'),
                 ('평균 만족도','happy'),('기존 무역 점수','trade'),('기존 총점','score'),('실사용 수출품','useful_exports'),
                 ('실제 사용된 자국 생산품','all_goods_unique_used'),('산업 활용 점수','industry_use_score'),('준비 완료 미충족 개발','evaluation.ready_unfulfilled'))
    add(table(['테크니아 지표','정상','반값','1G'],[(label,)+tuple(f(c(case,'Technia',key)) for case in ('None:normal','Technia:cheap','Technia:minimum')) for label,key in tech_fields]))
    tech_cases=('None:normal','Technia:cheap','Technia:minimum')
    component_fields=(('경제력 점수 /25','economic'),('산업 능력 점수 /15','industry_capacity_score'),
                      ('산업 활용 점수 /10','industry_use_score'),('만족도 점수 /25','happy'),('무역 점수 /25','trade'),('총점 /100','score'))
    add(table(['테크니아 점수 구성','정상','반값','1G'],[
        (label,)+tuple(f(scaled(c(case,'Technia',key),.25) if key=='happy' else c(case,'Technia',key)) for case in tech_cases) for label,key in component_fields]))
    add(table(['상한과 성장 진단','정상','반값','1G'],[
        ('경제력 25점 상한 도달',)+tuple(count(case,'countries.Technia.economic_at_cap') for case in tech_cases),
        ('초기 능력 대비 증가 비율 (1=100%)',)+tuple(f(c(case,'Technia','capacity_growth'),3) for case in tech_cases),
    ]))
    add(table(['테크니아 자국 생산량','정상','반값','1G'],[(label,)+tuple(f(c(case,'Technia','produced.'+key)) for case in ('None:normal','Technia:cheap','Technia:minimum')) for label,key in
        (('바나나','banana'),('밀','wheat'),('광물','ore'),('연료','fuel'),('기계','machine'),('전자제품','electronics'))]))
    p('산업 활용 10점은 실제 사용된 자국 생산품 수를 전체 자국 생산품 수로 나눈 비율에 비례한다. 실제 사용 증가와 생산량 감소가 함께 점수를 바꿀 수 있다. 한쪽 원인으로만 설명하지 않는다.')
    p('정식 결과의 테크니아 반값 행동은 실제 사용된 자국 생산품을 평균 3.08개 늘렸다. 동시에 총 생산량은 약 49.8개에서 46.2개로 줄었고 산업 활용 점수는 6.25점에서 7.40점으로 올랐다. 판매수입은 약 149G, 투자는 약 133G 감소했다. 실제 사용의 개선과 생산량 분모·점수 상한 효과가 함께 있어, 점수 상승을 순수한 악용이나 전반적인 경제 개선 한쪽으로 단정하지 않는다.')
    p('정상과 반값의 실제 생산 능력 증가 폭은 다르지만 산업 능력 점수는 둘 다 15점 상한이었다. 반값 판매가 유효한 가격 전략이라는 면과, 상한·국가별 성장 목표가 서로 다른 발전 정도를 충분히 구별하는지의 문제는 분리해서 검토한다.')
    end()

    h(5,'현재 무역 점수의 정확한 25점 구조')
    add(table(['항목','배점과 계산'],[
        ('실사용 수출 라운드','5 × min(실사용 수출 라운드/6, 1)'),
        ('외부 필요 충족량','8 × 외부 필요 충족량/외부 필요량'),
        ('교역 상대','4 × min(유효 교역 상대/3, 1)'),
        ('외부 필요 충족 라운드','4 × 충족 라운드/외부 필요가 있던 라운드'),
        ('수출 효과 라운드','4 × min(실사용 수출 라운드/6, 1)'),
    ]))
    p('합계는 25점이다. 같은 수출 라운드 지표가 5점과 4점, 총 9점에 쓰인다. 필요량·필요 라운드 분모가 0이면 해당 항목은 0점이다. 이번에는 이 배점을 수정하지 않는다.')
    p('기존 개발 코드는 기계를 사용했다고 기록하지만 기계의 개발 필요량·외부 충족량을 별도 필요 행으로 남기지 않았다. 기계가 실제 사용된 수출품이나 교역 상대 등 일부 지표에는 이미 영향을 줄 수 있어, “아무 점수에도 반영되지 않았다”는 뜻은 아니다. 연구 광물은 기존에도 필요 행으로 기록됐다.')
    end()

    h(6,'동일한 게임에 적용한 네 가지 평가 보기')
    add(prose_table(['보기','추가하는 개발용 기계 필요 행','주의할 점'],[
        ('기존 평가','없음','기존 공식 점수를 그대로 보존'),
        ('성공한 개발만','실제로 성공한 개발의 기계 사용','확인된 사용은 반영하지만 실패한 기회는 분모에 넣지 않음'),
        ('준비된 기회 전체','기계 외 투자·생활·원료 조건이 갖춰진 기회','미충족도 반영하며 기존 장비 충족과 중복될 수 있는 민감도 진단'),
        ('기존 충족과 중복 제한','준비된 기회 중 기존 동일 실물 장비 충족과 겹치지 않는 행','같은 국가·라운드·실물의 필요와 충족을 함께 제외하는 후보'),
    ]))
    p('준비 판정은 투자 직전의 동결된 실제 목표, 투자 가능한 라운드·산업, 연구비와 유보 현금, 식량·전자제품 생활 물량, 연구 광물과 다음 생산 원료를 확인한다. 기계 구입에 필요한 추가 현금까지 확보됐다는 뜻은 아니다. 현금·생활·원료 부족은 겹칠 수 있어 세 차단 횟수를 서로 독립된 원인 수로 더하지 않는다.')
    p('필요 최소 세대를 적용해 자국 G1을 G2 연구 대안으로 세지 않는다. 판매 등록한 적격 자국 기계도 국내 대안으로 본다. 외부 충족은 적격 외국산 기계의 실제 수입 이력과 성공한 연구 사용을 확인한다. 자국 기계 재수입은 새 외국산 대안과 구별한다.')
    p('중복 제한은 단지 장비로 사용했다는 이유로 작동하지 않는다. 기존 장비 필요 행에서 외부 충족으로 실제 인정된 UID를 확인한다. 서로 다른 개발에 같은 기계를 재사용한 효과는 기록하되, 이를 새 기계 여러 대의 수입으로 표현하지 않는다. 동일 명령 재실행은 새 기회가 아니다.')
    p('ready_once는 같은 국가·같은 라운드·같은 실물 UID의 기존 충족만 제한한다. 서로 다른 실물을 바꿔 쓰거나 다른 라운드·국가에서 재사용하는 경우까지 막는 포괄적인 점수 악용 방지 규칙은 아니다. 실제 사용 이력은 삭제하지 않고 평가에 더할 필요·충족 행만 구분한다.','note')
    add('<h3>정상 운영에서 원장 보완의 크기</h3>')
    add(table(['국가','기계 조건 투자 관측','준비 기회','외국산 기계 연구 사용','고유 외국산 실물','준비 완료 미충족','기존 장비 충족과 겹침'],[
        (COUNTRIES[n],)+tuple(f(c('None:normal',n,'evaluation.'+k)) for k in ('machine_attempts','ready_opportunities','foreign_machine_uses','unique_foreign_development_machines','ready_unfulfilled','existing_equipment_overlap')) for n in COUNTRIES]))
    add(table(['정상 운영 무역 점수']+list(VIEWS.values()),[(COUNTRIES[n],)+tuple(f(score('None:normal',n,v,field='trade')) for v in VIEWS) for n in COUNTRIES]))
    add(table(['국가·보기','추가 필요 행','추가 외부 필요','추가 외부 충족','제외한 기존 충족','무역 점수 변화'],[
        (COUNTRIES[n]+' · '+VIEWS[v],)+tuple(f(score('None:normal',n,v,field=k)) for k in ('added_needed','added_external','added_fulfilled','skipped_existing_credit','trade_delta')) for n in ('Mechania','Technia','Novia') for v in ('success_only','ready','ready_once')]))
    add('<h3>대표 경로: 성공 기록과 미충족 기회는 다르다</h3>')
    p('본 비교 정상 조건의 시드 78000에서 노비아는 5라운드에 메카니아의 G2 기계 실물 209를 58G에 수입하고 전자산업 Lv3 개발에 사용했다. 새 보기에는 필요 1·충족 1이 생기지만 기존 다른 수입도 모두 충족된 상태여서 무역 점수는 23.5점으로 같았다. 기록이 생겼다고 반드시 추가 점수가 생기는 것은 아니다.')
    p('같은 게임의 테크니아는 4~6라운드에 현금·생활·원료 조건을 갖췄지만 적격 G2 기계가 없어 개발하지 못했다. 7라운드에 메카니아의 기계 실물 210을 42G에 사서 개발했다. 기존 외부 필요 충족은 25/25였으나 준비된 기회를 넣으면 26/29가 되어 무역 점수는 25점에서 24.17점으로 바뀐다. 성공만 기록하는 보기에서는 앞선 미충족 기회가 보이지 않는다. 이 한 경로는 동작 설명이며 평균 결과를 대표한다고 가정하지 않는다.')
    all_overlap=sum(r['world']['evaluation']['existing_equipment_overlap'] for r in rows)
    trace_overlap=audit['audit_counts']['duplicate_equipment_service_rows_removed']
    coverage=audit['legacy_score_coverage']
    p(f"전체 4,400개 요약에는 기존 장비 외부 충족과 겹친 개발 사용 {all_overlap}건이 있다. 저장된 39개 대표 상세 경로의 해당 중복은 {trace_overlap}건이므로, 이 대표 경로들만으로 전체 중복 건의 실물 이력을 독립 재구성했다고 말하지 않는다. 전체 요약의 점수·개수 일치는 확인했고, 동일 실물·세대·원산지 등 경계 조건은 별도 테스트로 검사했다.",'note')
    p(f"39개 대표 상세 경로에서는 실제 개발 기계 사용 {coverage['machine_development_events']}건에 대응하는 기존 개발 기계 필요 행이 {coverage['machine_development_with_need_record']}건이었다. 이 누락 횟수는 전체 4,400게임의 상세 추적 횟수가 아니다.",'note')
    if supplemental is not None:
        example=supplemental['examples'][0];machine=example['machine'];tx=example['import_transaction'];views=example['country_score_views']
        p(f"중복을 실제 실물로 확인하기 위해 기존 정식 게임 중 트로피아 반값 조건 시드 {supplemental['formal_identity'][2]}를 한 번 보충 재생했다. 노비아는 {tx['round']}라운드에 메카니아 G{machine['generation']} 기계 실물 {machine['uid']}를 {tx['cash'][2]}G에 수입했다. {example['round']}라운드의 밀 산업 장비 필요 1·충족 1에 쓴 같은 실물을 전자산업 Lv3 개발에 재사용했다. 준비 전체 보기는 필요·충족 1을 더해 무역 점수를 {views['legacy']['trade']:.5f}점에서 {views['ready']['trade']:.5f}점으로 올렸고, 중복 제한 보기는 그 추가 행을 제외해 {views['ready_once']['trade']:.5f}점을 유지했다.")
        p(f"보충 재생은 원래 정식 요약과 모든 필드가 일치했고, 독립 대조 {supplemental['checks_evaluated']:,}회에서 오류가 없었다. 고유 경제 게임 수는 4,400개, 정식 대표 상세 경로는 39개 그대로다. 보충 1건을 전체 77건의 실물 재구성으로 확대해서 해석하지 않는다.",'note')
    end()

    h(7,'원장을 더 정확히 채우면 전략 비교도 공정해지는가')
    p('아래는 각 나라가 자기 정상 운영과 같은 시드에서 행동만 바꿨을 때의 총점 차이다. 사후 평가에서도 경제력·산업·만족도 점수는 유지하고 무역 점수의 차이만 반영한다. 추가 3개국의 종합 성장 목표는 보정되지 않아 비교용 총점도 기존 6개국만 표시한다.')
    for behavior in ('cheap','minimum','idle'):
        add('<h3>'+BEHAVIORS[behavior]+'의 정상 대비 총점 차이</h3>')
        add(table(['국가']+[VIEWS[v]+' 차이 [95% 구간]' for v in VIEWS],[
            (COUNTRIES[n],)+tuple(ci(cdiff(f'{n}:{behavior}',n,f'evaluation.scores.{v}.score')) for v in VIEWS) for n in ORIGINAL]))
    add('<h3>기존 충족과 중복 제한이 테크니아의 전략 차이에 더한 변화</h3>')
    add(table(['행동','기존 무역 점수 변화','성공만 보기의 보완량','준비 전체의 보완량','중복 제한의 보완량','중복 제한이 정상 대비 점수 차이에 더한 값'],[
        (BEHAVIORS[b],ci(cdiff(f'Technia:{b}','Technia','trade')),
         f(score(f'Technia:{b}','Technia','success_only',field='trade_delta')),
         f(score(f'Technia:{b}','Technia','ready',field='trade_delta')),
         f(score(f'Technia:{b}','Technia','ready_once',field='trade_delta')),
         ci(cdiff(f'Technia:{b}','Technia','evaluation.scores.ready_once.trade_delta'))) for b in ('cheap','minimum','idle')]))
    p('마지막 열은 “새 보기에서의 행동−정상 총점 차이”가 기존보다 얼마나 달라졌는지다. 양수이면 그 행동의 상대 점수 차이가 커지고, 음수이면 작아진다. 이런 변화를 관찰하는 것이 원장 수정의 공정성 검토다.')
    p('준비된 기회가 많은 국가는 확보하지 못한 기계 수요가 추가될 수 있다. 반대로 현금·생활·원료가 준비되지 않은 국가는 그 기회가 분모에 들어가지 않을 수 있다. 기록의 의미를 더 분명히 했더라도 정상적인 발전 노력을 더 불리하게 평가하지 않는지 확인해야 한다.')
    p('정상 테크니아는 준비 완료 미충족이 평균 1.37회여서 중복 제한 보기에서 약 0.50점 내려갔다. 반값 테크니아는 0.75회여서 약 0.23점 내려갔다. 그 결과 반값의 정상 대비 총점 차이는 1.09점에서 1.36점으로 커졌다. 중복 제한이 불필요하다는 뜻이 아니라, 필요량을 어느 기회에서 세는지와 국가별 성장 목표·활용 비율을 별도로 설계해야 한다는 결과다.')
    end()

    h(8,'투자까지 중단하거나 공급국이 참여하지 않는 경우')
    add('<h3>1G 공개 판매에서 투자를 더 중단하면</h3>')
    add(table(['국가','기존 총점 1G→1G+투자 중단','만족도 1G→투자 중단','현금 1G→투자 중단','투자 1G→투자 중단','기계 준비 완료 미충족 1G→투자 중단'],[
        (COUNTRIES[n],)+tuple(f(c(f'{n}:minimum',n,k,'stress'))+' → '+f(c(f'{n}:minimum_passive',n,k,'stress')) for k in ('score','happy','cash','investment','evaluation.ready_unfulfilled')) for n in ORIGINAL]))
    p('두 행동은 같은 추가 스트레스 30개 시드로 비교했다. 투자 중단은 의욕이라는 심리 상태를 직접 측정한 것이 아니다. 구매·자동 생산 등이 남아 있는 구체적인 자동 행동 조건이다.')
    p('메카니아의 추가 30시드에서는 두 행동 모두 실행된 투자가 0G였지만 평균 총점은 달랐다. 투자하지 않기로 한 정책은 계획·보호 물량·구매 판단에도 연결되므로, 실제 투자액만 같다는 이유로 두 경로가 같다고 보지 않는다.')
    combos=('None:normal','Mechania:idle','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum')
    labels={'None:normal':'정상','Mechania:idle':'메카니아 무행동','Mechania:idle+Technia:minimum':'메카니아 무행동+테크니아 1G','Mechania:idle+Novia:minimum':'메카니아 무행동+노비아 1G'}
    add(table(['복합 조건','테크니아 자국산 G3 사용','노비아 자국산 G3 사용','두 나라 모두','한 나라 이상','전체 만족도','전체 고급 기계 거래'],[
        (labels[case],count(case,'countries.Technia.routing.g3_electronics_used','stress'),count(case,'countries.Novia.routing.g3_electronics_used','stress'),count(case,'world.routing.both_electronics_used','stress'),either(case,'stress'),f(w(case,'happy','stress')),f(w(case,'development.bought_high_machines','stress'))) for case in combos]))
    add(table(['메카니아 무행동에 1G 행동을 추가한 효과','전체 만족도 차이','테크니아 총점 차이','노비아 투자 차이'],[
        (labels[case],ci(diff(case,'world.happy','stress','Mechania:idle')),ci(cdiff(case,'Technia','score','stress','Mechania:idle')),ci(cdiff(case,'Novia','investment','stress','Mechania:idle'))) for case in combos[2:]]))
    p('자국산 G3 사용은 그 나라가 생산한 G3 상품이 자국 또는 외국에서 사용된 경우다. 수입 G3를 소비한 것만으로 해당 생산국 성공을 세지 않는다. 한 나라 이상에는 두 나라 모두 성공한 게임도 포함한다.')
    p('메카니아 무행동에 테크니아의 1G 판매까지 더하면 한 나라 이상에서 자국산 G3가 사용된 게임은 27/30에서 11/30으로 줄었다. 노비아가 1G 판매를 하면 테크니아는 30/30으로 늘지만 노비아 자신의 G3 사용은 0/30이었다. 한 국가의 대체 성공을 두 나라 모두의 회복으로 해석하지 않는다.')
    add('<details><summary>기계·원료 수입 거부와 전체 무역 금지</summary>')
    checks=('Technia:no_high_machine','Novia:no_high_machine','Technia:no_raw','None:no_trade')
    add(table(['조건','만족도','준비 완료 미충족 개발','실제 외국산 기계 연구 사용','고급 기계 국경 거래'],[
        (case,f(w(case,'happy','stress')),f(w(case,'evaluation.ready_unfulfilled','stress')),f(w(case,'evaluation.foreign_machine_uses','stress')),f(w(case,'development.bought_high_machines','stress'))) for case in checks]))
    add('</details>')
    end()

    h(9,'학생에게 남겨야 할 학습 경험')
    add(table(['현재 상태','내용'],[
        ('구현·검증한 기록 개선','개발용 기계의 실제 사용, 준비됐지만 충족하지 못한 기회, 최소 세대·수입 이력, 기존 장비 충족과 동일 실물의 겹침을 추적한다.'),
        ('유지한 공식 규칙','경제·거래·가격·생산 규칙과 기존 공식 점수는 유지한다. 네 가지 보기의 숫자는 비교용 사후 평가다.'),
        ('다음 단계 제안','국가별 성장 목표와 산업 활용 비율·상한, 준비 여부에 따라 바뀌는 수입 필요 분모를 함께 검토한다. 낮은 가격 자체의 벌점이나 ready_once 자동 채택은 제안하지 않는다.'),
    ]))
    add('<blockquote>“가격을 낮추면 물건이 더 잘 팔릴 수 있어요. 우리나라에 필요한 물건을 살 돈과 다음 생산에 쓸 원료도 남는지 살펴보세요. 수입한 기계가 어떤 발전에 쓰였는지도 확인해 보세요.”</blockquote>')
    add(table(['학습 의도','교실에서 확인할 행동'],[
        ('가격과 판매 결과 연결','판매 수량뿐 아니라 수입에 필요한 현금이 남았는지 설명하는가'),
        ('수입의 목적 이해','기계·원료 구입과 실제 개발·생산·생활을 연결하는가'),
        ('가격의 상대국 효과','싸게 산 나라의 이익과 경쟁 공급국의 변화를 함께 말하는가'),
        ('지속형 상품의 사용','같은 기계를 여러 번 쓴 효과와 새 기계를 여러 대 수입한 경우를 구별하는가'),
        ('평가와 행동 비교','무역에 도움이 된 행동과 전체 국가 운영 성과를 함께 평가하는가'),
    ]))
    p('낮은 가격을 선택했다는 사실만으로 학생의 의욕이나 학습 실패를 판단하지 않는다. 판매 이유와 다음 수입·생산 계획을 확인하는 관찰이 필요하다. 추천 수량·가격·부족한 준비물을 간단히 보여 주는 안내는 후속 학생 화면의 제안이다.')
    p('모든 실행은 규칙 기반 자동 국가다. 학생이 맡은 나라의 투자·가격·주력 선택은 학생의 선택으로 남겨야 한다. 학생이 새 점수를 보고 전략을 바꾸는 반응, 실제 3명 학생과 AI 6개국의 상호작용·협상·40분+40분 진행 속도·개별 접속 웹앱은 이번 계산으로 검증하지 않았다.')
    end()

    h(10,'실행·독립 감사·재현 범위')
    add(table(['항목','기록'],[
        ('본 비교','정상 + 기존 6개국의 반값/1G/무행동 = 19조건 × 200 = 3,800게임; 78000~78199'),
        ('추가 스트레스','20조건 × 30 = 600게임; 80000~80029'),('고유 경제 게임',f"{meta['completed_games']:,}"),
        ('사후 평가','같은 경제 궤적마다 4개 보기; 별도 경제 실행 아님'),('통과 테스트',f"{tests['test_count']:,}; 기존 298개 및 신규 검증"),
        ('불변식 호출',f"{meta['verification_calls']:,}; 보고된 실패 {meta['verification_failures']}"),
        ('본 비교 현금·원료 원장','각 307,800 국가·라운드 행'),('대표 상세 추적','19개 본 비교 + 20개 추가 조건 = 39게임'),
        ('계산 시간',f(meta['elapsed_seconds'])+'초; 교실 진행 시간이 아님'),('독립 감사',audit['status']),
        ('독립 감사 비교 횟수',f"{audit['checks_evaluated']:,}; 오류 {len(audit['errors'])}"),
    ]))
    p('예비·테스트 시드와 정식 시드를 분리했고, 코드·테스트·실행기 해시의 실행 전후 일치를 확인했다. 전체 게임의 내부 불변식과 저장 요약을 검사하며, 상세 이력의 독립 재구성은 대표 39게임의 범위다. 모든 게임의 모든 경로를 독립 재실행했다고 표현하지 않는다.')
    if supplemental is not None:
        p(f"위 정식 감사와 별도로, 기존 게임 한 건을 다시 계산해 같은 기계 중복 사례를 확인했다. 보충 감사 {supplemental['checks_evaluated']:,}회는 정식 {audit['checks_evaluated']:,}회와 합쳐 정식 표본 수를 늘리지 않는다.")
    add('<pre>python3 -m unittest test_previous test_fixes test_costs test_expansion test_budget test_machinery test_recommendation test_raw_resources test_development test_routing test_evaluation\npython3 run_evaluation_validation.py --n 200 --stress-n 30 --workers 4 --output-dir reproduced_evaluation_results\npython3 audit_evaluation_results.py --results reproduced_evaluation_results\npython3 build_evaluation_report.py --results reproduced_evaluation_results --report REPRODUCED_V11_KO.html</pre>')
    p('Python 표준 라이브러리로 계산하며 이번 실행 환경은 Python 3.12다. 기존 결과를 보존하도록 새 출력 폴더를 지정한다. 코드가 바뀌면 실제 테스트·시뮬레이션·감사를 다시 수행한다. 보고서 생성기는 완성된 정식 결과와 통과 기록만 읽고 예비 자료로 빈 부분을 메우지 않는다.')
    end()

    h(11,'국가별 행동·평가 상세 평균')
    for n in ORIGINAL:
        add('<details><summary>'+COUNTRIES[n]+' · 본 비교 200시드</summary>')
        cases=('None:normal',)+tuple(f'{n}:{s}' for s in ('cheap','minimum','idle'))
        add(table(['행동','현금','만족도','판매수입','투자','실사용 수출품','전체 재고']+list(VIEWS.values()),[
            (BEHAVIORS[case.split(':')[-1]],)+tuple(f(c(case,n,k)) for k in ('cash','happy','revenue','investment','useful_exports','stock'))+tuple(f(score(case,n,v)) for v in VIEWS) for case in cases]))
        add(table(['평가 보기','1G>자국 정상','정상 최고점','반값 최고점','1G 최고점','무행동 최고점'],[
            (VIEWS[v],higher(f'{n}:minimum',n,v))+tuple(highest(case,n,v) for case in cases) for v in VIEWS]))
        add('</details>')
    p('압축 파일에는 코드·테스트·전체 게임 요약·동일 시드 차이 통계·현금과 원료 원장·대표 추적·독립 감사·보고서 검사 기록이 들어 있다. 이 파일은 결과 검토용 정적 HTML이며 플레이 가능한 게임 화면이 아니다.')
    end()

    css='''*{box-sizing:border-box}body{margin:0;background:#eff3f6;color:#1d2d3d;font:16px/1.7 system-ui,sans-serif}main{max-width:1300px;margin:auto;padding:28px}header{background:#174456;color:#fff;border-radius:18px;padding:40px 44px}.eyebrow{font-size:14px;color:#b6dce6}h1{font-size:38px;line-height:1.25;margin:14px 0}header p{color:#dfedf1}.badge{display:inline-block;background:#2b6073;padding:7px 14px;border-radius:8px;font-size:14px}nav{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}nav a{background:white;color:#1a5065;text-decoration:none;border:1px solid #d5e0e6;border-radius:8px;padding:7px 12px}section{background:white;border:1px solid #dce5ea;border-radius:14px;padding:26px 30px;margin:22px 0}h2{font-size:25px;line-height:1.35;color:#164153;margin:0 0 18px}h3{font-size:19px;margin:24px 0 10px}.table-wrap{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid #dce5eb;padding:10px 12px;text-align:right;vertical-align:top;white-space:nowrap}th:first-child,td:first-child{text-align:left;min-width:130px;white-space:normal}.prose-table th,.prose-table td{text-align:left;white-space:normal;min-width:0}.prose-table th:first-child{width:24%}thead th{background:#eaf3f6;color:#17465a}tbody th{font-weight:500}tbody tr:nth-child(even){background:#f8fafc}table.two-columns th:first-child{width:28%}table.two-columns th:last-child,table.two-columns td:last-child{text-align:left;white-space:normal;min-width:0;overflow-wrap:anywhere}.note{border-left:3px solid #86aaba;padding-left:14px;color:#566d7d;font-size:14px}.callout{background:#edf6f8;border-left:4px solid #4a7e91;border-radius:8px;padding:18px 22px}blockquote{background:#f2f7ed;border-left:4px solid #77915b;padding:20px 24px;margin:20px 0;font-size:18px}details{border:1px solid #dce5eb;border-radius:8px;padding:14px 16px;margin:14px 0}summary{cursor:pointer;color:#22556a;font-weight:600}pre{background:#162e3c;color:#dfedf4;white-space:pre-wrap;word-break:break-word;font-size:13px;padding:18px;border-radius:8px}footer{color:#627786;font-size:13px;text-align:center;padding:20px}@media(max-width:700px){main{padding:12px}header{padding:26px 22px}h1{font-size:29px}section{padding:22px 16px}}@media print{body{background:white}main{padding:0;max-width:none}nav{display:none}section{border:0;padding:15px 0}.table-wrap{overflow:visible}th,td{white-space:normal;padding:5px}table{font-size:10px}pre{background:#eee;color:#111}}'''
    html='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>#11 무역 게임 v11 · 1G 판매와 평가 원장 검증</title><style>'+css+'</style></head><body><main>'+''.join(parts)+'<footer>#11 무역 게임 · v11 실제 최저 공개 가격과 개발용 기계 평가</footer></main></body></html>'
    report.write_text(html,encoding='utf-8')
    structure=check_structure(html,report,folder)
    return {'report':str(report),'bytes':report.stat().st_size,'tables':structure['tables'],'numeric_cells':structure['numeric_cells'],'games':len(rows),'sha256':structure['report_sha256']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=DEFAULT_RESULTS)
    p.add_argument('--report',type=Path,default=ROOT/'TRADE_PRICE_SCORE_REVIEW_V11_KO.html');a=p.parse_args()
    print(json.dumps(build(a.results.resolve(),a.report.resolve()),ensure_ascii=False))


if __name__=='__main__':main()
