import json
from pathlib import Path

from app.engine import evaluate
from app.models import Product, Requirement

SEED = json.loads((Path(__file__).parent.parent / "data" / "seed.json").read_text(encoding="utf-8"))
REQS = [Requirement(**r) for r in SEED["requirements"]]
PRODUCTS = [Product(**p) for p in SEED["products"]]
TODAY = "2026-09-19"


def test_seed_matches_expected_for_every_product():
    for p in PRODUCTS:
        e = evaluate(p, REQS, TODAY)
        assert e.overall == p.expected, f"{p.id} {p.model}: {e.overall} != {p.expected}"


def test_no_false_pass_for_excluded():
    excluded = [p for p in PRODUCTS if p.expected == "EXCLUDED"]
    assert excluded
    assert all(evaluate(p, REQS, TODAY).overall != "MATCH" for p in excluded)


def test_missing_data_is_unknown_not_guessed():
    p = next(x for x in PRODUCTS if x.id == "V05")  # 인증 자료 없음
    e = evaluate(p, REQS, TODAY)
    assert e.overall == "CHECK"
    assert [i.req.field for i in e.unknown] == ["class_approval"]


def test_delivery_is_separate_from_technical_status():
    v03 = evaluate(next(x for x in PRODUCTS if x.id == "V03"), REQS, TODAY)
    assert v03.overall == "MATCH" and v03.delivery.status == "FAIL"
    v04 = evaluate(next(x for x in PRODUCTS if x.id == "V04"), REQS, TODAY)
    assert v04.overall == "MATCH" and v04.delivery.status == "UNKNOWN"


def test_expired_certificate_fails():
    e = evaluate(next(x for x in PRODUCTS if x.id == "V15"), REQS, TODAY)
    cert = next(i for i in e.items if i.req.field == "class_approval")
    assert cert.status == "FAIL" and "만료" in cert.reason


def test_certificate_valid_before_expiry_date():
    p = next(x for x in PRODUCTS if x.id == "V15").model_copy(deep=True)
    p.certs[0].validUntil = "2030-01-01"
    cert = next(i for i in evaluate(p, REQS, TODAY).items if i.req.field == "class_approval")
    assert cert.status == "PASS"


def test_range_spec_contains_requirement():
    e = evaluate(next(x for x in PRODUCTS if x.id == "V15"), REQS, TODAY)
    dia = next(i for i in e.items if i.req.field == "nominal_diameter")
    assert dia.status == "PASS"


def test_optional_requirement_does_not_exclude():
    e = evaluate(next(x for x in PRODUCTS if x.id == "V14"), REQS, TODAY)
    assert e.overall == "MATCH" and len(e.optionalMiss) == 1


def test_editing_requirement_changes_result():
    reqs = [r.model_copy(update={"value": "150"}) if r.field == "nominal_diameter" else r for r in REQS]
    v01 = evaluate(next(x for x in PRODUCTS if x.id == "V01"), reqs, TODAY)
    assert v01.overall == "EXCLUDED"


# ---- 다중 선급 허용
def _with_class(value):
    return [r.model_copy(update={"value": value}) if r.field == "class_approval" else r for r in REQS]


def _prod(certs):
    from app.models import Cert
    p = next(x for x in PRODUCTS if x.id == "V01").model_copy(deep=True)
    p.certs = [Cert(authority=a, certNo=f"N-{a}", validUntil=v, file="f.pdf", page=1) for a, v in certs]
    return p


def _cert_item(p, value):
    return next(i for i in evaluate(p, _with_class(value), TODAY).items if i.req.field == "class_approval")


def test_any_accepted_class_is_enough():
    p = _prod([("KR", "2030-01-01")])
    assert _cert_item(p, "DNV").status == "FAIL"
    it = _cert_item(p, "DNV|KR")
    assert it.status == "PASS" and it.actual == "KR 보유" and "인정 선급: DNV / KR" in it.reason


def test_expired_accepted_class_is_covered_by_valid_other():
    p = _prod([("DNV", "2021-06-30"), ("KR", "2030-01-01")])
    assert _cert_item(p, "DNV").status == "FAIL"           # DNV만 요구하면 만료로 미충족
    assert _cert_item(p, "DNV|KR").status == "PASS"        # KR 유효 → 충족


def test_all_accepted_classes_expired_fails_with_expiry_reason():
    p = _prod([("DNV", "2021-06-30"), ("KR", "2022-01-01")])
    it = _cert_item(p, "DNV|KR")
    assert it.status == "FAIL" and "만료" in it.reason and it.actual.startswith("KR 만료")   # 가장 늦게 만료된 것을 근거로


def test_class_not_in_accepted_list_fails_and_lists_holdings():
    it = _cert_item(_prod([("ABS", "2030-01-01")]), "DNV|KR")
    assert it.status == "FAIL" and "DNV / KR" in it.reason and "ABS" in it.reason


