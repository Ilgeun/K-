"""카탈로그 읽기 파이프라인 테스트 — 읽기 구현(Reader)을 가짜로 바꿔 외부 호출 없이 검증한다."""
import io

import pytest
from PIL import Image
from reportlab.pdfgen import canvas

from app import catalog_read as cr
from app.pdf import PageImage, is_scanned, page_images


def tab(rows, cols=("SIZE / Inch", "SIZE / mm", "L", "H")):
    return cr.CatalogTable(caption="DIMENSIONS", unit="mm", columns=list(cols), rows=rows)


R_OK = [["3", "80", "48", "252"], ["4", "100", "54", "274"], ["5", "125", "57", "290"]]


def variant(rows, r, c, v):
    out = [list(x) for x in rows]
    out[r][c] = v
    return out


class FakeReader:
    """kind 별로 미리 정한 응답을 순서대로 돌려준다(table 은 호출할 때마다 다음 응답)."""
    name = "fake"

    def __init__(self, kind="dimension_table", has_table=True, has_text=False, tables=(), facts=(), uncovered=()):
        self.kind, self.has_table, self.has_text = kind, has_table, has_text
        self.tables, self.facts, self.uncovered = list(tables), list(facts), list(uncovered)
        self.calls = []

    def call(self, kind, image, model, extra=""):
        self.calls.append(kind)
        if kind == "classify":
            return cr.PageKind(kind=self.kind, has_table=self.has_table, has_text=self.has_text)
        if kind == "table":
            return cr.TablePage(tables=[self.tables[(self.calls.count("table") - 1) % len(self.tables)]], notes=["NOTE 1"])
        if kind == "facts":
            return cr.FactPage(facts=self.facts)
        return cr.UncoveredPage(uncovered=self.uncovered)


IMG = PageImage(9, "image/jpeg", b"x")


def test_two_identical_reads_give_no_flag_and_keep_notation():
    rows = [["3", "80", "48.0", "252"], ["4", "100", "54.0", "274"]]
    res = cr.read_page(IMG, FakeReader(tables=[tab(rows)]))
    t = res.tables[0]
    assert t.flags == [] and t.reads == 2 and t.rows[0][2] == "48.0"           # 200.0 을 200 으로 바꾸지 않음
    assert res.warnings == [] and res.notes == ["NOTE 1"]


def test_disagreement_triggers_a_third_read_and_the_majority_wins():
    reader = FakeReader(tables=[tab(variant(R_OK, 1, 3, "999")), tab(R_OK), tab(R_OK)])
    res = cr.read_page(IMG, reader)
    t = res.tables[0]
    assert reader.calls.count("table") == 3
    assert t.rows[1][3] == "274" and t.reads == 3
    assert [(f.row, f.column, f.majority) for f in t.flags] == [(1, "H", "274")]


def test_disagreement_with_no_majority_leaves_the_cell_blank_and_warns():
    reader = FakeReader(tables=[tab(variant(R_OK, 1, 3, "111")), tab(variant(R_OK, 1, 3, "222")), tab(variant(R_OK, 1, 3, "333"))])
    res = cr.read_page(IMG, reader)
    t = res.tables[0]
    assert t.rows[1][3] is None and t.flags[0].majority is None
    assert any("끝내 일치하지 않은 셀 1개" in w for w in res.warnings)


def test_structure_check_reports_size_pair_and_monotonic_as_issues():
    rows = [["3", "80", "48", "252"], ["4", "125", "54", "274"], ["5", "125", "50", "290"]]   # 4" 는 100mm, L 감소
    t = cr.read_page(IMG, FakeReader(tables=[tab(rows)])).tables[0]
    kinds = {i["kind"] for i in t.issues}
    assert {"size_pair", "monotonic", "duplicate"} <= kinds


def test_table_without_size_columns_skips_structure_checks():
    t = cr.read_page(IMG, FakeReader(tables=[tab([["a", "1"], ["b", "2"]], cols=("Name", "Value"))])).tables[0]
    assert t.issues == []


def test_shape_mismatch_read_is_excluded_from_comparison():
    res = cr.read_page(IMG, FakeReader(tables=[tab(R_OK), tab(R_OK[:2])]))     # 2회 읽기에서 행 수가 다름
    t = res.tables[0]
    assert any(i["kind"] == "shape" for i in t.issues) or any("달라" in w for w in res.warnings)


class _TwoTables(FakeReader):
    """한 쪽에 표 두 개(Class 만 다른 같은 종류): 두 번째 표의 열이 하나 빠져 읽힘."""
    def call(self, kind, image, model, extra=""):
        if kind == "table":
            self.calls.append(kind)
            return cr.TablePage(tables=[tab(R_OK).model_copy(update={"caption": "DIMENSIONS / CLASS 150"}),
                                        tab([r[:3] for r in R_OK], cols=("SIZE / Inch", "SIZE / mm", "L")).model_copy(update={"caption": "DIMENSIONS / CLASS 600"})])
        return super().call(kind, image, model, extra)


