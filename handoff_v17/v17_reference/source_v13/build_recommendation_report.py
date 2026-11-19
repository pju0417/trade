"""Build a standalone Korean v7 report from completed, audited saved records.

This module never imports an economic engine and never starts a simulation.
The formal schedule is deliberately checked before any report is written.
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
DEFAULT_RESULTS = ROOT / 'advice_results'
COUNTRIES = {
    'Tropia': '트로피아', 'Grainia': '그레니아', 'Oilia': '오일리아',
    'Mechania': '메카니아', 'Mineria': '미네리아', 'Technia': '테크니아',
    'Novia': '노비아', 'Agrea': '아그레아', 'Ferria': '페리아',
}
ORIGINAL = tuple(COUNTRIES)[:6]
GOODS = {
    'banana': '바나나', 'wheat': '밀', 'ore': '광물', 'fuel': '연료',
    'machine': '기계', 'electronics': '전자제품',
}
MODES = {
    'baseline': '기준선', 'price': '가격 추천', 'listing': '가격 + 등록량',
    'planning': '투자·주력 추천', 'responsive': '가격 + 투자·주력',
    'combined': '전체 결합',
}
STRESS_MODES = ('baseline', 'price', 'responsive', 'combined')
SCENARIOS = tuple((name, style) for name in ORIGINAL for style in ('cheap', 'idle')) + (
    (None, 'normal'), (None, 'no_trade'), ('Mechania', 'no_raw'),
)
MAIN_SEEDS = range(44000, 44200)
STRESS_SEEDS = range(46000, 46030)
EXPECTED_GAMES = len(MODES) * len(MAIN_SEEDS) + len(STRESS_MODES) * len(SCENARIOS) * len(STRESS_SEEDS)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_lines(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def need(condition, message):
    if not condition:
        raise ValueError(message)


def get(obj, path):
    for key in path.split('.'):
        obj = obj[key]
    return obj


def f(value, digits=2):
    return f'{value:,.{digits}f}'


def signed(value, digits=2):
    return f'{value:+,.{digits}f}'


def paired_stats(values):
    values = list(values)
    avg = statistics.mean(values)
    margin = 1.96 * statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0
    return avg, avg - margin, avg + margin


def interval(values):
    avg, low, high = paired_stats(values)
    return f'{signed(avg)} [{signed(low)}, {signed(high)}]'


def table(headers, rows, caption=None):
    content = '<div class="table-wrap"><table>'
    if caption:
        content += '<caption>' + escape(caption) + '</caption>'
    content += '<thead><tr>' + ''.join('<th scope="col">' + escape(str(x)) + '</th>' for x in headers) + '</tr></thead><tbody>'
    for row in rows:
        content += '<tr>' + ''.join(('<th scope="row">' if index == 0 else '<td>') + escape(str(value))
                                  + ('</th>' if index == 0 else '</td>') for index, value in enumerate(row)) + '</tr>'
    return content + '</tbody></table></div>'


def load_completed(folder):
    required = ('summary.json', 'run_manifest.json', 'runs.jsonl.gz',
                'round_ledgers.jsonl.gz', 'first_seed_traces.json.gz', 'independent_audit.json')
    missing = [name for name in required if not (folder / name).is_file()]
    need(not missing, 'Formal files are incomplete; no report was written: ' + ', '.join(missing))
    summary = read_json(folder / 'summary.json')
    meta = summary['metadata']
    manifest = read_json(folder / 'run_manifest.json')
    need(meta == manifest, 'summary metadata and run_manifest differ.')
    need(meta['completed_games'] == EXPECTED_GAMES == 3000, 'Exactly 3,000 completed formal games are required.')
    need(meta['main_games'] == 1200 and meta['stress_games'] == 1800, 'Formal phase counts differ from the fixed schedule.')
    need(meta['main_seed_range'] == [44000, 44199] and meta['stress_seed_range'] == [46000, 46029], 'Unexpected formal seed bands.')
    need(meta['rounds'] == 9 and meta['countries'] == 9 and meta['physical_mode'] == 'coupled', 'Physical comparison conditions differ.')
    need(meta['source_unchanged'] is True and meta['pilot_excluded'] is True, 'Frozen-source/pilot-exclusion gate failed.')
    audit = read_json(folder / 'independent_audit.json')
    need(audit['status'] == 'passed' and not audit['errors'] and not audit.get('warnings'), 'The complete independent audit must pass before report publication.')
    need(audit['completed_runs'] == EXPECTED_GAMES, 'Audit does not cover the full formal run set.')

    tests_path = folder / 'tests_manifest.json'
    if not tests_path.is_file():
        tests_path = DEFAULT_RESULTS / 'tests_manifest.json'
    need(tests_path.is_file(), 'The verified tests_manifest.json is required.')
    tests = read_json(tests_path)
    need(tests['passed'] is True and tests['test_count'] == meta['tests_completed'], 'Recorded test results differ from the formal manifest.')
    need(hashlib.sha256(tests_path.read_bytes()).hexdigest() == meta['tests_manifest_sha256'], 'Test manifest hash differs from the frozen formal run.')

    rows = read_lines(folder / 'runs.jsonl.gz')
    keys = [(r['phase'], r['mode'], r['seed'], r['focal'], r['style']) for r in rows]
    expected = {('main', mode, seed, None, 'normal') for mode in MODES for seed in MAIN_SEEDS}
    expected.update(('stress', mode, seed, focal, style) for mode in STRESS_MODES
                    for focal, style in SCENARIOS for seed in STRESS_SEEDS)
    need(len(keys) == len(set(keys)) == EXPECTED_GAMES and set(keys) == expected, 'Saved records do not match all unique formal schedule cells.')
    groups = defaultdict(list)
    for row in rows:
        need(set(row['countries']) == set(COUNTRIES), 'Country set differs from nine-country report contract.')
        groups[(row['phase'], row['mode'], row['focal'], row['style'])].append(row)

    ledgers = read_lines(folder / 'round_ledgers.jsonl.gz')
    ledger_keys = [(r['mode'], r['seed']) for r in ledgers]
    need(len(ledger_keys) == len(set(ledger_keys)) == 1200, 'All main-run round ledgers are required.')
    need(set(ledger_keys) == {(mode, seed) for mode in MODES for seed in MAIN_SEEDS}, 'Main-ledger schedule mismatch.')
    expected_cells = {(name, round_no) for name in COUNTRIES for round_no in range(1, 10)}
    for ledger in ledgers:
        cells = [(r['country'], r['round']) for r in ledger['rows']]
        need(len(cells) == 81 and set(cells) == expected_cells, 'An incomplete country-by-round ledger was found.')
    return summary, meta, audit, tests, rows, groups, ledgers


def build(folder, report):
    summary, meta, audit, tests, rows, groups, ledgers = load_completed(folder)

    @lru_cache(maxsize=None)
    def mean(mode, path, phase='main', focal=None, style='normal'):
        return statistics.mean(get(row, path) for row in groups[(phase, mode, focal, style)])

    def country(mode, name, field):
        return mean(mode, f'countries.{name}.{field}')

    def world(mode, field):
        return mean(mode, 'world.' + field)

    def sum_country(mode, field):
        return sum(country(mode, name, field) for name in COUNTRIES)

    def metric(row, key):
        if key == 'all_useful_exports':
            return sum(c['useful_exports'] for c in row['countries'].values())
        if key == 'all_used_new':
            return sum(sum(c['use_by_good'].values()) for c in row['countries'].values())
        return get(row, key)

    def pair(a, b, key, phase='main', focal=None, style='normal'):
        left = {r['seed']:r for r in groups[(phase, a, focal, style)]}
        right = {r['seed']:r for r in groups[(phase, b, focal, style)]}
        need(left.keys() == right.keys(), 'Paired result seeds differ.')
        return [metric(right[s], key) - metric(left[s], key) for s in sorted(left)]

    def stress_delta(mode, focal, style, key):
        control = {r['seed']:r for r in groups[('stress', mode, None, 'normal')]}
        selected = groups[('stress', mode, focal, style)]
        return [metric(r, key) - metric(control[r['seed']], key) for r in selected]

    def change(a, b, key):
        return f(mean(a, key)) + ' → ' + f(mean(b, key))

    def score_parts(c):
        used = sum(c['use_by_good'].values())
        made = sum(c['produced'].values())
        use = 10 * used / max(1, made)
        return {'economic':c['economic'], 'happy':c['happy']/4, 'trade':c['trade'],
                'capacity':c['industry']-use, 'use':use, 'total':c['score']}

    # Recalculate selected summary claims from raw rows; a mismatched stale
    # summary must never silently accompany a newly generated report.
    for mode in MODES:
        experiment = summary['experiments'][f'main:{mode}:None:normal']
        need(experiment['n'] == 200, 'Summary group count mismatch.')
        for path in ('world.happy', 'world.inventory', 'world.listed', 'world.aged_unused',
                     'world.trade_units', 'countries.Mechania.cash'):
            need(math.isclose(mean(mode, path), experiment['metrics'][path]['mean'], abs_tol=1e-9), 'Summary/raw value mismatch: ' + path)

    round_rows = defaultdict(list)
    for ledger in ledgers:
        for row in ledger['rows']:
            round_rows[(ledger['mode'], row['country'], row['round'])].append(row)

    parts = []
    add = parts.append
    add('<header><p class="eyebrow">아이디어 노트 · #11 무역 게임 · 설계와 모형 검증</p>'
        '<h1>판매·투자 추천을 바꾸면<br>무역과 실제 활용도 바뀔까?</h1>'
        '<p>v7 정식 비교 · 9개국 · 9라운드 · 6가지 추천 정책</p></header>')
    add('<section class="lead"><h2>1단계 판정: 가격 추천을 다음 검증의 기준선 후보로 유지</h2>'
        '<p><strong>가격 추천과 필요한 물건의 판매 보호 수정은 다음 검증의 기준선 후보로 남긴다.</strong> '
        '공정성이 검증된 최종 기본안으로 확정한 것은 아니다. 투자·주력 추천과 공개 등록량 제한은 '
        '별도 수정·비교 대상으로 두고 전체 묶음을 자동 채택하지 않는다.</p>'
        '<p>기존 v6의 생산·원료 규칙을 고정하고 가격, 공개 판매 등록량, 투자와 주력 산업 추천을 비교했다. '
        '판매 창에 보이는 물건이 줄었다는 이유만으로 과잉 생산이 해결되었다고 판정하지 않는다. '
        '실제 보유 재고, 다른 나라에서 사용된 수출품, 국민 만족도를 함께 확인한다.</p>')
    add('<p>기준선 → 가격 추천에서 세계 평균 만족도는 <strong>' + change('baseline', 'price', 'world.happy')
        + '</strong>, 오래 남은 미사용 재고는 <strong>' + change('baseline', 'price', 'world.aged_unused')
        + '</strong>이다. 가격·투자·주력 추천에 등록량 제한까지 더하면 공개 매물은 <strong>'
        + change('responsive', 'combined', 'world.listed') + '</strong>, 전체 실재고는 <strong>'
        + change('responsive', 'combined', 'world.inventory') + '</strong>로 바뀐다.</p>')
    add('<p>가격 추천의 현금 격차는 <strong>' + change('baseline', 'price', 'world.all_country_cash_gap')
        + 'G</strong>로 좁아졌으나 실재고는 <strong>' + change('baseline', 'price', 'world.inventory')
        + '</strong>로 거의 같았다. 오래 미사용 재고의 증가는 남은 문제다. '
        '현금 격차 감소만으로 무역 학습이나 국가별 평가의 공정성이 확인된 것은 아니다.</p></section>')
    card_values = [(f(meta['completed_games'], 0), '정식 완료 게임'),
                   (f(tests['test_count'], 0), '기록과 해시를 대조한 통과 테스트'),
                   (f(meta['verification_calls'], 0), '실행 중 불변조건 검사'),
                   (f(sum(len(x['rows']) for x in ledgers), 0), '본 비교의 국가·라운드 원장 행')]
    add('<div class="cards">' + ''.join('<div><b>' + escape(v) + '</b><span>' + escape(k) + '</span></div>' for v, k in card_values) + '</div>')

    add('<section><h2>1. 유지한 결정과 이번에 바꾼 부분</h2>'
        '<p>9개국의 시작 조건, 9라운드, v6의 수요에 맞춘 기계 생산과 생산량 비례 원료 소비, '
        '만족도 연계 운영수입, 기계 세대와 기술 개발의 선행 조건, 시장 기준가 공식, 화폐 거래·물물교환, 기존 점수식을 유지했다. '
        '별도 정비 비용을 추가하는 v6 service 후보는 사용하지 않았다.</p>')
    add(table(['코드', '비교 이름', '추가된 추천'], [
        ['baseline', MODES['baseline'], 'v6 coupled 그대로'],
        ['price', MODES['price'], '공개 판매 가격 추천'],
        ['listing', MODES['listing'], '가격 추천 + 공개 등록 수량 제한'],
        ['planning', MODES['planning'], '투자·주력 산업 추천'],
        ['responsive', MODES['responsive'], '가격 + 투자·주력 산업 추천'],
        ['combined', MODES['combined'], '가격 + 투자·주력 산업 추천 + 공개 등록 수량 제한'],
    ]))
    add('<p class="note"><strong>공통 수정이 섞여 있다.</strong> 기준선 이외의 모든 안에는 필요한 등급의 기계와 생활·운영·연구용 물건을 '
        '판매에서 보호하도록 회수하는 수정이 공통으로 들어갔다. 따라서 기준선과의 차이를 가격 한 요인의 순수한 인과 효과로 단정할 수 없다. '
        '같은 등급 안에서는 이미 자유롭게 쓸 수 있는 물건을 우선 보호하며, 직접 거래와 공개 시장의 잉여 판정도 일치시켰다.</p>'
        '<h3>현재의 판단과 다음 작업</h3>')
    add(table(['대상', '이번 판단', '근거와 다음 확인'], [
        ['가격 추천 + 판매 보호', '후속 검증의 기준선 후보로 유지',
         '현금 격차는 줄고 만족도는 비슷하다. 오래 미사용 재고는 증가하여 과잉 해결안으로 보지는 않는다.'],
        ['투자·주력 추천', '진단용으로 유지하고 수정',
         '전체 재고 감소와 함께 농업·자원 국가의 투자 기회 감소, 일부 국가의 현금 집중을 확인해야 한다.'],
        ['공개 등록량 제한', '기본안으로 채택하지 않음',
         '공개 매물 감소와 전체 실재고 감소가 일치하지 않는다. 직접·물물교환을 포함한 효과를 다시 볼 필요가 있다.'],
        ['2단계 원료 묶음·초기 재고', '다음 검증; v7에서 실행하지 않음',
         '가격 추천 후보를 바탕으로 원료 수요와 초기 지급분을 별도로 점검한다.'],
        ['3단계 기계 구매·기술 개발 묶음', '이후 검증; v7에서 완전 연동하지 않음',
         'v7은 선행 기계와 원료의 비용 추정까지 포함한다. 구매·연구·사용을 묶은 완전한 의사결정은 별도 작업이다.'],
    ]))
    add('</section>')

    add('<section><h2>2. 자동 추천이 실제로 하는 일</h2>')
    add(table(['영역', '추천 방식', '학생에게 보여 줄 설명'], [
        ['판매 가격', '최근 2라운드의 자기 공개 매물과 실제 판매, 재고 나이, 같은 등급 이상 공개 경쟁 매물을 확인한다. '
         '기준가의 100%에서 시작하고 오래 미판매이면 80%·60%, 충분히 팔렸으면 105%를 시험한다. 추천 하한은 기준가의 50%다.',
         '“최근 잘 안 팔려서 가격을 낮춰 보자.”'],
        ['등록 수량', '목표 공개 매물 = 1 + 최근 2라운드의 라운드당 자기 판매량 × 2의 올림. 최소 2, 최대 10, 실제 잉여 수량 이내. '
         '현재 등록 중인 물건까지 합친 목표다.', '“지금은 이 정도만 시장에 내놓자.”'],
        ['투자', '남은 라운드, 자기 재고, 자기 최근 판매, 국내 사용 목적, 개발·선행 기계·추가 원료 비용을 보고 추가 산출의 활용 가능성을 비교한다.',
         '“새 설비를 남은 기간에 쓸 수 있을까?”'],
        ['주력 산업', '실제 추가 생산 보너스 중 국내 사용 또는 판매될 것으로 예상되는 양을 비교한다.',
         '“다음 라운드에는 필요한 물건을 더 만들자.”'],
    ]))
    add('<p>50%는 자동 추천의 하한이다. 학생이 정할 수 있는 법적 최저 판매가를 신설한 것이 아니다. '
        '등록 수량 제한도 <strong>공개 시장에 현재 내놓은 물건</strong>에만 적용한다. '
        '직접 화폐 거래와 물물교환에서는 나머지 정당한 잉여 물건도 거래할 수 있으며, 기존 협상 가격 방식을 유지했다. '
        '따라서 공개 등록량 제한이 전체 판매량 제한과 같지 않다.</p>'
        '<h3>이번에 확인하고 고친 구현 문제</h3><ul>'
        '<li>추천 가격을 계산한 다음 기존 주문 갱신이 이를 덮어쓰던 경로를 수정했다. 가격 추천을 쓰는 안은 최종 공개 주문 가격까지 대조한다.</li>'
        '<li>planning·responsive·combined의 계획 계산에서 식량 주력 보너스를 3으로 예상하던 부분을 실제 생산 규칙의 2에 맞췄다. '
        '실제 식량 보너스 자체를 바꾼 것은 아니며 price·listing은 기존 주력 선택 방식을 유지한다.</li>'
        '<li>필요한 고급 기계가 판매 목록에 묶인 채 낮은 등급만 남는 문제를 공통 보호 회수로 보정했다.</li>'
        '</ul></section>')

    add('<section><h2>3. 투자 추천의 불확실성</h2>'
        '<p>추천 점수는 예상 추가 활용 가치 ÷ 추정 비용에 주력 산업 선호 0.30을 더하는 휴리스틱이다. '
        '판정 문턱 0.45와 선호 0.30은 게임 모형의 계수다. 이 값을 넘는다는 것이 실제 순이익이 양수이거나 개발비를 반드시 회수한다는 뜻은 아니다.</p>'
        '<p>일반 판매 수요는 최근 자기 판매 속도를 남은 라운드로 연장한다. 신세대 투자 후보를 평가할 때는 기존 판매 흐름에서 얻을 수 있는 가격 차이를 추정하고, '
        '최근 알려진 구매자의 최대 절반 또는 알려진 구매자가 없을 때 최대 1개의 도입 판매 기회를 더한다. '
        '이 도입 기회는 실제 주문이나 한 게임 전체의 확정 판매 한도가 아니며, 후보를 다시 평가할 때 반복 추정될 수 있다. '
        '신세대의 추가 기회는 불확실하다고 표시하지만, 일반 판매 흐름 역시 확정 주문이 아니라 외삽이다. '
        '새 상품을 만들었다는 이유만으로 구매자를 생성하거나 강제로 구형을 폐기시키지 않는다.</p>'
        '<p class="note">새 가격·투자 기회 추천 함수는 자기 거래 기록과 허용된 공개 정보를 사용하며, '
        '다른 나라의 비공개 지갑이나 미래의 실제 판매 결과를 미리 읽지 않는다. 이 제한을 기존의 다른 모든 자동 정책까지 새로 검증한 것으로 확대하지 않는다. '
        '구매할 수 있는 자금과 향후 쓸 목적은 서로 다른 조건이므로 함께 확인해야 한다.</p></section>')

    add('<section><h2>4. 정식 검증 설계</h2>')
    add(table(['구분', '구성', '시드', '게임 수'], [
        ['본 비교', '6가지 안 × 200회', '44000–44199', '1,200'],
        ['반값·무행동', '4가지 안 × 기존 6개국 × 2전략 × 30회', '46000–46029', '1,440'],
        ['대조군·경계 조건', '같은 4가지 안 × 정상·무역 금지·메카니아 원료 수입 거부 × 30회', '46000–46029', '360'],
        ['정식 합계', '규칙과 코드 고정 후 실행', '개발용 시드와 분리', f(meta['completed_games'], 0)],
    ]))
    add('<p>스트레스 비교의 4가지 안은 기준선, 가격 추천, 가격·투자·주력 추천, 전체 결합이다. '
        '42000–42029의 개발용 예비 실행과 같은 시드의 재실행, 단위 테스트·추적용 별도 실행은 정식 평균에 넣지 않았다. '
        '기본 표는 200게임 평균이며 현금은 종료 현금, 만족도는 9라운드 평균이다. G는 게임 화폐다. '
        '대응 차이의 95% 구간은 같은 시드 차이의 평균 ± 1.96 × 표준오차로 계산한다. '
        '이 구간은 모형 안의 시드 변동을 나타내며 실제 학생 모집단의 학습 효과를 나타내지 않는다.</p></section>')

    add('<section><h2>5. 여섯 정책의 세계 결과</h2>')
    add(table(['안', '만족도', '실제 사용 수출품', '거래 수량', '종료 실재고', '오래 미사용', '공개 매물', '9국 현금 격차 G'], [
        [MODES[mode], f(world(mode, 'happy')), f(sum_country(mode, 'useful_exports')), f(world(mode, 'trade_units')),
         f(world(mode, 'inventory')), f(world(mode, 'aged_unused')), f(world(mode, 'listed')), f(world(mode, 'all_country_cash_gap'))]
        for mode in MODES]))
    add('<p>실제 사용 수출품은 자국이 이번 게임에서 생산해 해외에서 한 번 이상 사용된 실물을 국가별로 합친 수량이다. '
        '같은 물건을 되팔아 거래 횟수만 늘리는 것과 구분한다. 거래 수량은 거래 경로를 거친 묶음의 누계이므로 반복 거래가 포함될 수 있다. '
        '현금 격차는 매 게임의 9국 최대 현금 − 최소 현금을 구한 뒤 평균했다.</p><h3>같은 시드에서 바뀐 정도</h3>')
    pair_rows = []
    for a, b in [('baseline', 'price'), ('baseline', 'planning'), ('baseline', 'responsive'),
                 ('price', 'listing'), ('price', 'responsive'), ('responsive', 'combined')]:
        pair_rows.append([MODES[a] + ' → ' + MODES[b]] + [interval(pair(a, b, key)) for key in
                         ('world.happy', 'all_useful_exports', 'world.aged_unused', 'world.inventory')])
    add(table(['변경', '만족도 Δ [95% 구간]', '실사용 수출 Δ [95% 구간]', '오래 미사용 Δ [95% 구간]', '실재고 Δ [95% 구간]'], pair_rows))
    add('</section>')

    add('<section><h2>6. 9개국을 모두 확인하기</h2>'
        '<p>수익성은 현금 한 숫자로 판정하지 않는다. 판매가 늘어 현금이 늘었는지, 투자와 구매를 줄여 현금이 남았는지 다음 표와 현금 원장을 함께 읽는다. '
        '기존 6개국뿐 아니라 추가된 노비아·아그레아·페리아도 같은 지표로 확인한다.</p>')
    for title, field in [('종료 현금 G', 'cash'), ('9라운드 평균 국민 만족도', 'happy'),
                         ('해외에서 실제 사용된 자국 생산 수출품', 'useful_exports'), ('개발·산업 투자 지출 G', 'investment')]:
        add('<h3>' + title + '</h3>')
        add(table(['국가'] + list(MODES.values()), [[COUNTRIES[name]] + [f(country(mode, name, field)) for mode in MODES] for name in COUNTRIES]))
    zero_investment = [COUNTRIES[name] for name in COUNTRIES if country('responsive', name, 'investment') == 0]
    if zero_investment:
        add('<p class="note">가격·투자·주력 추천에서는 ' + escape('·'.join(zero_investment))
            + '의 본 비교 투자 지출이 모든 시드에서 0이었다. 불필요한 투자를 줄이는 효과와 함께 '
            '해당 국가가 산업 성장을 시도할 기회를 갖는지도 검토해야 한다. 남은 현금의 증가를 발전 성과의 증가로 바로 해석하지 않는다.</p>')
    add('<p>기준선 → 가격·투자·주력 추천에서 노비아의 종료 현금은 '
        + f(country('baseline', 'Novia', 'cash')) + ' → ' + f(country('responsive', 'Novia', 'cash'))
        + 'G, 메카니아의 실제 사용 수출품은 ' + f(country('baseline', 'Mechania', 'useful_exports'))
        + ' → ' + f(country('responsive', 'Mechania', 'useful_exports')) + ', 9국 현금 격차는 '
        + f(world('baseline', 'all_country_cash_gap')) + ' → ' + f(world('responsive', 'all_country_cash_gap'))
        + 'G이다. 재고가 줄어도 혜택이 모든 국가에 고르게 돌아가는 것은 아니다.</p>')
    add('<details><summary>국가별 현금의 출처와 지출 상세</summary>')
    for mode in MODES:
        add('<h3>' + MODES[mode] + '</h3>')
        add(table(['국가', '시작 G', '판매 수입 G', '구매 지출 G', '투자 G', '운영수입 G', '종료 G', '식량 부족 라운드'], [
            [COUNTRIES[name]] + [f(country(mode, name, key)) for key in
                                ('start_cash', 'revenue', 'purchases', 'investment', 'tax', 'cash', 'food_short_rounds')]
            for name in COUNTRIES]))
    add('</details></section>')

    add('<section><h2>7. 생산·실제 사용·재고를 상품별로 분리</h2>'
        '<p>아래의 실제 사용은 이번 게임의 신규 생산 실물 중 적어도 한 번 사용된 수량이다. 초기 지급품과 반복 사용 횟수는 제외했다. '
        '내구재는 사용 후에도 보유 재고에 남을 수 있다. 오래 미사용 재고는 생산 또는 초기 지급 뒤 2라운드 이상 지나도록 한 번도 사용되지 않은 보유품이다. '
        '이것은 모든 재고의 손실액이나 폐기 비용을 뜻하지 않는다.</p>')
    for good in GOODS:
        add('<h3>' + GOODS[good] + '</h3>')
        add(table(['안', '신규 생산', '신규품 실제 사용', '종료 실재고', '오래 미사용', '공개 매물', '거래 누계'], [
            [MODES[mode], f(world(mode, 'production.' + good)), f(sum_country(mode, 'use_by_good.' + good)),
             f(world(mode, 'remaining_goods.' + good)), f(world(mode, 'aged_unused_goods.' + good)),
             f(sum_country(mode, 'listed_by_good.' + good)), f(world(mode, 'trade_goods.' + good))]
            for mode in MODES]))
    add('<p class="note"><strong>등록량 제한의 숨은 재고 문제:</strong> 가격·투자·주력 추천 → 전체 결합에서 공개 매물 변화는 '
        + signed(world('combined', 'listed')-world('responsive', 'listed')) + ', 전체 실재고 변화는 '
        + signed(world('combined', 'inventory')-world('responsive', 'inventory')) + ', 오래 미사용 재고 변화는 '
        + signed(world('combined', 'aged_unused')-world('responsive', 'aged_unused')) + '이다. '
        '등록을 취소한 물건은 사라지지 않는다. 매물 감소와 실재고 감소를 따로 평가해야 한다.</p></section>')

    add('<section><h2>8. 공개 시장 밖의 거래와 기계의 실제 기여</h2>')
    add(table(['안', '공개 시장 수량', '직접 거래 수량', '물물교환 수량', '실제 사용 신규 기계', '초기 포함 사용 기계', '설비 지원 횟수', '설비 추가 생산량'], [
        [MODES[mode]] + [f(sum_country(mode, 'channel_stats.' + channel + '.sold_units')) for channel in ('market', 'direct', 'barter')]
        + [f(world(mode, key)) for key in ('machine_unique_used', 'machine_unique_used_including_initial', 'equipment_use_episodes', 'equipment_extra_output')]
        for mode in MODES]))
    add('<p>물물교환의 양은 교환 양쪽의 상품 이동을 모두 센다. 물물교환에 가상의 현금 판매액을 붙이지 않았다. '
        '기계의 실물 사용 수는 같은 기계를 한 번만 세고, 설비 지원 횟수는 여러 번의 사용을 센다. '
        '생산 공장이 효율적으로 가동되는 것과 수출품이 해외에 도움이 되는 것은 각각 별도 성과다.</p>')
    add(table(['메카니아 지표'] + list(MODES.values()), [[label] + [f(country(mode, 'Mechania', key)) for mode in MODES] for label, key in [
        ['기계 생산량', 'produced.machine'], ['해외에서 사용된 신규 기계', 'export_used_by_good.machine'],
        ['기계 판매 수입 G', 'sale_by_good.machine'], ['개발 투자 G', 'investment'],
        ['생산에 쓴 광물', 'production_raw.ore'], ['연구에 쓴 광물', 'research_raw.ore'],
        ['종료 보유 기계', 'end_stock_by_good.machine'], ['기계 생산 휴식 횟수', 'machine_pauses'],
    ]]))
    add('</section>')

    add('<section><h2>9. 항상 반값에 파는 전략은 무엇을 바꾸는가?</h2>'
        '<p>cheap은 판매가를 기준가의 절반으로 반복 지정하되 구매·투자는 계속하는 정책이다. '
        '의욕이 없는 실제 학생의 모든 행동을 대신하지 않는다. 낮은 가격은 거래를 성사시키거나 재고를 줄이는 선택이 될 수 있으므로, '
        '무조건 손해를 보도록 설계하지 않았다.</p>'
        '<p>각 행은 같은 시드·같은 추천 정책의 정상 행동과 비교한 해당 국가의 평균 차이다. '
        '총점은 경제력 25점 + 만족도 25점 + 무역 25점 + 산업 25점이다. 산업은 생산 능력 성장 최대 15점과 '
        '신규 생산품의 실제 활용 비율 최대 10점으로 나누었다.</p>')
    for mode in STRESS_MODES:
        score_rows = []
        control = {r['seed']:r for r in groups[('stress', mode, None, 'normal')]}
        for name in ORIGINAL:
            selected = groups[('stress', mode, name, 'cheap')]
            old = [score_parts(control[r['seed']]['countries'][name]) for r in selected]
            new = [score_parts(r['countries'][name]) for r in selected]
            cap_old = sum(x['economic'] >= 25-1e-9 for x in old)
            cap_new = sum(x['economic'] >= 25-1e-9 for x in new)
            score_rows.append([COUNTRIES[name], signed(statistics.mean(stress_delta(mode, name, 'cheap', f'countries.{name}.cash')))]
                + [signed(statistics.mean(b[k]-a[k] for a, b in zip(old, new))) for k in ('economic', 'happy', 'trade', 'capacity', 'use', 'total')]
                + [f'{cap_old}/30 → {cap_new}/30'])
        add('<h3>' + MODES[mode] + '</h3>')
        add(table(['반값 국가', '현금 ΔG', '경제력 Δ점', '만족 Δ점', '무역 Δ점', '생산 능력 Δ점', '활용 Δ점', '총점 Δ점', '경제력 25점 횟수'], score_rows))
    cheap_score_changes = {name:statistics.mean(stress_delta('price', name, 'cheap', f'countries.{name}.score')) for name in ORIGINAL}
    cheap_negative = [COUNTRIES[name] for name, value in cheap_score_changes.items() if value < 0]
    cheap_positive = [COUNTRIES[name] for name, value in cheap_score_changes.items() if value > 0]
    add('<p>가격 추천에서 반값 전략의 평균 총점 차이는 하락 ' + str(len(cheap_negative)) + '개국('
        + escape('·'.join(cheap_negative)) + '), 상승 ' + str(len(cheap_positive)) + '개국('
        + escape('·'.join(cheap_positive)) + ')이었다. 이는 각 30시드의 평균을 묘사한 것이며 '
        '특정 전략이 항상 유리하거나 불리하다거나 실제 학생의 선택이 검증되었다는 뜻은 아니다.</p>')
    add('<p class="note">경제력 점수에 상한이 있어 현금이 줄어도 이미 25점에 도달했다면 점수 차이가 작을 수 있다. '
        '또 생산을 줄이면 활용 점수의 분모가 줄어들 수 있다. 따라서 반값 전략의 총점 상승만으로 학습 효과나 공정성이 개선되었다고 판정하지 않는다. '
        '추가 3개국의 성장 목표는 아직 보정하지 않아 점수와 순위를 만들지 않았다.</p>')
    add('<details><summary>반값 전략의 판매와 실사용 수출 변화</summary>')
    for mode in STRESS_MODES:
        add('<h3>' + MODES[mode] + '</h3>')
        add(table(['반값 국가', '판매 수입 ΔG', '실사용 수출 Δ', '투자 ΔG', '공개 시장 판매 Δ', '직접 판매 Δ', '물물교환 판매 Δ'], [
            [COUNTRIES[name]] + [signed(statistics.mean(stress_delta(mode, name, 'cheap', f'countries.{name}.{key}'))) for key in
             ('revenue', 'useful_exports', 'investment', 'channel_stats.market.sold_units', 'channel_stats.direct.sold_units', 'channel_stats.barter.sold_units')]
            for name in ORIGINAL]))
    add('</details></section>')

    add('<section><h2>10. 한 나라가 무행동일 때 다른 8개국은?</h2>'
        '<p>idle 국가는 자동 생산과 운영수입은 유지하지만 거래·투자를 하지 않는다. 다음 표는 해당 국가가 무행동일 때 '
        '같은 시드의 정상 행동 대비 9개국 각각의 만족도 변화다. 마지막 열은 무행동 국가를 제외한 <strong>다른 8개국 전체</strong>의 변화다. '
        '추가 3개국을 빼고 기존 5개국만 평균하지 않았다.</p>')
    for mode in STRESS_MODES:
        idle_rows = []
        for focal in ORIGINAL:
            deltas = {name:statistics.mean(stress_delta(mode, focal, 'idle', f'countries.{name}.happy')) for name in COUNTRIES}
            idle_rows.append([COUNTRIES[focal]] + [signed(deltas[name]) + (' (본인)' if name == focal else '') for name in COUNTRIES]
                             + [signed(statistics.mean(value for name, value in deltas.items() if name != focal))])
        add('<h3>' + MODES[mode] + '</h3>')
        add(table(['무행동 국가'] + list(COUNTRIES.values()) + ['다른 8국 평균 Δ'], idle_rows))
    add('</section>')

    add('<section><h2>11. 무역 금지와 원료 수입 거부 대조군</h2>')
    add(table(['안', '정상 만족도', '무역 금지 만족도', '만족도 대응 차이 [95% 구간]', '무역 금지 거래량'], [
        [MODES[mode], f(mean(mode, 'world.happy', 'stress')), f(mean(mode, 'world.happy', 'stress', None, 'no_trade')),
         interval(stress_delta(mode, None, 'no_trade', 'world.happy')), f(mean(mode, 'world.trade_units', 'stress', None, 'no_trade'))]
        for mode in STRESS_MODES]))
    add('<h3>메카니아가 광물·연료 수입을 거부할 때</h3>'
        '<p>no_raw는 메카니아의 광물·연료 수입을 화폐 거래와 물물교환 양쪽에서 막는다. '
        '<strong>초기 지급 원료를 제거하지 않고</strong> 같은 시드의 정상군과 비교했다. 초기 재고나 낮은 세대의 기본 생산으로 생긴 산출을 '
        '원료 없이 고급 기계를 계속 만들 수 있다는 증거로 읽지 않는다.</p>')
    no_raw_rows = []
    for mode in STRESS_MODES:
        for style in ('normal', 'no_raw'):
            focal = None if style == 'normal' else 'Mechania'
            no_raw_rows.append([MODES[mode], '정상' if style == 'normal' else '원료 수입 거부'] + [
                f(mean(mode, f'countries.Mechania.{key}', 'stress', focal, style)) for key in
                ('import_goods.ore', 'import_goods.fuel', 'produced.machine', 'machine_fallbacks',
                 'machine_gen', 'cash', 'happy', 'investment')])
    add(table(['안', '조건', '광물 수입', '연료 수입', '기계 생산', '기본 생산 전환', '종료 기계 세대 평균', '현금 G', '만족도', '투자 G'], no_raw_rows))
    add('<p>종료 세대 평균은 분포를 요약한 값이다. 평균 2.4세대라는 종류의 기계가 존재한다는 의미는 아니다.</p></section>')

    add('<section><h2>12. 검증 범위와 아직 남은 과제</h2>')
    audit_rows = [
        ['정식 실행', f(meta['completed_games'], 0) + '개 고유 게임; 본 비교 1,200 + 스트레스 1,800'],
        ['독립 감사', audit['status'] + '; 저장 결과·원장·대표 추적 기록 대조'],
        ['테스트', f(tests['test_count'], 0) + '개 통과 기록; 정식 실행의 해시와 일치'],
        ['독립 검사 평가 수', f(audit['checks_evaluated'], 0)],
        ['실행 중 불변조건', f(meta['verification_calls'], 0) + '회; 보고된 실패 ' + str(meta['verification_failures'])],
        ['원장 범위', '본 비교 1,200게임 × 9개국 × 9라운드 = 97,200행'],
    ]
    add(table(['검증', '확인한 범위'], audit_rows))
    add('<h3>추천 결과와 실제 공개 주문의 일치</h3>')
    add(table(['안', '추천 가격 불일치 누계', '등록 계획 불일치 누계', '보호 재고 공개 등록 누계'], [
        [MODES[mode], f(sum(r['world']['offer_price_mismatches'] for r in groups[('main', mode, None, 'normal')]), 0),
         f(sum(r['world']['listing_plan_violations'] for r in groups[('main', mode, None, 'normal')]), 0),
         '기준선 미검사' if mode == 'baseline' else f(sum(r['world']['protected_offer_violations'] for r in groups[('main', mode, None, 'normal')]), 0)]
        for mode in MODES]))
    add('<p>가격·등록 검사는 해당 추천을 사용하는 경로의 실행 기록에 대한 검사다. 기준선의 보호 위반 필드 0은 '
        '새 보호 규칙의 통과를 의미하지 않아 미검사로 표시했다. 대표 시드의 상세 추적은 6모드 각 1게임이며, '
        '모든 3,000게임의 모든 내부 의사결정 경로를 외부 감사로 재실행한 것은 아니다.</p>')
    scope = audit.get('recommendation_audit_scope')
    if scope:
        rendered_scope = scope if isinstance(scope, str) else json.dumps(scope, ensure_ascii=False, indent=2)
        add('<p>공개 경쟁가격은 저장된 최저 경쟁가격 입력값과 추천 계산을 대조했다. '
            '모든 결정 순간의 다른 나라 공개 매물 전체를 별도로 저장한 것은 아니므로 그 목록까지 독립 재구성했다고 주장하지 않는다. '
            '투자의 미래 생산·원료 예측은 휴리스틱이며 경제적으로 최적인지를 증명한 검사가 아니다.</p>')
        add('<details><summary>독립 감사가 기록한 추천 검사 범위 원문</summary><pre>' + escape(rendered_scope) + '</pre></details>')
    add('<ul><li>국가별 현금·재고·활용의 차이가 남으므로 9개국 평가의 공정성이 확정된 것은 아니다. 추가 3개국의 성장 목표 평가 보정은 별도 과제다.</li>'
        '<li>가격 추천이 거래를 늘려도 실제 활용과 생활 충족을 함께 확인해야 한다. 최고 현금 국가가 가장 많이 수출하거나 가장 많이 도움을 준 국가일 필요는 없다.</li>'
        '<li>등록량 제한으로 남은 물건이 시장 화면에서만 숨을 수 있다. 총실재고·오래 미사용 재고를 항상 함께 표시해야 한다.</li>'
        '<li>규칙 기반 자동 국가의 실행 결과다. 실제 3명 학생의 이해·참여, 동시 접속 웹앱, 협상 화면, 40분+40분의 수업 속도를 검증하지 않았다.</li></ul></section>')

    add('<section><h2>13. 학생의 선택은 간단하게 유지하기</h2>'
        '<p>학생은 “무엇을 사고팔까, 얼마에 팔까, 어디에 투자할까”를 선택하고, 복잡한 추천 계산은 자동 처리하는 형태가 적합하다. '
        '추천 카드에는 추천 수량·가격과 짧은 이유를 먼저 보여 주고, “그대로 적용”과 “직접 바꾸기”를 제공할 수 있다. '
        '추천을 따르지 않았다고 감점하지 않는 것이 이 설계의 취지에 맞는다.</p>'
        '<p>교사용 화면에는 생산 능력과 실제 생산, 판매 수량과 판매 수입, 공개 매물과 전체 실재고를 구분해 두는 것이 좋다. '
        '이 화면 제안은 아직 학생을 대상으로 사용성을 확인한 결과가 아니다.</p>'
        '<div class="note"><h3>수업용 피드백 카드 예시</h3>'
        '<p><strong>바나나 2묶음을 8G에 팔아 볼까요?</strong><br>'
        '기준가는 10G예요. 2라운드 이상 잘 팔리지 않아 가격을 낮춰 보는 추천이에요.<br>'
        '우리 국민에게 필요한 물건은 남겨 두었어요.</p>'
        '<p>선택: 그대로 적용 / 가격·수량 직접 바꾸기<br>'
        '거래 뒤 확인: 팔린 수량 · 받은 돈 · 상대 나라에서 실제 사용됐는지</p>'
        '<p class="technical">숫자는 화면 설명용 예시이며 특정 정식 게임의 결과가 아니다. 실제 카드와 버튼은 아직 구현하지 않았다.</p></div>'
        '<h3>수업 마무리 질문</h3><ol>'
        '<li>우리 나라가 수입한 물건은 국민 생활, 생산, 기술 개발 중 어디에 쓰였을까?</li>'
        '<li>재고가 줄었을 때, 물건이 다른 나라에 팔려 사용된 것인지 생산·등록을 줄인 것인지 어떻게 알 수 있을까?</li>'
        '<li>가격을 낮췄을 때 더 팔린 양과 줄어든 수입을 비교하면, 다음에 필요한 물건을 사고 투자하는 데 어떤 변화가 생겼을까?</li>'
        '</ol><p>다음 2단계에서는 원료 묶음과 초기 재고를 별도로 점검한다. 그 뒤 3단계에서 이미 있는 고급 기술의 선행 기계 조건을 이용해 '
        '<strong>고급 기계 구매·연구·추가 원료를 하나의 사용 목적과 연결하는 의사결정</strong>을 검토한다. '
        'v7은 비용 추정을 포함하지만 이 완전한 연동까지 실행한 것은 아니다. 남은 라운드의 실제 사용 가능성을 확인하며, '
        '구형을 강제로 폐기하거나 구매자를 만들어 수요를 늘리는 규칙은 이번 결과에 넣지 않았다.</p></section>')

    add('<section><h2>14. 재현 방법과 증거 파일</h2>'
        '<p>기존 결과를 보존하면서 프로젝트 폴더 안의 새 결과 폴더로 재현한다. 보고서 생성기는 게임을 다시 실행하지 않고 저장 자료만 읽는다.</p>'
        '<pre>python3 -m unittest test_previous test_fixes test_costs test_expansion test_budget test_machinery test_recommendation\n'
        'python3 run_recommendation_validation.py --n 200 --stress-n 30 --workers 4 --output-dir reproduced_results\n'
        'python3 audit_recommendation_results.py --results reproduced_results\n'
        'python3 build_recommendation_report.py --results reproduced_results --report REPRODUCED_V7_KO.html</pre>'
        '<p>실행 전에 코드와 테스트가 기록된 해시와 일치해야 한다. 코드가 달라졌다면 테스트를 실제로 다시 실행하고 검증 기록을 갱신해야 한다. '
        '기존 기록의 수치만 바꾸어 통과한 것처럼 만들면 안 된다.</p>')
    add(table(['파일', '내용'], [
        ['runs.jsonl.gz', '모든 정식 게임의 국가·세계 결과'],
        ['round_ledgers.jsonl.gz', '본 비교 전체의 국가별 9라운드 현금 원장'],
        ['first_seed_traces.json.gz', '본 비교 첫 시드 44000의 모드별 실물·거래·추천 추적'],
        ['summary.json', '그룹 평균과 동일 시드 대응 차이'],
        ['run_manifest.json / pre_run_plan.json', '고정 조건, 표본 계획, 소스 해시, 실행 완료 기록'],
        ['independent_audit.json', '독립 재계산·보존 검사·점수 분해'],
        ['tests_manifest.json', '실행된 테스트 수와 코드·테스트 해시'],
    ]))
    add('<p class="technical">정식 결과 SHA-256: <code>' + hashlib.sha256((folder / 'runs.jsonl.gz').read_bytes()).hexdigest()
        + '</code><br>정식 결과 폴더: <code>' + escape(folder.name) + '</code></p></section>')

    add('<details class="appendix"><summary>부록: 모든 국가의 9라운드 현금·만족도 원장 평균</summary>')
    for mode in MODES:
        add('<h2>' + MODES[mode] + '</h2>')
        for name in COUNTRIES:
            add('<h3>' + COUNTRIES[name] + '</h3>')
            add(table(['라운드', '시작 G', '판매 G', '구매 G', '투자 G', '운영수입 G', '종료 G', '만족도'], [
                [round_no] + [f(statistics.mean(row[key] for row in round_rows[(mode, name, round_no)])) for key in
                             ('cash_start', 'sales', 'purchases', 'investment', 'operating_income', 'cash_end', 'happy')]
                for round_no in range(1, 10)]))
    add('</details>')
    add('<footer>이 보고서는 정식 결과 3,000건, 대응 원장, 독립 감사 통과를 확인한 뒤 생성되었다. '
        '화면의 수치는 반올림했으며 원본 파일의 값을 기준으로 재계산할 수 있다. 외부 글꼴·스크립트 없이 열 수 있는 정적 HTML 문서다.</footer>')

    css = '''*{box-sizing:border-box}html{color-scheme:light}body{margin:0;background:#edf2f5;color:#20343e;font:16px/1.8 "Noto Sans KR","Malgun Gothic",Arial,sans-serif}main{max-width:1240px;margin:auto;background:#fff;padding:48px 54px 64px}header{border-bottom:5px solid #14656b;padding-bottom:24px}.eyebrow{font-size:13px;color:#14656b;font-weight:700}h1{font-size:38px;line-height:1.35;margin:12px 0 20px}h2{font-size:24px;line-height:1.5;color:#104e57;margin:0 0 16px}h3{font-size:19px;margin:25px 0 10px}p{margin:12px 0}section{padding:30px 0;border-bottom:1px solid #d8e3e7}.lead{background:#eaf5f2;margin:26px -16px 22px;padding:24px;border:0;border-radius:10px}.note{padding:15px 18px;background:#fff5df;border-left:4px solid #c18a2c}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.cards div{background:#f0f5f8;border-radius:8px;padding:16px}.cards b{display:block;font-size:27px;color:#14656b}.cards span{font-size:12px;color:#526d78}.table-wrap{overflow-x:auto;margin:17px 0}table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.65}th,td{padding:9px 10px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}thead th{background:#e8f0f4;font-weight:700}tbody th{font-weight:600}tbody tr:nth-child(even){background:#f7fafb}caption{text-align:left;font-weight:700;padding:8px 0}code{font-size:.9em;background:#edf1f5;padding:2px 5px;border-radius:3px;overflow-wrap:anywhere}pre{background:#1c3540;color:#edf8f6;border-radius:8px;padding:17px;overflow:auto;font-size:12px;line-height:1.7}li{margin:9px 0}details{margin:20px 0;background:#f1f5f7;padding:18px;border-radius:8px}summary{cursor:pointer;font-weight:700}.technical{font-size:12px;overflow-wrap:anywhere}footer{font-size:12px;color:#607984;padding-top:28px}.appendix h2{margin-top:28px}@media(max-width:760px){main{padding:24px 17px}h1{font-size:29px}h2{font-size:21px}.cards{grid-template-columns:repeat(2,1fr)}.cards b{font-size:23px}table{font-size:11px}th,td{padding:8px}.lead{margin-left:0;margin-right:0}}@media print{body{background:white;font-size:10px}main{padding:0;max-width:none}h1{font-size:25px}h2{font-size:17px}h3{font-size:14px}section{padding:18px 0}.lead{margin:16px 0;padding:16px}.cards b{font-size:19px}.cards span{font-size:9px}table{font-size:8px}th,td{padding:4px 5px}tr{break-inside:avoid}h2,h3{break-after:avoid}.table-wrap{overflow:visible}details{background:white}pre{white-space:pre-wrap;color:#20343e;background:#f1f5f7}.appendix:not([open]){display:none}}'''
    html = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' \
           '<title>#11 무역 게임 v7 판매·투자 추천 검증</title><style>' + css + '</style></head><body><main>' + ''.join(parts) + '</main></body></html>\n'
    need('<script' not in html.lower(), 'A static report must not contain scripts.')
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(html, encoding='utf-8')
    print(json.dumps({'report':str(report), 'formal_games':len(rows), 'tests':tests['test_count'],
                      'audit':audit['status'], 'round_ledger_rows':sum(len(x['rows']) for x in ledgers),
                      'source_runs_sha256':hashlib.sha256((folder/'runs.jsonl.gz').read_bytes()).hexdigest()}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=DEFAULT_RESULTS)
    parser.add_argument('--report', type=Path, default=ROOT / 'TRADE_RECOMMENDATION_REVIEW_V7_KO.html')
    args = parser.parse_args()
    build(args.results.resolve(), args.report.resolve())


if __name__ == '__main__':
    main()
