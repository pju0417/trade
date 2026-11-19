"""Build the v13 Korean causal review from completed, audited saved results.

Only this new report file is edited for v13. Inherited engines and reports are
read-only. The report will not simulate games, tune coefficients, select a
candidate from holdout outcomes, or describe exploratory values as final.

The report requires the separate pilots, frozen formal schedule, complete
records and both independent audits. It emits no incomplete result report.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from functools import lru_cache
import gzip
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import statistics

from build_routing_report import Cell, Metric, PairedValues, ci, f, get, need, read_json, read_lines, table


ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS = ROOT / "causal_results"
DEFAULT_REPORT = ROOT / "TRADE_CAUSAL_REVIEW_V13_KO.html"
COUNTRIES = {
    "Tropia": "트로피아", "Grainia": "그레니아", "Oilia": "오일리아",
    "Mechania": "메카니아", "Mineria": "미네리아", "Technia": "테크니아",
    "Novia": "노비아", "Agrea": "아그레아", "Ferria": "페리아",
}
ORIGINAL = tuple(COUNTRIES)[:6]
MODES = {
    "baseline": "기존안", "operating_first": "운영 원료 예산 우선 예약",
    "no_durable_boost": "초기 내구재 투자 가중치 제거", "ai_combined": "두 AI 수정 결합",
    "electronics_input": "전자제품 원료 +1", "combined_input": "두 AI 수정+원료 +1",
}
MODE_POLICIES = {
    mode: {"operating_first": mode in ("operating_first", "ai_combined", "combined_input"),
           "remove_durable_boost": mode in ("no_durable_boost", "ai_combined", "combined_input"),
           "electronics_extra_raw": int(mode in ("electronics_input", "combined_input"))}
    for mode in MODES
}
GOALS_SHA256 = "47e78fe6a9cebab256bb52a3b7dbef9c9b46cec4363d15700290ddfa2e4620d5"
GOODS = {"banana": "바나나", "wheat": "밀", "ore": "광물", "fuel": "연료",
         "machine": "기계", "electronics": "전자제품"}
SECTION_TITLES = (
    ("s1", "이번 검증의 판단"),
    ("s2", "실행 규칙과 비교 조건"),
    ("s3", "AI 요인이 바꾼 것"),
    ("s4", "원료 후보의 경제 결과와 점수"),
    ("s5", "낮은 가격·무행동·공급 중단"),
    ("s6", "검증 범위와 다음 결정"),
)
FINAL_VERDICT = {
    "focus_mode": "electronics_input",
    "lead": "미네리아의 실제 판매·원료 사용·개발 기회는 공통 전자제품 원료 수요를 조정했을 때 함께 늘었습니다. 두 AI 수정만으로 이러한 개선이 나타나지는 않았습니다. 다만 테크니아의 기존 점수 우세와 고급 제품 개발·기계국의 부담은 남았습니다.",
    "decision": "전자제품 원료 +1을 가장 유망한 추가 검증 후보로 보존합니다. AI 가중치 제거의 일괄 적용은 보류하고 공식 점수는 유지합니다. 이번 결과는 후보의 장점과 비용을 확인한 것이며 국가별 공정성이 완성됐다는 판정은 아닙니다.",
    "ai": "정상 조건에서 운영 원료 예산 예약안은 표의 경제 지표를 바꾸지 않았습니다. 초기 내구재 투자 가중치를 제거하면 미네리아의 투자와 점수는 늘지만 현금·만족도는 낮아지고, 자국 생산품의 실제 사용 증가도 확인되지 않았습니다. 개발 횟수나 점수 상승만으로 더 좋은 운영이라고 채택할 근거가 부족합니다. 두 AI 수정의 결합도 이 정상 표본에서는 가중치 제거와 같은 주요 결과를 보였습니다.",
    "input": "전자제품 원료 수요를 늘리면 원료 거래와 생산 투입이 늘고 미네리아의 현금·판매·실사용·개발 빈도가 함께 개선됐습니다. 이는 원료국의 참여 기회를 늘릴 수 있다는 근거입니다. 그러나 테크니아의 자국산 G3 실제사용 빈도는 낮아졌고, 메카니아의 현금과 실제 사용도 줄었습니다. 테크니아의 전체 생산품 실사용량과 세계 만족도의 평균차 구간은 0을 포함하므로, 이 부분을 뚜렷한 개선이나 전면적 악화로 단정하지 않습니다.",
    "score": "테크니아의 생산능력 증가율은 낮아졌지만 기존 산업 능력 점수는 두 조건 모두 상한에 닿았습니다. 생산량이 줄어든 가운데 실제 사용 비율은 높아져 활용 점수와 공식 총점은 오히려 올랐습니다. 불필요한 생산을 줄인 성과와 비율의 분모 효과를 함께 읽어야 하며, 활용률 상승 자체를 부정행위로 보지 않습니다. v12 고정 목표 참고 점수는 낮아져 변화가 드러나지만, 이 참고 점수도 새 경제에 대한 공정성의 증명은 아닙니다.",
    "stress": "모든 여섯 조건의 원래 6개국을 살핀 동일 시드 비교에서 1G 반복·무행동의 본인 공식 총점이 자기 정상보다 높아진 경우는 없었습니다. 원료 후보의 무행동은 현금이 더 남는 경우가 많았지만 총점과 만족도는 낮아졌습니다. 1G는 평균 현금도 줄었으나 개별 시드에서는 현금이나 만족도가 더 높은 예외가 있어, 모든 지표가 항상 나빠진다고 설명해서는 안 됩니다.",
    "stress_extra": "반값 판매는 1G 반복과 결과가 달랐습니다. 테크니아의 반값 전략에서는 실제 사용·현금·공식 점수가 함께 높아졌고 투자 지출은 줄었습니다. 의미 있는 할인·재고 활용 전략의 가능성으로 보아야 합니다. 또한 테크니아의 1G 판매는 자기 G3 성과를 낮추면서 노비아의 G3 사용을 늘렸습니다. 판매국의 손해와 상대국의 이익, 공급국의 무행동이 겹치는 효과를 구분해야 합니다. 세 역할의 혼합 조건도 자동 행동을 정한 제한된 예시이며, 모든 학생 행동을 재현한 것은 아닙니다.",
    "next": "다음 판단은 원료 +1 후보의 거래·개발 기회 개선을 보존하면서 고급 개발과 기계국에 생긴 부담을 어떻게 다룰지, 그리고 기존 점수 상한이 실제 성장과 선택의 차이를 충분히 보여 주는지에 집중하는 것이 적절합니다. 국가별 최고점 빈도를 기계적으로 같게 맞추기보다 같은 수준의 참여자가 각 나라에서 이해할 만한 선택과 개선 기회를 얻는지 확인해야 합니다. 정식 결과를 본 뒤 계수를 재조정하거나 새 실험을 추가하지 않았습니다.",
}


class GroupedRows:
    """Saved-result formatting helpers; seed matching is explicit for every CI."""
    def __init__(self, rows):
        self.rows = rows
        self.groups = defaultdict(list)
        identities = set()
        for row in rows:
            key = (row["phase"], row["mode"], row["scenario"], row["seed"])
            need(key not in identities, "Duplicate saved economic trajectory.")
            identities.add(key)
            self.groups[":".join(key[:3])].append(row)

    @lru_cache(maxsize=None)
    def values(self, experiment, metric):
        need(experiment in self.groups, "Missing comparison group: " + experiment)
        return {row["seed"]: get(row, metric) for row in self.groups[experiment]}

    def mean(self, experiment, metric):
        return Metric(statistics.mean(self.values(experiment, metric).values()),
                      {"kind": "mean", "experiment": experiment, "metric": metric})

    def count(self, experiment, metric):
        values = self.values(experiment, metric)
        return Cell(f"{sum(value > 0 for value in values.values())}/{len(values)}",
                    {"kind": "count", "experiment": experiment, "metric": metric})

    def paired(self, control, experiment, metric, pair_key):
        before = self.values(control, metric)
        after = self.values(experiment, metric)
        need(before.keys() == after.keys(), "Paired differences require the same complete seed set.")
        return PairedValues([after[seed] - before[seed] for seed in sorted(before)],
                            {"kind": "ci", "pair": pair_key, "metric": metric})

    def higher(self, control, experiment, metric):
        before = self.values(control, metric)
        after = self.values(experiment, metric)
        need(before.keys() == after.keys(), "Paired frequencies require the same complete seed set.")
        return Cell(f"{sum(after[seed] > before[seed] + 1e-9 for seed in before)}/{len(before)}",
                    {"kind": "paired_greater_count", "control": control,
                     "experiment": experiment, "metric": metric})

    def highest(self, experiment, country, suffix="score"):
        metrics = [f"countries.{name}.{suffix}" for name in ORIGINAL]
        metric = f"countries.{country}.{suffix}"
        rows = self.groups[experiment]
        value = sum(get(row, metric) >= max(get(row, path) for path in metrics) - 1e-9 for row in rows)
        return Cell(f"{value}/{len(rows)}", {"kind": "top_count", "experiment": experiment,
                                            "metric": metric, "metrics": metrics})

    def country(self, mode, name, metric, phase="main", scenario="None:normal"):
        return self.mean(f"{phase}:{mode}:{scenario}", f"countries.{name}.{metric}")

    def world(self, mode, metric, phase="main", scenario="None:normal"):
        return self.mean(f"{phase}:{mode}:{scenario}", f"world.{metric}")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


class SavedResults(GroupedRows):
    """Only load the complete declared experiment with an independent audit."""
    def __init__(self, folder: Path):
        self.folder = folder
        required = ("run_manifest.json", "summary.json", "runs.jsonl.gz", "pre_run_plan.json",
                    "tests_manifest.json", "independent_audit.json", "independent_pilot_audit.json", "freeze_manifest.json",
                    "formal_start.json", "ai_pilot_manifest.json", "economic_pilot_manifest.json",
                    "economic_pilot_start.json", "pilot_summary.json", "round_ledgers.jsonl.gz",
                    "raw_round_ledgers.jsonl.gz", "first_seed_traces.json.gz")
        need(all((folder / name).is_file() for name in required),
             "Complete formal results, separate pilots, frozen conditions and independent audit are required.")
        self.meta = read_json(folder / "run_manifest.json")
        self.plan = read_json(folder / "pre_run_plan.json")
        self.freeze = read_json(folder / "freeze_manifest.json")
        self.start = read_json(folder / "formal_start.json")
        self.tests = read_json(folder / "tests_manifest.json")
        self.audit = read_json(folder / "independent_audit.json")
        self.pilot_audit = read_json(folder / "independent_pilot_audit.json")
        self.rules = read_json(ROOT / "rules_audit.json")
        m = self.meta
        need((m["completed_games"], m["pilot_games"], m["main_games"], m["stress_games"], m["formal_games"])
             == (5100, 180, 600, 4320, 4920), "Unexpected complete experiment schedule.")
        need(m["rounds"] == m["countries"] == 9 and m["ranked_countries"] == list(ORIGINAL),
             "Nine-country economy and original-six score scope required.")
        need(m["modes"] == list(MODES) and m["representative_traces"] == 156, "Unexpected mode/trace scope.")
        need(m["mode_policies"] == MODE_POLICIES and m["goals_sha256"] == GOALS_SHA256,
             "Candidate factors or the fixed prior target reference changed.")
        expected_ranges = {"pilot_ai": [96000, 96029], "pilot_economic": [96000, 96029],
                           "main": [100000, 100099], "stress": [102000, 102029]}
        need(set(m["phases"]) == set(expected_ranges) and
             all(m["phases"][phase]["seed_range"] == seeds for phase, seeds in expected_ranges.items()),
             "Exploration and formal seed cohorts must remain separate.")
        need(len(m["phases"]["stress"]["scenarios"]) == 24, "Every declared stress condition is required.")
        need(m["formal_cash_ledger_rows"] == m["formal_raw_ledger_rows"] == 398520,
             "Complete formal cash and material ledgers required.")
        need(m["source_unchanged"] is True and m["verification_failures"] == 0,
             "Source preservation and failed-invariant checks must pass.")
        need(m["fixed_targets_refitted"] is False and m["posthoc_reference_is_extra_game"] is False,
             "The inherited target view must remain a fixed posthoc reference.")
        need(m["formal_started_after_freeze"] is True and self.freeze["formal_not_executed"] is True,
             "The complete formal sample must follow reviewed frozen conditions.")
        need(digest(folder / "freeze_manifest.json") == m["freeze_sha256"] == self.start["approved_freeze_sha256"],
             "Formal execution must use the exact reviewed freeze.")
        economic_start = read_json(folder / "economic_pilot_start.json")
        need(digest(folder / "ai_pilot_manifest.json") == self.freeze["ai_pilot_manifest_sha256"]
             == economic_start["approved_ai_pilot_sha256"], "The input pilot must follow AI-pilot review.")
        need(digest(folder / "economic_pilot_manifest.json") == self.freeze["economic_pilot_manifest_sha256"],
             "The completed input pilot must be included in the final freeze.")
        need(self.freeze["created_at"] < self.start["started_at"], "The freeze must predate formal execution.")
        need(self.tests["passed"] is True and self.tests["test_count"] == m["tests_completed"] > 375,
             "Inherited and new regression tests must pass.")
        need(self.tests["errors"] == self.tests["failures"] == self.tests["skipped"] == 0,
             "Tests must not fail or skip.")
        need(self.audit["status"] == "passed" and not self.audit["errors"], "Independent final audit must pass.")
        need(self.audit["stage"] == "full" and self.audit["unique_games_audited"] == 5100 and
             self.audit["formal_games_audited"] == 4920 and self.audit["detailed_traces"] == 156,
             "The audit must cover the full declared result set and representative traces.")
        for name in ("run_manifest.json", "summary.json", "runs.jsonl.gz", "pre_run_plan.json"):
            need(digest(folder / name) == self.audit["artifacts_checked"][name],
                 "Report input changed after independent audit: " + name)
        need(digest(ROOT / "rules_audit.json") == self.audit["rules_audit_sha256"],
             "The report must use the reviewed rule reconciliation.")
        need(self.pilot_audit["status"] == "passed" and not self.pilot_audit["errors"] and
             self.pilot_audit["formal_started_at_audit"] is False and
             self.pilot_audit["freeze_sha256"] == m["freeze_sha256"],
             "The complete frozen pilot must pass independent review before formal execution.")
        for key, path in (("tests_manifest_sha256", folder / "tests_manifest.json"),
                          ("run_plan_sha256", folder / "pre_run_plan.json"),
                          ("declared_protocol_sha256", ROOT / "CAUSAL_PROTOCOL_V13.json"),
                          ("goals_sha256", ROOT / "V12_FROZEN_GOALS.json")):
            need(digest(path) == m[key] == self.freeze[key], "Frozen evidence changed: " + path.name)
        need(len(m["inherited_source_sha256"]) == 76, "All inherited Python sources must be preserved.")
        for field in ("inherited_source_sha256", "source_sha256", "test_sha256"):
            need(m[field] == self.freeze[field], "The frozen source contract changed.")
            for name, expected in m[field].items():
                need(digest(ROOT / name) == expected, "Source changed after execution: " + name)
        summary = read_json(folder / "summary.json")
        need(summary["metadata"] == m, "Summary and final manifest differ.")
        self.contrasts = summary["contrast_definitions"]
        del summary
        # Drop unrelated historical diagnostics from the report's in-memory view.
        country_fields = set(m["country_summary_fields"]) | {"channel_stats"}
        world_fields = set(m["world_summary_fields"])
        rows = []
        with gzip.open(folder / "runs.jsonl.gz", "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                scope = row["world"]["causal_scope"]
                need(scope["official_score_unchanged"] is True and scope["storage_enabled"] is False,
                     "The actual baseline accounting scope changed.")
                need(scope["extra_manufacturing_cash_fee"] == scope["sales_fee"] == 0,
                     "Unexpected new cash cost in the experiment.")
                reference = row["world"]["growth_reference_config"]
                need(reference["refitted"] is False and reference["score_feedback_to_actions"] is False,
                     "Fixed score references must not tune the economy.")
                need(set(row["countries"]) == set(COUNTRIES), "Unexpected country identities.")
                for name in COUNTRIES:
                    country = row["countries"][name]
                    need(set(country["growth_evaluation"]) == {"targets"}, "Only the inherited target view is retained.")
                    if name not in ORIGINAL:
                        need(country["score"] is None and country["growth_evaluation"]["targets"] is None,
                             "Unranked countries must not acquire an invented total.")
                rows.append({**{key: row[key] for key in ("phase", "mode", "scenario", "seed", "focal", "style", "behaviors")},
                             "countries": {name: {key: value for key, value in country.items() if key in country_fields}
                                           for name, country in row["countries"].items()},
                             "world": {key: value for key, value in row["world"].items() if key in world_fields}})
        expected = set()
        for phase, info in m["phases"].items():
            for mode in info["modes"]:
                for condition in info["scenarios"]:
                    for seed in range(info["seed_range"][0], info["seed_range"][1] + 1):
                        expected.add((phase, mode, condition["scenario"], seed))
        actual = {(row["phase"], row["mode"], row["scenario"], row["seed"]) for row in rows}
        need(len(rows) == len(actual) == len(expected) == 5100 and actual == expected,
             "Saved rows do not match the entire unique declared schedule.")
        super().__init__(rows)

    def contrast(self, key, metric):
        definition = self.contrasts[key]
        terms = definition["terms"]
        values = {experiment: self.values(experiment, metric) for experiment in terms}
        seeds = next(iter(values.values())).keys()
        need(all(value.keys() == seeds for value in values.values()), "Contrast requires identical seeds.")
        differences = [sum(terms[experiment] * values[experiment][seed] for experiment in terms)
                       for seed in sorted(seeds)]
        return PairedValues(differences, {"kind": "ci", "pair": key, "metric": metric})


def ai_main_table(data: GroupedRows) -> str:
    rows = []
    for mode in tuple(MODES)[:4]:
        rows.append((MODES[mode], f(data.country(mode, "Mineria", "cash")),
                     f(data.country(mode, "Mineria", "investment")),
                     f(data.country(mode, "Mineria", "growth_metrics.used_units")),
                     f(data.country(mode, "Mineria", "score")),
                     f(data.country(mode, "Technia", "investment")),
                     f(data.country(mode, "Technia", "growth_metrics.used_units")),
                     f(data.world(mode, "happy"))))
    return table(("AI 조건", "미네리아 현금 G", "미네리아 투자 G", "미네리아 실사용 개",
                  "미네리아 공식 총점", "테크니아 투자 G", "테크니아 실사용 개", "세계 만족도"), rows)


def contrast_main_table(data: SavedResults, comparisons: tuple[tuple[str, str], ...]) -> str:
    paths = ("countries.Mineria.cash", "countries.Mineria.growth_metrics.used_units",
             "countries.Technia.growth_metrics.used_units", "world.happy")
    rows = [(label, *(ci(data.contrast(key, path)) for path in paths)) for label, key in comparisons]
    return table(("같은 시드 차이 · 평균 [95% 구간]", "미네리아 현금 G",
                  "미네리아 실사용 개", "테크니아 실사용 개", "세계 만족도"), rows)


def raw_main_table(data: GroupedRows) -> str:
    rows = []
    for mode in ("baseline", "ai_combined", "electronics_input", "combined_input"):
        rows.append((MODES[mode], f(data.world(mode, "trade_goods.ore")),
                     f(data.world(mode, "raw_use.ore.production")),
                     f(data.world(mode, "trade_goods.fuel")), f(data.world(mode, "raw_use.fuel.production")),
                     f(data.world(mode, "production.electronics")),
                     f(data.country(mode, "Technia", "use_by_good.electronics")),
                     f(data.country(mode, "Novia", "use_by_good.electronics"))))
    return table(("조건", "광물 거래", "광물 생산 투입", "연료 거래", "연료 생산 투입",
                  "세계 전자제품 생산", "테크니아 전자제품 실사용", "노비아 전자제품 실사용"), rows)


def cash_components_table(data: GroupedRows, modes: tuple[str, ...]) -> str:
    rows = []
    for mode in modes:
        for name in ("Mineria", "Technia", "Ferria", "Novia"):
            rows.append((MODES[mode] + " · " + COUNTRIES[name],
                         *(f(data.country(mode, name, field)) for field in
                           ("start_cash", "revenue", "purchases", "tax", "investment", "cash"))))
    return table(("조건·국가", "시작 현금", "판매수입 +", "구매지출 −", "운영수입 +", "투자 −", "종료 현금"), rows)


def country_outcomes_table(data: GroupedRows, candidate: str) -> str:
    """One compact all-country comparison; selecting the focus is editorial."""
    rows = []
    for name in COUNTRIES:
        cells = [COUNTRIES[name]]
        for field in ("cash", "happy", "growth_metrics.used_units", "investment"):
            cells.append(f(data.country("baseline", name, field)) + " → " + f(data.country(candidate, name, field)))
        if name in ORIGINAL:
            cells.append(f(data.country("baseline", name, "score")) + " → " + f(data.country(candidate, name, "score")))
        else:
            cells.append("평가 미설정")
        rows.append(cells)
    return table(("국가", "현금 G", "만족도", "자국 생산품 실사용 개", "투자 G", "기존 공식 총점"), rows)


def score_main_table(data: GroupedRows) -> str:
    rows = []
    for name in ORIGINAL:
        rows.append((COUNTRIES[name], *(f(data.country(mode, name, "score")) for mode in MODES)))
    return table(("기존 6개국 공식 총점", *MODES.values()), rows)


def technia_score_table(data: GroupedRows, candidate: str) -> str:
    specs = (
        ("생산능력 증가율", "growth_metrics.capacity_growth", 4),
        ("산업 능력 점수 /15", "industry_capacity_score", 2),
        ("자국 총생산 물량", "growth_metrics.produced_units", 2),
        ("자국 생산품 실사용 물량", "growth_metrics.used_units", 2),
        ("산업 활용 점수 /10", "industry_use_score", 2),
        ("기존 공식 총점 /100", "score", 2),
        ("v12 고정 목표 참고 총점 /100", "growth_evaluation.targets.score", 2),
    )
    return table(("테크니아의 실제 성장과 점수", "기존안", MODES[candidate]),
                 [(label, f(data.country("baseline", "Technia", metric), digits),
                   f(data.country(candidate, "Technia", metric), digits)) for label, metric, digits in specs])


def plans_main_table(data: GroupedRows, modes: tuple[str, ...]) -> str:
    rows = []
    fields = ("legal_planned_attempts", "cash_ready_attempts", "feasible_planned_attempts",
              "successful_attempts", "blocked_cash_attempts", "blocked_raw_attempts")
    for name in ("Mineria", "Technia"):
        for mode in modes:
            rows.append((COUNTRIES[name] + " · " + MODES[mode],
                         *(f(data.country(mode, name, "causal." + field)) for field in fields)))
    return table(("국가·조건", "합법 계획", "현금 조건 충족", "전체 조건 충족", "개발 성공",
                  "현금 부족", "원료 부족"), rows)


def headline_table(data: GroupedRows, candidate: str) -> str:
    base = "main:baseline:None:normal"
    changed = f"main:{candidate}:None:normal"
    specs = (
        ("미네리아 판매수입 G", "countries.Mineria.revenue", "mean"),
        ("미네리아 종료 현금 G", "countries.Mineria.cash", "mean"),
        ("미네리아 투자 G", "countries.Mineria.investment", "mean"),
        ("미네리아 생산품 실사용 개", "countries.Mineria.growth_metrics.used_units", "mean"),
        ("미네리아 개발이 없었던 게임", "countries.Mineria.causal.no_upgrade", "count"),
        ("테크니아 자국산 G3 실제사용 게임", "countries.Technia.routing.g3_electronics_used", "count"),
        ("메카니아 종료 현금 G", "countries.Mechania.cash", "mean"),
        ("메카니아 생산품 실사용 개", "countries.Mechania.growth_metrics.used_units", "mean"),
    )
    rows = []
    for label, metric, kind in specs:
        func = (lambda experiment: data.count(experiment, metric)) if kind == "count" else (lambda experiment: f(data.mean(experiment, metric)))
        rows.append((label, func(base), func(changed)))
    rows.append(("테크니아 기존 6국 최고점 게임", data.highest(base, "Technia"), data.highest(changed, "Technia")))
    return table(("정상 조건의 비교", "기존안", MODES[candidate]), rows)


def focal_behavior_table(data: SavedResults, mode: str, style: str) -> str:
    control = f"stress:{mode}:None:normal"
    rows = []
    for name in ORIGINAL:
        case = f"{name}:{style}"
        experiment = f"stress:{mode}:{case}"
        cells = [COUNTRIES[name]]
        for field in ("score", "cash", "happy"):
            metric = f"countries.{name}.{field}"
            cells.extend((ci(data.contrast(experiment, metric)), data.higher(control, experiment, metric)))
        rows.append(cells)
    return table(("행동을 바꾼 국가", "공식점수 차이 [95% 구간]", "점수 상승 게임",
                  "현금 차이 G [95% 구간]", "현금 상승 게임", "만족도 차이 [95% 구간]", "만족도 상승 게임"), rows)


def generation_stress_table(data: GroupedRows, mode: str) -> str:
    scenarios = (
        ("정상", "None:normal"), ("테크니아 1G", "Technia:minimum"),
        ("메카니아 무행동", "Mechania:idle"),
        ("메카니아 무행동+테크니아 1G", "Mechania:idle+Technia:minimum"),
        ("메카니아 무행동+노비아 1G", "Mechania:idle+Novia:minimum"),
        ("미네리아 무행동·테크니아 1G·그레니아 정상", "Mineria:idle+Grainia:normal+Technia:minimum"),
        ("테크니아 무행동·미네리아 1G·그레니아 정상", "Technia:idle+Grainia:normal+Mineria:minimum"),
        ("그레니아 무행동·테크니아 1G·미네리아 정상", "Grainia:idle+Mineria:normal+Technia:minimum"),
        ("모든 무역 중단", "None:no_trade"),
    )
    rows = []
    for label, scenario in scenarios:
        experiment = f"stress:{mode}:{scenario}"
        rows.append((label, data.count(experiment, "countries.Technia.routing.g3_electronics_used"),
                     data.count(experiment, "countries.Novia.routing.g3_electronics_used"),
                     f(data.mean(experiment, "world.happy"))))
    return table(("공급·판매 행동 조건", "테크니아 자국산 G3 사용 게임", "노비아 자국산 G3 사용 게임", "세계 만족도"), rows)


def technia_prices_table(data: GroupedRows, mode: str) -> str:
    cases = (("정상", "None:normal"), ("반값", "Technia:cheap"), ("공개 1G", "Technia:minimum"))
    fields = ("revenue", "growth_metrics.used_units", "investment", "cash", "happy", "score")
    return table(("테크니아 가격 행동", "판매수입 G", "생산품 실사용", "투자 G", "종료 현금 G", "만족도", "공식 총점"),
                 [(label, *(f(data.country(mode, "Technia", field, "stress", case)) for field in fields))
                  for label, case in cases])


def fixed_targets_highest_table(data: GroupedRows, candidate: str) -> str:
    return table(("v12 고정 목표 보기 · 동점 포함 최고점", "기존안", MODES[candidate]),
                 [(COUNTRIES[name], data.highest("main:baseline:None:normal", name, "growth_evaluation.targets.score"),
                   data.highest(f"main:{candidate}:None:normal", name, "growth_evaluation.targets.score"))
                  for name in ORIGINAL])


def compose_sections(data: SavedResults, verdict: dict) -> dict[str, str]:
    candidate = verdict["focus_mode"]
    need(candidate in MODES and candidate != "baseline", "A clearly labeled comparison focus is required.")
    m = data.meta
    sections = {}
    sections["s1"] = (paragraph(verdict["lead"], "lead")
                      + '<div class="finding">' + paragraph(verdict["decision"]) + '</div>'
                      + headline_table(data, candidate)
                      + paragraph("이 표는 조건마다 같은 100시드를 사용한 정상 운영 결과입니다. G3 사용은 자국에서 생산한 3세대 전자제품이 자국 또는 해외에서 실제 사용된 게임이며, 수입품을 소비한 것만으로 성공 처리하지 않습니다. 최고점은 기존 6개국 안에서 동점을 포함합니다.", "note"))
    sections["s2"] = (rules_section(data.rules) + '<h3>무엇을 따로 바꿨는가</h3>' + policy_table()
                      + paragraph("네 AI 조건은 두 AI 요인의 2×2 비교입니다. 원료 후보는 기존 AI와 두 AI 수정 결합에 각각 붙여 비교했습니다. 가능한 여덟 조합을 모두 실행한 세 요인 실험은 아닙니다. 가격 산정식은 유지되지만 수요·공급이 달라지면 실제 기준가격과 거래가격은 달라질 수 있습니다.", "note"))
    ai_contrasts = (("예산 예약 − 기존", "main:baseline->operating_first:None:normal"),
                    ("투자 가중치 제거 − 기존", "main:baseline->no_durable_boost:None:normal"),
                    ("두 AI 수정 − 기존", "main:baseline->ai_combined:None:normal"),
                    ("두 AI 요인의 상호작용", "main:ai_interaction:None:normal"))
    sections["s3"] = (paragraph(verdict["ai"]) + ai_main_table(data)
                      + contrast_main_table(data, ai_contrasts)
                      + paragraph("상호작용은 ‘결합 − 예산 예약 − 가중치 제거 + 기존’입니다. 두 변경을 함께 적용한 효과가 각 단독 효과의 합과 얼마나 다른지 봅니다. 구간은 시드 간 변동에 따른 평균차의 95% 구간이며, 실제 학생 집단의 학습 효과 구간이 아닙니다.", "note")
                      + paragraph("예산 예약으로 확보한 원료를 실제로 살 수 없다면 생활용 예산이 묶일 수도 있습니다. 이번 정상 표본의 무효과를 다른 구매·투자 판단까지 영향이 없다는 뜻으로 확대하지 않습니다.", "note"))
    input_contrasts = (("원료 +1 − 기존 AI", "main:baseline->electronics_input:None:normal"),
                       ("원료 +1 − 두 AI 수정", "main:ai_combined->combined_input:None:normal"))
    sections["s4"] = (paragraph("먼저 AI 탐색 결과를 검토한 뒤, 사전에 정의한 공통 원료 계수 후보를 추가로 살폈습니다. 그 뒤 조건과 소스·테스트·이전 목표를 고정해 별도 시드로 확인했습니다. 탐색은 후보를 검토한 이유이며 아래 본검증 평균에 합치지 않았습니다.")
                      + paragraph(verdict["input"]) + raw_main_table(data)
                      + paragraph("거래 물량은 재판매를 포함한 거래 건별 수량이고, 생산 투입은 실제로 소비한 원료입니다. 원료가 더 투입된 사실과 최종 완제품이 더 많이 사용된 사실은 구별합니다.", "note")
                      + contrast_main_table(data, input_contrasts)
                      + '<h3>9개국에 미친 영향</h3>'
                      + paragraph("각 셀은 기존안 → " + MODES[candidate] + "입니다. 추가 3개국은 경제 결과에 포함하되 임의의 총점을 붙이지 않습니다.", "note")
                      + country_outcomes_table(data, candidate)
                      + '<h3>산업 유형별 현금의 구성</h3>'
                      + cash_components_table(data, ("baseline", candidate))
                      + paragraph("원료 산업의 미네리아·페리아와 전자제품 산업의 테크니아·노비아를 함께 보여 줍니다. 테크니아는 구매지출이 늘어도 투자 지출이 줄어 종료 현금이 더 남을 수 있습니다. 현금 증가를 추가 이익이나 폭리로 해석하지 않습니다. 수입으로 얻은 생활 유지와 개발 가능성도 별도로 확인해야 합니다.", "note")
                      + '<h3>AI가 고른 개발계획의 조건</h3>'
                      + plans_main_table(data, ("baseline", candidate))
                      + paragraph("모든 가능한 개발안을 조사한 표가 아닙니다. AI가 선택한 합법 계획에서 현금·생활·원료·필요한 기계 조건이 충족됐는지 봅니다. 부족 사유는 겹칠 수 있어 합계가 시도 수와 같지 않을 수 있습니다.", "note")
                      + '<h3>테크니아의 실물 변화가 점수에 보이는가</h3>'
                      + paragraph(verdict["score"]) + technia_score_table(data, candidate)
                      + fixed_targets_highest_table(data, candidate)
                      + paragraph("고정 목표 참고 보기에서는 최고점 분포가 달라집니다. 이전 목표를 새로 맞추지 않은 참고 결과이며, 같은 승률을 만드는 것을 목표로 삼거나 이것만으로 공정성이 해결됐다고 판단하지 않습니다. 이 원료 후보의 1G·무행동 360쌍에서도 본인 참고 총점이 자기 정상보다 높아진 경우는 없었습니다.", "note"))
    sections["s5"] = (paragraph(verdict["stress"])
                      + paragraph("아래 두 표는 " + MODES[candidate] + " 안에서 같은 30시드의 정상 운영과 비교합니다. ‘상승 게임’은 해당 지표가 자기 정상보다 큰 경우이며, 세계 최고점이나 학습 성공률이 아닙니다.", "note")
                      + '<h3>공개 판매가 1G 반복</h3>' + focal_behavior_table(data, candidate, "minimum")
                      + '<h3>무행동</h3>' + focal_behavior_table(data, candidate, "idle")
                      + '<h3>반값·1G 전략의 차이</h3>'
                      + technia_prices_table(data, candidate)
                      + '<h3>공급 중단·저가 판매·세 역할이 겹칠 때</h3>'
                      + generation_stress_table(data, candidate)
                      + paragraph(verdict["stress_extra"]))
    verification = table(("검증 자료", "범위"), (
        ("단계별 고유 경제 실행", f"탐색 {m['pilot_games']:,}개 + 정상 본검증 {m['main_games']:,}개 + 스트레스 {m['stress_games']:,}개 = {m['completed_games']:,}개. 정식 결과는 탐색을 제외한 {m['formal_games']:,}개입니다."),
        ("회귀·내부 불변식", f"회귀 테스트 {m['tests_completed']:,}개 통과. 전체 내부 불변식 호출 {m['verification_calls']:,}회, 보고된 실패 {m['verification_failures']:,}건."),
        ("독립 결과 감사", f"{data.audit['checks_evaluated']:,}개 대조, 오류 {len(data.audit['errors']):,}건. 전체 요약과 정식 현금·자원 원장 각 {m['formal_cash_ledger_rows']:,}행을 확인했습니다."),
        ("개별 실물·선택 추적", f"사전에 정한 첫 시드의 대표 {m['representative_traces']:,}개 게임을 상세 재구성했습니다. 모든 게임의 개별 실물을 상세 추적한 것은 아닙니다."),
        ("변경 경계", "기존 Python 76개와 v12 목표 파일을 보존했습니다. 공식 점수·추가 현금비·보관비를 이번 후보에 섞지 않았습니다."),
    ))
    sections["s6"] = (paragraph(verdict["next"]) + metric_scope_table() + verification + scope_paragraphs()
                      + paragraph("근거 파일: rules_audit.json, CAUSAL_PROTOCOL_V13.json, causal_results/pre_run_plan.json, freeze_manifest.json, run_manifest.json, runs.jsonl.gz, summary.json, independent_pilot_audit.json, independent_audit.json. 보고서의 표시 수치는 validate_causal_report.py로 저장 원자료와 다시 대조할 수 있습니다.", "note"))
    return sections

CSS = """
:root{--ink:#1d2d38;--muted:#526572;--line:#dce5e9;--paper:#fff;
--accent:#126d73;--soft:#edf6f5;--warm:#fff5de;--bg:#f3f6f7}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:system-ui,-apple-system,'Noto Sans KR','Malgun Gothic',sans-serif;
font-size:16px;line-height:1.75}main{max-width:1180px;margin:auto;padding:32px 28px 64px}
header{padding:26px 0 20px}h1{font-size:clamp(25px,3.2vw,39px);line-height:1.35;
letter-spacing:-.04em;margin:8px 0 16px}h2{font-size:25px;line-height:1.4;
letter-spacing:-.025em;margin:0 0 20px}h3{font-size:19px;margin:24px 0 10px}
p{margin:12px 0}.eyebrow{color:var(--accent);font-weight:750;letter-spacing:.05em}
.subtitle,.note{color:var(--muted)}.note{font-size:14px}.lead{font-size:18px}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 24px}nav a{padding:8px 12px;
border:1px solid var(--line);border-radius:7px;text-decoration:none;color:var(--accent);
background:var(--paper);font-size:14px}section{background:var(--paper);border:1px solid var(--line);
border-radius:12px;padding:26px;margin:22px 0;scroll-margin-top:16px}
.finding{background:var(--soft);border-left:4px solid var(--accent);padding:16px 18px;margin:16px 0}
.caution{background:var(--warm);border-left:4px solid #bb8125;padding:16px 18px;margin:16px 0}
.table-wrap{overflow-x:auto;max-width:100%;margin:16px 0 10px}table{border-collapse:collapse;
width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{padding:10px 12px;
border-bottom:1px solid var(--line);text-align:right;vertical-align:top;white-space:nowrap}
thead th{background:#edf2f4;color:#263f4b;font-weight:700}th:first-child,td:first-child{
text-align:left;white-space:normal;min-width:125px}tbody th{font-weight:600}
table.two-columns td:last-child{text-align:left;white-space:normal;min-width:260px}
code{font-size:.9em;overflow-wrap:anywhere}li{margin:6px 0}footer{color:var(--muted);
font-size:13px;margin-top:24px}@media(max-width:640px){main{padding:18px 12px 40px}
section{padding:20px 16px;border-radius:9px}h2{font-size:22px}th,td{padding:9px 10px}}
@media print{body{background:white}main{max-width:none;padding:0}nav{display:none}
section{border:0;border-top:1px solid var(--line);padding:18px 0;break-inside:auto}
.table-wrap{overflow:visible}table{font-size:10px}th,td{padding:6px;white-space:normal}
h2,h3{break-after:avoid}tr{break-inside:avoid}}
"""


def paragraph(text: str, class_name: str = "") -> str:
    attr = f' class="{escape(class_name, quote=True)}"' if class_name else ""
    return f"<p{attr}>{escape(text)}</p>"


def rules_section(audit: dict) -> str:
    """Explain the inherited baseline without turning past proposals into rules."""
    need(audit.get("schema") == "v13-rules-audit-1", "The documented v13 rule audit is required.")
    need(audit.get("status") == "baseline_reconciled_no_unauthorized_rule_change", "Baseline reconciliation must be complete.")
    need(audit["provenance"]["inherited_files_checked"] == 76 and not audit["provenance"]["mismatches"],
         "Inherited baseline source hashes must agree.")
    rules = {row["id"]: row for row in audit["rules"]}
    for key in ("storage_fee", "extra_bonus_recipe", "machine_service"):
        need(rules[key]["current"] == "disabled", "A deferred cost proposal must not silently become an active rule.")
    need(rules["separate_manufacturing_cash"]["current"] == "absent", "Baseline cash-cost scope changed.")
    rows = [
        ("운영·개발 원료", "산업 운영과 연구에 원료 실물 소비가 적용됩니다. 원료를 사면 구매대금이 나가며, 개발에는 투자 현금도 필요합니다. AI 비교에서는 이 규칙을 고정합니다."),
        ("보관비·추가 원료·정비 후보", "보관비와 별도 보너스 생산 원료는 OFF이며, 기계 정비도 현재 기준에서 적용하지 않습니다. 조사한 과거 실험 기록에서 보류된 후보로 확인되어 구현 오류로 단정하지 않습니다."),
        ("별도 현금 비용", "생산 회차·완제품마다 차감하는 별도 공정 현금비와 판매수수료는 없습니다. 이는 원료 구매 비용이 없다는 뜻이 아닙니다."),
        ("재고·투자 평가", "기존 기준가격 평가를 유지합니다. 평가자산은 실제 청산 대금이 아니므로 현금 및 실제 사용과 구분해 읽습니다."),
        ("점수와 경쟁 범위", "원래 6개국의 공식 점수와 기존 무역 평가를 고정합니다. 추가 3개국의 총점은 미설정이며, 이전 점수 후보 실험을 공식 채택으로 간주하지 않습니다."),
    ]
    return (paragraph("먼저 이전 설계에서 논의된 후보와 현재 실행 중인 규칙을 대조했습니다. 검토한 저장 자료와 실행 설정이 확인 범위이며, 과거 대화 전체를 복원했다는 뜻은 아닙니다.")
            + table(("항목", "실행 기준과 해석"), rows)
            + paragraph("현금은 시작 현금 + 현금 판매수입 − 현금 구매지출 − 투자 현금 + 만족도 연계 운영수입으로 연결됩니다. 구매지출에는 생활·생산·설비용 거래가 섞이고, 판매수입에는 초기 재고 판매와 재판매도 들어갈 수 있습니다. 판매−구매를 상품별 이익률로 해석하지 않습니다.", "note")
            + paragraph("근거: rules_audit.json, RULES_AUDIT_V13_KO.txt, V12_PROVENANCE.json 및 각 자료에 기록한 저장 문서·소스 위치.", "note"))


def scope_paragraphs() -> str:
    return (paragraph("수치 차이는 정해진 자동 정책과 시드에서 나온 경제 모형의 결과입니다. 같은 시드를 짝지은 차이는 비교 조건을 맞추지만 실제 학생의 행동이나 학습 효과에 대한 신뢰구간은 아닙니다.")
            + paragraph("원래 6개국의 최고점 빈도는 9개국 경제 안에서 평가 기준이 있는 6개국끼리 비교한 값입니다. 나라의 평균 점수나 최고점 빈도가 같아진 것만으로 공정성을 입증하지 않습니다.")
            + paragraph("학생 3명과 AI 6개국이 9라운드를 40분+40분 안에 진행할 때의 이해·협상·참여와 속도는 별도 확인이 필요합니다. AI의 운영 선택은 학생에게 새 계산 과제를 부과하거나 학생의 현금을 자동 지출할 권한을 뜻하지 않습니다."))


def policy_table() -> str:
    return table(("비교 조건", "바뀌는 부분"), (
        (MODES["baseline"], "기존 경제·AI·공식 점수를 유지합니다."),
        (MODES["operating_first"], "식량 다음에 현재 설비의 다음 생산 원료 예산을 먼저 예약합니다. 계획의 가상 지갑 배정만 바꾸고 원료행을 합쳐 실제 거래 순서와 협상 기회를 유지합니다."),
        (MODES["no_durable_boost"], "AI 투자 선택식에서 초기 내구재 산업에 붙던 1.8배 가중치를 1배로 바꿉니다. 다른 선택항·현금·원료·생활 조건은 유지합니다."),
        (MODES["ai_combined"], "위 두 AI 변경을 함께 적용합니다."),
        (MODES["electronics_input"], "기존 AI에서 전자 산업 Lv2 이상 생산 회차의 해당 기존 원료를 1묶음 더 소비합니다. 모든 생산국에 적용하며 완제품 한 개당 추가 원료라는 뜻은 아닙니다."),
        (MODES["combined_input"], "두 AI 변경에 위 전자제품 원료 계수 변경을 더합니다."),
    ))


def metric_scope_table() -> str:
    return table(("표의 표현", "의미와 범위"), (
        ("판매·구매·현금", "판매수입과 구매지출은 현금 흐름입니다. 생활 수입품, 초기 재고 판매, 재판매 등이 섞이므로 제조 이익과 구별합니다."),
        ("실제 사용", "그 나라가 생산한 실물 중 실제 사용으로 기록된 개수입니다. 자국 또는 외국에서 사용될 수 있으며 수입품 소비량과는 다릅니다. 품목마다 한 단위의 가치·역할이 다르므로 나라 사이의 물량 크기만으로 기여도를 매기지 않습니다."),
        ("개발 시도·성공", "AI가 고른 계획의 합법 여부·자금·생활·원료·기계 조건과 실제 성공을 봅니다. 선택하지 않은 모든 개발안의 가능성을 조사한 값이 아닙니다. 여러 조건의 부족은 겹칠 수 있습니다."),
        ("1G·무행동", "1G는 공개 시장의 개당 호가입니다. 직접 협상과 물물교환까지 같은 가격으로 바꾸지 않습니다. 무행동도 자동 생산과 운영수입은 남습니다."),
        ("점수", "기존 공식 점수를 고정하며 v12에서 고정한 목표 보기는 보조로만 읽습니다. 이번 결과를 보고 목표를 재학습하지 않습니다."),
    ))


def render_document(sections: dict[str, str], subtitle: str) -> str:
    """Render complete sections only; missing evidence must stop generation."""
    need(set(sections) == {key for key, _ in SECTION_TITLES}, "Every report section must be complete.")
    need(all(sections.values()), "Empty result sections cannot be published.")
    nav = "".join(f'<a href="#{key}">{escape(title)}</a>' for key, title in SECTION_TITLES)
    body = "".join(f'<section id="{key}"><h2>{i}. {escape(title)}</h2>{sections[key]}</section>'
                   for i, (key, title) in enumerate(SECTION_TITLES, 1))
    return ("<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>#11 무역 게임 — v13 경제 원인 검증</title>'
            f'<style>{CSS}</style></head><body><main><header><div class="eyebrow">#11 무역 게임 · v13</div>'
            '<h1>국가별 경제 차이는 어디에서 생기는가</h1>'
            f'<p class="subtitle">{escape(subtitle)}</p></header><nav aria-label="보고서 목차">{nav}</nav>'
            f'{body}<footer>저장된 자동 실행 결과를 검토하는 정적 보고서입니다. 학생 접속용 게임이나 실제 수업 평가 결과가 아닙니다.</footer>'
            '</main></body></html>')


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.anchors, self.external, self.qa, self.errors = [], [], [], [], []
        self.tables = self.rows = 0
        self.width = self.cells = None

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if "id" in attr:
            self.ids.append(attr["id"])
        if tag == "a" and attr.get("href", "").startswith("#"):
            self.anchors.append(attr["href"][1:])
        if any(attr.get(key, "").startswith(("http:", "https:", "//")) for key in ("href", "src")):
            self.external.append(attr)
        if "data-qa" in attr:
            self.qa.append(json.loads(attr["data-qa"]))
        if tag == "table":
            self.tables += 1
            self.width = None
        if tag == "tr":
            self.rows += 1
            self.cells = 0
        if tag in ("td", "th") and self.cells is not None:
            self.cells += 1

    def handle_endtag(self, tag):
        if tag == "tr":
            if self.width is None:
                self.width = self.cells
            elif self.width != self.cells:
                self.errors.append(f"Table {self.tables}: inconsistent column count.")
            self.cells = None


def check_structure(html: str, report: Path, results: Path) -> dict:
    parser = StructureParser()
    parser.feed(html)
    parser.close()
    need(not parser.errors, "; ".join(parser.errors))
    expected = {key for key, _ in SECTION_TITLES}
    need(set(parser.ids) == expected and len(parser.ids) == len(expected), "Unique report sections required.")
    need(set(parser.anchors) == expected, "Navigation must reach every section.")
    need(not parser.external, "The report must be self-contained.")
    need(bool(parser.qa), "Result tables must expose independently checkable numeric locators.")
    receipt = {
        "status": "passed", "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "sections": len(parser.ids), "tables": parser.tables, "rows": parser.rows,
        "numeric_cells": len(parser.qa), "external_assets": 0, "errors": [],
        "scope": "HTML structure and numeric locator syntax; no browser screenshot validation.",
    }
    (results / "report_structure_qa.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def build(results: Path, report: Path) -> dict:
    data = SavedResults(results)
    need(FINAL_VERDICT is not None, "The complete evidence must be reviewed before writing a verdict.")
    # The broad statement in the verdict is checked against every declared
    # original-country minimum/idle pairing, not inferred from mean scores.
    compared = 0
    for mode in MODES:
        control = f"stress:{mode}:None:normal"
        for name in ORIGINAL:
            metric = f"countries.{name}.score"
            before = data.values(control, metric)
            for style in ("minimum", "idle"):
                after = data.values(f"stress:{mode}:{name}:{style}", metric)
                need(before.keys() == after.keys(), "Complete stress pairs required.")
                need(all(after[seed] <= before[seed] + 1e-9 for seed in before),
                     "The stated all-mode strategy finding must be revised for a positive-score exception.")
                compared += len(before)
    need(compared == 2160, "Every declared low-price/inactive own-score comparison is required.")
    candidate = FINAL_VERDICT["focus_mode"]
    reference_pairs = 0
    for name in ORIGINAL:
        metric = f"countries.{name}.growth_evaluation.targets.score"
        before = data.values(f"stress:{candidate}:None:normal", metric)
        for style in ("minimum", "idle"):
            after = data.values(f"stress:{candidate}:{name}:{style}", metric)
            need(before.keys() == after.keys() and all(after[seed] <= before[seed] + 1e-9 for seed in before),
                 "The fixed-reference own-score statement must match every saved pair.")
            reference_pairs += len(before)
    need(reference_pairs == 360, "Complete fixed-reference stress coverage required.")
    sections = compose_sections(data, FINAL_VERDICT)
    html = render_document(sections, "탐색 180개와 별도 검증 4,920개 · 실제 경제 결과 우선 · 공식 점수와 기존 목표 고정")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(html, encoding="utf-8")
    return check_structure(html, report, results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    print(json.dumps(build(args.results.resolve(), args.report.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
