"""카탈로그 표 검증 함수 테스트. 픽스처는 손으로 만든 작은 표(실제 카탈로그 값 아님)다."""
from app.catalog_checks import (check_dependency, check_table, compare_reads, flagged_cells, flatten,
                                needs_more_reads, normalize)


def row(inch, mm, L, h1, typ="F07", c1=70):
    return {"size_inch": str(inch), "size_mm": str(mm), "L": str(L), "flange_h1": str(h1), "mount_type": typ, "mount_C1": str(c1)}


GOOD = [row(3, 80, 48, 19.1), row(4, 100, 54, 19.1), row(5, 125, 57, 22.2), row(6, 150, 57, 22.2)]


def kinds(issues):
    return sorted(i.kind for i in issues)


def test_good_table_has_no_issue():
    assert check_table("T", GOOD, monotonic=["L", "flange_h1"]) == []


def test_size_pair_mismatch_is_error():
    rows = [row(3, 80, 48, 19.1), row(4, 125, 54, 19.1)]      # 4" 는 100mm
    issues = check_table("T", rows)
    assert kinds(issues) == ["size_pair"] and issues[0].severity == "error"


def test_order_and_duplicate():
    assert "order" in kinds(check_table("T", [row(4, 100, 54, 19.1), row(3, 80, 48, 19.1)]))
    assert "duplicate" in kinds(check_table("T", [row(3, 80, 48, 19.1), row(3, 80, 49, 19.1)]))


def test_monotonic_violation_is_review_not_error():
    rows = [row(3, 80, 48, 19.1), row(4, 100, 54, 19.1), row(5, 125, 50, 22.2)]     # L 이 줄어듦
    issues = check_table("T", rows, monotonic=["L"])
    assert kinds(issues) == ["monotonic"] and issues[0].severity == "review"        # 원본 이상값일 수 있어 '확인'


def test_blank_cells_are_skipped_in_monotonic():
    rows = [row(3, 80, 48, 19.1), row(4, 100, 54, "-"), row(5, 125, 57, 22.2)]
    assert check_table("T", rows, monotonic=["flange_h1"]) == []


def test_known_limit_plausible_wrong_value_is_not_caught():
    """이웃 행의 값(25.4)을 가져와도 오름차순이 유지되면 구조 검사는 통과한다 — 실제 카탈로그 시험에서 나온 오류 유형."""
    rows = [row(6, 150, 59, 22.2), row(8, 200, 73, 25.4), row(10, 250, 83, 25.4)]
    wrong = [dict(rows[0], flange_h1="25.4")] + rows[1:]
    assert check_table("T", wrong, monotonic=["flange_h1"]) == []


def test_dependency_flags_minority_combination():
    t1 = [row(3, 80, 48, 19.1, "F07", 70), row(4, 100, 54, 19.1, "F07", 70)]
    t2 = [row(3, 80, 48, 19.1, "F07", 70), row(4, 100, 54, 19.1, "F07", 102)]      # 같은 TYPE 인데 C1 이 다름
    issues = check_dependency({"A": t1, "B": t2}, "mount_type", ["mount_C1"])
    assert len(issues) == 1 and issues[0].table == "B" and issues[0].row == "100"


def test_dependency_ok_when_consistent():
    t = [row(3, 80, 48, 19.1, "F07", 70), row(4, 100, 54, 19.1, "F10", 102)]
    assert check_dependency({"A": t}, "mount_type", ["mount_C1"]) == []


def test_normalize():
    assert normalize("-") is None and normalize(" ") is None and normalize(None) is None
    assert normalize("200.0") == normalize(200) == 200.0
    assert normalize("1  1/8-8") == "1 1/8-8"


def _read(h1_150):
    tables = [{"class": "CLASS 300", "rows": [
        {"size_mm": "150", "flange_h1": h1_150, "L": "59"}, {"size_mm": "200", "flange_h1": "25.4", "L": "73"}]}]
    return flatten(tables, ["flange_h1", "L"])


def test_three_reads_flag_only_the_disagreeing_cell_and_vote_the_majority():
    votes = compare_reads([_read("25.4"), _read("22.2"), _read("22.2")])
    assert flagged_cells(votes) == [("CLASS300", 150.0, "flange_h1")]
    v = votes[("CLASS300", 150.0, "flange_h1")]
    assert v.has_majority and v.majority == 22.2
    assert not needs_more_reads(votes)


def test_two_reads_disagreement_has_no_majority_and_needs_a_third():
    votes = compare_reads([_read("25.4"), _read("22.2")])
    v = votes[("CLASS300", 150.0, "flange_h1")]
    assert v.flagged and not v.has_majority and v.majority is None
    assert needs_more_reads(votes)


def test_identical_reads_raise_no_flag():
    votes = compare_reads([_read("22.2"), _read("22.2"), _read("22.2")])
    assert flagged_cells(votes) == [] and not needs_more_reads(votes)


def test_known_limit_same_wrong_value_in_every_read_is_not_caught():
    votes = compare_reads([_read("25.4"), _read("25.4"), _read("25.4")])      # 체계적 오류: 셋 다 같은 오답
    assert flagged_cells(votes) == []


def test_empty_input():
    assert compare_reads([]) == {} and not needs_more_reads({})
