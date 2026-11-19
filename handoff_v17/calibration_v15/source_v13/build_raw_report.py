"""Create the Korean v8 resource report from completed, independently audited data.

No engine imports, simulation runs, policy fitting or pilot-result fallbacks.
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
DEFAULT_RESULTS = ROOT / 'raw_results'
COUNTRIES = {
    'Tropia':'트로피아', 'Grainia':'그레니아', 'Oilia':'오일리아',
    'Mechania':'메카니아', 'Mineria':'미네리아', 'Technia':'테크니아',
    'Novia':'노비아', 'Agrea':'아그레아', 'Ferria':'페리아',
}
ORIGINAL = tuple(COUNTRIES)[:6]
INDUSTRIAL = ('Mechania', 'Technia', 'Novia')
GOODS = {'banana':'바나나', 'wheat':'밀', 'ore':'광물', 'fuel':'연료', 'machine':'기계', 'electronics':'전자제품'}
RAW = ('ore', 'fuel')
SOURCES = {'initial_own':'초기 자국 지급', 'initial_foreign':'초기 타국 지급',
           'produced_own':'신규 자국 생산', 'produced_foreign':'신규 타국 생산'}
MODES = {
    'baseline':'기준선', 'starter':'첫 생산분 지급', 'bridge':'첫 두 생산분 지급', 'recipe':'기계 원료 부담 증가',
    'coupled':'첫 생산분 + 원료 부담 증가', 'no_starter':'초기 원료 없음',
    'strict_no_starter':'초기 없음 + 원료 부담 증가',
}
POLICIES = {'baseline':(2,'legacy'), 'starter':(2,'first_cycle'), 'bridge':(2,'two_cycles'), 'recipe':(1,'legacy'),
            'coupled':(1,'first_cycle'), 'no_starter':(2,'none'), 'strict_no_starter':(1,'none')}
STRESS_MODES = ('baseline','starter','bridge','recipe','coupled')
REFUSALS = {'no_ore':'광물 수입 거부', 'no_fuel':'연료 수입 거부', 'no_raw':'두 원료 수입 거부'}
SCENARIOS = tuple((name, style) for name in ORIGINAL for style in ('cheap','idle')) + (
    (None,'normal'), (None,'no_trade'),
) + tuple((name, style) for name in INDUSTRIAL for style in REFUSALS)
MAIN_SEEDS = range(54000,54200)
STRESS_SEEDS = range(56000,56030)
EXPECTED_GAMES = 4850


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


def interval(values, digits=2):
    values = list(values)
    avg = statistics.mean(values)
    margin = 1.96 * statistics.stdev(values) / math.sqrt(len(values)) if len(values)>1 else 0
    return f'{signed(avg,digits)} [{signed(avg-margin,digits)}, {signed(avg+margin,digits)}]'


def table(headers, rows):
    html = '<div class="table-wrap"><table><thead><tr>' + ''.join('<th scope="col">'+escape(str(x))+'</th>' for x in headers) + '</tr></thead><tbody>'
    for row in rows:
        html += '<tr>' + ''.join(('<th scope="row">' if i==0 else '<td>') + escape(str(value))
                                + ('</th>' if i==0 else '</td>') for i,value in enumerate(row)) + '</tr>'
    return html + '</tbody></table></div>'


def load_completed(folder):
    required = ('summary.json','run_manifest.json','runs.jsonl.gz','round_ledgers.jsonl.gz',
                'raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz','independent_audit.json')
    missing = [name for name in required if not (folder/name).is_file()]
    need(not missing, 'Formal results are incomplete; no report written: '+', '.join(missing))
    summary = read_json(folder/'summary.json')
    meta = summary['metadata']
    need(meta == read_json(folder/'run_manifest.json'), 'Summary metadata and formal manifest differ.')
    need(meta['completed_games']==EXPECTED_GAMES and meta['main_games']==1400 and meta['stress_games']==3450,
         'Exactly 4,850 formal games (1,400 main + 3,450 stress) are required.')
    need(meta['main_seed_range']==[54000,54199] and meta['stress_seed_range']==[56000,56029], 'Formal seed bands differ.')
    need(meta['rounds']==9 and meta['countries']==9, 'Nine-round, nine-country comparison required.')
    need(meta['advice_mode']=='price' and meta['physical_mode']=='coupled', 'The inherited v7 price/v6 coupled policies must remain fixed.')
    need(meta['raw_modes']=={name:{'machine_credits':credit,'starter':starter} for name,(credit,starter) in POLICIES.items()},
         'Formal policy definitions differ from the report contract.')
    need(meta['source_unchanged'] is True and meta['pilot_excluded'] is True, 'Frozen-source/pilot-exclusion gate failed.')
    audit = read_json(folder/'independent_audit.json')
    need(audit['status']=='passed' and audit['completed_runs']==EXPECTED_GAMES and not audit['errors']
         and not audit.get('warnings'), 'Complete independent audit must pass before publication.')
    tests_path = folder/'tests_manifest.json'
    if not tests_path.is_file():
        tests_path = DEFAULT_RESULTS/'tests_manifest.json'
    need(tests_path.is_file(), 'Verified tests manifest is missing.')
    tests = read_json(tests_path)
    need(tests['passed'] is True and tests['test_count']==meta['tests_completed'], 'Test count or passed status differs from formal record.')
    need(tests['inherited_tests']==197 and tests['test_count']>197, 'Inherited and v8 test coverage must be recorded.')
    need(hashlib.sha256(tests_path.read_bytes()).hexdigest()==meta['tests_manifest_sha256'], 'Test manifest hash mismatch.')

    rows = read_lines(folder/'runs.jsonl.gz')
    keys = [(r['phase'],r['mode'],r['seed'],r['focal'],r['style']) for r in rows]
    expected = {('main',mode,seed,None,'normal') for mode in MODES for seed in MAIN_SEEDS}
    expected.update(('stress',mode,seed,focal,style) for mode in STRESS_MODES
                    for focal,style in SCENARIOS for seed in STRESS_SEEDS)
    need(len(keys)==len(set(keys))==EXPECTED_GAMES and set(keys)==expected, 'Saved games differ from the complete unique schedule.')
    groups = defaultdict(list)
    for row in rows:
        need(set(row['countries'])==set(COUNTRIES), 'Unexpected country set.')
        credit, starter = POLICIES[row['mode']]
        need(row['world']['raw_policy']=={'machine_credits':credit,'starter':starter}, 'Saved raw policy does not match its mode.')
        groups[(row['phase'],row['mode'],row['focal'],row['style'])].append(row)

    ledger_groups = {}
    expected_ledger_keys = {(mode,seed) for mode in MODES for seed in MAIN_SEEDS}
    expected_cells = {(name,r) for name in COUNTRIES for r in range(1,10)}
    for filename in ('round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz'):
        ledgers = read_lines(folder/filename)
        keys = [(g['mode'],g['seed']) for g in ledgers]
        need(len(keys)==len(set(keys))==1400 and set(keys)==expected_ledger_keys, filename+': incomplete main-game coverage.')
        for group in ledgers:
            cells = [(r['country'],r['round']) for r in group['rows']]
            need(len(cells)==81 and set(cells)==expected_cells, filename+': incomplete nine-country round ledger.')
        ledger_groups[filename] = ledgers
    traces = read_json(folder/'first_seed_traces.json.gz')
    expected_traces = {':'.join(map(str,('main',mode,54000,None,'normal'))) for mode in MODES}
    expected_traces.update(':'.join(map(str,('stress',mode,56000,name,style))) for mode in STRESS_MODES
                           for name in INDUSTRIAL for style in REFUSALS)
    need(len(traces)==52 and set(traces)==expected_traces, 'All seven main and 45 refusal representative traces are required.')
    return summary,meta,audit,tests,rows,groups,ledger_groups


def build(folder, report):
    summary,meta,audit,tests,rows,groups,ledgers = load_completed(folder)

    @lru_cache(maxsize=None)
    def mean(mode,path,phase='main',focal=None,style='normal'):
        return statistics.mean(get(r,path) for r in groups[(phase,mode,focal,style)])

    def c(mode,name,key):
        return mean(mode,f'countries.{name}.{key}')

    def w(mode,key):
        return mean(mode,'world.'+key)

    def total(mode,key):
        return sum(c(mode,name,key) for name in COUNTRIES)

    def metric(row,path):
        if path=='all_useful_exports':
            return sum(c['useful_exports'] for c in row['countries'].values())
        if path=='all_raw_imports':
            return sum(c['import_goods'][g] for c in row['countries'].values() for g in RAW)
        return get(row,path)

    def paired(a,b,path):
        left = {r['seed']:r for r in groups[('main',a,None,'normal')]}
        right = {r['seed']:r for r in groups[('main',b,None,'normal')]}
        return [metric(right[s],path)-metric(left[s],path) for s in MAIN_SEEDS]

    def stress_diff(mode,focal,style,path):
        control = {r['seed']:r for r in groups[('stress',mode,None,'normal')]}
        return [metric(r,path)-metric(control[r['seed']],path) for r in groups[('stress',mode,focal,style)]]

    def sm(mode,name,key,style):
        return mean(mode,f'countries.{name}.{key}','stress',None if style=='normal' else name,style)

    def change(a,b,path):
        return f(mean(a,path))+' → '+f(mean(b,path))

    def initial_used(mode,good):
        return w(mode,f'raw_use.{good}.initial_own')+w(mode,f'raw_use.{good}.initial_foreign')

    def produced_used(mode,good):
        return w(mode,f'raw_use.{good}.produced_own')+w(mode,f'raw_use.{good}.produced_foreign')

    def tech_key(name,grade):
        return ('machine' if name=='Mechania' else 'electronics')+f'_g{grade}'

    for mode in MODES:
        experiment = summary['experiments'][f'main:{mode}:None:normal']
        need(experiment['n']==200,'Summary group count mismatch.')
        for path in ('world.happy','world.inventory','world.aged_unused','world.initial_asset_value',
                     'world.raw_use.ore.consumed','world.raw_use.fuel.consumed','countries.Mechania.cash'):
            need(math.isclose(mean(mode,path),experiment['metrics'][path]['mean'],abs_tol=1e-9), 'Raw/summary mismatch: '+path)

    cash_rounds,raw_rounds = defaultdict(list),defaultdict(list)
    for group in ledgers['round_ledgers.jsonl.gz']:
        for row in group['rows']:
            cash_rounds[(group['mode'],row['country'],row['round'])].append(row)
    for group in ledgers['raw_round_ledgers.jsonl.gz']:
        for row in group['rows']:
            raw_rounds[(group['mode'],row['country'],row['round'])].append(row)

    out = []
    add = out.append
    add('<header><p class="eyebrow">아이디어 노트 · #11 무역 게임 · 2단계 경제 모형 검증</p>'
        '<h1>시작 원료와 기계 투입량이<br>실제 무역 필요를 바꿀까?</h1>'
        '<p>v8 정식 비교 · 9개국 · 9라운드 · v7 가격 추천 정책 고정</p></header>')
    add('<section class="lead"><h2>2단계 판정: 첫 두 생산분 지급을 후속 검증의 기준선 후보로</h2>'
        '<p><strong>bridge를 다음 검증의 기준선 후보로 남긴다.</strong> '
        '전자제품 국가의 시작 원료를 유지하면서 메카니아의 첫 두 기본 생산에 필요하지 않은 초기 원료 지급을 줄여, '
        '현재 자동 운영에서 기계 발전에 필요한 원료 확보 행동이 드러나게 했다. '
        '공정성이 확인된 최종 기본안이나 과잉 생산 해결안으로 확정한 것은 아니다.</p>')
    add('<p>기준선 → bridge에서 메카니아가 광물을 수입한 게임 비율은 <strong>'
        +f(100*c('baseline','Mechania','raw_importing.ore'),1)+'% → '+f(100*c('bridge','Mechania','raw_importing.ore'),1)
        +'%</strong>, 2세대 기계 도달 비율은 <strong>'+f(100*c('baseline','Mechania','machine_g2'),1)
        +'% → '+f(100*c('bridge','Mechania','machine_g2'),1)+'%</strong>였다. '
        '메카니아의 종료 현금은 <strong>'+f(c('baseline','Mechania','cash'))+' → '+f(c('bridge','Mechania','cash'))
        +'G</strong>, 만족도는 <strong>'+f(c('baseline','Mechania','happy'))+' → '+f(c('bridge','Mechania','happy'))
        +'</strong>로 낮아졌다. 원료 확보의 의미가 생기는 만큼 이 국가의 부담도 함께 남았다.</p>')
    add('<p>세계 만족도는 <strong>'+change('baseline','bridge','world.happy')+'</strong>, 실재고는 <strong>'
        +change('baseline','bridge','world.inventory')+'</strong>, 9국 현금 격차는 <strong>'
        +change('baseline','bridge','world.all_country_cash_gap')+'G</strong>이다. '
        '이 세 지표의 동일 시드 차이 구간은 모두 0을 포함하므로, 만족도·재고·공정성이 개선됐다고 단정하지 않는다. '
        '같다는 것이 입증된 것도 아니다. 원료 부담을 늘리는 1칸 방식과 초기 원료 완전 제거는 기본안으로 채택하지 않는다.</p></section>')
    add('<div class="cards">'+''.join('<div><b>'+escape(value)+'</b><span>'+escape(label)+'</span></div>' for value,label in [
        (f(meta['completed_games'],0),'정식 완료 게임'),(f(tests['test_count'],0),'통과 테스트 기록'),
        (f(meta['verification_calls'],0),'실행 중 불변조건 검사'),('226,800','현금·원료 원장 행 합계')])+'</div>')

    add('<section><h2>1. 무엇을 바꾸었는가?</h2>'
        '<p>v7의 가격 추천과 보호 재고 수정은 모든 안에서 고정했다. 기계 생산량을 조절하는 v6 coupled 규칙, '
        '나라별 시작 현금·산업, 전자제품 생산 원료, 기술 개발 원료, 시장 가격 공식, 점수식도 유지했다. '
        'v7의 새 투자·주력 추천과 공개 등록량 제한은 사용하지 않는다. '
        '이번에 바뀐 변수는 초기 원료 지급 방식과 <strong>기계 제조에 한정된 묶음당 작업량</strong>이다.</p>')
    add(table(['코드','이름','기계 원료 1묶음의 작업량','초기 원료'],[
        ['baseline',MODES['baseline'],'2칸','기존: 3개 산업국에 광물·연료 각 1묶음'],
        ['starter',MODES['starter'],'2칸','실제 첫 생산에 필요한 만큼'],
        ['bridge',MODES['bridge'],'2칸','시작 기술·주력의 첫 두 생산에 필요한 만큼'],
        ['recipe',MODES['recipe'],'1칸','기존 지급 유지'],
        ['coupled',MODES['coupled'],'1칸','실제 첫 생산에 필요한 만큼'],
        ['no_starter',MODES['no_starter'],'2칸','지급 없음; 경계 진단'],
        ['strict_no_starter',MODES['strict_no_starter'],'1칸','지급 없음; 경계 진단'],
    ]))
    add('<h3>후보별 판단</h3>')
    add(table(['후보','이번 판단','정식 결과에서 읽을 점'],[
        ['baseline','대조 기준 유지','기존 상태와 다음 후보의 효과를 계속 비교한다.'],
        ['bridge','후속 검증의 기준선 후보','메카니아 원료 확보 행동과 2세대 진행의 연결을 확인했다. 만족도·재고·현금 격차의 개선은 확정할 수 없다.'],
        ['starter','채택 보류','세계 만족도 '+f(w('baseline','happy'))+' → '+f(w('starter','happy'))
         +', 실재고 '+f(w('baseline','inventory'))+' → '+f(w('starter','inventory'))+'로 바뀌어 첫 생산분만 주는 이점이 충분하지 않았다.'],
        ['recipe','채택 보류','원료 부담 증가만으로 광물·연료 교역이 크게 달라지지 않았다. 이월 작업량은 '+f(w('baseline','material_work_left'))
         +' → '+f(w('recipe','material_work_left'))+'칸으로 줄었으나 이것만으로 무역 학습의 개선을 뜻하지 않는다.'],
        ['coupled','채택 보류','첫 생산분 지급과 부담 증가를 함께 적용해도 초기 생활·재고의 문제를 해결했다고 보기 어렵다.'],
        ['no_starter / strict_no_starter','경계 진단으로 유지','첫 거래 전에 두 전자제품 국가가 원료 미충족을 겪는 조건이다. 학생의 사전 구매 실패로 평가하지 않는다.'],
    ]))
    add('<p class="note"><strong>2칸 → 1칸의 뜻:</strong> 같은 가격의 원료 1묶음으로 수행할 수 있는 기계 제조 작업량을 절반으로 줄였다. '
        '기계 제조의 실질 원료 부담을 늘리는 실험이다. 모든 상품의 묶음 크기를 절반으로 바꾸는 단위 조정이 아니다. '
        '재료 이월과 올림 계산 때문에 각 시점의 구매 묶음 수가 항상 정확히 두 배가 되는 것은 아니다. '
        '전자제품·연구의 원료 규칙, 원료 한 묶음의 가격, 점수식을 함께 바꾸지 않았다.</p>'
        '<p>첫 생산은 거래보다 먼저 일어난다. 초기 원료가 전혀 없는 두 안은 사전에 수입할 기회가 없는 경계 조건이다. '
        '이 안의 첫 생산 실패를 학생의 구매 판단 실패로 해석해서는 안 된다.</p>'
        '<p><strong>첫 두 생산분 지급(bridge)</strong>은 시작 기술과 시작 주력 산업을 기준으로 계산한 첫 두 번의 생산 원료만 지급한다. '
        '초기 거래를 이어 가는 여유를 확인하는 후보이며, 앞으로 개발할 기술이나 산업 확장의 연구·생산 원료를 보장하지 않는다.</p></section>')

    add('<section><h2>2. 초기 지급량과 시작 자산을 따로 확인</h2>'
        '<p>각 칸은 광물 / 연료 묶음 수다. 실제 저장된 초기 지급량을 읽어 표시했다. 시작 현금으로 부족한 원료의 가치를 보상하지 않았다.</p>')
    add(table(['국가']+list(MODES.values()),[[COUNTRIES[name]]+[
        f(c(mode,name,'starter_raw.ore'),0)+' / '+f(c(mode,name,'starter_raw.fuel'),0) for mode in MODES]
        for name in COUNTRIES]))
    add('<h3>초기 원료가 줄면 성장 측정의 출발점도 낮아진다</h3>'
        '<p>기존 자산 평가식을 그대로 적용해 실제 지급품으로 시작 자산을 다시 계산했다. '
        '아래의 “자기 시작점 증가”는 종료 평가자산 − 해당 정책의 시작 평가자산, '
        '“공통 시작점 증가”는 종료 평가자산 − 기준선의 시작 평가자산이다. '
        '두 증가량의 차이는 시작 지급량을 바꾼 데 따른 기계적인 기준점 차이다. '
        '공통 시작점 수치는 해석을 위한 진단값이며 게임 점수에 새로 적용하지 않았다.</p>')
    assets = []
    for name in INDUSTRIAL:
        reference = c('baseline',name,'start_asset_value')
        for mode in MODES:
            start,end = c(mode,name,'start_asset_value'),c(mode,name,'end_asset_value')
            score = None if name not in ORIGINAL else c(mode,name,'economic')
            assets.append([COUNTRIES[name],MODES[mode],f(start),f(end),signed(end-start),signed(end-reference),
                           signed(reference-start),f(score)])
    add(table(['국가','안','시작 평가 G','종료 평가 G','자기 시작점 증가 G','공통 시작점 증가 G','기준점 효과 G','경제력 점수'],assets))
    add('<p class="note">평가자산은 현금과 기존 방식으로 평가한 재고, 종료 시 투자액의 45%를 합친 장부값이다. '
        '재고가 그 금액에 실제로 팔린다는 뜻은 아니다. 초기 평가액 감소로 성장 점수의 기준이 낮아질 수 있으므로 '
        '종료 현금·실제 활용·점수를 따로 읽는다. 노비아를 포함한 추가 3개국에는 미보정 종합 점수를 만들지 않았다.</p></section>')

    add('<section><h2>3. 정식 검증 설계</h2>')
    add(table(['구분','구성','시드','게임 수'],[
        ['본 비교','7가지 안 × 200회','54000–54199','1,400'],
        ['반값·무행동','5가지 안 × 기존 6개국 × 2전략 × 30회','56000–56029','1,800'],
        ['정상·무역 금지','같은 5가지 안 × 2조건 × 30회','56000–56029','300'],
        ['원료 수입 거부','같은 5가지 안 × 산업 3개국 × 거부 3종 × 30회','56000–56029','1,350'],
        ['합계','코드와 조건을 고정한 정식 실행','예비 실행·테스트 제외',f(meta['completed_games'],0)],
    ]))
    add('<p>스트레스 비교의 5가지 안은 기준선·첫 생산분 지급·첫 두 생산분 지급·기계 원료 부담 증가·두 변경 결합이다. '
        '원료 거부 국가는 메카니아·테크니아·노비아이며 광물만, 연료만, 두 원료 모두 거부하는 조건을 나누었다. '
        '표는 별도 표시가 없으면 본 비교 200게임 평균이다. G는 게임 화폐, 만족도는 9라운드 평균, 현금은 종료 값이다. '
        '동일 시드 대응 차이의 구간은 평균 ± 1.96 × 표준오차다. 모형 안의 변동 구간이며 실제 학생 모집단의 학습 효과 구간은 아니다.</p></section>')

    add('<section><h2>4. 일곱 정책의 세계 결과</h2>')
    add(table(['안','만족도','첫 2회 만족도','실사용 수출품','원료 수입','원료 실제 소비','실재고','오래 미사용','9국 현금 격차 G'],[
        [MODES[mode],f(w(mode,'happy')),f(w(mode,'first_two_happy')),f(total(mode,'useful_exports')),
         f(sum(total(mode,'import_goods.'+g) for g in RAW)),f(sum(w(mode,'raw_use.'+g+'.consumed') for g in RAW)),
         f(w(mode,'inventory')),f(w(mode,'aged_unused')),f(w(mode,'all_country_cash_gap'))] for mode in MODES]))
    add('<p>수입량은 상품이 국경을 넘은 누계이고, 실제 소비량은 생산·연구에 쓰여 사라진 실물 수다. '
        '수입을 했다가 재고로 남기거나 되파는 경우가 있으므로 두 값이 같아야 하는 것은 아니다. '
        '실사용 수출품은 신규 생산해 해외에서 한 번 이상 쓰인 실물을 센다.</p>'
        '<h3>bridge의 핵심 대응 차이</h3>')
    add(table(['지표','기준선','bridge','대응 차이 [95% 구간]'],[
        [label,f(mean('baseline',path)),f(mean('bridge',path)),interval(paired('baseline','bridge',path),4 if path=='world.happy' else 2)]
        for label,path in [('세계 만족도','world.happy'),('세계 실재고','world.inventory'),('9국 현금 격차 G','world.all_country_cash_gap'),
                           ('광물 교역 수량','world.trade_goods.ore'),('수입 이력 광물 실제 사용','world.raw_use.ore.imported_used'),
                           ('연료 교역 수량','world.trade_goods.fuel')]]))
    add('<p>광물 거래 증가와 연료 거래 변화는 같은 방향이 아니다. 원료 전체 거래가 일괄적으로 늘어났다고 표현하지 않는다. '
        '표의 구간은 같은 시드의 모형 차이에 관한 것으로 실제 수업의 효과를 보장하지 않는다.</p><h3>다른 후보의 같은 시드 변화</h3>')
    add(table(['비교','만족도 Δ [95% 구간]','원료 수입 Δ [95% 구간]','실사용 수출 Δ [95% 구간]','현금 격차 ΔG [95% 구간]'],[
        [MODES[a]+' → '+MODES[b]]+[interval(paired(a,b,key)) for key in
         ('world.happy','all_raw_imports','all_useful_exports','world.all_country_cash_gap')]
        for a,b in (('baseline','starter'),('baseline','bridge'),('starter','bridge'),('baseline','recipe'),('starter','coupled'),('recipe','coupled'),
                    ('starter','no_starter'),('coupled','strict_no_starter'))]))
    add('</section>')

    add('<section><h2>5. 광물·연료는 어디서 와서 어디에 쓰였나?</h2>'
        '<p>원료의 용도와 출처는 별도의 구분이다. “생산”과 “연구”는 사용 목적이고, 초기·신규 및 자국·타국은 '
        '그 실물의 최초 출처다. “수입 이력 후 사용”은 마지막 수입 기록이 있는 소비 실물 수다. '
        '자국에서 만든 물건이 재수입될 수도 있으므로 타국 출처 소비량과 완전히 같은 지표는 아니다.</p>')
    for good in RAW:
        add('<h3>'+GOODS[good]+'의 수입과 실제 소비</h3>')
        add(table(['안','수입 누계','생산 사용','연구 사용','초기 지급품 사용','신규 생산품 사용','수입 이력 후 사용','초기 원료 잔량'],[
            [MODES[mode],f(total(mode,'import_goods.'+good)),f(w(mode,'raw_use.'+good+'.production')),
             f(w(mode,'raw_use.'+good+'.research')),f(initial_used(mode,good)),f(produced_used(mode,good)),
             f(w(mode,'raw_use.'+good+'.imported_used')),f(w(mode,'initial_raw_left.'+good))] for mode in MODES]))
        add(table(['안']+list(SOURCES.values())+['소비 합계'],[
            [MODES[mode]]+[f(w(mode,'raw_use.'+good+'.'+source)) for source in SOURCES]
            +[f(w(mode,'raw_use.'+good+'.consumed'))] for mode in MODES]))
    add('<p>초기 원료 잔량은 현재 보유한 모든 초기 지급 실물이다. 다른 나라가 지급받은 물건을 수입해 보유한 경우도 포함한다. '
        '초기 타국 지급품을 수입해 사용하는 거래와 신규 생산 원료를 수입해 사용하는 거래를 구분해 보아야 '
        '계속 생산되는 원료에 대한 무역 필요를 판단할 수 있다.</p>')
    add('<h3>세계 전체의 원료 실물 보존</h3>')
    balance_rows = []
    for mode in MODES:
        for good in RAW:
            opening,produced,stock = (w(mode,key+'.'+good) for key in ('starter_raw','production','remaining_goods'))
            used = w(mode,'raw_use.'+good+'.consumed')
            residual = opening+produced-used-stock
            need(math.isclose(residual,0,abs_tol=1e-8), 'Saved world raw conservation mismatch.')
            balance_rows.append([MODES[mode],GOODS[good],f(opening),f(produced),f(used),f(stock),f(residual)])
    add(table(['안','원료','초기 지급','신규 생산','생산·연구 소비','종료 재고','차이'],balance_rows))
    add('<p>세계 전체에서는 국가 간 수입·수출이 서로 상쇄된다. 초기 지급 + 신규 생산 − 실제 소비 = 종료 재고를 확인했다. '
        '국가·라운드 원장에는 시작 재고, 자국 생산, 수입·수출, 소비, 종료 재고와 세대별 이월 작업량을 별도로 남겼다. '
        '생산 소비는 원료 묶음을 제조에 투입한 기록이다. 가공된 작업량 일부가 다음 생산을 위해 남을 수 있으므로 '
        '소비 원료가 모두 이미 완제품에 전부 반영됐다는 뜻은 아니다.</p>')
    add(table(['지표']+list(MODES.values()),[['세계 종료 이월 가공 작업량(칸)']+[f(w(mode,'material_work_left')) for mode in MODES]]))
    add('<details><summary>9개국의 원료 수입·사용 상세</summary>')
    for good in RAW:
        add('<h3>'+GOODS[good]+'</h3>')
        raw_rows = []
        for mode in MODES:
            for name in COUNTRIES:
                selected = groups[('main',mode,None,'normal')]
                imported_rounds = [r['countries'][name]['first_raw_import_round'][good] for r in selected
                                   if r['countries'][name]['raw_importing'][good]]
                raw_rows.append([MODES[mode],COUNTRIES[name],f(c(mode,name,'import_goods.'+good)),
                    f(100*c(mode,name,'raw_importing.'+good),1)+'%',
                    f(statistics.mean(imported_rounds)) if imported_rounds else '수입 없음',
                    f(c(mode,name,'raw_use.'+good+'.production')),f(c(mode,name,'raw_use.'+good+'.research')),
                    f(c(mode,name,'raw_use.'+good+'.imported_used')),f(c(mode,name,'end_stock_by_good.'+good))])
        add(table(['안','국가','수입량','수입한 게임 비율','수입한 게임의 첫 수입회','생산 사용','연구 사용','수입 이력 후 사용','종료 보유'],raw_rows))
    add('<p>첫 수입 라운드는 수입이 실제 있었던 게임만 평균했다. 원본의 값 10은 10라운드 거래가 아니라 '
        '9라운드 안에 수입하지 않았다는 표시다.</p></details></section>')

    add('<section><h2>6. 시작 두 라운드의 생활과 생산</h2>'
        '<p>산업 원료를 줄이는 수정이 게임을 시작하자마자 생활 부족과 현금 부담을 만드는지 확인한다. '
        '생산 실패 진단은 각 시설의 가동 차례에 필요한 원료를 충족하지 못한 횟수이며, 이후 기본 생산으로 전환하는 경우도 포함할 수 있다. '
        '원본의 raw_unmet_production은 각 시설 차례에서 관측한 부족분의 합이다. 모든 시설을 동시에 정상 가동하기 위해 필요한 최소 추가 원료량을 뜻하지 않는다.</p>')
    for field,title in [('first_two_happy','첫 2라운드 평균 만족도'),('first_two_food_short','첫 2라운드 식량 부족 횟수'),
                        ('first_two_production_failures','첫 2라운드 원료 미충족 생산 진단 횟수')]:
        add('<h3>'+title+'</h3>')
        add(table(['국가']+list(MODES.values()),[[COUNTRIES[name]]+[f(c(mode,name,field)) for mode in MODES] for name in COUNTRIES]))
    add('<p class="note">초기 원료 없음의 두 안에서는 첫 라운드 원료 미충족 진단이 세계 평균 '
        +f(w('no_starter','first_round_production_failures'))+'회이며, 첫 2라운드 만족도는 기준선 '
        +f(w('baseline','first_two_happy'))+'에서 '+f(w('no_starter','first_two_happy'))+'로 낮아졌다. '
        '첫 거래 전에 생산이 이뤄지는 제약을 확인하는 진단이다. '
        '학생에게 준비 시간을 준 수업의 결과와 같다고 볼 수 없다. 이 경계 결과를 이유로 사전 거래나 보조금을 새로 넣지는 않았다.</p></section>')

    add('<section><h2>7. 9개국의 현금·만족도·무역·투자</h2>')
    for field,title in [('cash','종료 현금 G'),('happy','9라운드 평균 만족도'),('useful_exports','해외에서 실제 사용된 신규 수출품'),
                        ('investment','산업·기술 투자 지출 G')]:
        add('<h3>'+title+'</h3>')
        add(table(['국가']+list(MODES.values()),[[COUNTRIES[name]]+[f(c(mode,name,field)) for mode in MODES] for name in COUNTRIES]))
    add('<h3>메카니아: 기계의 실제 기여와 부담을 함께 확인</h3>')
    add(table(['지표','기준선','bridge','대응 차이 [95% 구간]'],[
        [label,f(c('baseline','Mechania',key),3),f(c('bridge','Mechania',key),3),
         interval(paired('baseline','bridge','countries.Mechania.'+key),3)]
        for label,key in [('종료 현금 G','cash'),('평균 만족도','happy'),
                          ('신규 생산 기계 중 실제 사용된 실물','use_by_good.machine'),
                          ('해외에서 실제 사용된 신규 기계','export_used_by_good.machine')]]))
    add('<p>여기서는 기계 품목만의 사용·수출을 표시했다. 국가의 전체 실사용 수출품에는 밀 등 다른 품목도 포함되므로 '
        '전체 수출 실적을 기계 수출 실적으로 바꾸어 읽지 않는다. 메카니아의 만족도 차이 구간은 0 아래에 있어 '
        '국가별 부담을 후속 검증에서 계속 확인해야 한다.</p>'
        '<h3>미네리아: 점수가 올라도 수익과 활용이 늘었다고 단정하지 않기</h3>')
    add(table(['지표','기준선','bridge','차이'],[
        [label,f(c('baseline','Mineria',key),4),f(c('bridge','Mineria',key),4),
         signed(c('bridge','Mineria',key)-c('baseline','Mineria',key),4)]
        for label,key in [('종합 점수','score'),('생산 능력 점수','industry_capacity_score'),
                          ('실제 활용 점수','industry_use_score'),('실사용 수출품','useful_exports'),('종료 현금 G','cash')]]))
    add('<p>미네리아의 총점 상승에는 생산 능력 점수의 상승이 크게 작용했다. 실제 활용 점수·실사용 수출품·현금은 같은 방향으로 증가하지 않았다. '
        '이 점수 상승을 수익성이나 실제 사용 개선의 증거로 설명하지 않는다.</p>')
    add('<details><summary>현금 증가의 출처와 지출</summary>')
    for mode in MODES:
        add('<h3>'+MODES[mode]+'</h3>')
        add(table(['국가','시작 G','판매 수입 G','구매 지출 G','투자 G','운영수입 G','종료 G'],[
            [COUNTRIES[name]]+[f(c(mode,name,key)) for key in ('start_cash','revenue','purchases','investment','tax','cash')]
            for name in COUNTRIES]))
    add('</details></section>')

    add('<section><h2>8. 생산과 기술 발전은 이어지는가?</h2>'
        '<p>성공률은 9라운드가 끝날 때 해당 산업을 보유하고 목표 세대 이상에 도달한 게임의 비율이다. '
        '세대 개발 성공 자체가 수출 성공이나 투자 회수를 뜻하지는 않는다.</p>')
    tech_rows = []
    for name in INDUSTRIAL:
        good = 'machine' if name=='Mechania' else 'electronics'
        for mode in MODES:
            tech_rows.append([COUNTRIES[name],MODES[mode],f(100*c(mode,name,tech_key(name,2)),1)+'%',
                f(100*c(mode,name,tech_key(name,3)),1)+'%',f(c(mode,name,'produced.'+good)),
                f(c(mode,name,'export_used_by_good.'+good)),f(c(mode,name,'research_raw.ore')),f(c(mode,name,'research_raw.fuel'))])
    add(table(['국가','안','2세대 이상','3세대 이상','주요 제품 생산','해외 실제 사용','연구 광물','연구 연료'],tech_rows))
    add('<h3>메카니아의 기본 기계와 제조 원료</h3>')
    add(table(['지표']+list(MODES.values()),[[label]+[f(c(mode,'Mechania',key)) for mode in MODES] for label,key in [
        ['정상 규칙의 원료 없는 기본 1개 생산','machine_free_basic'],['원료 부족 후 기본 생산 전환','machine_fallbacks'],
        ['기계 생산 휴식','machine_pauses'],['전체 생산에 사용한 광물','production_raw.ore'],
        ['전체 생산에 사용한 연료','production_raw.fuel'],['종료 기계 재고','end_stock_by_good.machine'],
        ['종료 이월 가공 작업량(칸)','material_work_left'],
    ]]))
    add('<p>기존 규칙에는 원료 없이 기본 기계 1개를 만드는 경우가 남아 있다. 고급 기계 제조 원료를 늘렸어도 '
        '이 기본 생산이 사라지는 것은 아니다. 원료 수입 거부 결과는 세대와 기본 생산을 나누어 확인한다.</p></section>')

    add('<section><h2>9. 원료 수입을 거부해도 목표를 달성하는가?</h2>'
        '<p>원료 거부는 지정 국가가 해당 원료를 화폐 거래와 물물교환 모두에서 수입하지 않는 조건이다. '
        '각 정책이 주는 초기 원료는 유지하며, 다른 물건 구매와 투자 활동을 모두 멈추는 조건은 아니다. '
        '정상 행동과 동일 시드로 비교해 원료를 확보하려는 행동이 생산·발전·생활에 실제 차이를 만드는지 본다.</p>'
        '<h3>메카니아 광물 거부: 초기 지급과 자동 투자 보류를 분리해 해석</h3>')
    focused_rows = []
    for mode in ('baseline','bridge'):
        for style in ('normal','no_ore'):
            focal = None if style=='normal' else 'Mechania'
            selected = groups[('stress',mode,focal,style)]
            success = sum(r['countries']['Mechania']['machine_g2'] for r in selected)
            focused_rows.append([MODES[mode],'정상' if style=='normal' else '광물 수입 거부',
                str(success)+'/'+str(len(selected)),f(100*success/len(selected),1)+'%',
                f(sm(mode,'Mechania','investment',style)),f(sm(mode,'Mechania','cash',style)),
                f(sm(mode,'Mechania','machine_free_basic',style))])
    add(table(['안','조건','2세대 도달 게임','도달 비율','투자 G','종료 현금 G','원료 없는 정상 기본 생산 횟수'],focused_rows))
    add('<p class="note"><strong>새로운 필수 개발 조건을 만든 결과가 아니다.</strong> 기존 산업 Lv.2로 올리는 투자 자체는 현금으로 진행하는 개발이다. '
        '현재 자동 운영은 다음 생산의 원료가 확보되지 않으면 투자를 보류한다. '
        '따라서 bridge의 광물 거부 조건에서 2세대 도달이 0인 것은 이 자동 운영의 원료 확보 판단을 포함한 결과다. '
        '학생에게 “광물이 없으면 Lv.2 개발을 선택할 수 없다”는 새 규칙을 추가한 것이 아니다. '
        '고급 기계의 실제 생산에는 원료가 필요하고, 원료 없는 기본 기계 생산은 이어진다.</p>')
    add('<p>bridge의 광물 거부군은 정상군의 '+f(sm('bridge','Mechania','cash','normal'))+'G보다 높은 '
        +f(sm('bridge','Mechania','cash','no_ore'))+'G를 남겼지만 투자 지출은 '
        +f(sm('bridge','Mechania','investment','normal'))+' → '+f(sm('bridge','Mechania','investment','no_ore'))
        +'G였다. 이 현금 증가는 투자를 하지 않아 남긴 돈의 영향을 포함하며 번영이나 산업 발전의 증가로 읽어서는 안 된다.</p>')
    for name in INDUSTRIAL:
        add('<h3>'+COUNTRIES[name]+'</h3>')
        rr = []
        for mode in STRESS_MODES:
            for style in ('normal',*REFUSALS):
                rr.append([MODES[mode],'정상' if style=='normal' else REFUSALS[style],
                    f(sm(mode,name,'import_goods.ore',style)),f(sm(mode,name,'import_goods.fuel',style)),
                    f(sm(mode,name,'raw_use.ore.production',style)+sm(mode,name,'raw_use.fuel.production',style)),
                    f(sm(mode,name,'raw_use.ore.research',style)+sm(mode,name,'raw_use.fuel.research',style)),
                    f(sum(sm(mode,name,'raw_use.'+g+'.'+source,style) for g in RAW for source in ('initial_own','initial_foreign'))),
                    f(sm(mode,name,'cash',style)),f(sm(mode,name,'happy',style)),
                    f(100*sm(mode,name,tech_key(name,2),style),1)+'%',f(100*sm(mode,name,tech_key(name,3),style),1)+'%'])
        add(table(['안','조건','광물 수입','연료 수입','생산 원료 사용','연구 원료 사용','초기 원료 사용','현금 G','만족도','2세대 이상','3세대 이상'],rr))
        add('<h4>정상 행동 대비 차이</h4>')
        add(table(['안','거부 조건','현금 ΔG [95% 구간]','만족도 Δ [95% 구간]','실사용 수출 Δ [95% 구간]','투자 ΔG [95% 구간]'],[
            [MODES[mode],REFUSALS[style]]+[interval(stress_diff(mode,name,style,f'countries.{name}.{key}'))
              for key in ('cash','happy','useful_exports','investment')]
            for mode in STRESS_MODES for style in REFUSALS]))
    add('<p class="note">거부 조건에서 높은 현금이 남아도 생산과 발전을 포기해 지출이 줄었을 수 있다. '
        '수입량 0과 현금만으로 “원료가 필요 없다” 또는 “무역하지 않는 것이 최선”이라고 결론내리지 않는다. '
        '초기 지급품 사용, 연구 소비, 세대 성공, 실제 사용 수출품을 함께 읽는다.</p>'
        '<h3>같은 광물 거부가 점수에 똑같이 반영되는 것은 아니다</h3>')
    add(table(['bridge의 거부 국가','총점 차이','투자 차이 G','생산 능력 점수 차이','활용 점수 차이','정상→거부의 주요 고급 세대 성공률'],[
        [COUNTRIES[name]]+[signed(statistics.mean(stress_diff('bridge',name,'no_ore',f'countries.{name}.{key}')),4)
                          for key in ('score','investment','industry_capacity_score','industry_use_score')]
        +[f(100*sm('bridge',name,tech_key(name,grade),'normal'),1)+'% → '+f(100*sm('bridge',name,tech_key(name,grade),'no_ore'),1)+'%']
        for name,grade in (('Mechania',2),('Technia',3))]))
    add('<p>메카니아의 주요 세대는 기계 2세대, 테크니아는 전자제품 3세대다. '
        '발전이 멈추어도 기존 생산 능력 점수의 상한과 활용 점수의 분모 변화 때문에 총점의 손실은 국가별로 다를 수 있다. '
        '원료 확보의 필요를 더 분명히 한 결과와 국가별 평가의 공정성은 별도 문제로 남아 있다.</p></section>')

    add('<section><h2>10. 최저가 반복·무행동·무역 금지의 영향</h2>'
        '<p>cheap은 기준가 절반의 판매를 반복하되 구매·투자를 유지한다. idle은 자동 생산과 운영수입은 유지하지만 '
        '거래·투자는 하지 않는다. 실제 의욕이 없는 학생의 모든 행동을 대표하지 않는다.</p>')
    for mode in STRESS_MODES:
        add('<h3>'+MODES[mode]+' — 반값 판매</h3>')
        add(table(['국가','현금 ΔG','만족도 Δ','실사용 수출 Δ','투자 ΔG','총점 Δ'],[
            [COUNTRIES[name]]+[signed(statistics.mean(stress_diff(mode,name,'cheap',f'countries.{name}.{key}')))
                              for key in ('cash','happy','useful_exports','investment','score')]
            for name in ORIGINAL]))
    add('<p>경제력 25점의 상한과 산업 활용 점수의 생산량 분모를 유지했으므로, 총점 차이만으로 공정성을 평가하지 않는다. '
        '낮은 판매 가격이 항상 나쁘도록 처벌하는 규칙을 추가하지 않았다.</p>')
    add('<p class="note">bridge의 테크니아 반값 전략은 정상 행동 대비 총점 차이가 '
        +interval(stress_diff('bridge','Technia','cheap','countries.Technia.score'),4)
        +'점이었다. 판매 수입 차이는 '+signed(statistics.mean(stress_diff('bridge','Technia','cheap','countries.Technia.revenue')))
        +'G, 투자 차이는 '+signed(statistics.mean(stress_diff('bridge','Technia','cheap','countries.Technia.investment')))
        +'G, 종료 전자제품 세대 평균 차이는 '+signed(statistics.mean(stress_diff('bridge','Technia','cheap','countries.Technia.elec_gen')))
        +'였다. 점수상 유리함이 남아도 돈을 더 벌었거나 기술이 더 발전한 결과로 해석하지 않는다. '
        '반값 전략과 평가 공정성의 검토는 계속 필요하다.</p>')
    add('<details><summary>무행동 국가가 다른 8개국의 만족도에 미친 영향</summary>')
    for mode in STRESS_MODES:
        idle_rows = []
        for focal in ORIGINAL:
            ds = {name:statistics.mean(stress_diff(mode,focal,'idle',f'countries.{name}.happy')) for name in COUNTRIES}
            idle_rows.append([COUNTRIES[focal]]+[signed(ds[name])+(' (본인)' if name==focal else '') for name in COUNTRIES]
                             +[signed(statistics.mean(value for name,value in ds.items() if name!=focal))])
        add('<h3>'+MODES[mode]+'</h3>')
        add(table(['무행동 국가']+list(COUNTRIES.values())+['다른 8국 평균 Δ'],idle_rows))
    add('</details><h3>무역 금지 대조군</h3>')
    add(table(['안','정상 만족도','무역 금지 만족도','대응 차이 [95% 구간]','무역 금지 거래량'],[
        [MODES[mode],f(mean(mode,'world.happy','stress')),f(mean(mode,'world.happy','stress',None,'no_trade')),
         interval(stress_diff(mode,None,'no_trade','world.happy')),f(mean(mode,'world.trade_units','stress',None,'no_trade'))]
        for mode in STRESS_MODES]))
    add('</section>')

    add('<section><h2>11. 원료 변화가 다른 상품의 과잉을 옮기지 않는가?</h2>'
        '<p>신규품 실제 사용은 이번 게임에 생산한 실물이 한 번 이상 쓰인 수량이며 초기 지급품과 반복 사용 횟수는 제외한다. '
        '사용한 내구재도 재고로 남을 수 있다. 오래 미사용 재고는 2라운드 이상 한 번도 쓰이지 않은 보유 실물이다.</p>')
    for good in GOODS:
        add('<h3>'+GOODS[good]+'</h3>')
        add(table(['안','신규 생산','신규품 실제 사용','거래 누계','종료 실재고','오래 미사용'],[
            [MODES[mode],f(w(mode,'production.'+good)),f(total(mode,'use_by_good.'+good)),f(w(mode,'trade_goods.'+good)),
             f(w(mode,'remaining_goods.'+good)),f(w(mode,'aged_unused_goods.'+good))] for mode in MODES]))
    add('</section>')

    add('<section><h2>12. 검사 범위와 아직 확인하지 않은 것</h2>')
    add(table(['항목','확인한 범위'],[
        ['정식 결과',f(meta['completed_games'],0)+'개 고유 게임; 예비 실행 제외'],
        ['테스트',f(tests['test_count'],0)+'개 통과 기록과 정식 실행 해시 일치'],
        ['독립 감사',audit['status']+'; 평가 검사 '+f(audit['checks_evaluated'],0)+'개'],
        ['현금 원장','본 비교 1,400게임 × 9개국 × 9라운드 = 113,400행'],
        ['원료 원장','본 비교 1,400게임 × 9개국 × 9라운드 = 113,400행'],
        ['상세 대표 추적','본 비교 7게임 + 원료 거부 45게임 = 52게임'],
        ['실행 중 불변조건',f(meta['verification_calls'],0)+'회; 보고된 실패 '+str(meta['verification_failures'])],
    ]))
    add('<p>모든 게임의 요약과 본 비교 원장을 확인하고, 실물 출처와 세부 소비 경로는 저장된 대표 추적에서 대조했다. '
        '4,850게임의 모든 내부 경로를 외부에서 다시 실행했다는 뜻은 아니다. '
        '어떤 후보가 좋아 보이더라도 시작 자산 효과, 세대별 원료 부담, 국가별 생활·발전 기회를 함께 검토해야 한다.</p>')
    add('<div class="note"><h3>남은 핵심 과제: 원료 확보와 점수의 국가별 연결</h3>'
        '<p>bridge에서 메카니아가 광물을 거부할 때의 총점 차이는 '
        +signed(statistics.mean(stress_diff('bridge','Mechania','no_ore','countries.Mechania.score')),4)
        +'점, 테크니아는 '+signed(statistics.mean(stress_diff('bridge','Technia','no_ore','countries.Technia.score')),4)
        +'점이다. 테크니아는 투자 차이 '+signed(statistics.mean(stress_diff('bridge','Technia','no_ore','countries.Technia.investment')),3)
        +'G, 원료 미충족 생산 진단 '+f(sm('bridge','Technia','production_failures','no_ore'),3)
        +'회와 전자제품 3세대 도달 중단에도 생산 능력 점수 만점을 유지했다.</p>'
        '<p>테크니아 반값 전략의 점수 우위도 남아 있다. 따라서 <strong>원료 수입과 자동 운영의 발전 판단이 연결된 결과와 '
        '국가별 평가 공정성의 해결은 분리해야 한다.</strong> 이 불균형은 현재 점수식을 유지한 채 드러낸 남은 과제이며, '
        '이번 단계에서 점수나 학생 개발 조건을 바꾸어 해결한 것처럼 표시하지 않는다.</p></div>')
    for key in ('audit_scope','raw_audit_scope','recommendation_audit_scope'):
        scope = audit.get(key)
        if scope:
            text = scope if isinstance(scope,str) else json.dumps(scope,ensure_ascii=False,indent=2)
            add('<details><summary>독립 감사의 '+escape(key)+' 원문</summary><pre>'+escape(text)+'</pre></details>')
    add('<ul><li>추가 3개국의 성장 목표가 아직 보정되지 않아 9개국 종합 순위의 공정성을 확정하지 않았다.</li>'
        '<li>원료 거래량 증가는 원료 확보의 부담 증가일 수도 있다. 거래량을 늘리는 것 자체를 학습 성공으로 보지 않았다.</li>'
        '<li>초기 지급품이 줄어 성장 점수가 높아지는 부분과 실제 종료 자산·활용 개선을 분리해야 한다.</li>'
        '<li>실제 학생 3명의 이해·참여, 개별 접속 웹앱, 동시 거래와 협상 화면, 40분+40분 수업 속도는 검증하지 않았다.</li>'
        '<li>3단계인 고급 기계 구매·연구·사용의 완전한 의사결정 연동은 이번 단계의 작업이 아니다.</li></ul></section>')

    add('<section><h2>13. 학생에게는 사용 목적만 간단히 보여 주기</h2>'
        '<p>세부 원료 계산과 출처 추적은 자동 처리하고, 학생에게는 다음 생산 또는 연구에 필요한 물건과 부족량을 짧게 제시하는 방향이 적합하다. '
        '처음부터 받은 원료로 생산한 것인지, 수입한 원료로 생산한 것인지 결과 피드백에서 구분하면 무역의 필요를 설명하는 데 도움이 된다.</p>'
        '<div class="note"><h3>수업용 피드백 카드 제안</h3>'
        '<p><strong>이 원료는 어디에 쓰일까요?</strong><br>필요한 물건: 다음 생산용 광물<br>'
        '사용 목적: 기계 만들기 / 기술 연구 중 실제 목적 표시<br>거래 뒤 확인: 처음 받은 원료 사용 · 수입한 원료 사용 · 남은 원료</p>'
        '<p class="technical">화면 설계 제안이며 학생용 화면의 구현·사용성 검증 결과가 아니다. 실제 수량과 가격은 해당 게임 상태에서 표시한다.</p></div>'
        '<h3>마무리 질문</h3><ol>'
        '<li>이번에 사용한 원료는 처음 받은 물건이었을까, 다른 나라에서 수입한 물건이었을까?</li>'
        '<li>같은 원료가 상품을 만드는 데 쓰인 경우와 기술을 발전시키는 데 쓰인 경우에는 어떤 차이가 있었을까?</li>'
        '<li>원료를 덜 사고 돈을 남겼을 때, 생산·국민 생활·다음 발전에는 어떤 변화가 생겼을까?</li>'
        '</ol></section>')

    add('<section><h2>14. 재현 방법과 원본 기록</h2>'
        '<p>이번 검증은 Python 3.12 환경에서 수행했다. 프로젝트의 기존 결과를 보존하며 새 결과 폴더에 실행한다. '
        '보고서 생성기는 게임을 다시 실행하지 않는다.</p>'
        '<pre>python3 -m unittest test_previous test_fixes test_costs test_expansion test_budget test_machinery test_recommendation test_raw_resources\n'
        'python3 run_raw_validation.py --n 200 --stress-n 30 --workers 4 --output-dir reproduced_raw_results\n'
        'python3 audit_raw_results.py --results reproduced_raw_results\n'
        'python3 build_raw_report.py --results reproduced_raw_results --report REPRODUCED_V8_KO.html</pre>'
        '<p>코드와 테스트가 기록된 해시와 같아야 정식 실행이 시작된다. 수정했다면 실제 테스트 실행과 검증 기록을 새로 남겨야 한다. '
        '예비 결과나 일부 완료 파일로 정식 보고서를 만들지 않는다.</p>')
    add(table(['파일','내용'],[
        ['runs.jsonl.gz','전체 정식 게임의 국가·세계 결과'],['round_ledgers.jsonl.gz','본 비교의 국가·라운드별 현금 원장'],
        ['raw_round_ledgers.jsonl.gz','본 비교의 국가·라운드별 원료 수입·소비·재고와 생활'],
        ['first_seed_traces.json.gz','본 비교와 원료 거부의 대표 52게임 실물·거래·원료 추적'],
        ['summary.json','그룹 평균·같은 시드 대응 차이'],['run_manifest.json / pre_run_plan.json','고정 조건·완료 수·소스 해시'],
        ['tests_manifest.json','실제 통과 테스트 수·코드·테스트 해시'],['independent_audit.json','저장 결과의 독립 검사'],
    ]))
    add('<p class="technical">정식 결과 SHA-256: <code>'+hashlib.sha256((folder/'runs.jsonl.gz').read_bytes()).hexdigest()
        +'</code><br>결과 폴더: <code>'+escape(folder.name)+'</code></p></section>')

    add('<details class="appendix"><summary>부록: 3개 산업국의 9라운드 원료와 생활</summary>')
    for mode in MODES:
        add('<h2>'+MODES[mode]+'</h2>')
        for name in INDUSTRIAL:
            rr = []
            for round_no in range(1,10):
                raw = raw_rounds[(mode,name,round_no)]
                cash = cash_rounds[(mode,name,round_no)]
                rr.append([round_no,f(statistics.mean(r['cash_end'] for r in cash)),f(statistics.mean(r['happy'] for r in raw))]
                    +[f(statistics.mean(r['goods'][good][key] for r in raw)) for good in RAW for key in ('imports','production','research','stock')])
            add('<h3>'+COUNTRIES[name]+'</h3>')
            add(table(['라운드','종료 현금 G','만족도','광물 수입','광물 생산 사용','광물 연구 사용','광물 재고',
                       '연료 수입','연료 생산 사용','연료 연구 사용','연료 재고'],rr))
    add('</details><footer>이 문서는 정식 4,850게임·테스트 기록·독립 감사 통과를 확인한 뒤 저장 자료로 생성된다. '
        '표시 숫자는 반올림했으며, 외부 자산과 스크립트가 없는 정적 HTML 보고서다.</footer>')

    css = '''*{box-sizing:border-box}html{color-scheme:light}body{margin:0;background:#edf2f5;color:#20343e;font:16px/1.8 "Noto Sans KR","Malgun Gothic",Arial,sans-serif}main{max-width:1240px;margin:auto;background:#fff;padding:48px 54px 64px}header{border-bottom:5px solid #14656b;padding-bottom:24px}.eyebrow{font-size:13px;color:#14656b;font-weight:700}h1{font-size:38px;line-height:1.35;margin:12px 0 20px}h2{font-size:24px;line-height:1.5;color:#104e57;margin:0 0 16px}h3{font-size:19px;margin:25px 0 10px}h4{font-size:15px}p{margin:12px 0}section{padding:30px 0;border-bottom:1px solid #d8e3e7}.lead{background:#eaf5f2;margin:26px -16px 22px;padding:24px;border:0;border-radius:10px}.note{padding:15px 18px;background:#fff5df;border-left:4px solid #c18a2c}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.cards div{background:#f0f5f8;border-radius:8px;padding:16px}.cards b{display:block;font-size:27px;color:#14656b}.cards span{font-size:12px;color:#526d78}.table-wrap{overflow-x:auto;margin:17px 0}table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.65}th,td{padding:9px 10px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}thead th{background:#e8f0f4;font-weight:700}tbody th{font-weight:600}tbody tr:nth-child(even){background:#f7fafb}code{font-size:.9em;background:#edf1f5;padding:2px 5px;border-radius:3px;overflow-wrap:anywhere}pre{background:#1c3540;color:#edf8f6;border-radius:8px;padding:17px;overflow:auto;font-size:12px;line-height:1.7}li{margin:9px 0}details{margin:20px 0;background:#f1f5f7;padding:18px;border-radius:8px}summary{cursor:pointer;font-weight:700}.technical{font-size:12px;overflow-wrap:anywhere}footer{font-size:12px;color:#607984;padding-top:28px}.appendix h2{margin-top:28px}@media(max-width:760px){main{padding:24px 17px}h1{font-size:29px}h2{font-size:21px}.cards{grid-template-columns:repeat(2,1fr)}.cards b{font-size:23px}table{font-size:11px}th,td{padding:8px}.lead{margin-left:0;margin-right:0}}@media print{body{background:white;font-size:10px}main{padding:0;max-width:none}h1{font-size:25px}h2{font-size:17px}h3{font-size:14px}section{padding:18px 0}.lead{margin:16px 0;padding:16px}.cards b{font-size:19px}.cards span{font-size:9px}table{font-size:8px}th,td{padding:4px 5px}tr{break-inside:avoid}h2,h3{break-after:avoid}.table-wrap{overflow:visible}details{background:white}pre{white-space:pre-wrap;color:#20343e;background:#f1f5f7}.appendix:not([open]){display:none}}'''
    html = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' \
        '<title>#11 무역 게임 v8 초기 원료·기계 투입량 검증</title><style>'+css+'</style></head><body><main>'+''.join(out)+'</main></body></html>\n'
    need('<script' not in html.lower(),'Static report cannot contain scripts.')
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(html,encoding='utf-8')
    print(json.dumps({'report':str(report),'formal_games':len(rows),'tests':tests['test_count'],'audit':audit['status'],
                      'cash_ledger_rows':sum(len(g['rows']) for g in ledgers['round_ledgers.jsonl.gz']),
                      'raw_ledger_rows':sum(len(g['rows']) for g in ledgers['raw_round_ledgers.jsonl.gz'])},ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=DEFAULT_RESULTS)
    parser.add_argument('--report',type=Path,default=ROOT/'TRADE_RAW_REVIEW_V8_KO.html')
    args = parser.parse_args()
    build(args.results.resolve(),args.report.resolve())


if __name__=='__main__':
    main()
