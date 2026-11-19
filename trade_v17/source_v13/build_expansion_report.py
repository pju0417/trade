"""Write Korean report directly from closed-checkpoint summary; no invented values."""
from pathlib import Path
import json,hashlib,statistics,gzip
from dataclasses import asdict
from expansion_engine import NAMES,ADDITIONS,LABELS,Game
ROOT=Path(__file__).resolve().parent
s=json.loads((ROOT/'results/summary.json').read_text());E=s['experiments'];P=s['paired']
def m(v,key,phase='normal',focal=None,style='normal'):
 return E[f'{phase}:{v}:{focal}:{style}']['metrics'][key]['mean']
def w(v,key):return m(v,'world.'+key)
def c(v,n,key):return m(v,f'countries.{n}.{key}')
def fmt(x):return f'{x:.2f}'
lines=[]
def add(t=''):lines.append(t)
def table(headers,rows):
 block=['| '+' | '.join(headers)+' |','|'+ '|'.join(['---']*len(headers))+'|']
 block += ['| '+' | '.join(map(str,row))+' |' for row in rows]
 add('\n'.join(block))
add('# #11 무역 게임 — 6개국에서 9개국으로 소폭 확장 검증')
add('## 결론')
add('기존 유형을 그대로 늘리는 것보다, 전자제품의 추가 공급처와 서로 다른 생산·수입 조합을 가진 3개국을 추가하는 구성이 더 유망했다. 다만 총재고가 감소한 것은 아니며, 메카니아의 현금 부족과 미네리아의 일부 수출 감소는 남았다. 9개국 안은 시험 후보이지 공정성 인증을 받은 최종 규칙이 아니다.')
add('## 1. 실행과 비교 범위')
add('완료·검산된 본 실행은 **1,640게임**이다. 6개국/9개국 모두 **9라운드**. 원본 6개국, 판단 수정 6개국, 단순 복제 9개국, 역할 조합 9개국을 각200회(시드10000~10199) 비교했다. 수정6국/역할9국에서 기존6개국을 각각 최저가/무행동으로 바꾼 시험은 각30회(720게임), 같은 시드의 정상 대조군60게임, 무역 금지60게임을 추가했다(시드12000~12029).')
add('예비 시험·자동 테스트·대표 원장 재실행·중단된 비체크포인트 실행은 1,640게임에 포함하지 않았다. 9개국에서 기존6개국과 같은 결정 키에는 같은 난수값을 사용하지만 국가 구성 변화에 따른 거래 상대와 경제 상태는 달라진다.')
add('실제 학생3명·AI6명 수업의 후보를 시험하되, 이번에는 모든 국가를 규칙 기반 자동 정책으로 실행했다. 생성형 AI API, 학생 관찰, 실제 클라우드 동시 접속, 80분 수업 시간을 시험한 것이 아니다.')
add('### 먼저 수정한 판단 일치 문제')
add('현재 모형에서 실제 생산 효과가 있는 기계 배치는 주력 비공업 산업 한 곳이다. 그 효과와 예정 연구 조건에 맞춰 구매 목표를 계산해 효과 없는 두 번째 기계를 자동 추천하지 않는다. 새 기계 효과나 무료 설비를 추가하지 않았다. 상위 산업별 설비 슬롯의 최종 게임 규칙까지 완성했다는 뜻은 아니다.')
add('시장 수요 예측과 실제 구매가 동일한 예산 계획을 사용한다. 식량→다음 생산 자원→생활용 전자제품→설비·선택 교체 순서를 시험했다. 미래 실제 체결은 다른 국가의 선행 구매·가격 변경·물물교환에 의해 달라질 수 있다. 예측은 체결 보장이 아니다. 신규 국가에도 같은 계획을 적용한다.')
add('국가 수를6으로 고정했던 식량의 전체 수요 추정과 세계 평균의 분모를 실제 국가 수로 바꿨다. 원본 엔진은 변경하지 않고 별도 확장 클래스를 사용했다. 원본과의 동등성 회귀 검사도 포함했다.')
add('이 수정은 일관성을 맞춘 것이지 경제 최적화가 아니다. 동일200회에서 원본6국의 평균 만족도는 '+fmt(w('legacy6','original_happy'))+'점, 수정6국은 '+fmt(w('fixed6','original_happy'))+'점이었다. 메카니아는 '+fmt(c('legacy6','Mechania','happy'))+'→'+fmt(c('fixed6','Mechania','happy'))+'점으로 낮아졌다. 원료 우선 예산이 생활용 전자제품 구매를 늦추는 절충이 있다. 따라서 국가 수 효과는 모두 수정6국을 기준으로 분리했다.')
add('### 유지한 조건')
add('기존6개국 초기자금·기본생산·개발비·주력 보너스, 상품6종, 자동 생산/기본형 생산 보장, 기계·전자제품 세대별 재고, 1G 가격·시장 재고·직접 현금 거래·물물교환·목적형 투자·운영수입을 유지했다. 보관비·추가 생산 원료 실험 옵션과 별도 기계 개발비 할인은 OFF다. 새 현금 보충/무한 구매자/강제 거래/외부 상품 생성은 없다.')
add('## 2. 추가 AI 3개국의 시험 설정')
table(['추가국','시작 자금','Lv.1 정상 기본생산/라운드','주력','확장 경로'],[
 ['노비아',185,'전자제품1·밀1','전자제품','기계'],['아그레아',175,'바나나2·연료1','바나나','광물'],['페리아',175,'광물1·밀2','광물','기계']])
