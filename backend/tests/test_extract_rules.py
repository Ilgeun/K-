from pathlib import Path

import pytest

from app.extract_rules import extract
from app.pdf import read_pages

DATA = Path(__file__).parent.parent / "data"
REAL = DATA / "docs" / "DNV_TAP00000MH_UnicomValve.pdf"
SAMPLES = DATA / "samples"


def spec(ex, field):
    return next((s for s in ex.specs if s.field == field), None)


@pytest.fixture(scope="module")
def real():
    return extract(read_pages(REAL), REAL.name)


def test_real_certificate_fields(real):
    assert len(real.certs) == 1
    c = real.certs[0]
    assert (c.authority, c.certNo, c.validUntil, c.page) == ("DNV", "TAP00000MH", "2021-06-30", 1)
    assert c.extractedBy == "rules" and c.confirmed is False


def test_real_size_range(real):
    d = spec(real, "nominal_diameter")
    assert (d.rangeMin, d.rangeMax, d.page) == (50, 600, 1)


def test_real_doc_has_no_numeric_design_pressure(real):
    # 승인서의 'design pressure ≥ 16 bar'는 인증 요건 문구일 뿐 제품 사양이 아니다 (회귀 방지)
    assert spec(real, "design_pressure") is None


def test_real_flange_and_materials(real):
    f = spec(real, "flange_standard").value.split("|")
    assert {"JIS_10K", "JIS_16K", "JIS_20K", "PN10", "ASME_150"} <= set(f)
    m = spec(real, "body_material")
    assert set(m.value.split("|")) == {"WCB", "CF8", "CF8M"}
    assert "seawater" in m.note and m.page == 2


def test_real_temperature_uses_lowest_seat_limit(real):
    t = spec(real, "temp_max")
    assert t.value == "204" and "420" in t.display


def test_every_extracted_value_has_source_and_page(real):
    for s in real.specs:
        assert s.file == REAL.name and s.page >= 1 and s.raw


def test_flange_ignores_pressure_line_pn():
    ex = extract(["Design pressure: 16 bar (PN16)\nFlange standard: JIS B2220 10K"], "x.pdf")
    assert spec(ex, "flange_standard").value == "JIS_10K"


def test_pressure_unit_conversion_mpa():
    ex = extract(["Design pressure: 1.6 MPa"], "x.pdf")
    assert spec(ex, "design_pressure").value == "16"


def test_pressure_condition_sentence_not_a_spec():
    ex = extract(["Certificates are required for valves with design pressure ≥ 16 bar."], "x.pdf")
    assert spec(ex, "design_pressure") is None


def test_unrecognised_body_material_is_flagged_not_guessed():
    ex = extract(["Body: Unobtainium alloy"], "x.pdf")
    s = spec(ex, "body_material")
    assert s.value == "UNKNOWN" and "확인" in s.note


def test_scanned_pdf_gets_warning():
    ex = extract(["", ""], "scan.pdf")
    assert ex.warnings and not ex.specs


def test_synthetic_certificate_sample():
    f = SAMPLES / "SYNTHETIC_OF-BF200-X_DNV_certificate.pdf"
    ex = extract(read_pages(f), f.name)
    assert [(c.authority, c.certNo, c.validUntil) for c in ex.certs] == [("DNV", "SYN-DNV-0501", "2028-06-30")]


def test_synthetic_datasheet_sample():
    f = SAMPLES / "SYNTHETIC_BS-2000_datasheet_rev2.pdf"
    ex = extract(read_pages(f), f.name)
    assert spec(ex, "flange_standard").value == "JIS_10K"
    assert spec(ex, "body_material").value == "NAB"
    assert spec(ex, "design_pressure").value == "16"


# ---- 실제 문서 5건 평가에서 발견한 결함의 회귀 테스트 (문서 원문이 아닌 짧은 형식 조각 사용)
def test_lloyds_curly_apostrophe_and_long_month_date():
    page = "Certificate No.  17/30005\nIssue Date  11 November 2017\nExpiry Date  10 November 2022\nType Approval Certificate\nLloyd’s Register EMEA"
    c = extract([page], "x.pdf").certs[0]
    assert (c.authority, c.certNo, c.validUntil) == ("LR", "17/30005", "2022-11-10")


