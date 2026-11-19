# #11 무역 게임 (v17 경제 시뮬레이터 + 검증 자료)

초등학교 6학년 사회 무역 단원 마무리 게임의 경제 규칙을 만들고 검증하는 저장소다. 작업 지침은 `CLAUDE.md`에 있다.

마지막 정리: 2026-11-19

## 폴더 구조

| 경로 | 내용 |
| --- | --- |
| `CLAUDE.md` | 다른 PC에서 Claude와 작업할 때의 지침, 확정 결정, 코드 작업 규칙 |
| `docs/claude_review_report_v17.md` | Claude 교차 검증 보고서. 원본은 [Claude 문서](https://claude.ai/artifact/ExUwWNfED9nKjbTCEEYbSN) |
| `handoff_v17/` | ChatGPT가 만든 v17 인수인계 묶음 그대로. 인수인계서, 검증 요청문, v13~v16 이력, 목표 보정 자료(`calibration_v15/`) |
| `trade_v17/` | v17 전체 패키지(코드·설정·보고서·작은 결과). 대형 원본 6개는 제외 |
| `claude_review/` | Claude 검증 코드와 결과 |
| `claude_review/new_games/` | Claude가 새로 돌린 게임 결과(JSON)와 비교 결과 |

## 현재 상태

- v17 저장 결과 6,740판은 독립 재계산으로 모두 재현됐다.
- 수업 결과는 나라별 목표 달성도로 보여 주고, 공동 목표는 두지 않기로 정했다.
- 운영 자원 규칙은 `light`가 후보다. 다만 학생이 연료·광물을 사지 않으면 오히려 이득인 문제가 있었다.
- 이를 막는 '긴급 조달' 규칙을 시험했다. 정산일에 부족하면 기초 가격(연료 30G, 광물 20G)을 국가 수입에서 빼는 것만으로 충분했다. 정상 플레이 점수는 변하지 않았다. 아직 확정은 아니다.

- 새 경제(light + 긴급 조달 1.0배)에서 자산 증가 방식으로 목표를 다시 뽑았다(`docs/recalibration_light_fee1.md`). 무행동 미네리아가 여전히 목표의 83%를 채웠다.
- 그래서 경제 점수를 **수출 매출**로 재기로 했다(사용자 결정). 다른 나라가 실제로 쓴 물건만, 기준 가격까지만 인정하는 '쓰인 수출 가치'로 시험했다(`docs/export_revenue_experiment.md`). 무행동은 경제 점수 0, 혼자 1G 판매는 30/30판 손해, 나라 간 난도도 가장 고르다. 맞거래로 달성도가 0.09~0.11 오르는 허점이 남았다.
- 같은 물건 맞바꾸기를 수출에서 빼는 규칙을 시험했다(`docs/export_noswap_experiment.md`). 같은 물건 맞거래는 막혔고 정상 플레이에는 영향이 없었다. 다른 물건을 비싸게 주고받는 경우(미네리아 +0.102)는 남았지만 한쪽이 항상 손해라 허용하기로 했다(사용자 결정).

## 다음 할 일

1. 운영 무시 억제 방안 정하기(사용자 결정). 경제 점수를 수출로 바꾼 뒤 긴급 조달 비용이 점수에 거의 닿지 않는다(`docs/grades_experiment.md`). 후보: 조달해도 만족도 감점 유지 / 운영 부족을 생활 점수에 직접 반영 / 허용
2. 등급은 점수 구간 방식(A ≥ 90, B ≥ 80, C ≥ 60, D)이 후보다. 기준 7개 중 6개 통과

## 실행 방법

Python 3.10 이상, 표준 라이브러리만 필요하다. 저장소 루트에서 실행한다.

```bash
# 저장된 결과 요약 통계 (games_compact.json.gz 사용, 대형 파일 불필요)
python3 -X utf8 claude_review/stats_v17.py claude_review/games_compact.json.gz

# 새 시뮬레이션 예: 긴급 조달 1.2배에서 운영 자원을 무시하는 나라 (6개국 × 30시드)
PYTHONDONTWRITEBYTECODE=1 python3 -X utf8 claude_review/new_sims.py trade_v17 mult1.2_skip claude_review/new_games/mult1.2_skip.json

# 저장된 정상 게임과 짝 비교
python3 -X utf8 claude_review/compare_new.py claude_review/games_compact.json.gz claude_review/new_games/new_skip.json

# 긴급 조달 배수 비교 요약
python3 -X utf8 claude_review/analyze_mult.py claude_review
```

`recalibrate_targets.py`는 목표 재산출(`run A|B|valid`, `report`)을 한다. `export_revenue.py`는 수출 매출 점수 실험(`run cal|valid`, `report`), `export_noswap.py`는 같은 물건 맞바꾸기 제외 실험이다. 산업 목표 실험은 `industrial_levelup.py`(A안), `main_industry.py`(1번), `l3_flat_cost.py`(3번), `main_k1.py`(추천안)다. 등급 비교는 `grades.py`다. `sim_lib.py`는 공통 엔진 변형(Skip, Emergency)이다.

`new_sims.py`의 실험 이름: `repro`, `skip`, `class3`, `class3_cheap`, `fix`, `mult<배수>_normal|skip|idle`. 한 판에 약 0.35초 걸린다.

`recompute_v17.py`는 저장소에 없는 `validation_runs.jsonl.gz`가 있어야 돈다.

```bash
python3 -X utf8 claude_review/recompute_v17.py <trade_v17 전체 폴더> claude_review/games_compact.json.gz
```

## 저장소에 없는 대형 원본

GitHub 파일 크기 제한(100MB)과 저장소 용량 때문에 아래 6개는 넣지 않았다. 원래 PC의 `Downloads/trade/trade_game_national_resources_v17/trade_v17/operating_results/`에 있다. ChatGPT의 원래 전체 증거 ZIP에도 들어 있다(링크는 `handoff_v17/START_HERE_KO.txt`).

| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `summary.json` | 199,314,350 | `982075c9fb102a7821e4d1b8e2a96b7b7f9375e21437463f631cbb23f1dfa147` |
| `representative_traces.json.gz` | 59,766,357 | `465243d82c1c4fe614f3f3b03e7ba2d677a0c8e0fb44e4f79dc10eb70a696bbc` |
| `validation_runs.jsonl.gz` | 55,701,287 | `308f40ed059de4d1a7a1aafaea8ebdae941dff2d5833be7caa89cbb3725153d9` |
| `operating_round_ledgers.jsonl.gz` | 20,268,722 | `d3024c70dcd7880f12af331aa94e5fb2da40b0adbdf61ac0649ccd2cd3a1bbf5` |
| `round_ledgers.jsonl.gz` | 13,826,323 | `3c4fdd46c283aabd1bbd75938116afd02a5a0480faf65c9c81bb4d456890a49f` |
| `raw_round_ledgers.jsonl.gz` | 9,937,473 | `6fe7b98e0590b6f65ff7f8829a10d555d50a602540ca325f652f450a0692d689` |

이 파일이 없어도 코드 실행, 새 시뮬레이션, `games_compact.json.gz` 기반 통계는 된다. 기존 감사기(`audit_operating_validation.py`)와 전체 원장 재검산에는 필요하다.