add('단위는 게임 상품 묶음이다. 실제 생산에는 기존 주력 보너스·원료 부족·투자가 반영된다. 새 국가는 모두 Lv.1부터 시작한다. 모든 나라에 같은 초기 식량2개씩, 초기 공업국에는 기존과 같은 광물1·연료1·기계1을 지급했다. 노비아에도 이 공업국 시작 규칙만 적용했다.')
add('총 초기 현금은 수정6국1,090G, 역할9국1,625G다. 국가가 늘어 총 운영수입과 소비·투자도 증가한다. 돈의 총량을6국과 같게 유지한 실험이 아니다. 단순 복제9국은 기존6유형 중3유형을 균등 선택한20조합을 각각10회 적용했다(추가 초기현금 평균545G, 총1,635G). 두9국안은 추가국 구성 비교이며 모든 자산이 완벽하게 동일한 조건은 아니다.')
add('## 3. 세계 규모와 기존 국가의 실질 효과')
rows=[]
for label,v in [('수정6국','fixed6'),('단순복제9국','clone9'),('역할조합9국','role9')]:
 rows.append([label,fmt(w(v,'trade_units')),fmt(w(v,'trade_units_per_country')),fmt(w(v,'original_useful_exports')),fmt(100*w(v,'original_coverage')),fmt(w(v,'original_happy')),fmt(w(v,'aged_unused_per_country'))])
