"""Build a self-contained Korean report from COMPLETED validation outputs."""
from pathlib import Path
from collections import defaultdict
from html import escape
import gzip, hashlib, json, statistics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'budget_results'
LABELS={'Tropia':'트로피아','Grainia':'그레니아','Oilia':'오일리아','Mechania':'메카니아',
        'Mineria':'미네리아','Technia':'테크니아','Novia':'노비아','Agrea':'아그레아','Ferria':'페리아'}
VN={'baseline':'기존안','funded':'생산 자원 확보','living':'생활 수입 우선 추가',
    'balanced':'생활 충족 후 투자 추가','stock_guard':'재고에 따른 원료 구매 보류'}
GOODS={'banana':'바나나','wheat':'밀','ore':'광물','fuel':'연료','machine':'기계','electronics':'전자제품'}


def table(headers,rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def main():
    s=json.loads((OUT/'summary.json').read_text())
    assert s['metadata']['completed_games']==1840, 'This report expects the documented 200/30 design.'
    def m(v,path):return s['experiments'][f'main:{v}:None:normal']['metrics'][path]['mean']
    def c(v,n,k):return m(v,f'countries.{n}.{k}')
    def f(x,d=2):return f'{x:,.{d}f}'
    def delta(path):return s['paired']['main:baseline->balanced'][path]
    with gzip.open(OUT/'runs.jsonl.gz','rt') as file:records=[json.loads(line) for line in file]
    main_records={v:[r for r in records if r['phase']=='main' and r['variant']==v] for v in VN}
    gaps={v:statistics.mean(max(x['cash'] for x in r['countries'].values())-min(x['cash'] for x in r['countries'].values()) for r in rs) for v,rs in main_records.items()}
    machine_use={v:statistics.mean(sum(x['use_by_good']['machine'] for x in r['countries'].values()) for r in rs) for v,rs in main_records.items()}
    ledger=defaultdict(list)
    with gzip.open(OUT/'round_ledgers.jsonl.gz','rt') as file:
        for line in file:
            row=json.loads(line)
            for x in row['rows']:ledger[row['variant'],x['country'],x['round']].append(x)
    averages={v:{n:[{k:statistics.mean(row[k] for row in ledger[v,n,r]) for k in ('cash_start','sales','purchases','investment','operating_income','cash_end','happy')}
                     for r in range(1,10)] for n in LABELS} for v in VN}
    derived={'all_nine_cash_gap':gaps,'all_nine_unique_produced_machines_used':machine_use,
             'mechania_generation2_pct':{v:100*sum(r['countries']['Mechania']['machine_gen']>=2 for r in rs)/len(rs) for v,rs in main_records.items()},
             'round_means':averages,
             'runs_sha256':hashlib.sha256((OUT/'runs.jsonl.gz').read_bytes()).hexdigest()}
    (OUT/'derived_metrics.json').write_text(json.dumps(derived,ensure_ascii=False,indent=2))
    blocks=[]
    def add(x):blocks.append(x)
    add('<header><p class="eyebrow">아이디어 노트 · #11 무역 게임 · 설계·검증 v5</p><h1>메카니아 자금 흐름과<br>투자 판단 검증</h1><p class="subtitle">9개국 · 9라운드 · 동일 조건의 정책 비교 · 2026년 11월 18일</p></header>')
    add('<section class="lead"><h2>이번 결과</h2><p><strong>투자 계획의 자원 계산 불일치는 수정했다. 메카니아의 경제적 불리함과 기계 과잉은 남아 있다.</strong></p><p>생활 수요를 우선 충족하고 투자 후 다음 생산 자원을 확보하는 <code>balanced</code>를 후속 검증 후보로 남긴다. 메카니아 현금이 늘었다거나 국가 간 공정성이 검증됐다는 결론은 지지되지 않는다.</p></section>')
    add('<div class="cards"><div><b>1,840</b><span>정식 완료 게임</span></div><div><b>141</b><span>통과한 테스트</span></div><div><b>51,520</b><span>반복 불변조건 검사</span></div><div><b>81,000</b><span>본 비교 현금 원장 행</span></div></div>')
    add('<section><h2>1. 무엇을 유지하고 무엇을 비교했는가</h2><p>v4의 역할 조합 9개국, 9라운드, 시작 자금·생산량·자원 소비 공식·가격 결정·투자 비용·점수식을 고정했다. 보관비·추가 원료 비용은 기존과 같이 꺼져 있다. 새 보조금이나 무제한 구매자는 없다. 변경 대상은 자동국가의 구매·투자 판단이며, 학생의 합법적인 거래·투자 선택을 제한하는 새 게임 규칙이 아니다.</p>')
    add(table(['구분','게임 수','난수 시드','용도'],[
      ['정상 운영: 5개 안 × 200회','1,000','22000–22199','정책별 대응 비교'],
      ['기존/후보 × 기존6국 각각 반값·무행동 × 30회','720','24000–24029','가격 반복·무행동 영향'],
      ['기존/후보 × 정상·무역 금지 × 30회','120','24000–24029','스트레스의 대응 기준'],
      ['합계','1,840','서로 다른 본 비교·스트레스 시드','모두 완료한 결과만 집계']]))
    add('<p>개발용 시드 18000–18029의 예비 비교, 회귀 테스트, 기준선 재현용 실행은 위 합계에 포함하지 않았다. 같은 시드는 같은 결정 키의 난수를 공유하며, 정책 변경 이후 거래·가격·재고 경로는 달라질 수 있다. 모든 국가는 규칙 기반 자동 정책이다. 실제 학생 3명·AI 6명의 수업 실험이나 웹앱 동시접속 검증은 아니다.</p></section>')
    add('<section><h2>2. 메카니아가 가난해 보였던 이유</h2><p>기존안의 200게임 모두 기계 개발에 <strong>한 번, 125G</strong>를 투자했다. 반복적인 과잉 투자라는 가설은 맞지 않았다. 주된 부담은 기계의 낮은 판매량과 지속적인 광물·생활용품 수입이다.</p>')
    add(table(['현금 원장: 9라운드 누계','기존안','생활 충족 후 투자 후보'],[
      ['시작 자금','215.00','215.00'],
      ['상품 판매 수입 (+)',f(c('baseline','Mechania','revenue')),f(c('balanced','Mechania','revenue'))],
      ['상품 구매 지출 (−)',f(c('baseline','Mechania','purchases')),f(c('balanced','Mechania','purchases'))],
      ['투자 지출 (−)',f(c('baseline','Mechania','investment')),f(c('balanced','Mechania','investment'))],
      ['만족도 연계 운영수입 (+)',f(c('baseline','Mechania','tax')),f(c('balanced','Mechania','tax'))],
      ['종료 현금',f(c('baseline','Mechania','cash')),f(c('balanced','Mechania','cash'))]]))
    add('<p class="formula">기존안: 215 + 177.520 − 392.100 − 125 + 173.575 = 48.995G<br>후보안: 215 + 194.280 − 409.545 − 124.375 + 173.285 = 48.645G</p>')
    add(table(['구매 품목','기존안 지출 G','후보안 지출 G'],[[GOODS[g],f(c('baseline','Mechania','purchase_by_good.'+g)),f(c('balanced','Mechania','purchase_by_good.'+g))] for g in ('banana','wheat','ore','fuel','machine','electronics')]))
    add('<p>판매 수입에는 초기 지급 연료 판매와 일부 재판매도 포함된다. 광물 구매액과 기계 판매액의 차이는 현금 흐름의 부담을 보여 주지만, 재고·바터·설비 가치를 반영한 회계상 이익 계산은 아니다.</p><h3>확인한 계획 불일치</h3><ol><li>기계 Lv1인 상태로 다음 생산 광물 1개를 준비한다.</li><li>거래 종료 후 기계 Lv2/G2에 투자한다.</li><li>다음 생산에는 광물 2개가 필요하지만 1개만 보유한다.</li><li>원래의 안전 생산 규칙에 따라 G1 기계 1개만 생산한다.</li></ol><p>수정본은 가상 투자 후의 산업 수준·기술을 적용해 다음 생산 자원을 계산한다. 연구에 소비할 광물과 이후 생산에 남길 광물을 따로 계산하고, 실제 투자 직전에도 두 용도로 충분한지 확인한다. 범위는 투자한 산업의 증가분뿐 아니라 <strong>다음 라운드의 전체 산업 운영 자원</strong>이다.</p></section>')
    add('<section><h2>3. 비교한 다섯 가지 운영 방식</h2>')
    add(table(['코드 설정','변경 내용','판단'],[
      ['baseline','기존 v4 정책 그대로','대응 기준선'],
      ['funded','개발 재료와 투자 후 전체 다음 생산 자원을 확보한 경우에 투자','계획은 일치하지만 생활 수입이 밀림'],
      ['living','funded + 기본 생활 전자제품 수량을 원료보다 먼저 구매','구매 순서만으로는 부족'],
      ['balanced','living + 당회 식량·기본 전자제품 수량이 충족된 뒤 투자','후속 검증 후보'],
      ['stock_guard','living + 자국 현행등급 미사용 내구재가 정상생산 2회분을 넘으면 원료 구매·추가 투자 보류','기본안으로 채택하지 않음']]))
    add('<p>생활 충족 조건은 최고급 전자제품을 강요하지 않는다. 구형이어도 기본 수량이 있으면 된다. 선택적 신제품 교체는 필수 수입 뒤에 남는다. 재고 조절안은 자동 생산 규칙을 바꾸지 않으므로 원료가 없으면 기존 G1 안전 생산이 계속된다. 구매 목표를 줄인 다음의 안전 생산 횟수는 연관 지표이며, 모든 원료 부족의 원인을 완전히 분리한 수치는 아니다.</p>')
    add(table(['안','메카니아 현금 G','만족도 /100','생산 차질 회/게임','유효수출 개/게임','G2 달성 %'],[[VN[v],f(c(v,'Mechania','cash')),f(c(v,'Mechania','happy')),f(c(v,'Mechania','production_failures')),f(c(v,'Mechania','useful_exports')),f(derived['mechania_generation2_pct'][v],1)] for v in VN]))
    add('<p><strong>원료 확보만 강화한 안은 만족도를 90.50에서 85.44로 낮췄다.</strong> 재고에 따라 원료를 줄인 안은 메카니아 현금이 115.98G로 늘었으나, 미네리아 현금은 88.38→40.34G, 유효수출은 12.96→7.66개로 줄었다. 메카니아의 G2 달성도 100%→71.5%로 떨어졌다. 현금만 보면 이득이지만 산업·무역을 함께 보면 기본안으로 채택하기 어렵다.</p></section>')
    add('<section><h2>4. 후보안의 효과와 남은 문제</h2>')
    add(table(['지표','기존안','후보안'],[
      ['기존6국 평균 만족도',f(m('baseline','world.original_happy')),f(m('balanced','world.original_happy'))],
      ['전체9국 평균 만족도',f(m('baseline','world.happy')),f(m('balanced','world.happy'))],
      ['전체 거래 수량',f(m('baseline','world.trade_units')),f(m('balanced','world.trade_units'))],
      ['기존6국 외부 필요 충족률 %',f(100*m('baseline','world.original_coverage')),f(100*m('balanced','world.original_coverage'))],
      ['전체 미판매 등록 재고',f(m('baseline','world.listed')),f(m('balanced','world.listed'))],
      ['전체9국 1국당 2라운드 이상 미사용 재고',f(m('baseline','world.aged_unused_per_country')),f(m('balanced','world.aged_unused_per_country'))],
      ['기존6국 게임별 최대−최소 현금 평균 G',f(m('baseline','world.original_cash_gap')),f(m('balanced','world.original_cash_gap'))],
      ['전체9국 게임별 최대−최소 현금 평균 G',f(gaps['baseline']),f(gaps['balanced'])]]))
    add('<p>전체 생활과 무역에는 개선이 있지만, <strong>9개국 전체 현금 격차는 커졌다.</strong> 현금 격차 하나가 종합 공정성을 뜻하지는 않지만, 기존6국만의 격차 감소로 전체 공정성이 좋아졌다고 결론내릴 수 없다.</p><h3>메카니아의 기계 산업은 아직 회복되지 않았다</h3>')
    add(table(['메카니아 기계 지표','기존안','후보안'],[
      ['기계 생산량',f(c('baseline','Mechania','produced.machine')),f(c('balanced','Mechania','produced.machine'))],
      ['생산한 기계 중 해외 실제 사용',f(c('baseline','Mechania','export_used_by_good.machine')),f(c('balanced','Mechania','export_used_by_good.machine'))],
      ['생산한 기계 중 국내외 한 번 이상 사용',f(c('baseline','Mechania','use_by_good.machine')),f(c('balanced','Mechania','use_by_good.machine'))],
      ['최종 기계 보유',f(c('baseline','Mechania','end_stock_by_good.machine')),f(c('balanced','Mechania','end_stock_by_good.machine'))],
      ['최종 보유 기계 중 한 번도 사용하지 않음',f(c('baseline','Mechania','unused_by_good.machine')),f(c('balanced','Mechania','unused_by_good.machine'))],
      ['밀의 해외 실제 사용',f(c('baseline','Mechania','export_used_by_good.wheat')),f(c('balanced','Mechania','export_used_by_good.wheat'))]]))
    add('<p>메카니아의 유효수출 합계 증가는 밀 수출이 견인했다. 기계의 실제 해외 사용은 줄었으며 기계 재고는 늘었다. 전체9국 기계 생산은 '+f(m('baseline','world.production.machine'))+'→'+f(m('balanced','world.production.machine'))+'개인데, 생산한 기계 중 한 번 이상 사용한 수량은 '+f(machine_use['baseline'])+'→'+f(machine_use['balanced'])+'개에 그쳤다. 수출 거래 횟수와 고유 상품의 실제 사용량은 다른 지표다.</p>')
    add('<h3>반복 변동을 고려한 해석</h3>')
    cirows=[]
    for title,path in [('메카니아 현금 G','countries.Mechania.cash'),('메카니아 만족도','countries.Mechania.happy'),('메카니아 기계 해외 실제 사용','countries.Mechania.export_used_by_good.machine'),('기존6국 평균 만족도','world.original_happy'),('전체 미판매 등록 재고','world.listed')]:
        d=delta(path);cirows.append([title,f(d['mean'],3),f(d['ci95'][0],3)+' ~ '+f(d['ci95'][1],3)])
    add(table(['후보−기존 대응 차이','평균','근사 95% 구간'],cirows))
    add('<p>메카니아 현금과 만족도의 차이 구간은 0을 포함한다. 따라서 둘이 개선됐다고 단정하지 않는다. 이 구간은 모형 내 난수 시드 차이만 반영하며, 학생·수업·실물 경제의 불확실성을 나타내지 않는다.</p></section>')
    add('<section><h2>5. 다른 국가에 부담을 옮기지는 않았는가</h2>')
    add(table(['국가','현금 기존→후보 G','만족도 기존→후보','유효수출 기존→후보'],[[LABELS[n],f(c('baseline',n,'cash'))+' → '+f(c('balanced',n,'cash')),f(c('baseline',n,'happy'))+' → '+f(c('balanced',n,'happy')),f(c('baseline',n,'useful_exports'))+' → '+f(c('balanced',n,'useful_exports'))] for n in LABELS]))
    add('<p>미네리아는 현금 3.50G 감소와 함께 판매수입 217.17→234.54G, 투자 지출 89.28→104.25G, 유효수출 12.96→13.49개 변화가 있었다. 현금 차이의 95% 구간은 −9.61~+2.61G이므로 현금만으로 확실한 악화를 단정하지 않는다. 테크니아 현금은 감소하고 노비아는 증가했다. 다음 균형 검증은 새3국을 포함해야 한다.</p><p>기존 종합 점수는 보존했지만 신규3국 성장 목표는 여전히 미정이다. 9개국 우승률이나 국가 배정 공정성 통과 판정은 산출하지 않았다.</p></section>')
    add('<section><h2>6. 반값 반복 판매와 무행동</h2><p>반값 정책은 <strong>기준가격의 50%에 계속 판매하되, 구매·투자·필요 재고 보호는 정상 정책으로 수행</strong>한다. 실제 시장의 최저 호가를 탐색하는 정책이나 의욕 없는 학생의 전체 행동을 그대로 구현한 것은 아니다.</p>')
    cheaprows=[]
    for n in list(LABELS)[:6]:
        p=s['paired'][f'stress:balanced:{n}:cheap']
        cheaprows.append([LABELS[n],f(p[f'countries.{n}.cash']['mean']),f(p[f'countries.{n}.happy']['mean']),f(p[f'countries.{n}.score']['mean'])])
    add(table(['후보안에서 본인 반값 판매','현금 차이 G','만족도 차이','기존 진단 점수 차이 /100'],cheaprows))
    add('<p>싼 가격의 유효한 교역에 보상이 생기는 것 자체가 오류는 아니다. 다만 현금 손해가 큰 농업국과 이득이 큰 전자제품국의 차이, 가격을 숙고하는 전략과 단순 반복 전략의 차이는 남아 있다. 평균 진단 점수는 6국 모두 올랐지만, 모든 판에서 반값이 유리하다는 의미는 아니다. 가격을 낮췄다는 이유만으로 벌점을 주는 수정은 권하지 않는다.</p>')
    idlerows=[]
    for n in list(LABELS)[:6]:
        idlerows.append([LABELS[n]]+[f(s['paired'][f'stress:{v}:{n}:idle']['world.other_original_five_happy']['mean'],3) for v in ('baseline','balanced')])
    add(table(['거래·투자 무행동 국가','기존안: 다른 기존5국 만족도 차이','후보안: 다른 기존5국 만족도 차이'],idlerows))
    add('<p>무행동 국가는 자동 생산과 운영수입은 계속 받는다. 무행동 국가의 현금 축적을 우수한 경제 운영으로 해석하면 안 된다. 다른 국가의 피해가 줄어도 해당 학생의 참여·학습이 보장되는 것은 아니다.</p>')
    normal=s['experiments']['stress:balanced:None:normal']['metrics']['world.original_happy']['mean']
    nt=s['experiments']['stress:balanced:None:no_trade']['metrics']['world.original_happy']['mean']
    add('<p>후보안의 대응 스트레스 표본에서 기존6국 만족도는 정상 '+f(normal)+'점, 무역 금지 '+f(nt)+'점이다. 모형 안에서 무역이 생활에 기여하는 경로는 유지된다. 거래 금지에 대응해 투자 판단도 변하므로 모든 행동을 고정한 실험은 아니며, 학습 성취도 검증도 아니다.</p></section>')
    add('<section><h2>7. 9라운드 메카니아 현금 원장</h2><p>각 칸은 200게임 평균이다. 반복별로 모두 원장이 맞아야 집계에 포함되며, 표시 반올림으로 행 합계가 0.01G 어긋날 수 있다.</p>')
    for v in ('baseline','balanced'):
        add('<h3>'+VN[v]+'</h3>')
        add(table(['R','시작 G','판매 +','구매 −','투자 −','운영수입 +','종료 G','만족도'],[[i]+[f(row[k]) for k in ('cash_start','sales','purchases','investment','operating_income','cash_end','happy')] for i,row in enumerate(averages[v]['Mechania'],1)]))
    add('<p>후보안은 1라운드 투자를 대부분 2~3라운드로 미루어 생활·자원 준비와 연결했다. 그러나 중후반에는 판매보다 구매가 큰 흐름이 지속된다. 투자 시점 조정만으로 기계의 지속적인 수익 문제가 해결되지 않는 이유다.</p></section>')
    add('<section><h2>8. 학생에게 보여 줄 판단 정보</h2><p>복잡한 원장 전체를 학생에게 보여 주는 대신, 아래 세 가지를 짧게 제공하는 화면을 제안한다. 아직 실제 화면·수업 관찰로 검증한 내용은 아니다.</p>')
    add(table(['판단 카드','학생에게 필요한 정보','예시 문구'],[
      ['이번 생활','현재 식량·생활용품의 부족량','이번 라운드에 바나나 1개가 더 필요해.'],
      ['다음 생산','투자 전후 다음 생산 원료 수량','기계를 개발하면 다음 생산에 광물 2개가 필요해.'],
      ['이번 투자','생활·운영자원을 확보한 뒤 투자 여력','생활용품과 다음 생산 원료를 먼저 준비하면 좋아.']]))
    add('<p>자동 추천은 학생이 구매 목적을 설명할 수 있게 돕는 장치로 설계한다. 결과 분석에서는 “싸게 팔았는가”만 묻지 않고, 어떤 수입이 생활·생산·발전에 쓰였는지 확인한다. 3명 수업의 실제 이해도, 의욕이 낮은 학생의 참여, 40+40분 진행 속도는 별도 관찰이 필요하다.</p></section>')
    add('<section><h2>9. 다음 조정 순서</h2><ol><li><strong>기계의 기본 생산량·주력 보너스와 실제 사용 수요를 맞춘다.</strong> 여러 라운드 사용하는 내구재가 매번 대량 생산되는 구조부터 작은 범위로 비교한다.</li><li><strong>고급 기계의 가격과 효율 개선 가치를 비교한다.</strong> 현재 AI에는 일반 기계의 효율 향상 목적 교체 판단이 없고, 실제 추가 생산 가치가 가격을 회수할 수 있는지도 미검증이다. 강제 교체 수요를 만들기보다 남은 기간의 효과를 계산해야 한다.</li><li><strong>광물 공급국·추가 전자제품국의 변화를 함께 본다.</strong> 메카니아 지출을 줄이면 미네리아·페리아 수입에 영향을 주므로 9개국 전체를 확인한다.</li><li><strong>실제 판매 가능성을 반영한 수량·가격 추천을 검증한 뒤 점수를 조정한다.</strong> 미판매 평가나 활용률 점수만 바꾸어 경제 문제를 가리지 않는다.</li></ol><p>현재 코드에서 마지막 라운드 생산 지원용 기계 추천과, 최저 호가의 물량 깊이를 무시하는 구매 예산 근사는 별도 미해결 사항이다. 이번 변경 범위에는 포함하지 않았다.</p></section>')
    add('''<section><h2>10. 구현·검증과 재현</h2><p>v4 경제 엔진 4개 파일은 원본 그대로 보존했다. <code>budget_engine.py</code>는 정책 비교, <code>budget_trace.py</code>는 원장 추적, <code>run_budget_validation.py</code>는 고정 시드 실행, <code>test_budget.py</code>는 추가 경계 검증을 담당한다.</p><p>기존 120개 + 새 21개 = 141개 테스트를 한 번에 실행해 통과했다. 자금·상품 보존, 소유권·판매 잠금, 중복 명령, 순수 예측, 연구/운영 재료 분리, 생활 조건, 원장 일치 등을 검사했다. 51,520은 게임 진행 중 불변조건 함수를 반복 호출한 횟수이며 서로 다른 테스트 수가 아니다.</p><p>원본 실행 기록의 시드 10000·10037·10199를 현재 기준선으로 재현하여 기존 국가·세계 요약의 모든 직렬화 필드가 일치함을 확인했다. 정식 원장 81,000행도 현금식·상품별 합·라운드 연속성·최종 잔액을 독립 재계산해 불일치가 없었다.</p><pre>python3 -m unittest test_previous test_fixes test_costs test_expansion test_budget
python3 run_budget_validation.py --n 200 --stress-n 30 --workers 4
python3 build_budget_report.py</pre><p>한 판 실행:</p><pre>from budget_trace import Game
game = Game(seed=22000, variant="balanced")
result = game.run()
ledger = game.cash_ledger</pre><p>주요 근거: <code>budget_results/summary.json</code>, <code>runs.jsonl.gz</code>, <code>round_ledgers.jsonl.gz</code>, <code>first_seed_traces.json.gz</code>, <code>run_manifest.json</code>, <code>derived_metrics.json</code>, <code>compatibility_checks.json</code>. 원본 v4 결과는 <code>results/</code>에 별도로 보존했다.</p></section>''')
    css='''*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#192b3a;font:16px/1.75 "Noto Sans KR","Malgun Gothic",Arial,sans-serif}main{max-width:1120px;margin:auto;background:white;padding:54px 60px 70px}header{border-bottom:5px solid #165d67;padding-bottom:28px}.eyebrow{font-size:13px;font-weight:700;letter-spacing:.05em;color:#165d67}h1{font-size:38px;line-height:1.35;margin:12px 0}.subtitle{color:#516678}h2{font-size:24px;line-height:1.45;color:#114d56;margin:0 0 18px}h3{font-size:19px;margin-top:26px}section{padding:30px 0;border-bottom:1px solid #dae3e8}.lead{background:#eaf5f3;margin:30px -16px 20px;padding:24px;border:0;border-radius:10px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.cards div{background:#f2f5f9;border-radius:8px;padding:18px}.cards b{display:block;font-size:27px;color:#165d67}.cards span{font-size:12px;color:#516678}.table-wrap{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px 12px;border-bottom:1px solid #dae3e8;text-align:left;vertical-align:top}th{background:#eaf0f4;font-weight:700}tbody tr:nth-child(even){background:#f7f9fb}td:first-child{font-weight:600}code{font-size:.9em;background:#edf1f5;padding:2px 5px;border-radius:3px}pre{background:#182f3b;color:#ecf7f5;border-radius:6px;padding:18px;overflow:auto;line-height:1.6;font-size:13px}.formula{background:#f3f5f9;border-left:4px solid #165d67;padding:14px 20px}li{margin:8px 0}footer{font-size:12px;color:#627784;padding-top:30px}@media(max-width:700px){main{padding:24px 18px}h1{font-size:29px}.cards{grid-template-columns:repeat(2,1fr)}table{font-size:12px}th,td{padding:8px}h2{font-size:21px}}@media print{body{background:white;font-size:11px}main{max-width:none;padding:0}header{padding:0 0 14px}h1{font-size:28px}h2{font-size:18px}h3{font-size:14px}section{padding:18px 0}table{font-size:10px}th,td{padding:5px 7px}tr{break-inside:avoid}h2,h3{break-after:avoid}.cards b{font-size:20px}.table-wrap{overflow:visible}}'''
    doc='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>#11 무역 게임 — 메카니아 자금 흐름 검증 v5</title><style>'+css+'</style></head><body><main>'+''.join(blocks)+'<footer>단위 G는 게임 화폐이며 상품 수량은 게임용 묶음이다. 이 문서의 수치는 제공된 모형에서 실제 실행한 결과이며 실물경제 통계가 아니다.</footer></main></body></html>'
    (ROOT/'TRADE_BUDGET_REVIEW_KO.html').write_text(doc,encoding='utf-8')
    print('Built',ROOT/'TRADE_BUDGET_REVIEW_KO.html')


if __name__=='__main__':main()
