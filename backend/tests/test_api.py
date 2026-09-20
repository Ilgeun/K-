import importlib
import shutil

import pytest
from fastapi.testclient import TestClient

SAMPLE = "SYNTHETIC_OF-BF200-X_DNV_certificate.pdf"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.db as db
    monkeypatch.setattr(db, "DATA", db.DATA)  # 실제 데이터 폴더의 PDF를 쓰되 DB는 임시 파일
    real_store = db.Store
    monkeypatch.setattr(db, "Store", lambda path=tmp_path / "t.db": real_store(path))
    import app.main as main
    main = importlib.reload(main)
    # 테스트는 절대 실제 Claude(API·CLI)를 호출하지 않고, 실제 업로드 폴더(개발 서버와 공유)도 건드리지 않는다
    monkeypatch.setattr(main.extractor, "cli_available", lambda: False)
    monkeypatch.setattr(main.extractor, "llm_available", lambda: False)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(main, "UPLOADS", uploads)
    yield TestClient(main.app), main


def test_bootstrap_and_evaluate(client):
    c, main = client
    b = c.get("/api/bootstrap").json()
    assert len(b["products"]) == 15 and b["samples"]
    ev = c.post("/api/evaluate", json={"requirements": b["requirementsByProject"]["P001"]}).json()["evaluations"]
    assert ev["V01"]["overall"] == "MATCH" and ev["V15"]["overall"] == "EXCLUDED"


def test_metrics_all_agree(client):
    c, _ = client
    m = c.get("/api/metrics").json()
    assert m["falsePass"] == 0 and m["falseExcluded"] == 0 and m["agree"] == m["total"] == 15


def test_upload_extract_confirm_reevaluate(client):
    c, _ = client
    # V05: 인증 자료 없음 → 확인 필요
    ex = c.post("/api/products/V05/documents/sample", params={"mode": "rules"}, json={"name": SAMPLE}).json()
    assert ex["method"] == "rules" and ex["certs"][0]["certNo"] == "SYN-DNV-0501"
    assert ex["certs"][0]["confirmed"] is False
    reqs = c.get("/api/bootstrap").json()["requirementsByProject"]["P001"]
    before = c.post("/api/evaluate", json={"requirements": reqs}).json()["evaluations"]["V05"]
    assert before["overall"] == "CHECK"          # 확정 전에는 판정에 반영되지 않는다
    r = c.post("/api/products/V05/confirm", json={"certs": ex["certs"], "confirmedBy": "홍길동"})
    assert r.status_code == 200
    after = c.post("/api/evaluate", json={"requirements": reqs}).json()["evaluations"]["V05"]
    assert after["overall"] == "MATCH"
    cert = next(i for i in after["items"] if i["req"]["field"] == "class_approval")
    assert cert["evidence"]["confirmedBy"] == "홍길동" and cert["evidence"]["extractedBy"] == "rules"
    log = c.get("/api/audit", params={"product_id": "V05"}).json()
    assert log and log[0]["action"] == "confirm_cert" and log[0]["who"] == "홍길동"