def test_preferred_class_first_and_both_valid_noted():
    it = _cert_item(_prod([("KR", "2030-01-01"), ("DNV", "2030-01-01")]), "DNV|KR")
    assert it.actual == "DNV 보유" and "KR도 유효" in it.reason


def test_single_class_behaviour_unchanged():
    assert _cert_item(_prod([("DNV", "2030-01-01")]), "DNV").status == "PASS"


# ---- 사용 제한 조건(문서 기반) 판정
from app.models import Restriction


def _rp(restrictions, materials="NAB"):
    p = next(x for x in PRODUCTS if x.id == "V01").model_copy(deep=True)
    for s in p.specs:
        if s.field == "body_material":
            s.value = materials
    p.restrictions = restrictions
    return p


def _r(kind="PROHIBITED", contexts=("seawater",), materials=(), scope_other=None, summary="해수 사용 불가"):
    return Restriction(kind=kind, contexts=list(contexts), materials=list(materials), scope_other=scope_other,
                       summary=summary, quote="Seawater applications", file="c.pdf", page=2, extractedBy="cli",
                       confirmedBy="홍", confirmedAt="2026-09-20T10:00:00+09:00")


def _rx(p, contexts):
    e = evaluate(p, REQS, TODAY, contexts=contexts)
    return e, next(i for i in e.items if i.req.field == "usage_restriction")


def test_restriction_not_evaluated_without_contexts():
    e = evaluate(_rp([_r()]), REQS, TODAY)
    assert all(i.req.field != "usage_restriction" for i in e.items) and e.overall == "MATCH"


def test_blanket_prohibition_matching_ship_system_excludes():
    e, it = _rx(_rp([_r()]), ["seawater"])
    assert e.overall == "EXCLUDED" and it.status == "FAIL" and it.actual == "사용 불가 1건"
    assert it.evidence.raw == "Seawater applications" and it.evidence.confirmedBy == "홍"
    assert e.restrictions[0].level == "BLOCK" and "해수" in e.restrictions[0].reason


def test_prohibition_for_other_system_is_irrelevant():
    e, it = _rx(_rp([_r()]), ["freshwater"])
    assert e.overall == "MATCH" and it.status == "PASS" and it.actual == "해당 제한 없음"


def test_material_scoped_prohibition_only_hits_matching_material():
    # 종합 판정은 재질 허용 목록 등 다른 조건과 섞이므로 '사용 제한' 항목 자체를 본다
    stainless = _r(materials=["CF8", "CF8M"])
    e, it = _rx(_rp([stainless], "NAB"), ["seawater"])
    assert it.status == "PASS" and it.actual == "해당 제한 없음" and not e.restrictions          # 다른 재질 → 무관
    e, it = _rx(_rp([stainless], "CF8M"), ["seawater"])
    assert it.status == "FAIL" and e.restrictions[0].level == "BLOCK"                            # 전부 대상 → 제외
    e, it = _rx(_rp([stainless], "WCB|CF8M"), ["seawater"])                                      # 일부만 대상 → 주의
    assert it.status == "PASS" and it.actual == "주의 1건" and e.restrictions[0].level == "CAUTION"


def test_material_scoped_prohibition_with_unknown_material_is_caution_not_block():
    p = _rp([_r(materials=["CF8"])])
    p.specs = [s for s in p.specs if s.field != "body_material"]
    e, it = _rx(p, ["seawater"])
    assert e.restrictions[0].level == "CAUTION" and it.status == "PASS"      # 재질을 모르면 차단하지 않고 주의


def test_scope_other_downgrades_prohibition_to_caution():
    e, it = _rx(_rp([_r(scope_other="시트 재질 EPDM·HYPALON")]), ["seawater"])
    assert e.overall == "MATCH" and e.restrictions[0].level == "CAUTION" and "시트 재질" in e.restrictions[0].reason


def test_conditional_and_advisory_never_exclude():
    for kind in ("CONDITIONAL", "ADVISORY"):
        e, it = _rx(_rp([_r(kind=kind, contexts=["seawater"])]), ["seawater"])
        assert e.overall == "MATCH" and it.status == "PASS" and e.restrictions[0].level == "CAUTION"


def test_no_analysed_restrictions_is_unknown_but_does_not_change_overall():
    e, it = _rx(_rp([]), ["seawater"])
    assert it.status == "UNKNOWN" and it.actual == "문서 미분석" and not it.req.mandatory
    assert e.overall == "MATCH" and e.optionalMiss == []          # '선택조건 미달'로 세지 않는다


def test_ballast_ship_covers_seawater_restriction():
    from app.contexts import contexts_of
    assert _rx(_rp([_r()]), contexts_of("밸러스트"))[0].overall == "EXCLUDED"
    assert _rx(_rp([_r(contexts=["lng_lpg"])]), contexts_of("해수 냉각"))[0].overall == "MATCH"