def test_lloyds_table_layout_with_dd_mm_yyyy():
    # 레이블과 값이 떨어져 추출되는 양식: 'Issue' 를 인증서 번호로 오인하면 안 된다
    page = "Type Approval Certificate\nCertificate No: \nIssue Date: \nExpiry Date: 10/01/2027\n11/01/2022\nLR2206108TA\nLloyd's Register Group"
    ex = extract([page], "x.pdf")
    c = ex.certs[0]
    assert (c.certNo, c.validUntil) == ("LR2206108TA", "2027-01-10")
    assert any("DD/MM/YYYY" in w for w in ex.warnings)


def test_plain_class_150_without_ansi_prefix():
    assert "ASME_150" in extract(["Max. working press.:  Class 150, PN10, PN16"], "x.pdf").specs[0].value


def test_multiline_body_list_and_bullets():
    page = "Material:\nBody:  \nASTM A216 Gr.WCB\nASTM A351 Gr.CF8M\nEN 1563 EN-GJS-400-15\nShaft: A276-316"
    vals = set(next(s for s in extract([page], "x.pdf").specs if s.field == "body_material").value.split("|"))
    assert {"WCB", "CF8M", "DUCTILE_IRON"} <= vals
    bullet = extract(["• Valve body: EN-JS1030 (GGG40);"], "x.pdf")
    assert next(s for s in bullet.specs if s.field == "body_material").value == "DUCTILE_IRON"


def test_pressure_label_variants():
    assert extract(["Max. working press.: 16 ba r"], "x.pdf").specs[0].value == "16"
    assert extract(["Ratings Operating pressure:   up to 50 bar"], "x.pdf").specs[0].value == "50"
    assert extract(["Max. Pressure : 16 bar"], "x.pdf").specs[0].value == "16"


def test_dn_range_and_list_forms():
    d = lambda t: next(s for s in extract([t], "x.pdf").specs if s.field == "nominal_diameter")
    assert (d("PTFE seat DN 50 – DN 600, Metal seat DN 50 – DN 125").rangeMin, d("PTFE seat DN 50 – DN 600").rangeMax) == (50, 600)
    x = d("Wafer type: DN 32,40,50,65, 1000 & 1200\nLug type: DN 32,40,300")
    assert (x.rangeMin, x.rangeMax) == (32, 1200)
    assert (d("EVS Wafer type DN40  to 1400\nEVUS DN600 to 2200").rangeMax) == 2200


def test_product_type_is_read_and_mismatch_warned_against_part_type():
    from app.extract import check_part_type
    page = "TYPE APPROVAL CERTIFICATE\nCertificate No:\nTAP000012E\nThat the Check Valve\nwith type designation(s)\nSeries 716\nDNV\nThis Certificate is valid until 2027-07-12."
    ex = extract([page], "x.pdf")
    assert ex.productType == "Check Valve"
    check_part_type(ex, "버터플라이 밸브")
    assert "Check Valve" in ex.warnings[0] and "버터플라이" in ex.warnings[0]
    ok = extract([page], "x.pdf"); check_part_type(ok, "체크 밸브")
    assert not ok.warnings


def test_seawater_prohibition_list_is_noted():
    page = "Valves covered by this certificate shall not be used in:\n Ship's side or bottom\n Seawater applications\n Collision bulkheads"
    assert any("Seawater" in n.text for n in extract([page], "x.pdf").notes)


def test_material_specific_seawater_sentence_is_not_a_blanket_prohibition():
    # 평가 중 발견한 오탐: 'shall not be used in direct contact with seawater'(스테인리스 한정)를 승인서 전체 해수 금지로 안내함
    page = "Austenitic stainless steels (e.g. CF8M, 316) are not seawater resistant and shall not be used in direct contact with seawater."
    assert not any("사용 불가로 명시된 승인서" in n.text for n in extract([page], "x.pdf").notes)