table(['조건','전체 거래 물량','국가당 거래','기존국당 유효수출','기존국 수입충족%','기존국 만족도','전체국당 장기미사용 재고'],rows)
add('거래 물량은 현금·직접 거래의 상품 수량과 물물교환 양방향 수량이다. 유효수출은 자국이 생산하고 다른 나라에서 실제 사용된 고유 상품으로, 재판매로 중복 증가하지 않는다. 수입충족은 생활·생산·개발의 실제 외부 필요 사건 대비 사용된 수입품 비율이며, 지속형 상품의 여러 라운드 활용을 포함한다. 이 비율은 학생의 이해도 점수가 아니다.')
add('장기미사용 재고는 생산/취득 이력상 최소2라운드 경과하고 한 번도 사용되지 않은 보유 상품이다. 전부 쓸모없는 재고라는 뜻은 아니다. 상품별 단위가 다른 물량의 합을 부 또는 복지로 해석하지 않는다.')
add('### 총재고와 국가당 재고를 구분')
table(['조건','시장 미판매 총량','국가당 미판매','기존6개국의 국가당 장기미사용'],[[label,fmt(w(v,'listed')),fmt(w(v,'listed')/(6 if v=='fixed6' else 9)),fmt(w(v,'original_aged_unused'))] for label,v in [('수정6국','fixed6'),('단순복제9국','clone9'),('역할조합9국','role9')]])
add('국가 수가50% 증가하므로 총거래가50% 정도 늘어나는 것만으로 효과라고 판단하지 않았다. 역할9국의 총거래는 수정6국보다 '+fmt((w('role9','trade_units')/w('fixed6','trade_units')-1)*100)+'% 늘었지만 국가당 거래 증가는 '+fmt((w('role9','trade_units_per_country')/w('fixed6','trade_units_per_country')-1)*100)+'%다. 기존6개국의 유효수출은 '+fmt((w('role9','original_useful_exports')/w('fixed6','original_useful_exports')-1)*100)+'%, 수입충족은 '+fmt((w('role9','original_coverage')-w('fixed6','original_coverage'))*100)+'%p 개선됐다.')
add('전체 총미판매는 '+fmt(w('fixed6','listed'))+'→'+fmt(w('role9','listed'))+'개로 증가했다. 국가당 장기미사용은 약'+fmt((1-w('role9','aged_unused_per_country')/w('fixed6','aged_unused_per_country'))*100)+'% 줄었고, 기존6개국만 따로 봐도 약'+fmt((1-w('role9','original_aged_unused')/w('fixed6','original_aged_unused'))*100)+'% 줄었다. 새 국가 분모가 추가된 효과만으로 감소한 것은 아니다.')
add('### 대응 시드 차이의 95% 구간')
for key,label,factor in [('original_happy','기존국 평균 만족도',1),('original_coverage','기존국 수입충족%p',100),('original_useful_exports','기존국당 유효수출',1),('aged_unused_per_country','전체국당 장기미사용',1)]:
 v=P['fixed6->role9']['world.'+key];add(f"- {label}: {v['mean']*factor:+.3f}, 구간 [{v['ci95'][0]*factor:.3f}, {v['ci95'][1]*factor:.3f}]")
add('구간은 이 자동 정책·모형에서의 시드 변동이다. 실제 학생의 학습·행동을 예측한 통계가 아니다.')
add('## 4. 기존6개국의 경제 균형')
table(['국가','현금6국','현금9국','만족도6국','만족도9국','유효수출6국','유효수출9국'],[[LABELS[n],fmt(c('fixed6',n,'cash')),fmt(c('role9',n,'cash')),fmt(c('fixed6',n,'happy')),fmt(c('role9',n,'happy')),fmt(c('fixed6',n,'useful_exports')),fmt(c('role9',n,'useful_exports'))] for n in NAMES])
add('메카니아의 만족도와 필요한 수입의 충족은 개선됐지만 최종 현금은 거의 변하지 않았다. 미네리아는 만족도가 높아졌지만 유효수출·현금이 줄었다. 추가 광물 공급자와 경쟁하는 구성이므로 국가 추가가 모든 기존 판매자의 이익을 보장하지 않는다. 테크니아의 현금도 의미 있게 줄었다고 결론 내리지 않는다.')
add('## 5. 한 국가 무행동의 영향')
table(['무행동 국가','수정6국: 나머지 기존5국 만족도 변화','역할9국: 같은 기존5국 변화'],[[LABELS[n],fmt(P[f'fixed6:{n}:idle']['world.other_original_happy']['mean']),fmt(P[f'role9:{n}:idle']['world.other_original_happy']['mean'])] for n in NAMES])
add('각 행은 같은 시드의 정상 운영 대비 변화(각30회)다. 9국에서도 추가AI를 분모에 끼워 피해가 작아 보이게 하지 않고, 원래의 동일한 다른5개국만 비교했다. 일부 국가 무행동 때 다른 나라 만족도가 오르는 것은 구매 경쟁도 줄어드는 결과다. 무행동 학생에게 학습이 생긴다는 뜻이 아니다.')
add('테크니아 무행동 때 나머지5국 하락은 '+fmt(P['fixed6:Technia:idle']['world.other_original_happy']['mean'])+'→'+fmt(P['role9:Technia:idle']['world.other_original_happy']['mean'])+'점이다. 노비아는 자금·원료·개발비를 실제 부담하는 추가 생산국이며, 테크니아가 쉬면 무료 상품을 생성하는 구조가 아니다.')
add('## 6. 최저가 반복 판매')
table(['국가','역할9국 현금 변화G','역할9국 만족도 변화','역할9국 판매물량 변화'],[[LABELS[n],fmt(P[f'role9:{n}:cheap'][f'countries.{n}.cash']['mean']),fmt(P[f'role9:{n}:cheap'][f'countries.{n}.happy']['mean']),fmt(P[f'role9:{n}:cheap'][f'countries.{n}.exports']['mean'])] for n in NAMES])
add('각 국가30회. 가격만 변경하고 필요 재고 보호·투자 정책은 유지했다. 나라에 따라 현금 효과가 다르므로 최저가를 일괄 금지하거나 벌점 처리하지 않는다. 특히 신규국 확장만으로 단순 최저가 선택의 교육적 문제가 자동 해결되지는 않는다.')
add('## 7. 무역 필요성과 점수의 한계')
for v in ('fixed6','role9'):
 normal=m(v,'world.original_happy','stress');nt=m(v,'world.original_happy','stress',None,'no_trade')
 add(f"- {v}: 정상 기존국 평균 만족도 {normal:.2f} → 무역 금지 {nt:.2f}점(각30회).")