def test_same_kind_tables_with_different_column_counts_are_warned():
    res = cr.read_page(IMG, _TwoTables())
    assert any("같은 종류의 표" in w and "열 수가 서로 다릅니다" in w and "CLASS 600: 3열" in w for w in res.warnings)


def test_excluded_shape_reads_are_surfaced_as_page_warnings():
    """두 번 읽은 결과의 행 수가 다르면(어느 쪽이 맞는지 모름) 한쪽을 제외했다는 사실을 쪽 경고로 알린다."""
    res = cr.read_page(IMG, FakeReader(tables=[tab(R_OK), tab(R_OK[:2])]))
    assert any("행·열 수가 달라 비교에서 제외" in w and "제외된 쪽이 맞을 수 있으니" in w for w in res.warnings)


def test_facts_and_audit_missing_sentences_are_reported():
    fact = cr.CatalogFact(category="end flange", availability="STANDARD", statement="JIS B2210", classes=["10K"])
    unc = [cr.Uncovered(text="Fire safe design", contains_spec_info=True, reason="feature"),
           cr.Uncovered(text="DESIGN FEATURE", contains_spec_info=False, reason="heading")]
    res = cr.read_page(IMG, FakeReader(kind="spec_list", has_table=False, has_text=True, facts=[fact], uncovered=unc))
    assert [m.text for m in res.missing] == ["Fire safe design"]                # 제목만 있는 항목은 제외
    assert any("빠진 사양 관련 문장 1개" in w for w in res.warnings) and res.tables == []


def test_pages_without_table_or_text_are_not_read_further():
    reader = FakeReader(kind="cover", has_table=False, has_text=False)
    res = cr.read_page(IMG, reader)
    assert reader.calls == ["classify"] and res.tables == [] and res.facts == []


def test_contact_pages_are_skipped_even_if_they_have_text():
    reader = FakeReader(kind="contact", has_table=False, has_text=True)
    res = cr.read_page(IMG, reader)
    assert reader.calls == ["classify"] and res.facts == []


def test_one_failing_page_does_not_stop_the_others():
    class Flaky(FakeReader):
        def call(self, kind, image, model, extra=""):
            if image.page == 2:
                raise RuntimeError("boom")
            return super().call(kind, image, model, extra)
    imgs = [PageImage(1, "image/jpeg", b"x"), PageImage(2, "image/jpeg", b"x")]
    out = cr.read_catalog(imgs, Flaky(kind="cover", has_table=False), "f.pdf", page_count=2, workers=1)
    assert [p.kind for p in out.pages] == ["cover", "error"] and "boom" in out.pages[1].warnings[0]


def test_no_images_gives_a_clear_warning():
    out = cr.read_catalog([], FakeReader(), "f.pdf", page_count=3)
    assert out.pages == [] and "이미지를 꺼낼 수 있는 쪽이 없습니다" in out.warnings[0]


def test_api_reader_sends_an_image_block_and_returns_the_parsed_output():
    class Resp:
        stop_reason, parsed_output = "end_turn", cr.PageKind(kind="cover", has_table=False, has_text=False)

    class Msgs:
        def parse(self, **kw):
            self.kw = kw
            return Resp()

    class Client:
        messages = Msgs()

    out = cr.ApiReader(Client()).call("classify", PageImage(3, "image/png", b"abc"), cr.PageKind)
    kw = Client.messages.kw
    block = kw["messages"][0]["content"][0]
    assert out.kind == "cover" and kw["output_format"] is cr.PageKind
    assert block["type"] == "image" and block["source"]["media_type"] == "image/png" and block["source"]["data"] == "YWJj"


def test_api_reader_refusal_and_truncation_raise():
    class Resp:
        def __init__(self, stop, parsed): self.stop_reason, self.parsed_output = stop, parsed

    class Msgs:
        def __init__(self, r): self.r = r
        def parse(self, **kw): return self.r

    for r in (Resp("refusal", None), Resp("max_tokens", None), Resp("end_turn", None)):
        client = type("C", (), {"messages": Msgs(r)})()
        with pytest.raises(RuntimeError):
            cr.ApiReader(client).call("classify", IMG, cr.PageKind)


# --------------------------------------------------------------- pdf 도우미
def _scan_pdf(tmp_path, pages=2):
    p = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(p))
    for i in range(pages):
        buf = io.BytesIO()
        Image.new("RGB", (200 + i * 50, 300), (240, 240, 240)).save(buf, "PNG")
        buf.seek(0)
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(buf), 0, 0, width=200, height=300)
        c.showPage()
    c.save()
    return p


def test_page_images_extracts_one_image_per_scanned_page(tmp_path):
    imgs = page_images(_scan_pdf(tmp_path, 3))
    assert [i.page for i in imgs] == [1, 2, 3] and all(i.data for i in imgs)
    assert [i.page for i in page_images(_scan_pdf(tmp_path, 3), pages=[2])] == [2]


def test_is_scanned():
    assert is_scanned(["", "  ", ""]) and not is_scanned(["a" * 100])
