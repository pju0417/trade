"""Korean v9 report from completed, audited saved results only.

No engine import, simulation execution, parameter search or pilot fallback.
The report does not certify classroom learning, fairness or final adoption.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from functools import lru_cache
import gzip
import hashlib
from html import escape
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS = ROOT / 'development_results'
COUNTRIES = {
    'Tropia':'트로피아', 'Grainia':'그레니아', 'Oilia':'오일리아',
    'Mechania':'메카니아', 'Mineria':'미네리아', 'Technia':'테크니아',
    'Novia':'노비아', 'Agrea':'아그레아', 'Ferria':'페리아',
}
ORIGINAL = tuple(COUNTRIES)[:6]
GOODS = {'banana':'바나나', 'wheat':'밀', 'ore':'광물', 'fuel':'연료', 'machine':'기계', 'electronics':'전자제품'}
MODES = {'baseline':'기존안', 'supply':'공급 분리', 'gate':'개발 조건', 'combined':'결합안'}
POLICIES = {'baseline':{'sale_buffer':False,'prior_machine':False},
            'supply':{'sale_buffer':True,'prior_machine':False},
            'gate':{'sale_buffer':False,'prior_machine':True},
            'combined':{'sale_buffer':True,'prior_machine':True}}
REFUSALS = (('Mechania','no_high_machine'),('Technia','no_high_machine'),('Novia','no_high_machine'),
            ('Technia','no_ore'),('Mechania','no_raw'))
SCENARIOS = tuple((n,s) for n in ORIGINAL for s in ('cheap','idle')) + ((None,'normal'),(None,'no_trade')) + REFUSALS
MAIN_SEEDS = range(60000,60200)
STRESS_SEEDS = range(62000,62030)
EXPECTED_GAMES = 3080


def need(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def read_lines(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def get(obj, path):
    for key in path.split('.'):
        obj = obj[key]
    return obj


def f(value, digits=2):
    return '—' if value is None else f'{value:,.{digits}f}'


def signed(value, digits=2):
    return f'{value:+,.{digits}f}'


def ci(values, digits=2):
    values = list(values)
    avg = statistics.mean(values)
    margin = 1.96 * statistics.stdev(values) / math.sqrt(len(values)) if len(values)>1 else 0
    return f'{signed(avg,digits)} [{signed(avg-margin,digits)}, {signed(avg+margin,digits)}]'


def table(headers, rows):
    out = '<div class="table-wrap"><table><thead><tr>' + ''.join('<th scope="col">'+escape(str(x))+'</th>' for x in headers) + '</tr></thead><tbody>'
    for row in rows:
        out += '<tr>' + ''.join(('<th scope="row">' if i==0 else '<td>') + escape(str(v)) + ('</th>' if i==0 else '</td>') for i,v in enumerate(row)) + '</tr>'
    return out + '</tbody></table></div>'


def load_completed(folder):
    names = ('pre_run_plan.json','summary.json','run_manifest.json','runs.jsonl.gz','round_ledgers.jsonl.gz',
             'raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz','tests_manifest.json','independent_audit.json')
    need(all((folder/n).is_file() for n in names), 'Formal results, tests and independent audit must be complete.')
    summary = read_json(folder/'summary.json')
    meta = read_json(folder/'run_manifest.json')
    need(summary['metadata']==meta, 'Summary and completed manifest differ.')
    need(meta['completed_games']==EXPECTED_GAMES and meta['main_games']==800 and meta['stress_games']==2280,
         'Report contract requires 3,080 formal games: 800 main plus 2,280 stress.')
    need(meta['main_seed_range']==[60000,60199] and meta['stress_seed_range']==[62000,62029], 'Formal seed bands differ.')
    need(meta['rounds']==9 and meta['countries']==9 and meta['source_unchanged'] is True and meta['pilot_excluded'] is True,
         'Nine-country, nine-round frozen-source execution required.')
    need(meta['modes']==POLICIES, 'The four development policies differ from the report contract.')
    tests = read_json(folder/'tests_manifest.json')
    need(tests['passed'] is True and tests['test_count']==meta['tests_completed'] and tests['test_count']>230,
         'Recorded inherited and new tests must pass.')
    need(hashlib.sha256((folder/'tests_manifest.json').read_bytes()).hexdigest()==meta['tests_manifest_sha256'],
         'Tests manifest hash differs from formal execution.')
    audit = read_json(folder/'independent_audit.json')
    need(audit['status']=='passed' and not audit['errors'] and not audit.get('warnings'), 'Independent audit must pass.')
    rows = read_lines(folder/'runs.jsonl.gz')
    expected = {('main',m,s,None,'normal') for m in MODES for s in MAIN_SEEDS}
    expected.update(('stress',m,s,n,style) for m in MODES for s in STRESS_SEEDS for n,style in SCENARIOS)
    keys = [(r['phase'],r['mode'],r['seed'],r['focal'],r['style']) for r in rows]
    need(len(keys)==len(set(keys))==EXPECTED_GAMES and set(keys)==expected, 'Saved rows do not cover the exact unique formal schedule.')
    groups = defaultdict(list)
    for row in rows:
        need(set(row['countries'])==set(COUNTRIES), 'Unexpected country set.')
        need(row['world']['development_policy']==POLICIES[row['mode']], 'Saved policy differs from its mode.')
        need(row['world']['raw_policy']=={'machine_credits':2,'starter':'two_cycles'}, 'All variants must retain the v8 bridge raw policy.')
        groups[(row['phase'],row['mode'],row['focal'],row['style'])].append(row)
    traces = read_json(folder/'first_seed_traces.json.gz')
    expected_traces = {':'.join(map(str,('main',m,60000,None,'normal'))) for m in MODES}
    expected_traces.update(':'.join(map(str,('stress',m,62000,n,s))) for m in MODES for n,s in REFUSALS)
    need(set(traces)==expected_traces and len(traces)==24, 'All 24 representative traces are required.')
    for filename in ('round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz'):
        ledgers = read_lines(folder/filename)
        need(len(ledgers)==800 and {(x['mode'],x['seed']) for x in ledgers}=={(m,s) for m in MODES for s in MAIN_SEEDS},
             'All 800 main games must have saved ledgers: '+filename)
        expected_cells = {(n,r) for n in COUNTRIES for r in range(1,10)}
        for group in ledgers:
            need(len(group['rows'])==81 and {(r['country'],r['round']) for r in group['rows']}==expected_cells,
                 'Incomplete country-round ledger: '+filename)
    return summary,meta,tests,audit,rows,groups,traces


def build(folder, report):
    summary,meta,tests,audit,rows,groups,traces = load_completed(folder)

    @lru_cache(maxsize=None)
    def mean(mode,path,phase='main',focal=None,style='normal'):
        return statistics.mean(get(r,path) for r in groups[(phase,mode,focal,style)])

    def c(mode,name,key): return mean(mode,'countries.'+name+'.'+key)
    def w(mode,key): return mean(mode,'world.'+key)
    def d(mode,key): return w(mode,'development.'+key)
    def values(mode,path,phase='main',focal=None,style='normal'):
        return {r['seed']:get(r,path) for r in groups[(phase,mode,focal,style)]}
    def diff(a,b,path,phase='main',focal=None,style='normal'):
        left=values(a,path,phase,focal,style);right=values(b,path,phase,focal,style)
        need(left.keys()==right.keys(), 'Unpaired seeds.')
        return [right[s]-left[s] for s in sorted(left)]
    def stressdiff(mode,name,style,path):
        left=values(mode,path,'stress');right=values(mode,path,'stress',name,style)
        need(left.keys()==right.keys(), 'Stress seeds do not match normal controls.')
        return [right[s]-left[s] for s in sorted(left)]
    def count_games(mode,path,phase='main',focal=None,style='normal'):
        vals=values(mode,path,phase,focal,style)
        return f'{sum(v>0 for v in vals.values())}/{len(vals)}'

    parts=[]
    def add(x):parts.append(x)
    def h(num,title):add(f'<section id="s{num}"><h2>{num}. {escape(title)}</h2>')
    def p(text,cls=''):add(f'<p class="{cls}">{escape(text)}</p>')
    def end():add('</section>')
    def metric_table(fields):
        add(table(['지표·단위']+[MODES[m] for m in MODES],[(label,)+tuple(f(w(m,key)) for m in MODES) for label,key in fields]))

    add('<header><div class="eyebrow">아이디어 노트 · #11 무역 게임 · 3단계 검증</div><h1>고급 기계의 거래가<br>기술 개발과 실제 사용으로 이어지는가</h1><p class="lead">9개국·9라운드 · 기존안과 공급·개발 조건의 2×2 비교 · 3,080회 실제 반복 계산</p><div class="status">실험 결과 보고서 · 최종 규칙 채택 및 교실 효과 확정 아님</div></header>')
    add('<nav aria-label="보고서 목차">'+''.join(f'<a href="#s{i}">{label}</a>' for i,label in ((1,'판단 범위'),(2,'비교 규칙'),(3,'전체 결과'),(4,'개발 연결'),(5,'국가별'),(6,'메카니아'),(7,'거부 실험'),(8,'플레이 전략'),(9,'점수'),(10,'학생 설명'),(11,'검증·재현'),(12,'세부 지표')) )+'</nav>')

    h(1,'이번 검증이 답하는 질문')
    p('지난 v8에서 후속 기준선 후보로 남긴 bridge를 모든 안에 적용했다. 시작 기술·주력 산업으로 첫 두 번 생산하는 데 필요한 원료를 지급하며, 기계 원료 1묶음당 작업 2칸을 유지한다. v9의 기존안은 v8 bridge와 같다. v8 보고서의 다른 시드 평균을 v9 평균과 직접 차감하지 않는다.')
    add('<div class="callout"><strong>검증 판단: 두 수정을 결합하면 거래와 개발의 연결은 작동한다. 기본안 확정은 보류한다.</strong>')
    p('결합안에서는 본 비교 '+count_games('combined','world.development.foreign_machine_used_output_upgrades')+'게임에서 외국산 기계 사용 → 개발 → 정상 생산 → 생산품의 실제 사용이 관측됐다. 공급만 늘리거나 개발 조건만 바꾸는 안에서는 이 연결이 없었다. 메카니아의 종료 현금은 기존 '+f(c('baseline','Mechania','cash'))+'G에서 결합안 '+f(c('combined','Mechania','cash'))+'G로 높아졌다.')
    p('다만 메카니아가 무행동이면 현재 컴퓨터 운영에서 테크니아·노비아의 G3 도달이 모두 0/30으로 떨어진다. 결합안의 메카니아는 '+count_games('combined','countries.Mechania.production_failures')+'게임에서 원료 부족에 따른 기본 생산이 있었고, 세계 전체의 고급 기계 미사용 종료 재고는 평균 '+f(d('combined','high_machine_unused_stock'))+'대 남았다. 공급국 의존, 생산 원료 준비, 평가식은 계속 수정해야 한다.')
    add('</div>')
    add('<div class="callout"><strong>기존 구조의 두 연결 문제</strong><ol><li>3세대 상품은 산업 3단계에서 만들지만, 2세대 기계 사용은 산업 4단계 진입에서만 요구했다.</li><li>메카니아가 처음 만든 고급 기계 1대를 자국 지원용으로 보유하면, 판매 이력 0과 재고 목표 1이 맞물려 판매할 다음 기계가 생기지 않을 수 있었다.</li></ol></div>')
    p('따라서 공급을 열어 주는 수정과 실제 개발 수요를 만드는 수정을 나누어 비교했다. 거래량의 증가만으로 성공이라 하지 않고, 거래된 기계가 연구에 쓰였는지, 이후 정상 생산이 있었는지, 그 상품이 실제로 사용됐는지를 확인한다.')
    p('공급·개발 조건은 시험 중인 후보다. 현재 결과는 컴퓨터 국가의 경제 모형이며 학생의 이해, 참여, 협상 경험, 40분+40분 수업 속도를 검증한 것이 아니다. 추가 3개국의 목표가 보정되지 않아 9개국 종합 순위를 만들지 않는다.','note')
    end()

    h(2,'유지한 규칙과 비교한 두 가지 변경')
    add(table(['안','고급 기계 재고 계획','3세대 내구재 개발 조건'],[
        ('기존안','기존 판매 목표에서 전체 적격 재고를 뺌','기존: 산업 3단계 진입에 광물, 4단계에 G2 기계'),
        ('공급 분리','G2·G3에서 국내 지원용 1자리와 기존 판매 목표를 분리','기존 조건 그대로'),
        ('개발 조건','기존 재고 계획 그대로','기계·전자제품 산업 3단계 진입에 G2 이상 1대 사용'),
        ('결합안','공급 분리 적용','개발 조건 적용'),
    ]))
    p('공급 분리의 실제 생산 목표는 기존 1 + 최근 두 라운드 같은 세대 자국 기계 판매 평균의 올림 + 현재 국내 지원 자리(0 또는 1)이다. 적격 보유 재고를 빼고 생산 능력 안에서만 만든다. 미래 생산 원료를 준비할 때는 주력 변경 가능성에 대비해 비내구재 산업이 있으면 지원 자리 1을 예약한다. G1 기계의 규칙은 바꾸지 않는다.')
    p('공개 판매 중인 기계, 사용한 기계, 수입한 적격 기계도 보유량에 포함한다. 보유 재고가 목표를 채우면 추가 생산을 멈춘다. 다만 최근 판매에 따른 보충 목표가 남아 있어, 수요가 끝난 뒤 미판매 재고가 항상 1대 이하라는 보장은 없다. 공급 분리는 보조금·무료 구매자·강제 구매를 추가하지 않는다.')
    add(table(['항목','모든 안에서 유지'],[
        ('국가·시간','9개국, 9라운드, 기존 시작 현금·산업·주력·확장 경로'),
        ('원료·가격','v8 bridge 초기 원료, 기존 생산·연구 광물량, 기계 원료 작업 2칸, 기준가·자유 판매·가격 추천'),
        ('기계 사용','설비 재사용, 구형 성능 100%·80%·60%, 기존 생산 능력·원료비'),
        ('개발','산업 2단계는 현금 중심, 기존 연구비·광물량 유지; 실험안만 내구재 3단계에 G2 조건 추가'),
        ('자동 판단','생활 우선 구매, 생활 물량·다음 생산 원료를 확인하는 기존 투자 정책, v7 price 판단'),
        ('거래·평가','현금·물물교환, 같은 점수식; 경제력·산업 점수는 기존 6개국만 비교'),
    ]))
    p('기계는 연구에 사용해도 없어지지 않는다. 같은 적격 기계를 이후 연구나 산업 지원에 다시 사용할 수 있고, 자국 생산 기계도 조건을 충족한다. 특정 나라에서 반드시 수입하도록 만드는 조건은 아니다. 개발 성공 뒤의 생산은 다음 라운드부터이며, 실제 가동 원료도 필요하다.')
    end()

    h(3,'전체 결과: 거래·재고·생활을 함께 보기')
    metric_table([
        ('고급 기계 신규 생산(대)','development.high_machine_produced'),
        ('고급 기계 국경 거래(대, 재거래 포함)','development.bought_high_machines'),
        ('고급 기계 실사용 수출품(고유 실물)','development.high_machine_useful_exports'),
        ('고급 기계 종료 미사용 재고(대)','development.high_machine_unused_stock'),
        ('외국산 기계를 사용한 개발(건)','development.foreign_machine_upgrades'),
        ('후속 상품 사용까지 이어진 개발(건)','development.foreign_machine_used_output_upgrades'),
        ('G3 전자제품 생산(개)','development.g3_electronics_output'),
        ('G3 전자제품 실제 사용(고유 실물)','development.g3_electronics_used'),
        ('G3 기계 생산(대)','development.g3_machine_output'),
        ('G3 기계 실제 사용(고유 실물)','development.g3_machine_used'),
        ('전체 평균 만족도(점)','happy'),
        ('전체 종료 재고(개)','inventory'),
        ('2라운드 이상 지난 미사용 재고(개)','aged_unused'),
        ('9개국 최대·최소 종료 현금 격차(G)','all_country_cash_gap'),
    ])
    p('표는 각 안의 본 비교 200게임 평균이다. 사용은 자국 사용과 외국 사용을 포함하며, 실사용 수출품은 게임 중 생산되어 외국에서 실제 사용된 고유 상품이다. 거래량은 국경 이동 누계이므로 같은 실물이 다시 거래되면 늘 수 있다.')
    p('결합안은 기존안보다 평균 만족도가 높지만 전체 재고도 늘었다. 9개국 현금 격차의 차이 구간은 0을 포함한다. 고급 기계의 경제 연결이 생긴 사실과 재고·공정성이 해결됐다는 판단은 별개다. G3 기계는 네 가지 안 모두 이번 본 비교에서 생산되지 않아, 모든 기계 세대의 진보가 활성화된 것은 아니다.')
    add('<h3>같은 시드에서 기존안 → 결합안의 차이</h3>')
    fields=[('고급 기계 거래(대)','world.development.bought_high_machines'),('기계 실사용 수출품(개)','world.development.high_machine_useful_exports'),('외국산 기계 개발 후 사용 연결(건)','world.development.foreign_machine_used_output_upgrades'),('만족도(점)','world.happy'),('종료 재고(개)','world.inventory'),('9개국 현금 격차(G)','world.all_country_cash_gap'),('메카니아 종료 현금(G)','countries.Mechania.cash'),('메카니아 만족도(점)','countries.Mechania.happy')]
    add(table(['지표','평균 차이 [95% 구간]'],[(label,ci(diff('baseline','combined',path))) for label,path in fields]))
    p('95% 구간은 동일한 시드에서 계산한 차이에 평균 ± 1.96 × 표준오차를 적용한 탐색적 구간이다. 구간에 0이 들어가면 해당 지표의 개선을 단정하지 않는다. 여러 지표를 비교하는 게임 설계 진단이며, 학생 모집단이나 실제 경제를 대표하는 통계가 아니다.','note')
    end()

    h(4,'구매 → 개발 → 정상 생산 → 실제 사용')
    flow=[('고급 기계 수입이 한 번 이상 있었던 게임','world.development.bought_high_machines'),('외국산 기계를 연구에 쓴 게임','world.development.foreign_machine_upgrades'),('연구 뒤 정상 생산이 있었던 게임','world.development.foreign_machine_productive_upgrades'),('후속 생산품 사용까지 있었던 게임','world.development.foreign_machine_used_output_upgrades')]
    add(table(['관측한 연결']+[MODES[m] for m in MODES],[(label,)+tuple(count_games(m,path) for m in MODES) for label,path in flow]))
    metric_table([
        ('외국산 기계 연구 사용(개발 건)','development.foreign_machine_upgrades'),
        ('연구에 사용한 외국산 기계(국가별 고유 실물 수의 합)','development.unique_foreign_machines_development'),
        ('정상 생산이 뒤따른 개발(건)','development.foreign_machine_productive_upgrades'),
        ('상품 사용까지 이어진 개발(건)','development.foreign_machine_used_output_upgrades'),
        ('해당 개발 이후 정상 생산품(고유 실물)','development.foreign_machine_output_units'),
        ('그중 실제 사용된 상품(고유 실물)','development.foreign_machine_output_used_units'),
        ('그중 외국에서 사용된 상품(고유 실물)','development.foreign_machine_export_used_units'),
    ])
    p('생산 묶음은 같은 나라·같은 산업의 가장 최근 개발 1건에만 연결한다. 다음 개발이 일어나면 이전 개발의 관찰 구간을 끝내고, 같은 생산품을 두 개발에 중복 계산하지 않는다. 원료 부족으로 기본 상품만 만든 경우는 정상 생산 연결에서 제외한다. 정상 가동이어도 실제 생산량이 0이면 생산 성공 연결로 세지 않는다.')
    p('이 수치는 시간순 연결의 증거다. “기계 한 대가 이 상품을 전부 추가로 만들었다”는 인과적 순증 생산량은 아니다. 기존 생산 능력과 이후 선택이 섞여 있다. 한 기계를 여러 개발에 재사용하면 개발 건수는 늘지만 고유 기계 수는 늘지 않는다. 나라별 고유 수의 세계 합계는 실물이 여러 나라로 옮겨 가면 세계 전체 고유 수와 다를 수 있다.','note')
    p('결합안에서 외국산 기계를 쓴 개발 이후의 정상 생산품은 평균 '+f(d('combined','foreign_machine_output_units'))+'개, 그중 실제 사용품은 '+f(d('combined','foreign_machine_output_used_units'))+'개, 외국에서 사용된 상품은 '+f(d('combined','foreign_machine_export_used_units'))+'개다. 따라서 연결 성공 200/200이 후속 상품 전체의 판매·사용 성공을 뜻하지 않는다.')
    add('<h3>첫 정식 시드의 실제 기록: 결합안 60000</h3>')
    sample=traces['main:combined:60000:None:normal'];sample_rows=[]
    for event in sample['development_chains']:
        if not event['foreign_machine']:continue
        tx=sample['transactions'][event['machine']['import_transaction']]
        seller=next(leg['seller'] for leg in tx['legs'] if event['machine']['uid'] in leg['ids'])
        sample_rows.append((COUNTRIES[event['country']],f"{tx['round']}라운드 · {COUNTRIES[seller]}",f(tx['cash'][2],0)+'G' if tx['cash'] else '물물교환',f"{event['round']}라운드 · {GOODS[event['industry']]} {event['to_level']}단계",len(event['output_ids']),len(event['used_output_ids']),len(event['foreign_used_output_ids'])))
    add(table(['구매국','G2 이상 기계 수입','거래 금액','연결된 개발','이후 정상 생산품','실제 사용품','외국 사용품'],sample_rows))
    p('위 두 개발 이후의 정상 생산품은 각각 관찰 구간의 전체 생산량이다. 표시한 기계 거래 금액에는 별도로 지출한 연구비·광물 비용이 포함되지 않는다. 첫 시드를 보여 준 사례이며 전체 평균을 대신하지 않는다.')
    end()

    h(5,'국가별 생활·경제 변화')
    add(table(['국가','현금 기존→결합(G)','만족도 기존→결합','판매수입 기존→결합(G)','투자 기존→결합(G)','실사용 수출품 기존→결합'],[
        (COUNTRIES[n],f"{f(c('baseline',n,'cash'))} → {f(c('combined',n,'cash'))}",f"{f(c('baseline',n,'happy'))} → {f(c('combined',n,'happy'))}",f"{f(c('baseline',n,'revenue'))} → {f(c('combined',n,'revenue'))}",f"{f(c('baseline',n,'investment'))} → {f(c('combined',n,'investment'))}",f"{f(c('baseline',n,'useful_exports'))} → {f(c('combined',n,'useful_exports'))}") for n in COUNTRIES]))
    add('<h3>개발과 실제 사용의 국가별 위치</h3>')
    add(table(['국가','결합안 고급 기계 수입(대)','외국산 기계 개발(건)','후속 사용 연결(건)','G3 전자제품 도달 게임','G3 기계 도달 게임'],[
        (COUNTRIES[n],f(c('combined',n,'development.bought_high_machines')),f(c('combined',n,'development.foreign_machine_upgrades')),f(c('combined',n,'development.foreign_machine_used_output_upgrades')),count_games('combined',f'countries.{n}.electronics_g3'),count_games('combined',f'countries.{n}.machine_g3')) for n in COUNTRIES]))
    p('소득이 낮아진 나라와 늘어난 나라를 함께 본다. 종료 현금만 높아져도 투자를 포기한 결과일 수 있다. 전체 실사용 수출품에는 각 나라의 모든 품목이 포함되므로 메카니아의 기계 실적과 따로 확인한다.')
    p('특히 광물 전체 거래가 늘었다고 광물 생산국 모두가 이익을 얻었다고 말할 수 없다. 미네리아의 종료 현금은 '+f(c('baseline','Mineria','cash'))+'G → '+f(c('combined','Mineria','cash'))+'G이며, 같은 시드 차이는 '+ci(diff('baseline','combined','countries.Mineria.cash'))+'G다. 판매수입과 투자 변화도 함께 살펴야 한다.')
    end()

    h(6,'메카니아의 새 기계는 팔리고 사용되는가')
    fields=[('고급 기계 생산(대)','development.high_machine_produced'),('고급 기계 공개 판매에 내놓은 고유 실물','development.high_machine_public_unique'),('고급 기계 수출(대)','development.sold_high_machines'),('고급 기계 판매 현금(G)','development.high_machine_sales_cash'),('고급 기계 실사용 수출품','development.high_machine_useful_exports'),('고급 기계 미사용 종료 재고','development.high_machine_unused_stock'),('광물 수입량(묶음)','import_goods.ore'),('광물 구입 지출(G)','purchase_by_good.ore'),('전체 투자(G)','investment'),('종료 현금(G)','cash'),('평균 만족도','happy'),('기존 종합 점수','score')]
    add(table(['메카니아 지표']+[MODES[m] for m in MODES],[(label,)+tuple(f(c(m,'Mechania',key)) for m in MODES) for label,key in fields]))
    p('고급 기계 판매 현금은 현금 거래만 포함한다. 물물교환은 거래 수량에는 포함되지만 임의의 현금 매출로 바꾸지 않는다. 광물 지출은 연구와 생산에 쓰일 수 있고, 기계가 아닌 산업에도 영향을 받을 수 있으므로 이 두 금액의 단순 차이를 기계 순이익이라고 부르지 않는다.')
    add('<h3>전자제품 생산국의 반응</h3>')
    add(table(['국가·안','고급 기계 수입','기계 이용 개발','G3 도달 게임','G3 생산','G3 실제 사용','종료 현금'],[
        (COUNTRIES[n]+' · '+MODES[m],f(c(m,n,'development.bought_high_machines')),f(c(m,n,'development.foreign_machine_upgrades')),count_games(m,f'countries.{n}.electronics_g3'),f(c(m,n,'development.g3_electronics_output')),f(c(m,n,'development.g3_electronics_used')),f(c(m,n,'cash'))) for n in ('Technia','Novia') for m in MODES]))
    end()

    h(7,'기계를 사지 않으면 무엇이 달라지는가')
    p('no_high_machine은 지정 국가만 G2 이상 기계 수입을 거부하는 진단이다. 현금 거래와 물물교환 모두 거부하며, G1 수입·기계 수출·다른 국가의 거래·자국 고급 기계 생산은 허용한다. 따라서 “기계 없이 플레이” 또는 “무역 전체 금지”가 아니다.')
    add(table(['안·거부 국가','G3 전자제품 도달 정상→거부','투자 차이(G)','만족도 차이','점수 차이','기계 조건 미충족 관측(건)'],[
        (MODES[m]+' · '+COUNTRIES[n],count_games(m,f'countries.{n}.electronics_g3','stress')+' → '+count_games(m,f'countries.{n}.electronics_g3','stress',n,'no_high_machine'),ci(stressdiff(m,n,'no_high_machine',f'countries.{n}.investment')),ci(stressdiff(m,n,'no_high_machine',f'countries.{n}.happy')),ci(stressdiff(m,n,'no_high_machine',f'countries.{n}.score')) if n in ORIGINAL else '추가국 점수 없음',f(mean(m,f'countries.{n}.development.machine_condition_blocks','stress',n,'no_high_machine'))) for m in MODES for n in ('Technia','Novia')]))
    p('기계 조건 미충족 관측은 투자하지 못한 시점에 필요한 기계가 없었던 경우다. 현금·생활 물량·다음 생산 원료 부족이 동시에 있을 수 있으므로 이 횟수를 모두 기계 하나만의 원인으로 해석하지 않는다. 메카니아는 자국 기계를 쓸 수 있어 수입 거부 효과가 전자제품 국가와 다를 수 있다.')
    p('개발 조건만 적용한 gate에서 현금과 만족도가 높아져도 발전 성공으로 보지 않는다. 실제로 테크니아·노비아의 G3 진행이 멈췄다. 투자비 지출이 줄고 최고 세대의 출시가 멈추면서 기존 제품의 구형 판정에도 영향이 생기므로, 현금·만족도 상승만으로 학습 설계가 좋아졌다고 결론 내릴 수 없다.')
    add('<details><summary>메카니아 기계 거부와 원료 거부 결과</summary>')
    add(table(['안·국가·거부','현금 차이','투자 차이','만족도 차이','생산 원료 부족 횟수 차이','기계 이용 개발 차이'],[
        (MODES[m]+' · '+COUNTRIES[n]+' · '+{'no_high_machine':'G2 이상 기계','no_ore':'광물','no_raw':'광물·연료'}[s],ci(stressdiff(m,n,s,f'countries.{n}.cash')),ci(stressdiff(m,n,s,f'countries.{n}.investment')),ci(stressdiff(m,n,s,f'countries.{n}.happy')),ci(stressdiff(m,n,s,f'countries.{n}.production_failures')),ci(stressdiff(m,n,s,f'countries.{n}.development.foreign_machine_upgrades'))) for m in MODES for n,s in (('Mechania','no_high_machine'),('Technia','no_ore'),('Mechania','no_raw'))]))
    add('</details>')
    end()

    h(8,'반값 판매·무행동·전체 무역 금지')
    p('반값 판매(cheap)는 공개 판매가를 기준 가격의 50%로 정하고 구매·투자는 계속하는 자동 전략이다. 가능한 모든 합법적 최저가를 탐색하는 전략은 아니다. 무행동(idle)은 거래와 투자를 하지 않지만 자동 생산과 만족도 연계 운영수입은 유지한다. 각 조건의 정상 운영과 같은 30개 시드에서 비교했다.')
    add(table(['반값 판매 국가','기존안 점수 차이','결합안 점수 차이','결합안 판매수입 차이(G)','결합안 투자 차이(G)','결합안 실사용 수출품 차이'],[
        (COUNTRIES[n],ci(stressdiff('baseline',n,'cheap',f'countries.{n}.score')),ci(stressdiff('combined',n,'cheap',f'countries.{n}.score')),ci(stressdiff('combined',n,'cheap',f'countries.{n}.revenue')),ci(stressdiff('combined',n,'cheap',f'countries.{n}.investment')),ci(stressdiff('combined',n,'cheap',f'countries.{n}.useful_exports'))) for n in ORIGINAL]))
    add(table(['무행동 국가','결합안 점수 차이','결합안 현금 차이(G)','결합안 만족도 차이','결합안 투자 차이(G)','결합안 실사용 수출품 차이'],[
        (COUNTRIES[n],ci(stressdiff('combined',n,'idle',f'countries.{n}.score')),ci(stressdiff('combined',n,'idle',f'countries.{n}.cash')),ci(stressdiff('combined',n,'idle',f'countries.{n}.happy')),ci(stressdiff('combined',n,'idle',f'countries.{n}.investment')),ci(stressdiff('combined',n,'idle',f'countries.{n}.useful_exports'))) for n in ORIGINAL]))
    add('<h3>메카니아가 참여하지 않을 때 다른 나라의 발전</h3>')
    add(table(['안','고급 기계 거래 정상→메카니아 무행동','테크니아 G3 도달 게임 정상→무행동','노비아 G3 도달 게임 정상→무행동','전체 만족도 차이'],[
        (MODES[m],f(mean(m,'world.development.bought_high_machines','stress'))+' → '+f(mean(m,'world.development.bought_high_machines','stress','Mechania','idle')),count_games(m,'countries.Technia.electronics_g3','stress')+' → '+count_games(m,'countries.Technia.electronics_g3','stress','Mechania','idle'),count_games(m,'countries.Novia.electronics_g3','stress')+' → '+count_games(m,'countries.Novia.electronics_g3','stress','Mechania','idle'),ci(stressdiff(m,'Mechania','idle','world.happy'))) for m in MODES]))
    p('이 비교는 한 학생의 무행동이 상대 학생의 고급 발전 기회를 막는지도 확인한다. 자국 기계 생산이 규칙상 가능하더라도, 현재 자동 투자 판단이 실제로 그 대안을 선택하는지는 별개다. 무역의 필요성을 만드는 것과 한 공급국의 참여에 지나치게 의존하게 만드는 것을 구별해야 한다.')
    add(table(['전체 무역 금지','평균 만족도 정상→금지','종료 현금 총계 정상→금지','전체 투자 정상→금지','외국산 기계 연구 사용 정상→금지'],[
        (MODES[m],f(mean(m,'world.happy','stress'))+' → '+f(mean(m,'world.happy','stress',None,'no_trade')),f(mean(m,'world.cash_total','stress'))+' → '+f(mean(m,'world.cash_total','stress',None,'no_trade')),f(mean(m,'world.investment','stress'))+' → '+f(mean(m,'world.investment','stress',None,'no_trade')),f(mean(m,'world.development.foreign_machine_upgrades','stress'))+' → '+f(mean(m,'world.development.foreign_machine_upgrades','stress',None,'no_trade'))) for m in MODES]))
    p('낮은 가격이 더 많은 실사용을 가능하게 만들 수는 있지만 판매수입·투자·세대 발전이 낮아져도 점수가 오르는지 별도로 살펴야 한다. 반대로 무행동에서 현금이 남는 사실만으로 경제 전략이 더 우수하다고 판단하지 않는다.')
    end()

    h(9,'점수는 실제 발전을 얼마나 반영하는가')
    p('이번 단계에서는 점수식을 바꾸지 않았다. 경제력 25점·만족도 25점·무역 25점·산업 발전 25점의 기존 구조와 국가별 성장 목표를 유지하며, 추가 3개국에는 경제력·산업·종합 점수가 없다.')
    add(table(['기존 6개국','종합 기존→결합','경제력 기존→결합','생산 능력 점수 기존→결합','활용 점수 기존→결합','무역 점수 기존→결합'],[
        (COUNTRIES[n],)+tuple(f(c('baseline',n,k))+' → '+f(c('combined',n,k)) for k in ('score','economic','industry_capacity_score','industry_use_score','trade')) for n in ORIGINAL]))
    add('<h3>테크니아 반값 판매: 점수와 실제 경제를 나란히</h3>')
    keys=[('종합 점수','score'),('경제력 점수','economic'),('생산 능력 점수','industry_capacity_score'),('활용 점수','industry_use_score'),('무역 점수','trade'),('판매수입(G)','revenue'),('투자(G)','investment'),('종료 현금(G)','cash'),('전자제품 세대','elec_gen'),('실제 사용된 자국 생산품 전체','all_goods_unique_used'),('G3 전자제품 실제 사용','development.g3_electronics_used')]
    add(table(['테크니아 반값 판매 지표']+[MODES[m] for m in MODES],[(label,)+tuple(ci(stressdiff(m,'Technia','cheap','countries.Technia.'+key)) for m in MODES) for label,key in keys]))
    prod_rows=[]
    for m in MODES:
        normal=groups[('stress',m,None,'normal')];cheap=groups[('stress',m,'Technia','cheap')]
        made=lambda rr:statistics.mean(sum(r['countries']['Technia']['produced'].values()) for r in rr)
        used=lambda rr:statistics.mean(r['countries']['Technia']['all_goods_unique_used'] for r in rr)
        prod_rows.append((MODES[m],f(made(normal))+' → '+f(made(cheap)),f(used(normal))+' → '+f(used(cheap))))
    add(table(['테크니아 정상→반값 판매','자국 생산품 총수(분모)','그중 실제 사용된 고유 실물(분자)'],prod_rows))
    p('현재 산업 활용 10점은 실제 사용된 자국 생산품 수 ÷ 전체 자국 생산품 수에 비례한다. 생산량 감소가 분모를 줄여 점수를 높일 수 있다. 생산 능력·경제력 점수가 이미 상한에 닿은 경우, 투자와 발전이 줄어도 해당 점수가 거의 떨어지지 않을 수 있다. 이 때문에 기술 조건 수정만으로 평가 공정성이 해결됐다고 선언하지 않는다.')
    p('테크니아의 반값 판매에는 실제 사용량이 늘어나는 효과도 함께 나타났다. 따라서 점수 상승을 전부 분모 효과라고 단정하지 않는다. 그 대신 판매수입·투자·기술 세대가 낮아지는 결과와 실사용 증가가 현재 점수에서 어떤 비중으로 평가되는지 다시 정해야 한다.')
    p('또한 기존 점수 원장에서는 개발에 사용한 기계를 실사용으로 기록하지만, 개발용 기계의 필요량·외부 충족량을 별도 수요 행으로 기록하지 않는다. 이 사용은 실사용 수출·교역 상대 등의 일부 지표에는 반영될 수 있어도, 수입 필요 충족률의 분모·분자에 개발 수요로 직접 들어가지 않는다. 개발용 광물 소비는 수요로 기록된다. 이 비대칭도 후속 점수 수정에서 다룰 항목이다.')
    p('후속 점수 개선에서는 같은 거래·생산 궤적에 대안 점수를 사후 적용해 비교하는 것이 적절하다. 실제 사용의 절대량·달성 가능한 국가별 목표·개발 이후 이용을 함께 살피되, 한 기계를 여러 번 사용하는 정상 행동을 중복 수입 점수로 바꾸지 않아야 한다. 이 보고서의 연결 지표는 진단용이며 새로운 가산점 규칙이 아니다.','note')
    end()

    h(10,'학생에게 보일 설명과 교실에서 확인할 것')
    add('<blockquote>“3세대 전자제품을 개발하려면 연구비와 광물, 2세대 이상 기계 1대가 필요해요. 기계는 연구 뒤에도 남아서 다시 쓸 수 있어요. 개발에 성공하면 다음 라운드부터 새 상품을 만들 수 있어요.”</blockquote>')
    p('위 문구는 개발 조건 실험안의 설명 예시다. 개발 버튼 옆에는 지금 부족한 현금·광물·기계를 보여 주고, 다음 생산에 쓸 원료도 확인하도록 안내할 수 있다. 내부 재고 목표식이나 통계는 학생에게 규칙으로 외우게 하지 않는다.')
    add(table(['학습 의도','게임에서 관찰할 행동','아직 필요한 교실 확인'],[
        ('수입의 목적 이해','기계를 구매하고 어떤 개발에 썼는지 연결해 말함','“싸서 샀다”와 “개발에 필요해 샀다”를 구별해 설명하는가'),
        ('수출의 가치 이해','판매한 기계가 상대 국가에서 실제 사용됨','판매 가격·수량을 비교하고 그 이유를 말하는가'),
        ('상호 의존 이해','광물·기계·전자제품의 거래가 이어짐','국가별 차이 때문에 서로 교환한다는 점을 발견하는가'),
        ('지속형 상품 이해','기계가 사라지지 않고 다음 활동에 재사용됨','매 라운드 새 기계를 사야 한다고 오해하지 않는가'),
        ('의욕이 낮은 학생의 참여','추천 수량·가격을 선택해도 거래 이유가 보임','반복 클릭만으로 진행하는 학생이 최소 한 번 선택 이유를 말하는가'),
    ]))
    p('3명의 학생에게는 한 사람당 한 국가를 맡기고 나머지는 컴퓨터 국가로 운영하는 기존 방향을 유지한다. 실제 화면에서는 “이번에 필요한 물건”, “판매할 물건”, “다음 발전”을 간단히 보여 주는 것이 후속 시제품의 확인 과제다. 이 계산만으로 학습 효과나 협상 소요 시간을 입증하지 않는다.')
    end()

    h(11,'검증 범위와 재현')
    add(table(['항목','실제 기록'],[
        ('본 비교','4안 × 200시드 = 800게임, 시드 60000~60199'),
        ('스트레스','4안 × 19조건 × 30시드 = 2,280게임, 시드 62000~62029'),
        ('합계',f"{meta['completed_games']:,}게임"),
        ('자동 테스트',f"{tests['test_count']:,}개 통과; 기존 230개와 v9 추가 검증"),
        ('상태 불변식 호출',f"{meta['verification_calls']:,}회, 보고된 실패 {meta['verification_failures']}건"),
        ('현금 원장','본 비교 800게임 × 9개국 × 9라운드 = 64,800행'),
        ('원료 원장','본 비교 64,800행'),
        ('대표 상세 추적','첫 본 비교 4개 + 거부 조건 20개 = 24게임'),
        ('계산 시간',f"{f(meta['elapsed_seconds'])}초; 실행기 기록이며 교실 진행 시간이 아님"),
        ('독립 감사',str(audit['status'])),
    ]))
    p('정식 시드는 후보를 탐색한 예비 실행 및 단위 테스트 시드와 분리했다. 게임 규칙·실행기·테스트를 고정한 뒤 실행했고 완료 전후 해시를 비교했다. 보고서 생성기는 완성된 결과와 감사 통과 기록만 읽으며 게임을 다시 실행하거나 예비 결과로 누락을 채우지 않는다.')
    p('전체 게임에는 현금·물품·소유권·판매 등록·원료 작업량·개발 조건·생산 연결의 내부 검사를 적용한다. 저장된 상세 이력을 별도로 재구성하는 독립 검사는 24개 대표 게임 범위를 포함하므로, 모든 게임의 모든 상세 경로를 독립 재실행했다고 표현하지 않는다.')
    add('<pre>python3 -m unittest test_previous test_fixes test_costs test_expansion test_budget test_machinery test_recommendation test_raw_resources test_development\npython3 run_development_validation.py --n 200 --stress-n 30 --workers 4 --output-dir reproduced_development_results\npython3 audit_development_results.py --results reproduced_development_results\npython3 build_development_report.py --results reproduced_development_results --report REPRODUCED_V9_KO.html</pre>')
    p('Python 표준 라이브러리를 사용하며 이번 실행 환경은 Python 3.12다. 기존 결과를 보존하도록 새 출력 폴더를 지정한다. 코드를 수정했다면 이전 검증 기록을 그대로 사용하지 않고 실제 테스트와 결과를 다시 계산해야 한다.')
    end()

    h(12,'네 가지 안의 국가별 세부 지표')
    p('세부 표는 검토용이다. 수입·수출은 상품 수, 현금·판매수입·투자는 G, 만족도·종합은 점이다. 추가국 종합 점수는 “—”로 둔다. 모든 표는 정식 본 비교 평균이다.')
    for mode in MODES:
        add('<details><summary>'+MODES[mode]+' · 9개국 전체</summary>')
        add(table(['국가','현금','만족도','판매수입','투자','실사용 수출품','전체 재고','고급 기계 수입','G3 전자 생산','G3 전자 사용','종합'],[
            (COUNTRIES[n],)+tuple(f(c(mode,n,k)) for k in ('cash','happy','revenue','investment','useful_exports','stock','development.bought_high_machines','development.g3_electronics_output','development.g3_electronics_used'))+(f(c(mode,n,'score')) if n in ORIGINAL else '—',) for n in COUNTRIES]))
        add('</details>')
    p('함께 제공한 압축 파일에는 재현 코드, 테스트, 전체 게임 요약, 같은 시드 차이 통계, 현금·원료 원장, 대표 상세 추적, 독립 감사 결과가 들어 있다. 이 HTML은 정적 결과 보고서이며 학생이 접속해 게임을 플레이하는 웹앱이 아니다.')
    end()

    css='''*{box-sizing:border-box}body{margin:0;background:#eef2f6;color:#182538;font:16px/1.7 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1240px;margin:auto;padding:28px}header{background:#123747;color:#fff;border-radius:20px;padding:42px 44px;margin-bottom:24px}.eyebrow{font-size:14px;letter-spacing:.05em;color:#bce2e4}h1{font-size:38px;line-height:1.25;margin:14px 0 18px}header p{color:#dbeaed}.status{display:inline-block;background:#235267;border:1px solid #568092;padding:8px 14px;border-radius:8px;font-size:14px}nav{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0 28px}nav a{background:white;color:#125268;text-decoration:none;padding:7px 12px;border-radius:8px;border:1px solid #d8e1e8}section{background:white;border:1px solid #dbe3e9;border-radius:16px;padding:26px 30px;margin:20px 0}h2{font-size:25px;line-height:1.35;margin:0 0 18px;color:#123747}h3{font-size:19px;margin:24px 0 10px}.table-wrap{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{padding:10px 12px;border-bottom:1px solid #dce4eb;text-align:right;vertical-align:top;white-space:nowrap}th:first-child,td:first-child{text-align:left;white-space:normal;min-width:140px}thead th{background:#eaf2f5;color:#163d4f}tbody th{font-weight:500}tbody tr:nth-child(even){background:#f8fafc}.note{font-size:14px;color:#526375;border-left:3px solid #8caebd;padding-left:14px}.callout{background:#edf6f8;padding:20px 24px;border-radius:10px}ol{padding-left:22px}li{margin:9px 0}blockquote{margin:18px 0;background:#f2f6ed;border-left:4px solid #71894e;padding:20px 24px;font-size:19px}details{border:1px solid #dce4eb;border-radius:8px;padding:14px 16px;margin:14px 0}summary{cursor:pointer;font-weight:600;color:#285266}pre{white-space:pre-wrap;word-break:break-word;background:#142532;color:#deecf3;border-radius:8px;padding:18px;font-size:13px;line-height:1.8}footer{font-size:13px;color:#586b78;text-align:center;padding:18px}@media(max-width:700px){main{padding:12px}header{padding:26px 22px}h1{font-size:29px}section{padding:22px 16px}h2{font-size:22px}}@media print{body{background:white}main{padding:0;max-width:none}nav{display:none}header{border-radius:0}section{break-inside:auto;border:0;padding:16px 0}details{display:block}.table-wrap{overflow:visible}table{font-size:10px}th,td{white-space:normal;padding:6px}pre{color:#111;background:#f0f0f0}h2{break-after:avoid}}'''
    html='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>#11 무역 게임 v9 · 고급 기계와 기술 개발 검증</title><style>'+css+'</style></head><body><main>'+''.join(parts)+'<footer>#11 무역 게임 · v9 개발 연계 검증 · 인터넷 없이 읽는 정적 보고서</footer></main></body></html>'
    report.write_text(html,encoding='utf-8')
    return {'report':str(report),'bytes':report.stat().st_size,'tables':html.count('<table>'),'games':len(rows),'sha256':hashlib.sha256(report.read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=DEFAULT_RESULTS)
    parser.add_argument('--report',type=Path,default=ROOT/'TRADE_DEVELOPMENT_REVIEW_V9_KO.html')
    args=parser.parse_args()
    print(json.dumps(build(args.results.resolve(),args.report.resolve()),ensure_ascii=False))


if __name__=='__main__':
    main()
