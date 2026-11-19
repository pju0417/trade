"""Build the Korean national-resource report from completed, audited v17 files.

This program reads JSON evidence only. It never imports or runs an economic game.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SUMMARY='operating_results/summary.json'
RUN='operating_results/run_manifest.json'
SMOKE='operating_results/smoke/smoke_manifest.json'
AUDIT='operating_results/independent_audit.json'
TEST='semantic_tests.json'
PROTOCOL='OPERATING_PROTOCOL_V17.json'
SELECTION='CANDIDATE_SELECTION_V17.json'
NAMES=('Tropia','Grainia','Oilia','Mechania','Mineria','Technia')
ADDED=('Novia','Agrea','Ferria')
KO=dict(zip(NAMES+ADDED,('트로피아','그레니아','오일리아','메카니아','미네리아','테크니아','노비아','아그레아','페리아')))
PROFILES=('none','light','regular','daily')
PKO={'none':'기존 · 운영 수요 없음','light':'완만 · 연료3/광물2','regular':'중간 · 연료4/광물3','daily':'경계 · 연료9/광물3'}
SHORT={'none':'기존','light':'완만','regular':'중간','daily':'매 라운드 연료'}
MODES=('baseline','electronics_input')
MKO={'baseline':'기존 제조 경제','electronics_input':'전자산업 원료 추가 조건'}
STKO={'minimum':'최저가 반복','minimum_passive':'최저가·투자 중단','idle':'무행동','invest':'투자 중심','trade':'무역 중심'}
DATA={}


def esc(value):return html.escape(str(value),quote=True)
def load(file):
    if file not in DATA:DATA[file]=json.loads((ROOT/file).read_text(encoding='utf-8'))
    return DATA[file]
def at(file,parts):
    value=load(file)
    for k in parts:value=value[int(k)] if isinstance(value,list) else value[k]
    return value
def pointer(parts):return '/'+ '/'.join(str(x).replace('~','~0').replace('/','~1') for x in parts)
def num(file,parts,digits=2,scale=1,sign=False):
    value=at(file,parts);assert type(value) in (int,float),(file,parts)
    text=format(value*scale,('+' if sign else '')+',.'+str(digits)+'f')
    return f'<span data-file="{esc(file)}" data-pointer="{esc(pointer(parts))}" data-digits="{digits}" data-scale="{scale}" data-sign="{str(sign).lower()}">{text}</span>'
def s(parts,**kwargs):return num(SUMMARY,parts,**kwargs)
def key(mode,profile,phase='main',scenario='None:normal'):return f'{phase}:{mode}:{profile}:{scenario}'
def mean(mode,profile,field,phase='main',scenario='None:normal',**kwargs):
    return s(['groups',key(mode,profile,phase,scenario),'stats',field,'mean'],**kwargs)
def diff(mode,profile,field,phase='main',scenario='None:normal',interval=False):
    base=['profile_comparisons',f'profile:{phase}:{mode}:{scenario}:none->{profile}','stats',field]
    value=s(base+['mean'],sign=True)
    if interval:value+='<small>구간 '+s(base+['ci95',0],sign=True)+' ~ '+s(base+['ci95',1],sign=True)+'</small>'
    return value
def behavior(mode,profile,scenario,field,interval=False):
    base=['behavior_comparisons',f'behavior:{mode}:{profile}:{scenario}','stats',field]
    value=s(base+['mean'],sign=True)
    if interval:value+='<small>구간 '+s(base+['ci95',0],sign=True)+' ~ '+s(base+['ci95',1],sign=True)+'</small>'
    return value
def table(headers,rows,cls=''):
    return '<div class="table-wrap"><table class="'+cls+'"><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+x+'</td>' for x in r)+'</tr>' for r in rows)+'</tbody></table></div>'
def section(n,title,body):return f'<section id="s{n}"><div class="number">{n:02d}</div><h2>{esc(title)}</h2>{body}</section>'
def bullets(items):return '<ul>'+''.join('<li>'+esc(x)+'</li>' for x in items)+'</ul>'
def status_ko(selection):
    return selection.get('status_ko',{'FOLLOWUP_CANDIDATE_NOT_CLASSROOM_ADOPTION':'후속 검증 후보 · 수업용 확정 보류'}.get(selection.get('status'),selection.get('status','검증 결과 기록')))


def schedule():
    rows=[]
    p=load(PROTOCOL)
    for profile in PROFILES:
        fuel=p['profiles'][profile]['fuel_rounds'];ore=p['profiles'][profile]['ore_rounds']
        world='없음' if profile=='none' else num(PROTOCOL,['design_rationale','extra_world_need',profile,'fuel'],digits=0)+' / '+num(PROTOCOL,['design_rationale','extra_world_need',profile,'ore'],digits=0)
        rows.append([SHORT[profile],', '.join(map(str,fuel)) or '없음',', '.join(map(str,ore)) or '없음',world,'일반 운영만' if profile=='daily' else '일반 운영 + 행동 비교'])
    out=table(['안','연료 정산 라운드','광물 정산 라운드','세계 추가 필요량<br>연료 / 광물','정식 검증 범위'],rows,'text-table')
    out+='<p>정해진 라운드마다 각 국가에서 해당 자원을 '+num(PROTOCOL,['quantity_per_due'],digits=0)+'묶음씩 사용한다. 인구에 비례해 늘어나는 방식은 이번에 넣지 않았다. 기계는 기존처럼 보유하며 사용하는 내구재다.</p>'
    out+='<div class="warning"><strong>주기적 정산을 나타내는 게임 규칙이다.</strong> 정산일 사이에도 연료를 매일 소모한다고 계산하는 모형은 아니다. 첫 정산일 전에는 현재 운영 부담이 없고, 정산이 없는 라운드에는 해당 자원 부족 감점도 없다. 마지막 라운드 이후의 서비스를 미리 구매한 것으로 사용 실적을 만들지 않는다.</div>'
    out+=table(['구분','실제 처리'],[
      ['생산·기술 개발','기존 제조 원료와 개발 원료 소비를 유지한다.'],
      ['나라 기본 운영','산업 투자와 별도로, 모든 국가가 공개된 일정에 따라 연료·광물을 소비한다. 광물은 게임에서 시설 유지용 기초 자재를 대표한다.'],
      ['구매와 자체 재고','음식 예산을 우선하고, 현재 운영용 자원을 준비한다. 생산·개발용과 합산하되 같은 필요량을 두 번 요청하지 않는다. 자기 물건도 필요량만큼 보유·회수한다.'],
      ['부족과 소득','해당 정산에서 연료가 없으면 만족도8점, 광물이 없으면4점 감소한다. 둘 다 없으면12점이다. 기존 만족도 연계 소득식으로 그 라운드 소득도 정확히 조정한다.'],
      ['점수','운영 소비에 별도 보너스 점수를 더하지 않는다. 실제 사용된 고유 물품은 기존 무역·활용 기록에 연결한다.'],
    ],'text-table')
    return out


def world_tables():
    out='<p>아래 값은 세계 전체 '+num(PROTOCOL,['execution','country_count'],digits=0)+'개 국가의 일반 운영 평균이다. 각 조건 '+s(['metadata','main_per_condition'],digits=0)+'게임이며 같은 시드를 대응시켰다. 생산·개발·국가 운영 소비는 서로 다른 실제 물품 사용 목적이다.</p>'
    for mode in MODES:
        rows=[]
        for profile in PROFILES:
            for good,label in (('fuel','연료'),('ore','광물')):
                rows.append([SHORT[profile],label,mean(mode,profile,'world.production.'+good),
                    mean(mode,profile,'world.raw_use.'+good+'.production'),mean(mode,profile,'world.raw_use.'+good+'.research'),
                    mean(mode,profile,'world.raw_use.'+good+'.national'),mean(mode,profile,'world.remaining_goods.'+good),
                    mean(mode,profile,'world.national_operation.required.'+good),mean(mode,profile,'world.national_operation.missing.'+good)])
        out+='<h3>'+MKO[mode]+'</h3>'+table(['안','자원','생산','제조 소비','개발 소비','운영 소비','기말 보유','운영 필요','운영 부족'],rows,'wide')
        rows=[]
        for profile in PROFILES:
            rows.append([SHORT[profile],mean(mode,profile,'world.raw_unmet_production.fuel'),
                mean(mode,profile,'world.raw_unmet_production.ore'),mean(mode,profile,'world.national_operation.any_shortage_rounds'),
                mean(mode,profile,'world.end_prices.fuel'),mean(mode,profile,'world.end_prices.ore'),
                mean(mode,profile,'world.original_food_short'),mean(mode,profile,'world.original_production_failures')])
        out+=table(['안','제조용 연료<br>미충족 물량','제조용 광물<br>미충족 물량','운영 부족<br>국가·라운드 합(9국)','마지막 연료<br>기준가G','마지막 광물<br>기준가G','식량 부족 라운드<br>6국의 국가당 평균','생산 실패 수<br>6국의 국가당 평균'],rows,'wide')
        out+='<h4>기존안 대비 기말 자원과 생활 변화 · 같은 시드 차이</h4>'
        out+=table(['변경안','연료 기말 재고 변화','광물 기말 재고 변화','6국 평균 만족도 변화','6국 평균 현금 변화'],[
            [SHORT[p],diff(mode,p,'world.remaining_goods.fuel',interval=True),diff(mode,p,'world.remaining_goods.ore',interval=True),
             diff(mode,p,'world.original_happy',interval=True),diff(mode,p,'world.original_cash',interval=True)] for p in PROFILES[1:]],'wide')
        out+='<p>완만안에서 중간안으로 바뀔 때 연료 생산은 '+mean(mode,'light','world.production.fuel')+' → '+mean(mode,'regular','world.production.fuel')+'묶음, 기말 연료 보유는 '+mean(mode,'light','world.remaining_goods.fuel')+' → '+mean(mode,'regular','world.remaining_goods.fuel')+'묶음으로 달라졌다. 운영 수요를 늘려도 생산과 다른 소비가 함께 변하므로 기말 재고가 항상 줄어드는 것은 아니다.</p>'
    out+='<p>전자제품 원료 추가 조건과 완만안을 결합한 경우에는 운영용 광물 부족이 게임당 평균 '+mean('electronics_input','light','world.national_operation.missing.ore')+'묶음 나타났다. 정상 운영의 평균이므로 모든 국가·모든 행동에서 부족이 없다는 뜻으로 읽지 않는다.</p>'
    out+='<p class="note">기말 보유는 현재 남은 물품 수이며 초기 지급품도 포함할 수 있다. 자국 생산품 중 미사용 물량과 같은 개념이 아니다. 제조용 미충족 물량은 생산 시점에 부족했던 요구량이며, 운영용 부족과 합쳐 같은 사건처럼 세지 않는다. 국가 운영 부족은 아홉 나라의 부족 라운드 합을 게임별로 평균낸 값이다. 식량 부족과 생산 실패는 원래 여섯 나라의 국가당 평균이다. 구간은 시드별 대응 차이의 평균±1.96×표준오차다.</p>'
    return out


def country_tables():
    out='<p>종합 점수는 기존 v15 국가별 목표와 생산 능력15점·실제 활용10점 계산을 그대로 적용했다. 경제가 달라진 조건을 비교하는 진단 점수이며, 새로운 목표를 결과에 맞춰 보정하지 않았다. 1위 횟수를 같게 만드는 것이 채택 기준은 아니다.</p>'
    for mode in MODES:
        out+='<h3>'+MKO[mode]+'</h3>'
        for field,label in (('fixed_evaluation.score','종합 점수 · 아래는 1위 횟수'),('cash','기말 현금G'),('happy','평균 국민 만족도')):
            rows=[]
            for name in NAMES:
                cells=[KO[name]]
                for profile in PROFILES:
                    x=mean(mode,profile,f'countries.{name}.{field}')
                    if field=='fixed_evaluation.score':x+='<small>1위 '+s(['groups',key(mode,profile),'score_diagnostics','top_counts_including_ties',name],digits=0)+'회</small>'
                    cells.append(x)
                rows.append(cells)
            out+='<h4>'+label+'</h4>'+table(['국가']+[SHORT[p] for p in PROFILES],rows)
        rows=[]
        for profile in PROFILES:
            diag=['groups',key(mode,profile),'score_diagnostics']
            rows.append([SHORT[profile],s(diag+['country_mean_score_range']),s(diag+['mean_within_game_score_range']),
                         '비교 기준' if profile=='none' else diff(mode,profile,'world.fixed_evaluation.score_spread',interval=True)])
        out+='<h4>점수 격차를 두 방식으로 확인</h4>'+table(['안','국가별 평균 점수의<br>최고−최저 차이','게임 안 최고−최저 차이의<br>평균','게임 안 점수차 평균의<br>기존안 대비 변화'],rows)
        out+='<p class="note">국가별 평균 점수 차이는 국가마다 먼저 평균을 낸 뒤 가장 높은 나라와 낮은 나라를 비교한다. 게임 안 점수차는 각 게임의 최고·최저 차이를 먼저 구한 뒤 평균낸다. 서로 다른 지표이며, 대응 차이의 구간에 0이 포함되면 이번 시드 범위에서 개선 방향이 뚜렷하다고 단정하지 않는다.</p>'
        rows=[]
        for name in NAMES:
            for profile in PROFILES:
                rows.append([KO[name],SHORT[profile],mean(mode,profile,f'countries.{name}.investment'),
                    mean(mode,profile,f'countries.{name}.upgrades_total'),mean(mode,profile,f'countries.{name}.machine_gen'),
                    mean(mode,profile,f'countries.{name}.elec_gen'),mean(mode,profile,f'countries.{name}.food_short_rounds'),
                    mean(mode,profile,f'countries.{name}.national_operation.any_shortage_rounds'),
                    mean(mode,profile,f'countries.{name}.growth_metrics.utilization',scale=100),
                    mean(mode,profile,f'countries.{name}.low_cash_rounds')])
        out+='<details><summary>투자·개발·부족·활용 상세표</summary>'+table(['국가','안','투자G','산업 개선<br>완료 수','기계<br>기술 세대','전자제품<br>기술 세대','식량 부족<br>라운드','운영 부족<br>라운드','자국 생산품<br>활용률%','현금20G미만<br>라운드'],rows,'wide')+'</details>'
    out+='<div class="warning"><strong>자원 활용률 상승의 뜻을 구분한다.</strong> 새 운영 수요로 실제 자원이 소비되면 자원 생산국의 활용률이 높아지는 것은 규칙의 의도된 결과다. 이것만으로 산업 생산성이 높아졌거나 특정 설비 투자가 유익했다고 입증되는 것은 아니다. 자산·현금·만족도·부족·개발을 함께 본다. 기존 국가별 점수 목표가 새 수요에서도 적절한지는 별도 판단 대상이다. 이번 비교에서는 그 영향을 드러내기 위해 목표를 고정했다.</div>'
    return out


def added_tables():
    out='<p>추가 AI 국가도 동일한 운영 수요를 부담한다. 이 세 나라의 종합 순위와 국가별 목표 점수는 만들지 않았다. 이들의 구매·생산·생활 결과가 원래 여섯 나라의 시장에 영향을 주므로 물리 지표는 함께 확인했다.</p>'
    for mode in MODES:
        rows=[]
        for name in ADDED:
            for profile in PROFILES:
                rows.append([KO[name],SHORT[profile],mean(mode,profile,f'countries.{name}.cash'),
                    mean(mode,profile,f'countries.{name}.happy'),mean(mode,profile,f'countries.{name}.investment'),
                    mean(mode,profile,f'countries.{name}.food_short_rounds'),mean(mode,profile,f'countries.{name}.national_operation.any_shortage_rounds'),
                    mean(mode,profile,f'countries.{name}.raw_use.fuel.national'),mean(mode,profile,f'countries.{name}.raw_use.ore.national')])
        out+='<h3>'+MKO[mode]+'</h3>'+table(['국가','안','현금G','만족도','투자G','식량 부족<br>라운드','운영 부족<br>라운드','운영 연료<br>실소비','운영 광물<br>실소비'],rows,'wide')
    return out


def behavior_tables():
    out='<p>각 행동은 같은 경제·운영안·시드의 일반 운영 전략과 비교했다. 일반 운영 '+s(['metadata','main_per_condition'],digits=0)+'게임 평균과 섞지 않고 별도의 '+s(['metadata','stress_per_condition'],digits=0)+'쌍을 사용한다. 아래 횟수는 여섯 나라와 두 경제 조건을 합친 관측값이며 실제 학생의 행동 확률이 아니다.</p>'
    rows=[]
    for profile in PROFILES[:3]:
        for style in ('minimum','minimum_passive','idle'):
            base=['diagnostics',profile,style]
            rows.append([SHORT[profile],STKO[style],s(base+['n'],digits=0),s(base+['total_up'],digits=0),
                         s(base+['total_down'],digits=0),s(base+['total_tie'],digits=0)])
    out+=table(['안','행동','비교 수','종합 점수 상승','종합 점수 하락','동일'],rows)
    out+='<p>최저가 반복은 공개 판매가를 1G로 설정하면서 구매·생활 관리는 계속하는 모형이다. 투자 중단을 결합한 경우도 구매는 계속한다. 직접 협상과 물물교환까지 모두1G로 거래한다는 뜻은 아니다. 무행동은 거래·투자를 하지 않지만 자동 생산과 운영 정산은 남는다.</p>'
    out+='<p class="note">매 라운드 연료안은 정식 행동 비교를 실행하지 않았으므로 이 표에 넣지 않았다. 연결 확인용 소수 실행으로 행동 우위를 일반화하지 않는다. 낮은 가격으로 실제 사용과 수출이 증가한 사례를 가격만으로 오류라고 판정하지 않는다.</p>'
    out+='<div class="warning"><strong>정상 운영 결과를 모든 행동에 적용하지 않는다.</strong> 완만안도 투자 중심·무행동 조건에서는 운영 자원이 부족한 사례가 있었다. 일반 운영의 낮은 부족 수준은 정해진 구매·생산·투자 전략에서 나온 결과이며, 어떤 선택을 해도 필수 자원이 충분하다는 보장은 아니다.</div>'
    out+='<h3>테크니아의 기준가 절반 판매</h3><p>이 별도 조건은 공개 판매가를 현재 기준가의 절반으로 계산해 반올림한다. 모든 물건을 1G로 파는 최저가 반복과 다르다. 각 경제 조건의 같은 시드 '+s(['metadata','stress_per_condition'],digits=0)+'쌍을 비교했으며, 테크니아 한 나라만 시험했다.</p>'
    rows=[]
    for profile in PROFILES[:3]:
        base=['diagnostics',profile,'cheap']
        rows.append([SHORT[profile],s(base+['n'],digits=0),s(base+['total_up'],digits=0),s(base+['total_down'],digits=0),s(base+['total_tie'],digits=0),
          behavior('baseline',profile,'Technia:cheap','countries.Technia.fixed_evaluation.score',interval=True),
          behavior('electronics_input',profile,'Technia:cheap','countries.Technia.fixed_evaluation.score',interval=True)])
    out+=table(['안','비교 수','총점 상승','총점 하락','동일','기존 제조 조건<br>평균 총점 차이','전자 원료 추가 조건<br>평균 총점 차이'],rows,'wide')
    out+='<h3>투자 중심과 무역 중심 · 일반 운영 대비 종합 점수 차이</h3>'
    for mode in MODES:
        rows=[]
        for name in NAMES:
            for style in ('invest','trade'):
                rows.append([KO[name],STKO[style]]+[behavior(mode,p,f'{name}:{style}',f'countries.{name}.fixed_evaluation.score',interval=True) for p in PROFILES[:3]])
        out+='<h4>'+MKO[mode]+'</h4>'+table(['국가','전략','기존','완만','중간'],rows)
    rows=[]
    for profile in PROFILES[:3]:
        base=['diagnostics',profile,'invest']
        rows.append([SHORT[profile],s(base+['n'],digits=0),s(base+['investment_up_used_not_up_score_up'],digits=0),
                     s(base+['investment_up_selected_outcomes_not_up_score_up'],digits=0)])
    out+=table(['안','투자 비교 수','투자↑·실사용 비증가·총점↑','왼쪽 중 만족도·유용한 수출입·자산 증가도 비증가'],rows,'wide')
    out+='<p class="note">이 신호는 검토 대상을 찾는 기준이며 투자가 낭비됐다는 확정 판정은 아니다. 생산 능력을 갖추는 성과 자체가 기존 평가에 포함되어 있다.</p>'
    return out


def no_trade_tables():
    out='<p>무역 중단은 세계의 모든 거래를 꺼 두고 같은 시드와 운영안을 비교한 조건이다. 기존의 기본 생산과 만족도 연계 수입, 생활 정산·운영 소비는 유지한다. 이 규칙 안에서 수출입을 막았을 때 생기는 차이를 확인하며, 학생의 학습 효과를 직접 측정한 결과는 아니다.</p><p class="note">식량 부족은 원래 여섯 나라의 국가당 부족 라운드를 평균낸 값이다. 운영 부족은 아홉 나라의 부족 국가·라운드 합이며, 둘의 분모가 다르다.</p>'
    for mode in MODES:
        rows=[]
        for profile in PROFILES[:3]:
            rows.append([SHORT[profile],mean(mode,profile,'world.original_happy','stress'),
                mean(mode,profile,'world.original_happy','stress','None:no_trade'),
                behavior(mode,profile,'None:no_trade','world.original_happy',interval=True),
                mean(mode,profile,'world.original_food_short','stress'),mean(mode,profile,'world.original_food_short','stress','None:no_trade'),
                mean(mode,profile,'world.national_operation.any_shortage_rounds','stress'),
                mean(mode,profile,'world.national_operation.any_shortage_rounds','stress','None:no_trade')])
        out+='<h3>'+MKO[mode]+'</h3>'+table(['안','6국 평균 만족도<br>거래 가능','6국 평균 만족도<br>무역 중단','만족도 차이','식량 부족 · 국가당 평균<br>거래 가능(6국)','식량 부족 · 국가당 평균<br>무역 중단(6국)','운영 부족 · 국가·라운드 합<br>거래 가능(9국)','운영 부족 · 국가·라운드 합<br>무역 중단(9국)'],rows,'wide')
    out+='<h3>자원이 있는 나라도 다른 물건을 수입해야 하는가</h3><p>완만안의 오일리아·미네리아를 따로 보았다. 자국 자원으로 기본 운영을 일부 또는 전부 해결하더라도 식량 등 다른 필요가 남으므로, 자원이 있다는 이유만으로 무역에서 벗어나는 것은 아니다. 아래는 두 나라 각각의 게임 평균이다.</p>'
    rows=[]
    for mode in MODES:
        for name in ('Oilia','Mineria'):
            rows.append([MKO[mode],KO[name],mean(mode,'light',f'countries.{name}.happy','stress'),mean(mode,'light',f'countries.{name}.happy','stress','None:no_trade'),
                         mean(mode,'light',f'countries.{name}.food_short_rounds','stress'),mean(mode,'light',f'countries.{name}.food_short_rounds','stress','None:no_trade'),
                         mean(mode,'light',f'countries.{name}.national_operation.any_shortage_rounds','stress'),mean(mode,'light',f'countries.{name}.national_operation.any_shortage_rounds','stress','None:no_trade')])
    out+=table(['경제 조건','국가','만족도<br>거래 가능','만족도<br>무역 중단','식량 부족 라운드<br>거래 가능','식량 부족 라운드<br>무역 중단','운영 부족 라운드<br>거래 가능','운영 부족 라운드<br>무역 중단'],rows,'wide')
    return out


def exceptions():
    cases=load(SUMMARY)['positive_price_or_idle_exceptions']
    out='<p>각 운영안·행동에서 일반 운영보다 종합 점수가 높았던 사례 중 상승 폭이 가장 큰 사례를 하나씩 골랐다. 같은 상승 폭이면 결과 목록에서 먼저 나온 사례를 사용한다. 유리한 사례만으로 평균 효과를 판단하지 않으며, 양수·음수 전체 비교 기록은 ZIP의 behavior_cases.jsonl.gz에 보존했다.</p><p class="note">“자국산 자원의 국가 운영 사용”은 그 나라에서 생산한 물품이 세계 어느 나라에서든 운영용으로 사용된 수량이다. 자기 나라가 직접 소비한 운영 자원 수량과는 다르다. 초기 지급품도 이 생산 실적에는 포함하지 않는다.</p>'
    chosen={}
    for i,e in enumerate(cases):
        k=(e['operating_profile'],e['style'])
        if k not in chosen or e['delta']['fixed_evaluation.score']>cases[chosen[k]]['delta']['fixed_evaluation.score']:
            chosen[k]=i
    if not chosen:return out+'<p>세 행동에서 일반 운영보다 점수가 높은 사례가 관측되지 않았다. 이 결과는 현재 고정 전략과 시드 범위에 한정된다.</p>'
    for (profile,style),i in sorted(chosen.items(),key=lambda item:(PROFILES.index(item[0][0]),('minimum','minimum_passive','idle').index(item[0][1]))):
        e=cases[i];base=['positive_price_or_idle_exceptions',i]
        title=f'{SHORT[profile]} · {MKO[e["mode"]]} · {KO[e["country"]]} · {STKO[style]} · 시드{e["seed"]}'
        rows=[]
        for field,label in (('cash','기말 현금G'),('growth_metrics.asset_gain','자산 증가G'),('happy','만족도'),
            ('investment','투자G'),('growth_metrics.produced_units','자국 총생산'),('growth_metrics.used_units','실제 사용된 자국 생산품'),
            ('useful_exports','실효 수출'),('national_operation.any_shortage_rounds','자국 운영 부족 라운드'),
            ('national_operation_origin_used.fuel','자국산 연료의 국가 운영 사용'),('national_operation_origin_used.ore','자국산 광물의 국가 운영 사용')):
            rows.append([label,s(base+['before',field]),s(base+['after',field]),s(base+['delta',field],sign=True)])
        score_rows=[]
        for field,label in (('economic_growth','경제 성장'),('reserve','현금 여력'),('capacity','생산 능력'),('utilization','실제 활용'),('wellbeing','국민 만족도'),('trade','무역'),('score','종합 점수')):
            f='fixed_evaluation.'+field
            score_rows.append([label,s(base+['before',f]),s(base+['after',f]),s(base+['delta',f],sign=True)])
        out+='<details class="case"><summary>'+esc(title)+'<span class="case-delta">종합 차이 '+s(base+['delta','fixed_evaluation.score'],sign=True)+'점</span></summary><div class="case-body">'+table(['지표','일반 운영','해당 행동','차이'],rows)+table(['점수 항목','일반 운영','해당 행동','차이'],score_rows)+'</div></details>'
    return out


def evidence_and_next():
    selection=load(SELECTION);audit=load(AUDIT)
    rows=[['정식 경제 실행',num(RUN,['completed_games'],digits=0)+'게임 · 일반 운영 '+s(['metadata','main_games'],digits=0)+' + 행동 조건 '+s(['metadata','stress_games'],digits=0)],
          ['연결 확인 실행',num(SMOKE,['completed_games'],digits=0)+'게임'],
          ['의미·이전 결과 호환 검증',num(TEST,['completed_economic_games'],digits=0)+'게임 · '+num(TEST,['tests'],digits=0)+'개 검증 메서드'],
          ['실제 완료된 경제 실행 합계',num(AUDIT,['statistics','execution_accounting','total_completed_economic_games'],digits=0)+'게임'],
          ['완료 게임이 아닌 구성 상태',num(TEST,['isolated_fixture_instances'],digits=0)+'개'],
          ['정식 조건 집단',s(['metadata','group_count'],digits=0)+'개'],
          ['운영안 대응 비교',s(['metadata','profile_contrasts'],digits=0)+'개'],
          ['경제 조건 대응 비교',s(['metadata','economic_contrasts'],digits=0)+'개'],
          ['행동 대응 비교',s(['metadata','behavior_contrasts'],digits=0)+'개'],
          ['보존한 상세 게임 기록',num(RUN,['representative_traces'],digits=0)+'개'],
          ['각 종류의 라운드 원장',num(PROTOCOL,['execution','formal_ledger_rows_per_kind'],digits=0)+'행 · 현금/원료/국가 운영 각각'],
          ['독립 검산 상태',esc(audit['status'])]]
    if 'check_count' in audit:rows.append(['독립 정합성 대조',num(AUDIT,['check_count'],digits=0)+'개'])
    out=table(['검증 항목','범위·결과'],rows,'text-table')
    out+='<p>시작 자금·초기 물품·생산식·투자 비용·가격 규칙·이전 점수 목표와 '+num(RUN,['preserved_python_sources'],digits=0)+'개 상속 코드 파일을 보존했다. 신규 국가 운영 규칙은 별도 확장 코드에서 적용했다. 기존 원료 검증의 “생산+개발” 분할을 “생산+개발+국가 운영”으로 확장하고 실물·출처·현금 보존을 확인했다.</p>'
    out+='<p>국가 운영 수요가 없는 설정은 원래 엔진과 '+num(TEST,['backcompat_pairs'],digits=0)+'쌍을 비교해 국가·세계 결과 및 상세 기록의 모든 기존 값이 일치했다. 구성 상태 검증은 게임 횟수로 세지 않는다. 정식 실행·분석·독립 검산의 범위와 한계는 각각의 영수증에 보존했다.</p>'
    out+='<h3>다음 단계</h3><div class="callout"><p>'+esc(selection['next_step_ko'])+'</p></div>'
    out+='<div class="student"><strong>학생 화면에 제안하는 흐름</strong><p>이번 라운드 필요한 자원 확인 → 사고팔 물건 선택 → 자동 정산 결과 확인</p><p>생산용·개발용·나라 운영용의 자세한 기록은 교사용 결과 화면에서 확인하도록 제안한다. 학생에게 새 계산식이나 별도 운영 지표를 직접 계산하도록 요구하지 않는다.</p></div>'
    out+=bullets(['사용한 AI는 기존 규칙에 따라 움직이는 자동 국가다. 새 점수에 맞춰 전략을 최적화하는 AI나 학생 행동을 검증한 것은 아니다.',
      '학생3명·40분+40분 수업의 이해도·협상·진행 속도, 클라우드 동시 접속은 이번 범위가 아니다.',
      '주기적 정산과 공통 일정은 실제 에너지 시장의 추정 모형이 아니다. 자원 소비량은 교육용 설계 후보다.',
      '기본 운영 수요를 추가해도 기존의 미래 운영비 예비자금 보호나 식량·전자제품 중심 투자 보호조건을 새로 바꾸지는 않았다.',
      '운영 부족이 개발과 함께 나타날 수 있고, 모든 나라가 같은 정산일을 쓰므로 수요가 몰릴 수 있다. 이러한 영향까지 결과에서 확인해야 한다.',
      '보고서는 저장 수치와 HTML 구조를 검산하는 대상이며 실제 학생용 웹앱이나 화면 렌더링 검증 결과가 아니다.'])
    return out


CSS='''
:root{--ink:#17313f;--muted:#586d78;--line:#d7e1e6;--teal:#176c68;--paper:#f3f6f7}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.75 "Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif}main{max-width:1220px;margin:28px auto 60px;padding:0 24px}header{padding:38px 40px;background:linear-gradient(120deg,#153b4d,#236b65);color:white;border-radius:16px}h1{font-size:34px;line-height:1.35;margin:12px 0 16px;letter-spacing:-.7px}.eyebrow{font-size:13px;color:#cde4e1;letter-spacing:1px}.lead{font-size:19px;max-width:980px}.status{display:inline-block;background:#e7f4ec;color:#17503c;padding:5px 13px;border-radius:20px;font-size:14px;font-weight:700}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-top:25px;padding-top:20px;border-top:1px solid #61918e}.metrics b{display:block;font-size:26px}.metrics span{font-size:13px;color:#dcecea}.metrics b span{font-size:inherit;color:inherit}nav{display:flex;flex-wrap:wrap;gap:8px;padding:21px 0}nav a{background:white;border:1px solid var(--line);border-radius:6px;text-decoration:none;color:var(--teal);font-size:13px;padding:6px 10px}section{background:white;border:1px solid var(--line);border-radius:12px;margin-bottom:22px;padding:30px 32px;scroll-margin-top:20px}.number{color:var(--teal);font-size:12px;font-weight:700;letter-spacing:2px}h2{font-size:25px;line-height:1.4;margin:7px 0 20px}h3{font-size:20px;margin:28px 0 12px}h4{font-size:16px;margin:23px 0 11px}p{margin:12px 0}ul{padding-left:23px}li{margin:8px 0}.table-wrap{overflow-x:auto;margin:15px 0 22px}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.5;font-variant-numeric:tabular-nums}th,td{text-align:right;padding:10px 9px;border-bottom:1px solid #dfe7eb;white-space:nowrap}th{background:#e9f1f3;border-bottom:2px solid #bacdd4;color:#234a58;font-weight:700}th:first-child,td:first-child{text-align:left}tbody tr:nth-child(even){background:#f8fafb}td small{display:block;font-size:11px;color:#647b85;margin-top:4px}.wide{font-size:12px}.wide th,.wide td{padding:9px 6px}.text-table td{white-space:normal;text-align:left}.text-table td:first-child{white-space:nowrap}.callout,.warning,.student{padding:16px 20px;border-left:4px solid var(--teal);background:#edf7f3;margin:18px 0}.warning{border-color:#bd7b35;background:#fff6e9}.student{border-color:#567fa6;background:#eff5fb}.note,footer{font-size:13px;color:var(--muted)}details{border:1px solid var(--line);border-radius:7px;overflow:hidden;margin:14px 0}summary{padding:12px 16px;font-weight:700;background:#eff4f6;cursor:pointer}.case-body{padding:0 16px 14px}.case-delta{display:block;color:var(--teal);font-size:13px;font-weight:400;margin-top:5px}details>.table-wrap{padding:0 12px}.toolbar{text-align:right;margin:12px 0}button{background:white;border:1px solid var(--line);padding:8px 13px;border-radius:6px;color:var(--ink);cursor:pointer}footer{margin:25px 0;overflow-wrap:anywhere}footer code{font-size:11px}.foot-source{margin:7px 0}@media(max-width:760px){main{margin:12px auto;padding:0 12px}header{padding:26px 22px}h1{font-size:27px}section{padding:23px 18px}.metrics{grid-template-columns:repeat(2,1fr)}h2{font-size:22px}table{min-width:670px}.text-table{min-width:530px}}@media print{@page{size:A4 landscape;margin:13mm}body{background:white;font-size:11px;line-height:1.55}main{margin:0;padding:0;max-width:none}header{background:#eef5f4;color:#17313f;border-radius:0;padding:23px}header .eyebrow,.metrics span{color:#4c6971}h1{font-size:26px}.lead{font-size:14px}.metrics b{font-size:21px}nav,.toolbar{display:none}section{border:0;border-bottom:1px solid #ccd8dd;border-radius:0;break-before:page;padding:20px 0}h2{font-size:21px}h3{font-size:17px}h4{font-size:14px}table,.wide{font-size:10px;min-width:0}th,td,.wide th,.wide td{padding:6px 5px}tr{break-inside:avoid}thead{display:table-header-group}.table-wrap{overflow:visible}details:not([open])>.table-wrap,details:not([open])>.case-body{display:block!important}summary{list-style:none}details.case{break-inside:avoid}.callout,.warning,.student{break-inside:avoid}.note,footer{font-size:10px}}
'''


def write_readme():
    selection=load(SELECTION)
    text=f'''#11 무역 게임 — v17 국가 기본 자원 수요 검증

판단
----
{selection['decision_ko']}
선택 상태: {status_ko(selection)}
다음 검증의 추천 프로필: {selection['recommended_profile']}
다음 단계: {selection['next_step_ko']}

먼저 열 파일
------------
TRADE_NATIONAL_RESOURCES_V17_KO.html
인터넷 없이 읽을 수 있는 한국어 정적 보고서다. 학생용 게임이나 배포한 클라우드 웹앱이 아니다.
표 수치는 원본 JSON 경로와 연결된다. 렌더링 실사용 검증을 완료했다는 뜻은 아니다.

검증 범위
---------
정식 경제 게임 6,740회 = 일반 운영 800회 + 행동 조건 5,940회.
별도 연결 확인 24회, 의미·기존 결과 호환 검사 12회를 실행했다.
실제 완료된 경제 실행 합계는 6,776회이며 구성 상태 15개는 여기에 더하지 않는다.
국가 9개·라운드 9개이며 기존 6개국만 고정 목표 점수로 비교한다.
추가 3개국은 경제에 참여하되 종합 점수를 부여하지 않는다.
기존 제조 경제와 전자제품 원료 추가 조건을 같은 시드로 비교한다.
일반 운영은 조건별 100회, 행동 비교는 별도의 시드로 조건별 30회다.
정식 daily는 일반 운영 경계 시험만 수행했다. daily 행동 비교 결과를 추정하지 않는다.

기본 운영 규칙
--------------
none: 기존안. 새로운 기본 운영 소비 없음.
light: 연료 R3·6·9, 광물 R4·8에 국가당 1묶음씩 정산.
regular: 연료 R2·4·6·8, 광물 R3·6·9에 국가당 1묶음씩 정산.
daily: 연료 R1~9, 광물 R3·6·9에 국가당 1묶음씩 정산. 높은 수요의 경계 시험.
모든 국가에 같은 일정이며 이번에는 인구 비례 소비를 넣지 않았다.
각 일정은 주기적 정산의 게임 추상화다. 정산 없는 라운드의 연속적 에너지 소비를 계산하지 않는다.
원료를 미리 소모하고 마지막 이후 서비스까지 사용한 것으로 인정하지 않는다.
해당 정산에 연료가 없으면 만족도 8점, 광물이 없으면 4점, 모두 없으면 12점 감소.
기존의 10+floor(만족도/10+0.5) 소득식을 사용하여 같은 라운드 소득도 조정한다.
식량 우선 구매, 현재 운영 필요량 추가, 상품별 구매행 통합, 자체 재고 보호를 적용한다.
국가 운영 실제 소비는 생산·개발과 별도 목적으로 기록된다.
별도 운영 보너스 점수, 강제 매수자, 추가 지원금, 가격 하한을 새로 만들지 않았다.

점수 해석
---------
v15에서 선택한 기존 국가별 경제·산업 목표와 생산 능력 15점 + 실제 활용 10점을 유지했다.
새 경제 조건에서의 점수는 진단 자료다. 결과를 보고 새 목표를 맞추거나 1위 횟수를 같게 만들지 않았다.
운영용 실제 소비로 자원 활용률이 올라도 생산성 향상이나 특정 투자의 인과 효과를 입증하는 것은 아니다.
기존 점수 목표가 새 수요에서도 적절한지는 별도 판단 대상이며 이번에는 그 영향을 드러내도록 고정했다.
기말 재고, 생산 원료 부족, 운영 부족, 현금, 식량, 만족도, 개발을 함께 본다.
최저가 행동의 점수 상승은 실제 사용·수출·자산 변화와 함께 확인한다.
national_operation_origin_used는 자국에서 생산한 자원이 세계 어느 나라에서든 운영용으로 쓰인 수량이다.
자기 나라가 직접 소비한 운영 자원 수량과는 다르며 초기 지급품도 이 생산 실적에는 포함하지 않는다.

파일
----
OPERATING_PROTOCOL_V17.json: 결과를 보기 전에 고정한 실험 범위·일정·판정 원칙.
CANDIDATE_SELECTION_V17.json: 결과에 근거한 채택/보류 및 다음 단계.
operating_engine.py: 기존 코드를 수정하지 않고 국가 기본 운영을 추가한 확장 엔진.
test_operating_engine.py: 의미 검증 및 6쌍의 기존 동작 정확 재현.
run_operating_validation.py: 정식/연결 확인 실행, 3종류의 원장과 상세 기록 보존.
analyze_operating_validation.py: 조건 평균·같은 시드 대응 비교·예외 사례.
audit_operating_validation.py: 엔진과 분석 함수를 불러오지 않는 독립 검산.
build_operating_report.py: 저장 결과만 읽어 이 보고서를 생성.
source_v13/: 변경 없이 보존한 85개 기존 코드.
operating_results/: 게임 결과, 현금/원료/국가 운영 원장, 상세 기록, 통계, 독립 검증 영수증.
semantic_tests.json/log: 완료 게임 12회와 별도 구성 상태 15개의 검증 범위 및 결과.

재현
----
이 README 파일이 있는 폴더에서 Python 3.10 이상 표준 라이브러리로 실행한다.
기존 결과를 덮어쓰지 않도록 새 출력 디렉터리를 지정한다.
아래 명령은 각각 실행한다. 정식 재현은 6,740개의 실제 경제 게임을 추가 실행하므로 시간이 걸린다.

python3 run_operating_validation.py --stage smoke --workers 3 --output-dir reproduced_v17
python3 run_operating_validation.py --stage freeze --output-dir reproduced_v17 --test-receipt semantic_tests.json
python3 run_operating_validation.py --stage formal --workers 3 --output-dir reproduced_v17
python3 analyze_operating_validation.py --results reproduced_v17
python3 audit_operating_validation.py --results reproduced_v17

의미 검증을 다시 실행하려면 기존 semantic_tests.json/log를 다른 이름으로 보존한 뒤
python3 test_operating_engine.py
를 실행한다. 이 검증은 기존 엔진 6회와 none 프로필 6회의 총 12게임을 실제로 실행한다.
보고서만 다시 생성할 때는 완료된 기존 파일에서 python3 build_operating_report.py를 실행한다.

검증하지 않은 범위
----------------
학생 3명의 80분 수업, 실제 학습 성과, 새 점수를 노리는 최적 전략, 클라우드 동시 접속은 별도다.
AI는 고정된 규칙에 따라 운영하는 자동 국가이며 새 LLM 서비스를 호출하지 않는다.
현재 수요 일정의 국가 동시 집중, 미래 운영비 예비자금 보호 부재, 운영 부족을 직접 금지 조건으로 삼지 않는
기존 투자 판단은 추가 검토할 수 있다. 결과를 보고 계수를 추가로 조정하지 않았다.
'''
    (ROOT/'README_V17_KO.txt').write_text(text,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'TRADE_NATIONAL_RESOURCES_V17_KO.html')
    args=parser.parse_args()
    assert load('operating_results/analysis_manifest.json')['status']=='PASS'
    summary=load(SUMMARY);run=load(RUN);audit=load(AUDIT);selection=load(SELECTION)
    assert run['status']==audit['status']==load(SMOKE)['status']==load(TEST)['status']=='PASS'
    assert run['completed_games']==6740 and load(SMOKE)['completed_games']==24
    assert load(TEST)['completed_economic_games']==12 and summary['metadata']['formal_economic_games']==6740
    chosen=selection['recommended_profile'];assert chosen in PROFILES
    hero='<header><div class="eyebrow">아이디어 노트 · #11 무역 게임 · v17</div><h1>나라 운영에도 필요한 자원<br>기본 수요 추가 검증</h1><p class="lead">'+esc(selection['decision_ko'])+'</p><div class="status">'+esc(status_ko(selection))+'</div><div class="metrics"><div><b>'+num(RUN,['completed_games'],digits=0)+'</b><span>정식 경제 게임</span></div><div><b>'+num(SMOKE,['completed_games'],digits=0)+' + '+num(TEST,['completed_economic_games'],digits=0)+'</b><span>연결 확인 + 의미 검증 게임</span></div><div><b>'+num(PROTOCOL,['execution','country_count'],digits=0)+'개국 · '+num(PROTOCOL,['execution','rounds'],digits=0)+'라운드</b><span>기존 6개국만 순위 평가</span></div><div><b>'+esc(SHORT[chosen])+'</b><span>다음 검증의 추천 프로필</span></div></div></header>'
    intro='<p>사용자가 말한 자원은 생산·연구에만 쓰는 원료가 아니라, 산업 투자를 하지 않아도 나라를 유지하는 데 필요한 품목이다. 이번에는 그 기본 운영 수요를 실제 소비로 추가하고 생산·가격·거래·생활이 어떻게 달라지는지 새 게임으로 확인했다.</p><div class="callout">'+bullets(selection['reasons_ko'])+'</div><p class="note">이 보고서는 검증 결과를 읽는 문서다. 학생 접속용 게임이나 배포된 웹앱이 아니다. 운영안의 채택·보류와 구현 범위는 선택 기록에 따라 구분한다.</p>'
    parts=[section(1,'이번 판단과 비교한 규칙',intro+schedule()),
           section(2,'세계의 자원은 어디에 쓰이고 얼마나 남았나',world_tables()),
           section(3,'원래 여섯 나라의 경제와 생활',country_tables()),
           section(4,'추가 AI 세 나라의 영향',added_tables()),
           section(5,'최저가·무행동·투자·무역 전략',behavior_tables()),
           section(6,'무역을 중단했을 때의 변화',no_trade_tables()),
           section(7,'점수 상승 예외의 실제 사용과 경제 성과',exceptions()),
           section(8,'검증 근거와 다음 단계',evidence_and_next())]
    nav='<nav>'+''.join(f'<a href="#s{i}">{i}. {t}</a>' for i,t in enumerate(('판단·규칙','세계 자원','6국 비교','AI 3국','전략 비교','무역 필요성','예외 사례','검증·다음 단계'),1))+'</nav>'
    sources=[PROTOCOL,SELECTION,RUN,SUMMARY,AUDIT,TEST]
    footer='<footer><strong>근거 파일</strong><p>수치 표식은 ZIP 안의 JSON 경로에 연결되어 있다. 이 보고서 생성기는 저장된 파일만 읽고 경제 게임을 실행하지 않는다. 원본 게임·목표·고정 조건·원장·양수와 음수 행동 결과를 함께 제공한다.</p>'+''.join('<div class="foot-source">'+esc(f)+'<br><code>'+hashlib.sha256((ROOT/f).read_bytes()).hexdigest()+'</code></div>' for f in sources)+'</footer>'
    document='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>#11 무역 게임 · v17 국가 기본 자원 검증</title><style>'+CSS+'</style></head><body><main><div class="toolbar"><button onclick="document.querySelectorAll(\'details\').forEach(d=&gt;d.open=true);window.print()">보고서 인쇄</button></div>'+hero+nav+''.join(parts)+footer+'</main></body></html>'
    args.output.write_text(document,encoding='utf-8');write_readme()
    print(json.dumps({'status':'PASS','output':str(args.output),'bytes':args.output.stat().st_size,
                      'recommended_profile':chosen,'sections':8,'numeric_spans':document.count('data-pointer='),
                      'new_economic_games':0},ensure_ascii=False))


if __name__=='__main__':main()
