"""검수 시트 생성·채점 도구 테스트."""
import csv
import json

import pytest

from eval import make_review_sheet as mk
from eval import score_review as sc
from eval.stats import stratified, wilson


def test_wilson_matches_known_values():
    lo, hi = wilson(35, 37)                 # 앞선 보고서의 재현율 95% [82~99%]
    assert round(lo, 2) == 0.82 and round(hi, 2) == 0.99
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(10, 10)
    assert hi == pytest.approx(1.0) and lo < 1.0


def test_stratified_weights_the_strata_by_population():
    est, lo, hi = stratified([(900, 30, 30), (100, 30, 15)])     # 큰 층은 100%, 작은 층은 50%
    assert round(est, 3) == 0.95 and lo <= est <= hi
    assert stratified([(10, 0, 0)]) == (0.0, 0.0, 1.0)


def result():
    def table(cap, rows, cols=("SIZE / Inch", "SIZE / mm", "L", "H"), flags=()):
        return {"caption": cap, "columns": list(cols), "rows": rows, "flags": list(flags), "issues": [], "reads": 3}
    return {"pages": [
        {"page": 9, "tables": [table("T9", [["3", "80", "48", "252"]])], "facts": []},
        {"page": 11, "tables": [table("T11", [["3", "80", "48", "252"], ["4", "100", "54", None], ["5", "125", "57", "290"]],
                                      flags=[{"row": 1, "column": "H", "values": ["9", None, None], "majority": None}])],
         "facts": [{"category": "end flange", "availability": "STANDARD", "statement": "JIS B2210"}]},
    ]}


def test_universe_skips_pages_and_marks_flags_and_blank_majority_as_resolved():
    cells = mk.cell_universe(result(), {9})
    assert {c["page"] for c in cells} == {11} and len(cells) == 12
    f = [c for c in cells if c["flagged"]]
    assert len(f) == 1 and f[0]["unresolved"] is False and f[0]["ai"] is None      # 과반이 빈칸 → 해결됨


def test_sample_includes_all_flagged_and_hides_flags_in_the_sheet(tmp_path):
    cells, facts = mk.sample(result(), 5, 5, {9})
    assert sum(c["stratum"] == "flagged" for c in cells) == 1 and len(facts) == 1
    mk.write(tmp_path, cells, facts, {"flagged": 1, "plain": 11, "fact": 1})
    sheet = (tmp_path / "review_sheet.csv").read_text(encoding="utf-8-sig")
    assert "flagged" not in sheet and "stratum" not in sheet                         # 검수자에게 경고 여부를 숨긴다
    key = (tmp_path / "answer_key.csv").read_text(encoding="utf-8-sig")
    assert "flagged" in key and "plain" in key


def fill(tmp_path, answers):
    rows = list(csv.reader(open(tmp_path / "review_sheet.csv", encoding="utf-8-sig")))
    head, body = rows[0], rows[1:]
    idx = next(i for i, h in enumerate(head) if h.startswith("검수"))
    for r in body:
        r[idx] = answers(r)
    out = tmp_path / "filled.csv"
    csv.writer(open(out, "w", newline="", encoding="utf-8-sig")).writerows([head] + body)
    return out


def test_scoring_counts_o_and_corrections_and_reports_unreviewed(tmp_path):
    cells, facts = mk.sample(result(), 50, 5, {9})
    mk.write(tmp_path, cells, facts, {"flagged": 1, "plain": 11, "fact": 1})
    pop = json.loads((tmp_path / "population.json").read_text())

    def answers(r):
        if r[1] == "사실":
            return "O"
        if r[5] == "H" and r[4] == "4 | 100":                       # 경고가 뜬 셀: AI 는 빈칸, 사람은 274 라고 정정 → 틀림
            return "274"
        return "O" if r[7] == "" and r[2] != "" and r[4] != "3 | 80" else ""     # 첫 행은 일부러 미검수로 둔다
    res = sc.score(sc.load(tmp_path, fill(tmp_path, answers)), pop)
    assert res["unreviewed"] >= 4
    assert res["strata"]["flagged"]["n"] == 1 and res["strata"]["flagged"]["correct"] == 0
    assert res["flag_precision"] == 1.0 and res["silent_error_rate"] == 0.0
    assert res["strata"]["fact"]["correct"] == 1


def test_is_correct_rules():
    assert sc.is_correct("O", "48") and sc.is_correct(" ok ", "48") and sc.is_correct("48.0", "48")
    assert not sc.is_correct("X", "48") and not sc.is_correct("50", "48")
    assert sc.is_correct("없음", "(빈칸)") and not sc.is_correct("없음", "48")
    assert not sc.is_correct("48", "(빈칸)")                       # 사람이 값을 적었는데 AI가 빈칸 → 누락 오류