# ---- 사용 제한 조건(규칙 기반)
from app.extract_rules import _restriction_items


def _items(page):
    return _restriction_items([page])


def test_list_form_prohibition_items_and_following_paragraph_are_separated():
    page = ("Valves covered by this certificate shall not be used in:\n- Seawater applications\n- Ship's side or bottom and on sea chest\n"
            "These valves may be used for bilge suction only when fitted in connection with a non-return valve.")
    rs = _items(page)
    assert [(r.kind, r.contexts) for r in rs[:2]] == [("PROHIBITED", ["seawater"]), ("PROHIBITED", ["shipside"])]
    assert rs[2].kind == "CONDITIONAL" and rs[2].contexts == ["bilge"]


def test_wrapped_list_item_is_joined():
    page = "Valves shall not be used in:\n\uf0b7 Ballast lines to forward tanks through\ncargo oil tanks\n\uf0b7 Collision bulkheads\n"
    rs = _items(page)
    assert rs[0].quote == "Ballast lines to forward tanks through cargo oil tanks" and rs[1].contexts == ["collision_bulkhead"]


def test_material_scope_from_list_header():
    page = "1. Grey Cast Iron valves are not permitted to be fitted on:-\n• Ship’s side, bottom and sea chest;\n"
    r = _items(page)[0]
    assert r.materials == ["CAST_IRON"] and r.contexts == ["shipside"] and r.kind == "PROHIBITED"


def test_conditioned_prohibition_is_never_a_blanket_block():
    # 실제 평가에서 발견: '여객선의 빌지 계통 사용 불가'를 빌지 전체 금지로 오인하던 오류
    r = _items("Application in bilge system of passengerships is not allowed.")[0]
    assert r.kind == "PROHIBITED" and r.scope_other, "선종 조건이 붙은 금지는 적용 조건으로 표시돼야 한다"
    assert _items("Ballast lines to forward tanks through cargo oil tanks are not permitted.")[0].scope_other
    assert _items("EPDM and HYPALON shall not be used for hydrocarbon services.")[0].scope_other


def test_when_clause_is_conditional_not_prohibited():
    r = _items("When used as shipside valves the disc must not extend outside the hull plating in open position.")[0]
    assert r.kind == "CONDITIONAL" and r.contexts == ["shipside"]


def test_low_fire_risk_is_not_a_fire_safe_system():
    assert _items("Class I and II piping systems, except in hydraulic piping where failure would introduce a fire risk shall not be used.") == []


def test_abbreviations_do_not_split_sentences():
    r = _items("Austenitic stainless steels (e.g. CF8M, 316) covered by this certificate are not seawater resistant and shall not be used in direct contact with seawater.")
    assert len(r) == 1 and r[0].materials and r[0].contexts == ["seawater"]


def test_real_certificate_seawater_restriction_is_found():
    from pathlib import Path as P
    from app.pdf import read_pages as rp
    doc = P(__file__).parent.parent / "data" / "docs" / "DNV_TAP00000MH_UnicomValve.pdf"
    rs = _restriction_items(rp(doc))
    sea = next(r for r in rs if r.contexts == ["seawater"])
    assert sea.kind == "PROHIBITED" and set(sea.materials) >= {"CF8", "CF8M"} and sea.page == 2 and not sea.scope_other


def test_continuation_page_with_repeated_title_does_not_warn_when_certificate_found():
    p1 = "TYPE APPROVAL CERTIFICATE\nCertificate No:\nTAP1234E\nDNV\nThis Certificate is valid until 2027-01-01."
    p2 = "TYPE APPROVAL CERTIFICATE - Application / Limitation\nCertificate No: TAP1234E"
    assert not extract([p1, p2], "x.pdf").warnings
    assert extract([p2], "x.pdf").warnings          # 인증서 정보를 하나도 못 찾았다면 경고