def test_upload_rejects_non_pdf(client):
    c, _ = client
    r = c.post("/api/products/V05/documents", files={"file": ("a.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 415


def test_confirm_rejects_unknown_file(client):
    c, _ = client
    bad = {"certs": [{"authority": "DNV", "certNo": "X1", "validUntil": "2030-01-01", "file": "nope.pdf", "page": 1}]}
    assert c.post("/api/products/V05/confirm", json=bad).status_code == 422


def test_create_product_from_real_pdf_then_evaluate(client):
    c, main = client
    p = c.post("/api/products", json={"manufacturer": "Korea Unicomvalve", "model": "High-Seal (사용자 등록)"}).json()
    assert p["id"].startswith("U") and p["specs"] == []
    real = main.DOCS / "DNV_TAP00000MH_UnicomValve.pdf"
    r = c.post(f"/api/products/{p['id']}/documents", files={"file": (real.name, real.read_bytes(), "application/pdf")},
               params={"mode": "rules"}).json()
    assert r["certs"][0]["certNo"] == "TAP00000MH"
    c.post(f"/api/products/{p['id']}/confirm", json={"specs": r["specs"], "certs": r["certs"]})
    reqs = c.get("/api/bootstrap").json()["requirementsByProject"]["P001"]
    ev = c.post("/api/evaluate", json={"requirements": reqs}).json()["evaluations"][p["id"]]
    assert ev["overall"] == "EXCLUDED"           # 인증 만료 + 스테인리스 재질


def test_path_traversal_blocked(client):
    c, _ = client
    assert c.get("/api/docs/..%2F..%2Fseed.json").status_code == 404
    assert c.get("/api/docs/DNV_TAP00000MH_UnicomValve.pdf").status_code == 200


def test_reset_restores_seed(client):
    c, _ = client
    c.post("/api/products", json={"manufacturer": "A", "model": "B"})
    c.post("/api/reset")
    assert len(c.get("/api/bootstrap").json()["products"]) == 15


# ---- 선박(프로젝트) 관리
def _new_ship(c, **over):
    body = {"ship_name": "(테스트) 탱커 D호", "class_society": "ABS", "system": "해수 냉각", "need_by_date": "2999-01-01",
            "ship_type": "탱커", "hull_no": "H-9999", **over}
    return c.post("/api/projects", json=body)


def test_seed_has_two_ships_with_own_requirements(client):
    c, _ = client
    b = c.get("/api/bootstrap").json()
    assert [p["project_id"] for p in b["projects"]] == ["P001", "P002"]
    cls = {pid: next(r["value"] for r in rs if r["field"] == "class_approval") for pid, rs in b["requirementsByProject"].items()}
    assert cls == {"P001": "DNV", "P002": "KR"}
    assert b["partTypes"][0] == "버터플라이 밸브"


def test_different_class_society_changes_the_result(client):
    c, _ = client
    b = c.get("/api/bootstrap").json()
    r1 = c.post("/api/evaluate", json={"requirements": b["requirementsByProject"]["P001"]}).json()["evaluations"]
    r2 = c.post("/api/evaluate", json={"requirements": b["requirementsByProject"]["P002"]}).json()["evaluations"]
    assert r1["V01"]["overall"] == "MATCH" and r2["V01"]["overall"] == "EXCLUDED"   # DNV 인증만 있는 후보는 KR 선박에서 제외


def test_create_ship_copies_requirements_and_adjusts_class_and_lead_time(client):
    c, _ = client
    r = _new_ship(c)
    assert r.status_code == 200
    p, reqs = r.json()["project"], r.json()["requirements"]
    assert p["project_id"] == "S001" and p["is_synthetic"] == "false"
    assert next(x["value"] for x in reqs if x["field"] == "class_approval") == "ABS"
    assert int(next(x["value"] for x in reqs if x["field"] == "lead_time_days")) > 1000
    assert len(reqs) == 7
    assert any(p2["project_id"] == "S001" for p2 in c.get("/api/bootstrap").json()["projects"])


def test_create_ship_validation(client):
    c, _ = client
    assert _new_ship(c, ship_name="  ").status_code == 422
    assert _new_ship(c, class_society="XYZ").status_code == 422
    assert _new_ship(c, need_by_date="2020-01-01").status_code == 422
    assert _new_ship(c, need_by_date="내일").status_code == 422
    assert _new_ship(c, copy_from="P999").status_code == 404


def test_requirement_edits_are_saved_per_ship(client):
    c, _ = client
    pid = _new_ship(c).json()["project"]["project_id"]
    reqs = c.get("/api/bootstrap").json()["requirementsByProject"][pid]
    for r in reqs:
        if r["field"] == "nominal_diameter":
            r["value"] = "150"
    assert c.put(f"/api/projects/{pid}/requirements", json=reqs).status_code == 200
    got = c.get("/api/bootstrap").json()["requirementsByProject"]
    assert next(r["value"] for r in got[pid] if r["field"] == "nominal_diameter") == "150"
    assert next(r["value"] for r in got["P001"] if r["field"] == "nominal_diameter") == "200"   # 다른 선박은 그대로


def test_delete_any_ship_but_never_the_last_one(client):
    c, _ = client
    pid = _new_ship(c).json()["project"]["project_id"]
    assert c.delete(f"/api/projects/{pid}").status_code == 200
    assert c.delete("/api/projects/P001").status_code == 200          # 시연용 선박도 삭제 가능
    r = c.delete("/api/projects/P002")
    assert r.status_code == 409 and "마지막" in r.json()["detail"]     # 마지막 1척은 보호
    assert c.delete("/api/projects/NOPE").status_code == 404
    assert [p["project_id"] for p in c.get("/api/bootstrap").json()["projects"]] == ["P002"]


def test_reset_removes_user_ships(client):
    c, _ = client
    _new_ship(c)
    c.post("/api/reset")
    assert len(c.get("/api/bootstrap").json()["projects"]) == 2


def test_copy_from_another_ship(client):
    c, _ = client
    reqs = _new_ship(c, copy_from="P002", class_society="KR").json()["requirements"]
    assert next(r["value"] for r in reqs if r["field"] == "class_approval") == "KR"


# ---- 교체 대상 기자재(부품 종류·기존 모델·사유) 변경
def test_patch_replacement_part(client):
    c, _ = client
    r = c.patch("/api/projects/P001", json={"part_type": "체크 밸브", "replace_model": "B사 CV-200", "replace_reason": "단종"})
    assert r.status_code == 200
    p = next(x for x in c.get("/api/bootstrap").json()["projects"] if x["project_id"] == "P001")
    assert (p["part_type"], p["replace_model"], p["replace_reason"]) == ("체크 밸브", "B사 CV-200", "단종")
    assert c.patch("/api/projects/P001", json={"part_type": "펌프"}).status_code == 422
    assert c.patch("/api/projects/NOPE", json={"part_type": "체크 밸브"}).status_code == 404


def test_new_ship_with_part_type_and_replaced_model(client):
    c, _ = client
    p = _new_ship(c, part_type="게이트 밸브", replace_model="C사 GV-100", replace_reason="품질 이슈").json()["project"]
    assert (p["part_type"], p["replace_model"], p["replace_reason"]) == ("게이트 밸브", "C사 GV-100", "품질 이슈")
    assert _new_ship(c, part_type="펌프").status_code == 422


def test_products_carry_part_type(client):
    c, _ = client
    b = c.get("/api/bootstrap").json()
    assert all(p["partType"] == "버터플라이 밸브" for p in b["products"])
    p = c.post("/api/products", json={"manufacturer": "V", "model": "Series 716", "part_type": "체크 밸브"}).json()
    assert p["partType"] == "체크 밸브"
    assert c.post("/api/products", json={"manufacturer": "V", "model": "x", "part_type": "펌프"}).status_code == 422


def test_document_of_other_part_type_is_warned(client):
    # 체크 밸브 승인서 형식의 문서를 버터플라이 제품에 올리면 경고, 체크 밸브 제품에 올리면 경고 없음
    c, main = client
    import io
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); cv = canvas.Canvas(buf)
    for i, line in enumerate(["TYPE APPROVAL CERTIFICATE", "Certificate No:", "TAP000012E", "That the Check Valve", "with type designation(s)",
                              "Series 716", "DNV", "This Certificate is valid until 2027-07-12."]):
        cv.drawString(50, 800 - 20 * i, line)
    cv.save()
    files = {"file": ("cv.pdf", buf.getvalue(), "application/pdf")}
    bf = c.post("/api/products/V05/documents", files=files, params={"mode": "rules"}).json()
    assert "Check Valve" in bf["warnings"][0]
    cvp = c.post("/api/products", json={"manufacturer": "V", "model": "716", "part_type": "체크 밸브"}).json()["id"]
    ok = c.post(f"/api/products/{cvp}/documents", files={"file": ("cv.pdf", buf.getvalue(), "application/pdf")}, params={"mode": "rules"}).json()
    assert not any("Check Valve" in w for w in ok["warnings"])


# ---- 삭제: 제품·확정 자료
def test_delete_product_removes_it_and_orphan_uploads(client):
    c, main = client
    pid = c.post("/api/products", json={"manufacturer": "A", "model": "B"}).json()["id"]
    real = main.DOCS / "DNV_TAP00000MH_UnicomValve.pdf"
    ex = c.post(f"/api/products/{pid}/documents", files={"file": (real.name, real.read_bytes(), "application/pdf")}, params={"mode": "rules"}).json()
    c.post(f"/api/products/{pid}/confirm", json={"specs": ex["specs"], "certs": ex["certs"]})
    assert (main.UPLOADS / ex["file"]).exists()
    assert c.delete(f"/api/products/{pid}").status_code == 200
    assert not (main.UPLOADS / ex["file"]).exists()                  # 다른 제품이 안 쓰는 업로드 파일은 정리
    assert all(p["id"] != pid for p in c.get("/api/bootstrap").json()["products"])
    assert c.delete(f"/api/products/{pid}").status_code == 404


def test_delete_seed_product_keeps_shared_docs(client):
    c, main = client
    assert c.delete("/api/products/V15").status_code == 200
    assert (main.DOCS / "DNV_TAP00000MH_UnicomValve.pdf").exists()   # 시드 문서는 지우지 않는다
    m = c.get("/api/metrics").json()
    assert m["total"] == 14 and m["agree"] == 14


def test_delete_confirmed_spec_and_cert_reverts_judgement(client):
    c, _ = client
    ex = c.post("/api/products/V05/documents/sample", params={"mode": "rules"}, json={"name": SAMPLE}).json()
    c.post("/api/products/V05/confirm", json={"certs": ex["certs"], "confirmedBy": "홍길동"})
    reqs = c.get("/api/bootstrap").json()["requirementsByProject"]["P001"]
    ev = lambda: c.post("/api/evaluate", json={"requirements": reqs}).json()["evaluations"]["V05"]["overall"]
    assert ev() == "MATCH"
    assert c.delete("/api/products/V05/certs/SYN-DNV-0501", params={"who": "홍길동"}).status_code == 200
    assert ev() == "CHECK"                                            # 되돌리면 다시 '확인 필요'
    assert c.delete("/api/products/V05/specs/nominal_diameter").status_code == 200
    assert c.delete("/api/products/V05/specs/nominal_diameter").status_code == 404
    log = c.get("/api/audit", params={"product_id": "V05"}).json()
    assert any(x["action"] == "delete_cert" and x["who"] == "홍길동" for x in log)


def test_cert_number_with_slash_can_be_deleted(client):
    c, _ = client
    from app.models import Cert
    main = client[1]
    main.store.confirm("V05", [], [Cert(authority="LR", certNo="17/30005", validUntil="2030-01-01", file="DNV_TAP00000MH_UnicomValve.pdf", page=1)], "t")
    assert c.delete("/api/products/V05/certs/17/30005").status_code == 200


def test_create_ship_with_multiple_accepted_classes(client):
    c, _ = client
    r = _new_ship(c, class_society="DNV", also_accept=["KR", "DNV", "ABS"])
    assert r.status_code == 200
    reqs = r.json()["requirements"]
    assert next(x["value"] for x in reqs if x["field"] == "class_approval") == "DNV|KR|ABS"    # 중복 제거·주 선급 우선
    ev = c.post("/api/evaluate", json={"requirements": reqs}).json()["evaluations"]
    assert ev["V13"]["overall"] == "MATCH"        # KR·ABS 승인만 있는 후보도 KR/ABS 인정 시 충족
    assert ev["V01"]["overall"] == "MATCH"
    assert _new_ship(c, also_accept=["XYZ"]).status_code == 422


# ---- 사용 제한 조건(문서 기반)
REAL = "DNV_TAP00000MH_UnicomValve.pdf"
RESTRICTION = {"kind": "PROHIBITED", "contexts": ["seawater"], "materials": [], "summary": "해수 계통 사용 불가",
               "quote": "Seawater applications", "file": REAL, "page": 2}


def _eval(c, pid, system):
    reqs = c.get("/api/bootstrap").json()["requirementsByProject"]["P001"]
    return c.post("/api/evaluate", json={"requirements": reqs, "system": system}).json()["evaluations"][pid]


def test_bootstrap_exposes_contexts_and_seeded_restrictions(client):
    c, _ = client
    b = c.get("/api/bootstrap").json()
    assert b["contexts"]["seawater"] == "해수" and b["systemContexts"]["해수 냉각"] == ["seawater"]
    v15 = next(p for p in b["products"] if p["id"] == "V15")
    assert {r["kind"] for r in v15["restrictions"]} == {"PROHIBITED", "CONDITIONAL"} and all(r["key"] for r in v15["restrictions"])


def test_restriction_confirmed_then_applied_to_ship_system(client):
    c, _ = client
    assert _eval(c, "V01", "해수 냉각")["overall"] == "MATCH"
    r = c.post("/api/products/V01/confirm", json={"restrictions": [RESTRICTION], "confirmedBy": "홍길동"})
    assert r.status_code == 200
    ev = _eval(c, "V01", "해수 냉각")
    assert ev["overall"] == "EXCLUDED"                                         # 해수 계통 선박에서 제외
    rx = next(i for i in ev["items"] if i["req"]["field"] == "usage_restriction")
    assert rx["status"] == "FAIL" and rx["evidence"]["confirmedBy"] == "홍길동" and rx["evidence"]["raw"] == "Seawater applications"
    assert _eval(c, "V01", "청수 냉각")["overall"] == "MATCH"                    # 다른 계통은 무관
    assert _eval(c, "V01", None)["overall"] == "MATCH" and all(i["req"]["field"] != "usage_restriction" for i in _eval(c, "V01", None)["items"])
    log = c.get("/api/audit", params={"product_id": "V01"}).json()
    assert any(x["action"] == "confirm_restriction" and x["who"] == "홍길동" for x in log)


def test_delete_restriction_reverts(client):
    c, _ = client
    prod = c.post("/api/products/V01/confirm", json={"restrictions": [RESTRICTION]}).json()
    key = prod["restrictions"][0]["key"]
    assert c.delete(f"/api/products/V01/restrictions/{key}").status_code == 200
    assert _eval(c, "V01", "해수 냉각")["overall"] == "MATCH"
    assert c.delete(f"/api/products/V01/restrictions/{key}").status_code == 404


def test_confirm_restriction_rejects_unknown_file_and_unknown_context(client):
    c, _ = client
    assert c.post("/api/products/V01/confirm", json={"restrictions": [{**RESTRICTION, "file": "nope.pdf"}]}).status_code == 422


def test_rules_extraction_returns_restrictions_flagged_by_default(client):
    c, main = client
    real = main.DOCS / REAL
    ex = c.post("/api/products/V05/documents", files={"file": (real.name, real.read_bytes(), "application/pdf")}, params={"mode": "rules"}).json()
    assert ex["restrictions"] and all(f"restriction:{r['key']}" in ex["flagged"] for r in ex["restrictions"])   # 규칙 해석은 기본 선택 제외
    sea = next(r for r in ex["restrictions"] if r["contexts"] == ["seawater"])
    assert sea["kind"] == "PROHIBITED" and "CF8M" in sea["materials"] and sea["extractedBy"] == "rules" and sea["confirmed"] is False


def test_deleting_product_removes_its_restrictions(client):
    c, _ = client
    c.post("/api/products/V01/confirm", json={"restrictions": [RESTRICTION]})
    c.delete("/api/products/V01")
    import app.main as m
    assert m.store.conn.execute("SELECT COUNT(*) FROM restrictions WHERE product_id='V01'").fetchone()[0] == 0


def test_old_db_without_restrictions_is_migrated_with_seed_restrictions(tmp_path):
    import app.db as db
    s = db.Store(tmp_path / "old.db")
    s.conn.execute("DELETE FROM restrictions"); s.conn.commit()            # 사용 제한 기능이 없던 시절의 DB를 흉내
    s2 = db.Store(tmp_path / "old.db")
    assert len(s2.product("V15").restrictions) == 3
