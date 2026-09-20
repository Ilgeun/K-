"""카탈로그 벤치마크의 순수 함수 테스트(렌더링·AI 호출 없음)."""
import io

from PIL import Image

from eval import catalog_bench as cb

TEXT = """BUTTERFLY VALVES, FLANGE TYPE - JIS 10K
DN Code Body Stem Disc Seat PCD L
80 MV752380CS SC480 SUS410 Alu-Bronze NBR 150 4 x M16 60
100 MV752381CS SC480 SUS410 Alu-Bronze NBR 175 4x M16 60
some other line
"""


def test_truth_rows_and_token_normalization():
    rows = cb.truth_rows(30, TEXT)
    assert [r.code for r in rows] == ["MV752380CS", "MV752381CS"]
    assert rows[0].tokens == ["80", "MV752380CS", "SC480", "SUS410", "ALU-BRONZE", "NBR", "150", "4", "X", "M16", "60"]
    assert rows[1].tokens[7:10] == ["4", "X", "M16"]                    # '4x M16' 도 같은 토큰으로 통일


def table(rows, flags=()):
    return {"tables": [{"rows": rows, "flags": [{"row": i} for i in flags]}]}


def truth():
    return cb.truth_rows(30, TEXT)


def test_perfect_reading_scores_all_exact():
    ai = cb.ai_rows(table([["80", "MV752380CS", "SC480", "SUS410", "Alu-Bronze", "NBR", "150", "4 x M16", "60"],
                           ["100", "MV752381CS", "SC480", "SUS410", "Alu-Bronze", "NBR", "175", "4x M16", "60"]]))
    s = cb.score_page(truth(), ai)
    assert s["rows"] == s["found"] == s["exact"] == 2 and s["wrong_rows"] == [] and s["matched_tokens"] == s["truth_tokens"]


def test_wrong_value_missing_row_and_flag_detection():
    rows = [["80", "MV752380CS", "SC480", "SUS410", "Alu-Bronze", "NBR", "160", "4 x M16", "60"]]        # PCD 150 → 160
    s = cb.score_page(truth(), cb.ai_rows(table(rows)))
    assert s["found"] == 1 and s["exact"] == 0 and s["missing"] == ["MV752381CS"]
    assert s["wrong_silent"] == 1 and s["wrong_flagged"] == 0 and s["matched_tokens"] == 10                # 11개 토큰 중 10개
    s2 = cb.score_page(truth(), cb.ai_rows(table(rows, flags=[0])))
    assert s2["wrong_flagged"] == 1 and s2["wrong_silent"] == 0                                             # 경고가 뜬 행은 '검출됨'


def test_extra_and_duplicate_rows_are_counted():
    good = ["80", "MV752380CS", "SC480", "SUS410", "Alu-Bronze", "NBR", "150", "4 x M16", "60"]
    s = cb.score_page(truth(), cb.ai_rows(table([good, good, ["1", "MV999", "X"]])))
    assert s["extra"] == 1 and s["duplicates"] == 1


def test_row_without_a_code_cannot_be_matched():
    s = cb.score_page(truth(), cb.ai_rows(table([["80", "SC480", "SUS410"]])))
    assert s["found"] == 0 and len(s["missing"]) == 2


def test_summarize_and_degrade():
    a = cb.score_page(truth(), cb.ai_rows(table([["80", "MV752380CS", "SC480", "SUS410", "Alu-Bronze", "NBR", "150", "4 x M16", "60"]])))
    t = cb.summarize({30: a})
    assert t["rows"] == 2 and t["found"] == 1 and 0 < t["token_recall"] < 1 and t["row_exact_ci"][0] < t["row_exact_ci"][1]
    buf = io.BytesIO()
    Image.new("RGB", (400, 600), (255, 255, 255)).save(buf, "JPEG")
    small = Image.open(io.BytesIO(cb.degrade(buf.getvalue())))
    assert small.width >= 200 and small.height >= 300 and small.width < 400 + 20        # 절반 해상도 + 기울기로 약간 커짐


def test_table_border_glyph_is_ignored_and_error_kinds_are_classified():
    assert cb.norm_tokens("4 | 18") == cb.norm_tokens("4 18") == ["4", "18"]
    assert cb.norm_tokens("4|18") == ["4", "18"]
    t = ["80", "MV1", "SC480", "150", "4", "40"]
    assert cb.classify(t, t[:-1]) == "마지막 값 누락"
    assert cb.classify(t, ["80", "MV1", "SC480", "160", "4", "40"]) == "값 오독(치환)"
    assert cb.classify(t, ["80", "MV1", "150", "4", "40"]) == "값 누락"
    assert cb.classify(t, t + ["X"]) == "값 삽입"
    assert cb.classify(t, ["80", "MV1", "SC480", "150", "4", "40", "9"][:5] + ["7", "8"]) == "기타"