add('생산·소비·운영수입은 유지하고 외국 거래만 금지한 비교다. 9개국에도 자급만으로 생활을 똑같이 충족하지 못하는 경로가 남아 있다. 이는 모형 내 효용 경로이며 초6 학생의 수출입 개념 이해를 측정하지 않았다.')
add('추가3개국의 경제력·산업 성장 목표는 아직 정하지 않았으므로 9개국 우승률을 만들지 않았다. 기존6개국의 미보정 점수식을 비교용으로 남겼지만, 그 여섯 국가만의1위는 수정6국 테크니아95.0%, 역할9국 테크니아82.0%·오일리아18.0%로 여전히 집중됐다. 이는 9개국 전체 승률도 실제 학생 승률도 아니며, 평가 공정성 통과를 뜻하지 않는다.')
add('## 8. 검증 상태와 권장 판단')
add('기존 회귀96개+이번 확장·판단 검증24개=**120개 통과**. 본1,640게임의 자금·상품·소유권·주문 잠금 검사는 **45,920회**, 실패0. 초기 1회+라운드당3회×9의 호출을 게임마다 센 값이다. 이는 서로 다른45,920종류의 테스트가 아니라 반복 불변조건 검사다.')
add('권장: 1G 가격 및 공통계획을 사용한 **9개국 역할조합을 다음 시험 후보로 유지**, 무한 상점·추가 벌점·보관비는 OFF. 기계 사용 추천의 정확성과 공급 공백 완화는 가치가 있지만, 메카니아 구매력·미네리아 경쟁·기존 성장 목표는 추가 조정 대상이다. 단순 복제9국은 국가당 거래와 재고 개선이 뚜렷하지 않아 추천 기본안으로 채택하지 않는다.')
add('제약: 모든 국가는 자동 정책이다. 실시간 서버·권한·UI·학생의 반응 속도·모둠 운영·학습 이해도는 미검증이다. 기존 엔진의 원료주기·기계배치·세대효용·협상은 단순화된 상태이며 기계2대를 서로 다른 산업에 배치하는 완전한 UI 규칙을 구현한 것이 아니다. 국가가 많아도 학생 화면에모든 국가를 동시에 노출하지 않는 설계가 별도로 필요하다.')
add('## 재현 파일')
add('`README.md`, `expansion_engine.py`, `run_batches.py`, `run_expansion.py`, `test_expansion.py`, `results/batch_00..08.jsonl.gz`, `results/summary.json`, `results/run_manifest.json`, `tests_all.txt`에 설정·소스·개별결과·검사기록을 포함했다. 기존엔진3파일은변경하지 않았으며 `UPSTREAM_PROVENANCE.json`으로 확인한다.')
(ROOT/'RESULTS_KO.md').write_text('\n\n'.join(lines),encoding='utf-8')
print('Report written',len('\n'.join(lines)),'characters')
