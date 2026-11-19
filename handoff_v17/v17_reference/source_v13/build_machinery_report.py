"""Build the v6 Korean evidence report from completed, audited held-out runs."""
from pathlib import Path
from collections import defaultdict
from html import escape
import argparse, gzip, hashlib, json, statistics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'machinery_results'
LABELS={'Tropia':'트로피아','Grainia':'그레니아','Oilia':'오일리아','Mechania':'메카니아',
        'Mineria':'미네리아','Technia':'테크니아','Novia':'노비아','Agrea':'아그레아','Ferria':'페리아'}
VN={'baseline':'v5 생활 우선 기준선','quantity':'생산량·주력 판단 조절','recipe':'생산량 비례 원료만',
    'coupled':'생산량·원료 연동','service':'연동 + 사용 정비'}
GOODS={'banana':'바나나','wheat':'밀','ore':'광물','fuel':'연료','machine':'기계','electronics':'전자제품'}

def table(headers,rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def main():
    global OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=OUT)
    parser.add_argument('--report',type=Path,default=ROOT/'TRADE_MACHINERY_REVIEW_V6_KO.html')
    args=parser.parse_args()
    OUT=args.results.resolve()
    summary=json.loads((OUT/'summary.json').read_text())
    meta=summary['metadata']
    assert meta['completed_games']==2350
    audit=json.loads((OUT/'independent_audit.json').read_text())
    assert audit['status']=='passed', 'Independent final-result audit must pass before publication.'
    with gzip.open(OUT/'runs.jsonl.gz','rt') as stream: rows=[json.loads(line) for line in stream]
    groups=defaultdict(list)
    for r in rows:groups[r['phase'],r['mode'],r['focal'],r['style']].append(r)
    def get(obj,path):
        for key in path.split('.'):obj=obj[key]
        return obj
    def m(v,path,phase='main',focal=None,style='normal'):
        return statistics.mean(get(r,path) for r in groups[phase,v,focal,style])
    def c(v,n,path):return m(v,'countries.'+n+'.'+path)
    def f(x,d=2):return f'{x:,.{d}f}'
    def pct(v,fn):return 100*statistics.mean(fn(r) for r in groups['main',v,None,'normal'])
    def paired(a,b,path):
        aa={r['seed']:get(r,path) for r in groups['main',a,None,'normal']}
        bb={r['seed']:get(r,path) for r in groups['main',b,None,'normal']}
        ds=[bb[s]-aa[s] for s in aa]
        mean=statistics.mean(ds);se=statistics.stdev(ds)/(len(ds)**.5)
        return mean,mean-1.96*se,mean+1.96*se
    def change(a,b,path):return f(m(a,path))+' → '+f(m(b,path))
    def stress_delta(v,n,style,path):
        ctr={r['seed']:get(r,path) for r in groups['stress',v,None,'normal']}
        return statistics.mean(get(r,path)-ctr[r['seed']] for r in groups['stress',v,n,style])
    cashrounds=defaultdict(list)
    with gzip.open(OUT/'round_ledgers.jsonl.gz','rt') as stream:
        for line in stream:
            record=json.loads(line)
            for row in record['rows']:cashrounds[record['mode'],row['country'],row['round']].append(row)
    derived={'round_means':{v:{n:[{k:statistics.mean(t[k] for t in cashrounds[v,n,r]) for k in
        ('cash_start','sales','purchases','investment','operating_income','cash_end','happy')} for r in range(1,10)]
        for n in LABELS} for v in VN},
        'grade2_success_pct':{v:pct(v,lambda r:r['countries']['Mechania']['machine_gen']>=2) for v in VN},
        'grade3_success_pct':{v:pct(v,lambda r:r['countries']['Mechania']['machine_gen']>=3) for v in VN},
        'run_sha256':hashlib.sha256((OUT/'runs.jsonl.gz').read_bytes()).hexdigest()}
    (OUT/'derived_metrics.json').write_text(json.dumps(derived,ensure_ascii=False,indent=2))
    b=[]
    def add(s):b.append(s)
    add('<header><p class="eyebrow">아이디어 노트 · #11 무역 게임 · 🛠 설계·경제 모형 검증</p><h1>기계 생산과 실제 수요를<br>연결하는 v6 비교 실험</h1><p>9개국 · 9라운드 · 5가지 안 · 2026년 11월 18일</p></header>')
    add('<section class="lead"><h2>판정</h2><p><strong>생산량과 원료를 함께 줄이는 안은 기계 과잉과 메카니아의 지출 부담을 완화했다. 기계 수출 자체의 활성화와 9개국 평가 공정성은 아직 해결되지 않았다.</strong></p><p><code>coupled</code>를 다음 경제 검증의 유력 후보로 남긴다. <code>service</code>는 추가 비용으로 광물 거래를 늘리지만, 설비의 실제 기여가 비슷하고 다른 나라의 부담이 생겨 기본 규칙으로 채택하지 않는다. 이 문서는 규칙 후보의 검증 결과이며, 새 규칙을 사용자 확정 사항으로 바꾸지 않는다.</p></section>')
    add('<div class="cards">'+''.join('<div><b>'+s+'</b><span>'+label+'</span></div>' for s,label in [
        (f(meta['completed_games'],0),'정식 완료 게임'),('168','통과한 회귀·경계 테스트'),
        (f(meta['verification_calls'],0),'반복 불변조건 검사'),('81,000','독립 대조한 본 비교 원장 행')])+'</div>')
    add('<section><h2>1. 기존 결정과 이번 실험의 범위</h2><p>시작 국가·자금·생산 능력·주력 보너스 크기·기술 개발 비용·기계 세대 성능·가격 결정·화폐/물물교환·기존6국 점수식을 유지했다. 기준선은 원래 v4가 아니라 <strong>v5의 생활 우선·투자 후 자원 확보 정책</strong>이다. 보관비와 별도의 추가 원료 보너스 규칙은 v5 비교 조건과 같이 꺼져 있다.</p><p>이번에는 자동 생산의 실제 수량과 원료 소비를 바꾸는 <strong>게임 규칙 후보</strong>를 구현했다. 단순한 AI 구매 순서 수정과는 다르다. 무제한 구매자·보조금·폐기 환급·강제 신제품 교체는 넣지 않았다.</p>')
    add(table(['안','바뀐 부분','검증 목적'],[
        [VN['baseline'],'v5 balanced 그대로','정확한 대응 기준선'],
        [VN['quantity'],'자기 재고·최근 판매로 생산량 조절 + 실제 추가 산출이 있는 산업에 주력 지정','생산량만 줄였을 때의 효과'],
        [VN['recipe'],'기계 실제 생산 수량·세대에 비례한 원료','원료만 줄이면 과잉이 남는지'],
        [VN['coupled'],'앞의 생산량·주력 판단과 비례 원료를 결합','재고와 불필요한 원료 비용을 함께 개선'],
        [VN['service'],'coupled + 기계 3회 실제 지원마다 광물 1묶음 정비','자원 거래 증가와 다른 국가 부담을 함께 점검']]))
    add('</section><section><h2>2. 현실에서 참고한 원리와 게임용 가정</h2><p>미국 연방준비제도는 생산 능력과 실제 산출을 구분한다. 미 Census 생산 능력 조사에는 주문 부족·완제품 재고 충분 등이 정상 능력보다 적게 생산하는 이유로 제시된다. BLS는 기계 같은 자본이 여러 기간에 걸쳐 서비스를 제공한다고 설명한다. 실제 장비 제조사의 정비표도 사용 시간에 따른 정비를 명시한다. 아래 수치는 이 자료에서 추정한 값이 아니라 <strong>9라운드 게임을 위한 시험 계수</strong>이다.</p>')
    add(table(['현실의 개념','이번 게임의 단순화','구분'],[
        ['생산 능력과 실제 생산은 다름','기계 목표 재고 = 1 + 최근 2라운드 자기 판매량 평균의 올림','1묶음 여유·2라운드는 실험 계수'],
        ['판매·재고를 보고 생산 조절','현행 세대 이상 보유량이 목표를 채우면 생산 휴식','판매 등록 중·사용 중인 자기 물건도 재고에 포함'],
        ['내구 설비는 여러 번 사용','초기 지급 기계와 신규 생산 기계의 실제 사용 횟수를 따로 확인','새 기계가 덜 팔려도 설비 서비스는 유지될 수 있음'],
        ['실제 제조량에 따라 투입 재료가 달라짐','기계 생산량·세대에 따라 원료를 차감, 남은 가공 재료는 이월','원료 1묶음 = 재료 2칸은 게임용'],
        ['설비 사용에는 정비가 필요','3회 사용마다 광물 1묶음으로 부품 정비를 추상화','새 규칙 후보; 이번 기본안에서는 보류']]))
    add('<p>광물은 정비 부품 재료의 추상화다. 현실의 기계가 광물 원석을 직접 소비한다는 뜻이 아니다. 환율·관세·운송보험 등을 한꺼번에 추가하지 않았다. 출처는 마지막 절에서 확인할 수 있다.</p></section>')
    add('<section><h2>3. 검증 설계</h2>')
    add(table(['표본','구성','시드','완료 게임'],[
        ['본 비교','5가지 안 × 200회','34000–34199','1,000'],
        ['반값·무행동','기준선/coupled/service × 기존6국 × 2정책 × 30회','36000–36029','1,080'],
        ['정상·무역 금지·메카니아 원료 수입 거부','같은 3안 × 3정책 × 30회','36000–36029','270'],
        ['합계','규칙 고정 후 동일 시드 대응 비교','개발용 표본과 분리','2,350']]))
    add('<p>개발용 32000–32029의 150게임과 회귀·감사용 실행은 정식 합계에서 제외했다. 200회 반복은 모형의 무작위 순서·선택 차이에 대한 비교이며 실제 학생 200명을 의미하지 않는다. 아래 숫자는 별도 표시가 없으면 본 비교 200게임의 평균, 만족도는 9라운드 평균, 현금은 종료 현금이다. 단위 G는 게임 화폐다.</p></section>')
    add('<section><h2>4. 다섯 가지 안의 주요 결과</h2>')
    add(table(['안','메카니아 현금 G','기계 생산','종료 보유 기계','세계 만족도','거래 수량','9국 현금 격차 G'],[[VN[v],f(c(v,'Mechania','cash')),f(c(v,'Mechania','produced.machine')),f(c(v,'Mechania','end_stock_by_good.machine')),f(m(v,'world.happy')),f(m(v,'world.trade_units')),f(m(v,'world.all_country_cash_gap'))] for v in VN]))
    add('<p>현금 격차는 매 게임의 최대−최소 현금을 구한 뒤 평균한 값이다. 현금만으로 종합 공정성을 판단하지 않는다. 종료 보유 기계는 자국이 현재 가진 모든 기계로, 생산 기계 중 미판매량과 완전히 같은 지표는 아니다.</p><h3>산업이 실제로 도운 양도 확인했다</h3>')
    add(table(['지표','v5 기준선','coupled','service'],[[label]+[f(m(v,key)) for v in ('baseline','coupled','service')] for label,key in [
        ['세계 신규 기계 생산','world.production.machine'],
        ['신규 생산 기계 중 한 번 이상 사용된 실물 수','world.machine_unique_used'],
        ['초기 지급 포함 한 번 이상 사용된 기계 실물 수','world.machine_unique_used_including_initial'],
        ['기계의 실제 생산 지원 횟수','world.equipment_use_episodes'],
        ['기계가 추가로 생산한 상품 수','world.equipment_extra_output'],
        ['기계 지원 미충족 횟수','world.machine_missing_episodes'],
        ['정비에 소비한 광물','world.machine_upkeep_ore']]]))
    add('<p>사용 실물 수는 같은 기계를 한 번만 세고, 지원 횟수는 여러 라운드 사용을 반복 집계한다. 지원 미충족에는 service에서 실물은 있으나 정비가 안 되어 보너스를 못 받은 경우도 들어간다. 이를 새 기계의 실물 부족량으로 해석하지 않는다.</p><h3>다른 상품의 과잉까지 해결된 것은 아니다</h3>')
    goodsrows=[]
    for good in GOODS:
        used={v:sum(c(v,n,'use_by_good.'+good) for n in LABELS) for v in ('baseline','coupled')}
        goodsrows.append([GOODS[good],change('baseline','coupled','world.production.'+good),f(used['baseline'])+' → '+f(used['coupled']),change('baseline','coupled','world.aged_unused_goods.'+good)])
    add(table(['상품','신규 생산: 기준→연동','신규 생산 중 실제 사용: 기준→연동','2라운드 이상 미사용 재고: 기준→연동'],goodsrows))
    add('<p>이 표의 실제 사용은 이번 게임에서 새로 생산한 실물 중 한 번 이상 사용된 수량이다. 초기 지급 물건과 반복 사용 횟수는 제외한다. 내구재는 사용된 뒤에도 재고로 남는다. 세계 판매 등록 재고는 '+change('baseline','coupled','world.listed')+'개로 줄었으나, 밀·전자제품 등의 오래 남은 미사용 재고는 증가했다. 기계의 개선을 전체 상품의 공급 과잉 해결로 확대하지 않는다.</p></section>')
    add('<section><h2>5. 메카니아: 절약과 수출 성과를 분리</h2>')
    add(table(['누계 지표','v5 기준선','coupled','service'],[[label]+[f(c(v,'Mechania',key)) for v in ('baseline','coupled','service')] for label,key in [
        ['전체 판매 수입 G','revenue'],['기계 판매 수입 G','sale_by_good.machine'],['전체 구매 지출 G','purchases'],
        ['광물 구매 지출 G','purchase_by_good.ore'],['개발 투자 지출 G','investment'],['만족도 연계 운영수입 G','tax'],
        ['종료 현금 G','cash'],['전체 산업 생산에 쓰인 광물','production_raw.ore'],
        ['새로 생산해 해외에서 실제 사용된 기계','export_used_by_good.machine'],
        ['새로 생산해 해외에서 실제 사용된 밀','export_used_by_good.wheat'],
        ['전체 유효수출','useful_exports'],['평균 만족도','happy']]]))
    add('<p>시작 현금은 세 안 모두 215G다. 현금식은 <strong>215 + 판매 − 구매 − 투자 + 운영수입</strong>이다. 판매 수입에는 초기 자산 판매·재판매가 포함될 수 있으며, 물물교환은 현금 수입으로 잡히지 않는다. 현금 증가는 기계 수출의 증가와 같지 않다. 이번 개선은 불필요한 생산·원료 지출을 줄인 효과가 크다.</p>')
    add(table(['기술·재고','v5 기준선','coupled','service'],[
        ['메카니아 기계 기술 G2 이상 비율 %']+[f(derived['grade2_success_pct'][v],1) for v in ('baseline','coupled','service')],
        ['메카니아 기계 기술 G3 비율 %']+[f(derived['grade3_success_pct'][v],1) for v in ('baseline','coupled','service')],
        ['메카니아 G2 이상 기계 실제 생산 비율 %']+[f(pct(v,lambda r:sum(r['countries']['Mechania']['machine_produced_by_gen'][g] for g in ('2','3'))>0),1) for v in ('baseline','coupled','service')],
        *[[f'메카니아 G{g} 생산']+[f(c(v,'Mechania','machine_produced_by_gen.'+str(g))) for v in ('baseline','coupled','service')] for g in (1,2,3)],
        *[[f'메카니아 G{g} 종료 재고']+[f(c(v,'Mechania','machine_stock_by_gen.'+str(g))) for v in ('baseline','coupled','service')] for g in (1,2,3)]]))
    add('<p>신제품이 처음 나올 때에는 최소 1개 생산을 계획해 구형 재고가 첫 출시를 영구히 막지 않게 했다. 단, 재료가 없으면 고급 기계를 공짜로 주지 않는다. 기존처럼 G1 1개 안전 생산으로 내려간다.</p><h3>대응 차이의 모형 내 95% 구간</h3>')
    add(table(['coupled − 기준선','평균 차이','하한','상한'],[[label]+[f(x) for x in paired('baseline','coupled',key)] for label,key in [
        ['메카니아 현금 G','countries.Mechania.cash'],['메카니아 만족도','countries.Mechania.happy'],
        ['메카니아 해외 사용 신규 기계','countries.Mechania.export_used_by_good.machine'],
        ['세계 실제 설비 지원 횟수','world.equipment_use_episodes'],['세계 만족도','world.happy'],
        ['미네리아 현금 G','countries.Mineria.cash']]]))
    add('<p>구간은 같은 시드끼리 차이를 내어 평균 ± 1.96×표준오차로 계산했다. 여러 지표를 탐색하는 설명용 구간이며, 학생 학습 효과나 실제 경제에 대한 신뢰구간이 아니다.</p></section>')
    add('<section><h2>6. 다른 8개국으로 부담이 이동했는가</h2>')
    add(table(['국가','현금: 기준→연동 G','만족도: 기준→연동','유효수출: 기준→연동','투자: 기준→연동 G'],[[LABELS[n]]+[change('baseline','coupled','countries.'+n+'.'+k) for k in ('cash','happy','useful_exports','investment')] for n in LABELS]))
    add('<p>기계를 적게 만들면 광물 수요도 줄어드는 것이 자연스러운 연쇄 변화다. 과잉 생산에 쓰이던 광물 판매량을 억지로 보존하는 것을 목표로 삼지 않았다. 대신 자원 국가의 생활, 실제 유효수출, 투자 기회가 함께 악화되는지 확인했다. 자원 국가의 역할과 기계 수출 기회는 추가 조정이 필요하다.</p><h3>원료 흐름</h3>')
    add(table(['지표','v5 기준선','coupled','service'],[[label]+[f(m(v,key)) for v in ('baseline','coupled','service')] for label,key in [
        ['세계 광물 생산','world.production.ore'],['세계 광물 거래','world.trade_goods.ore'],['세계 광물 소비','world.consumed.ore'],
        ['세계 연료 생산','world.production.fuel'],['세계 연료 거래','world.trade_goods.fuel'],['세계 연료 소비','world.consumed.fuel']]]))
    add('</section><section><h2>7. 정비안은 왜 기본 규칙으로 보류하는가</h2>')
    add(table(['국가','coupled 현금 G','service 현금 G','차이 G','service 정비 광물'],[[LABELS[n],f(c('coupled',n,'cash')),f(c('service',n,'cash')),f(c('service',n,'cash')-c('coupled',n,'cash')),f(c('service',n,'machine_upkeep_ore'))] for n in LABELS]))
    add('<p>정비안은 실제 사용에 비용을 붙인다는 점에서는 설명 가능하다. 그러나 정비 없는 안과 설비 지원·추가 산출이 거의 같다면, 거래 증가의 주된 의미는 비용과 수입의 재배분이다. 학생의 선택을 늘리지 않은 채 자동 구매로 비용을 부과하는 현 정책은 정비의 이득과 비용도 비교하지 않는다.</p><p>예를 들어 구형 기계 효율 0.6, 식량 가격 7G라면 3회 지원의 장기 평균 추가 산출 가치는 3×0.6×7=12.6G다. 광물 기준가격 하한 14G보다 작다. 실제 3회 산출은 소수 이월과 시점에 따라 달라지므로 이것은 손해가 가능한 조건 예시이며, 모든 정비의 손해를 입증하는 계산은 아니다.</p><p><strong>따라서 광물 국가의 판매를 늘리기 위한 수단으로는 채택하지 않는다.</strong> 정비 자체를 수업 주제로 삼을 때 비용·효과·사용 선택을 다시 검토할 별도 후보로 보존한다.</p></section>')
    add('<section><h2>8. 반복 반값 판매와 무행동</h2><p>반값 정책은 시장의 최저 호가를 탐색하는 전략이 아니라 <strong>기준가격의 50%로 계속 판매</strong>하는 고정 정책이다. 구매·투자·필요 재고 보호는 정상적으로 한다. 따라서 의욕 없는 학생의 모든 행동을 재현했다고 볼 수 없다.</p>')
    add(table(['coupled에서 반값 판매한 국가','본인 현금 차이 G','본인 만족도 차이','유효수출 차이','기존 진단 점수 차이'],[[LABELS[n]]+[f(stress_delta('coupled',n,'cheap','countries.'+n+'.'+key)) for key in ('cash','happy','useful_exports','score')] for n in list(LABELS)[:6]]))
    add('<p><strong>이번 30개 대응 시드의 평균 진단 점수는 기존6국 모두 반값 정책에서 올랐다.</strong> 모든 개별 게임에서 반값이 유리하다는 뜻은 아니다. 농업국의 현금은 크게 줄지만 미네리아는 반값 판매로 현금과 유효수출이 함께 늘었다. 현재 추천 가격과 평가가 가격을 생각하는 선택을 충분히 보상하는지는 해결되지 않았다.</p><p>싸게 판 결과 실제 수요를 충족했다면 거래의 학습 가치는 있다. 가격을 낮췄다는 이유만으로 벌점을 주지 않는다. 실제 거래의 수익·상대국 사용·필요 수입 결과를 보여 주고, 가격 추천과 점수의 민감도를 함께 다시 검증해야 한다.</p>')
    idlerows=[]
    for n in list(LABELS)[:6]:
        row=[LABELS[n]]
        for v in ('baseline','coupled','service'):
            ctr={r['seed']:r for r in groups['stress',v,None,'normal']}
            ds=[statistics.mean(r['countries'][other]['happy']-ctr[r['seed']]['countries'][other]['happy'] for other in LABELS if other!=n) for r in groups['stress',v,n,'idle']]
            row.append(f(statistics.mean(ds)))
        idlerows.append(row)
    add(table(['무행동 국가','다른8국 만족도 변화: 기준선','coupled','service'],idlerows))
    add('<p>무행동은 거래·투자를 하지 않되 자동 생산과 운영수입은 계속되는 조건이다. 해당 국가의 현금 축적을 참여·학습 성공으로 해석하지 않는다. 다른 나라 피해가 제한되어도 그 학생이 수출입의 이유를 이해했는지는 별도 관찰이 필요하다.</p>')
    add(table(['세계9국 만족도','정상 거래','무역 금지','차이'],[[VN[v],f(m(v,'world.happy','stress')),f(m(v,'world.happy','stress',style='no_trade')),f(m(v,'world.happy','stress')-m(v,'world.happy','stress',style='no_trade'))] for v in ('baseline','coupled','service')]))
    add('<p>무역 금지의 차이는 모형에서 무역이 생활에 기여하는 통로가 있음을 보여 준다. 거래 금지에 따라 투자 등도 달라지므로 거래 수량만 고정한 실험은 아니며 실제 학습 성취 증거도 아니다.</p></section>')
    add('<section><h2>9. 원료를 일부러 수입하지 않으면</h2><p>메카니아만 광물·연료 수입을 현금 거래와 물물교환 모두에서 거부했다. 초기 재고와 자국 생산 원료의 사용은 허용한다. 삭제된 구매 계획의 예산을 뒤 품목에 재배분하지 않으므로 가능한 모든 무원료 최적 전략을 탐색한 것은 아니다.</p>')
    add(table(['원료 수입 거부 정책','현금 G','만족도','G2 이상 기술 도달 %','G1 생산','해외 사용 신규 기계','기계 안전 생산 회수'],[[VN[v],f(m(v,'countries.Mechania.cash','stress','Mechania','no_raw')),f(m(v,'countries.Mechania.happy','stress','Mechania','no_raw')),f(100*statistics.mean(r['countries']['Mechania']['machine_gen']>=2 for r in groups['stress',v,'Mechania','no_raw']),1),f(m(v,'countries.Mechania.machine_produced_by_gen.1','stress','Mechania','no_raw')),f(m(v,'countries.Mechania.export_used_by_good.machine','stress','Mechania','no_raw')),f(m(v,'countries.Mechania.machine_fallbacks','stress','Mechania','no_raw'))] for v in ('baseline','coupled','service')]))
    add(table(['coupled의 같은 30개 시드','정상 메카니아','원료 수입 거부','차이'],[[label,f(m('coupled','countries.Mechania.'+key,'stress')),f(m('coupled','countries.Mechania.'+key,'stress','Mechania','no_raw')),f(stress_delta('coupled','Mechania','no_raw','countries.Mechania.'+key))] for label,key in [('종료 현금 G','cash'),('투자 지출 G','investment'),('평균 만족도','happy'),('기존 진단 점수','score')]]))
    add('<p>coupled에서는 원료 수입을 거부해도 30게임 중 22게임에서 초기 광물을 활용해 G2 기술에 도달했다. 정상보다 현금은 늘지만 투자 지출·진단 점수는 낮아진다. 이는 모든 면에서 우월한 전략이라는 증거는 아니며, 초기 원료가 줄어든 실제 생산 수요를 상당 부분 덮어 <strong>지속적인 원료 수입의 필요성이 약해졌다는 점</strong>은 다음에 조정해야 한다.</p>')
    add('<p>기존의 원료 부족 시 G1 1개 안전 생산은 유지했다. 따라서 원료 없이 판매 가능한 물건을 얻는 통로는 남아 있다. 고급 생산 계획이 계속 실패하면 구형 재고가 누적될 수도 있다. 이 문제를 이번 검증에서 완전히 제거했다고 주장하지 않는다. 기본 생존 지원을 남길지, 생산 보조·일회 지원 등으로 바꿀지는 별도 규칙 결정이다.</p></section>')
    add('<section><h2>10. 고급 기계의 추가 생산만으로 교체비를 회수할 수 있는가</h2>')
    add(table(['안','비교 가능한 판매 제안 검사 횟수/게임','생산 증가 가치 > 판매가 건수/게임'],[[VN[v],f(m(v,'world.replacement_screen_count')),f(m(v,'world.replacement_screen_positive'))] for v in VN]))
    add('<p>검사는 현재 주력 산업을 유지하고 구형·신형이 모두 정상 작동하며, 늘어난 산출을 현재 기준가격으로 전부 유용하게 쓴다고 가정한다. 남은 라운드의 추가 산출 가치를 공개 판매가와 비교했으며 실제 교체 구매를 실행하지 않았다. 정비비 차이·연구 조건·미래 가격·산업 변경 등 교체 이유 전체의 가치를 평가한 것은 아니다.</p><p>고급 기계를 억지로 사게 만들기 전에, 기존 <strong>상위 개발에 필요한 기계 + 개발비 + 개발 재료</strong>를 묶어 남은 기간에 쓸모가 있는 투자로 판단하는 방식을 다음에 검증하는 것이 적절하다. 이미 가진 기계를 폐기하거나 특정 국가의 매출을 보장하지 않는다. 동시에 초기 원료·묶음 단위·실제 생산 규모의 관계를 조정해야 한다. 이 후속 조정은 이번 2,350게임에서 시험한 내용이 아니다.</p></section>')
    add('<section><h2>11. 종합 점수는 진단용으로만 비교</h2>')
    add(table(['기존6국','기준선 점수','coupled 점수','산업 점수: 기준→연동 /25'],[[LABELS[n],f(c('baseline',n,'score')),f(c('coupled',n,'score')),f(c('baseline',n,'industry'))+' → '+f(c('coupled',n,'industry'))] for n in list(LABELS)[:6]]))
    add('<p>산업 점수에는 실제 사용량/생산량 비율이 있다. 생산량을 줄이면 실제 사용이 증가하지 않아도 비율이 상승할 수 있다. 남은 선불 가공 재료는 기존 평가에서 별도 자산으로 더하지 않았다. 신규3국의 성장 목표도 아직 정해지지 않아 점수는 미산출이다. 그러므로 이 결과로 9개국 우승률이나 배정 공정성이 통과했다고 말하지 않는다.</p></section>')
    add('<section><h2>12. 학생 화면과 학습 효과</h2><p>복잡한 재료 칸·예측식을 학생에게 계산시키기보다 자동 처리하고 원인을 짧게 보여 주는 화면을 제안한다. 주요 선택은 수입·판매 가격과 수량·주력 산업·개발을 유지한다.</p>')
    add(table(['화면 정보','학생에게 보일 예시'],[
        ['생산 능력과 실제 생산','기계 생산 능력은 4개예요. 재고가 남아 이번에는 1개만 만들어요.'],
        ['수입의 목적','이 광물은 다음 기계 생산에 사용해요.'],
        ['판매 결과','팔린 2개 중 1개가 다른 나라의 생산에 사용됐어요.'],
        ['개발의 전체 준비물','이 개발에는 2등급 기계와 개발비·광물이 필요해요.']]))
    add('<p>위 문구는 화면 설계 제안이며 이번 파일은 완성 웹앱이 아니다. 3명 학생+6개 자동 국가의 실제 사용, 동시 접속, 40분+40분 안의 설명·9라운드·정리 시간은 별도로 시험해야 한다. 이번에는 계산 실행 속도를 수업 진행 속도로 대체하지 않았다.</p><h3>수업 마무리 질문</h3><ol><li>수입한 물건 하나는 생활·생산·개발 중 어디에 쓰였고, 수입하지 못했다면 무엇이 달라졌을까?</li><li>기계를 적게 만들어 재고가 줄었다면 수출도 잘됐다고 말할 수 있을까? 다른 나라의 사용 기록으로 설명해 보자.</li><li>이번 판매 가격과 수량은 필요한 물건을 사는 데 어떤 도움이 됐을까? 다시 한다면 무엇을 바꾸고 싶을까?</li></ol></section>')
    add('<section><h2>13. 오류 수정·검증의 구체적 범위</h2><ul><li>계획 생산량 0은 실제 생산 0·원료 0이다. G1 안전 생산이 잘못 발동하지 않는다.</li><li>구매 예측·투자 후 예측·실제 생산에서 동일한 기계 수량·재료 계획을 사용한다. 이후 주력 변경의 가능한 최대 생산량까지 예측한다.</li><li>원료에서 얻은 가공 재료는 국가·원료 종류·세대별로 보존한다. 거래·세대 변경으로 재료를 중복 사용하지 않는다.</li><li>구형 재고가 있어도 새 세대 첫 생산을 계획하되, 재료가 있어야 실제 새 세대가 출시된다.</li><li>정비 횟수는 기계 실물 ID에 붙는다. 재등록·재판매로 횟수가 초기화되지 않는다.</li><li>정비 불가 시 기계 추가 보너스만 멈추며 기본 생산과 주력 보너스는 유지된다.</li><li>모든 나라의 투입·장비 판정을 끝낸 뒤 새 생산품을 생성한다. 같은 생산 단계의 새 광물을 먼저 만든 나라만 유리하게 즉시 쓰지 못한다.</li><li>생산을 쉬는 기계에 주력 보너스를 낭비하던 자동 판단을 실제 추가 생산량에 맞췄다.</li></ul>')
    add('<p>기존 141개 + 신규 27개 = 168개 테스트를 통과했다. 기준선은 기존 v5 balanced와 기존 결과 필드·거래·현금 원장·가격이 일치하는 회귀 검사를 포함한다. '+f(meta['verification_calls'],0)+'회는 게임 중 반복 검사 호출 수이며 서로 다른 테스트 수가 아니다. 독립 감사는 본 비교 현금 원장 81,000행과 대표 시드의 물품·재료·정비 기록을 다시 계산했다. 감사 원문은 <code>machinery_results/independent_audit.json</code>에 포함했다.</p><p>한계: 기존 안전 생산, 주문 깊이를 단순화한 구매 예산, 마지막 라운드의 향후 생산용 추천, 고급 교체·개발의 묶음 판단, 전체9국 목표 점수와 실제 학생 수업 검증은 남아 있다. 낮은 오류 발생률과 교육적 성공은 다른 판정이다.</p></section>')
    add('<section><h2>14. 재현과 결과 읽기</h2><p>패키지의 기존 정식 결과를 보존하며 새 폴더에 재현하는 명령:</p><pre>python3 -m unittest test_previous test_fixes test_costs test_expansion test_budget test_machinery\npython3 run_machinery_validation.py --n 200 --stress-n 30 --workers 4 --output-dir reproduced_results\npython3 audit_machinery_results.py --results reproduced_results\npython3 build_machinery_report.py --results reproduced_results --report REPRODUCED_V6_KO.html</pre><p>기존 결과 폴더에는 덮어쓰지 않는다. 코드·테스트를 바꾸었다면 먼저 실제 테스트를 실행하고 새 검증 기록을 남겨야 한다. 옛 검증 기록과 새 코드의 해시가 다르면 정식 실행기는 중단한다.</p><p>후보 한 판만 실행:</p><pre>from machinery_engine import Game\ngame = Game(seed=34000, mode="coupled")\nresult = game.run()\ntrace = game.trace()</pre><p>원본 자료: <code>runs.jsonl.gz</code> 전체 게임 결과, <code>round_ledgers.jsonl.gz</code> 본 비교 원장, <code>first_seed_traces.json.gz</code> 대표 시드 상세 기록, <code>summary.json</code> 집계·대응 차이, <code>run_manifest.json</code> 고정 조건·소스 해시. 예비 자료 <code>pilot.json</code>는 개발용이며 정식 평균에 합치지 않았다. 보고서 생성 때 실제 완료 게임 수가 2,350과 다르거나 독립 감사가 통과하지 않으면 중단하도록 했다.</p></section>')
    add('<section><h2>15. 현실 경제 개념의 출처</h2><ol><li><a href="https://www.federalreserve.gov/releases/g17/CapNotes.htm">Federal Reserve — Capacity and Capacity Utilization Methodology</a>: 산출과 생산 능력의 구분.</li><li><a href="https://www.census.gov/programs-surveys/qpc/about.html">U.S. Census Bureau — Quarterly Survey of Plant Capacity Utilization</a>, <a href="https://www2.census.gov/programs-surveys/qpc/technical-documentation/questionnaires/form-mq-c2-worksheet-final-after-omb-approval.pdf">조사표 Item 3B</a>: 주문·완제품 재고·재료 등이 가동률에 영향을 줄 수 있음.</li><li><a href="https://www.bls.gov/opub/hom/opt/concepts.htm">BLS — Productivity Measures: Concepts</a>: 자본이 여러 기간 서비스를 제공하고 노후화·기술 변화로 성능이 달라지는 개념.</li><li><a href="https://www.deere.com/assets/pdfs/common/qrg/e240c00001.pdf">John Deere — E240 Replacement Parts Guide, July 2022</a>: 사용 시간에 따른 실제 정비 일정의 예.</li></ol><p>열람일 2026-11-18. 현실 자료는 설계 원리를 참고하기 위한 것이며, 국가별 자금·가격·생산량·재료 소모·정비 주기의 실증 추정 근거가 아니다.</p></section>')
    add('<details><summary>부록: 메카니아 9라운드 현금 흐름 보기</summary>')
    for v in ('baseline','coupled','service'):
        add('<h3>'+VN[v]+'</h3>')
        add(table(['R','시작 G','판매 +','구매 −','투자 −','운영수입 +','종료 G','만족도'],[[i]+[f(row[k]) for k in ('cash_start','sales','purchases','investment','operating_income','cash_end','happy')] for i,row in enumerate(derived['round_means'][v]['Mechania'],1)]))
    add('</details>')
    css='''*{box-sizing:border-box}body{margin:0;background:#eef2f5;color:#20333d;font:16px/1.8 "Noto Sans KR","Malgun Gothic",Arial,sans-serif}main{max-width:1180px;margin:auto;background:#fff;padding:52px 58px 64px}header{border-bottom:5px solid #15636a;padding-bottom:25px}.eyebrow{font-size:13px;color:#15636a;font-weight:700}h1{font-size:38px;line-height:1.35;margin:12px 0 20px}h2{font-size:24px;line-height:1.5;color:#104e57;margin:0 0 16px}h3{font-size:19px;margin-top:26px}p{margin:12px 0}section{padding:28px 0;border-bottom:1px solid #d9e2e7}.lead{background:#eaf5f2;margin:28px -18px 20px;padding:25px;border:0;border-radius:10px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.cards div{background:#f1f5f8;border-radius:8px;padding:16px}.cards b{display:block;font-size:28px;color:#15636a}.cards span{font-size:12px;color:#506b78}.table-wrap{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:10px 11px;border-bottom:1px solid #d9e2e7;text-align:left;vertical-align:top}th{background:#eaf0f4;font-weight:700}tbody tr:nth-child(even){background:#f8fafb}td:first-child{font-weight:600}code{font-size:.9em;background:#edf1f5;padding:2px 5px;border-radius:3px}pre{background:#1b343f;color:#eef9f7;border-radius:8px;padding:18px;overflow:auto;line-height:1.7;font-size:13px}a{color:#12676c}li{margin:8px 0}details{margin-top:28px;background:#f3f6f8;padding:18px;border-radius:8px}summary{cursor:pointer;font-weight:700}footer{font-size:12px;color:#627984;padding-top:28px}@media(max-width:760px){main{padding:24px 18px}h1{font-size:29px}.cards{grid-template-columns:repeat(2,1fr)}h2{font-size:21px}table{font-size:12px}th,td{padding:8px}}@media print{body{background:white;font-size:11px}main{padding:0;max-width:none}h1{font-size:27px}h2{font-size:18px}h3{font-size:15px}section{padding:18px 0}table{font-size:10px}th,td{padding:5px 7px}tr{break-inside:avoid}h2,h3{break-after:avoid}.table-wrap{overflow:visible}.cards b{font-size:20px}details{display:block}}'''
    doc='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>#11 무역 게임 — 기계 생산·수요 검증 v6</title><style>'+css+'</style></head><body><main>'+''.join(b)+'<footer>이 자료는 반복 실행한 게임 모형의 기록이다. 실제 무역 시장의 통계나 학생 성취도 실험으로 해석하지 않는다.</footer></main></body></html>'
    args.report.resolve().write_text(doc,encoding='utf-8')
    print('Built',args.report.resolve().name)

if __name__=='__main__':main()
