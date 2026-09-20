import re
import shutil
import uuid
from pathlib import Path
from typing import Literal, Optional

from datetime import date

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import extract as extractor
from .contexts import CONTEXT_LABEL, SYSTEM_CONTEXTS, contexts_of
from . import security
from .db import DATA, STATE, Store, derive_requirements
from .engine import evaluate
from .extract_llm import MODEL
from .extract_types import Extraction
from .models import Cert, Product, Project, Requirement, Restriction, Spec

import json

DOCS, UPLOADS, SAMPLES = DATA / "docs", STATE / "uploads", DATA / "samples"
UPLOADS.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 20 * 1024 * 1024
PART_TYPES = ["버터플라이 밸브", "게이트 밸브", "글로브 밸브", "체크 밸브"]   # 같은 요구조건 항목(구경·압력·재질·플랜지·인증·온도·납기)을 쓰는 밸브 계열
app = FastAPI(title="SpecBridge API")
security.install(app)
store = Store()
SEED = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
DEFAULT_REQS = [Requirement(**r) for r in SEED["requirements"]]


def _files() -> list[str]:
    return sorted({p.name for d in (DOCS, UPLOADS, SAMPLES) for p in d.glob("*.pdf")})


def _need(pid: str) -> Product:
    p = store.product(pid)
    if not p:
        raise HTTPException(404, f"제품 {pid}를 찾을 수 없습니다")
    return p


@app.get("/api/bootstrap")
def bootstrap():
    return {
        "projects": store.projects(), "requirementsByProject": store.all_requirements(), "products": store.products(),
        "partTypes": PART_TYPES, "contexts": CONTEXT_LABEL, "systemContexts": SYSTEM_CONTEXTS, "docs": _files(), "samples": sorted(p.name for p in SAMPLES.glob("*.pdf")),
        "llm": {"available": extractor.llm_available(), "model": MODEL, "cli": extractor.cli_available()},
    }


CLASS_SOCIETIES = ["DNV", "KR", "ABS", "LR", "NK", "BV"]


class ProjectIn(BaseModel):
    ship_name: str
    class_society: str
    system: str
    need_by_date: str
    part_type: str = "버터플라이 밸브"
    replace_model: str = ""
    replace_reason: str = "납품 지연"
    ship_type: str = ""
    hull_no: str = ""
    copy_from: Optional[str] = None
    also_accept: list[str] = []          # 주 선급 외에 추가로 인정하는 선급


@app.post("/api/projects")
def create_project(body: ProjectIn):
    if not body.ship_name.strip():
        raise HTTPException(422, "선박명을 입력하세요")
    if body.class_society not in CLASS_SOCIETIES:
        raise HTTPException(422, f"적용 선급은 {', '.join(CLASS_SOCIETIES)} 중 하나여야 합니다")
    try:
        need = date.fromisoformat(body.need_by_date)
    except ValueError:
        raise HTTPException(422, "필요 납기일을 YYYY-MM-DD 형식으로 입력하세요")
    if need <= date.today():
        raise HTTPException(422, "필요 납기일은 오늘 이후여야 합니다")
    if body.part_type not in PART_TYPES:
        raise HTTPException(422, f"교체 대상 기자재는 {', '.join(PART_TYPES)} 중 하나여야 합니다")
    if any(c not in CLASS_SOCIETIES for c in body.also_accept):
        raise HTTPException(422, f"인정 선급은 {', '.join(CLASS_SOCIETIES)} 중에서 고르세요")
    base = store.requirements(body.copy_from or "P001")
    if base is None:
        raise HTTPException(404, f"복제할 선박 {body.copy_from}를 찾을 수 없습니다")
    p = Project(project_id="", ship_name=body.ship_name.strip(), class_society=body.class_society, system=body.system.strip() or "해수 냉각",
                part_type=body.part_type, need_by_date=body.need_by_date, ship_type=body.ship_type.strip(), hull_no=body.hull_no.strip(),
                replace_model=body.replace_model.strip() or "기존 모델 미입력", replace_reason=body.replace_reason.strip() or "납품 지연")
    created = store.add_project(p, derive_requirements(base, body.class_society, body.need_by_date, also_accept=body.also_accept))
    return {"project": created, "requirements": store.requirements(created.project_id)}


@app.put("/api/projects/{pid}/requirements")
def save_requirements(pid: str, body: list[Requirement]):
    if store.requirements(pid) is None:
        raise HTTPException(404, f"선박 {pid}를 찾을 수 없습니다")
    store.set_requirements(pid, body)
    return {"ok": True}


class ProjectPatch(BaseModel):
    part_type: Optional[str] = None
    replace_model: Optional[str] = None
    replace_reason: Optional[str] = None


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, body: ProjectPatch):
    if body.part_type is not None and body.part_type not in PART_TYPES:
        raise HTTPException(422, f"교체 대상 기자재는 {', '.join(PART_TYPES)} 중 하나여야 합니다")
    p = store.update_project(pid, part_type=body.part_type,
                             replace_model=body.replace_model.strip() if body.replace_model is not None else None,
                             replace_reason=body.replace_reason.strip() if body.replace_reason is not None else None)
    if not p:
        raise HTTPException(404, f"선박 {pid}를 찾을 수 없습니다")
    return p


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    r = store.delete_project(pid)
    if r == "missing":
        raise HTTPException(404, "존재하지 않는 선박입니다")
    if r == "last":
        raise HTTPException(409, "마지막 선박은 삭제할 수 없습니다. 새 선박을 먼저 등록하세요.")
    return {"ok": True}


class EvalIn(BaseModel):
    requirements: list[Requirement]
    system: Optional[str] = None        # 선박의 사용 계통. 주어지면 문서의 사용 제한 조건도 대조한다


@app.post("/api/evaluate")
def evaluate_all(body: EvalIn):
    ctx = contexts_of(body.system) if body.system is not None else None
    return {"evaluations": {p.id: evaluate(p, body.requirements, contexts=ctx) for p in store.products()}}


@app.get("/api/metrics")
def metrics():
    rows = []
    for p in store.products():
        if p.expected:
            rows.append((p, evaluate(p, DEFAULT_REQS)))
    false_pass = sum(1 for p, e in rows if p.expected == "EXCLUDED" and e.overall == "MATCH")
    false_excl = sum(1 for p, e in rows if p.expected != "EXCLUDED" and e.overall == "EXCLUDED")
    chk = [(p, e) for p, e in rows if p.expected == "CHECK"]
    judged = [i for _, e in rows for i in e.items if i.status != "UNKNOWN"]
    return {
        "total": len(rows), "agree": sum(1 for p, e in rows if p.expected == e.overall),
        "falsePass": false_pass, "falseExcluded": false_excl,
        "excludedCount": sum(1 for p, _ in rows if p.expected == "EXCLUDED"),
        "checkOk": sum(1 for _, e in chk if e.overall == "CHECK"), "checkTotal": len(chk),
        "judged": len(judged), "linked": sum(1 for i in judged if i.evidence),
        "rows": [{"id": p.id, "model": p.model, "scenario": p.scenario, "expected": p.expected, "actual": e.overall,
                  "real": p.real is not None} for p, e in rows],
    }


class ProductIn(BaseModel):
    manufacturer: str
    model: str
    part_type: str = "버터플라이 밸브"


@app.post("/api/products")
def create_product(body: ProductIn):
    if not body.manufacturer.strip() or not body.model.strip():
        raise HTTPException(422, "제조사와 모델명을 입력하세요")
    if body.part_type not in PART_TYPES:
        raise HTTPException(422, f"부품 종류는 {', '.join(PART_TYPES)} 중 하나여야 합니다")
    return store.add_product(body.manufacturer.strip(), body.model.strip(), body.part_type)


def _cleanup_uploads(files: list[str]) -> None:
    """삭제된 제품이 참조하던 업로드 파일 중 다른 제품이 쓰지 않는 것만 지운다(시드 문서·샘플은 건드리지 않는다)."""
    still = store.referenced_files()
    for f in files:
        path = UPLOADS / Path(f).name
        if f not in still and path.is_file():
            path.unlink()


@app.delete("/api/products/{pid}")
def delete_product(pid: str):
    _need(pid)
    _cleanup_uploads(store.delete_product(pid))
    return {"ok": True}


@app.delete("/api/products/{pid}/specs/{field}")
def delete_spec(pid: str, field: str, who: str = "담당자"):
    _need(pid)
    if not store.delete_spec(pid, field, who):
        raise HTTPException(404, "해당 사양이 없습니다")
    return store.product(pid)


@app.delete("/api/products/{pid}/restrictions/{key}")
def delete_restriction(pid: str, key: str, who: str = "담당자"):
    _need(pid)
    if not store.delete_restriction(pid, key, who):
        raise HTTPException(404, "해당 사용 제한이 없습니다")
    return store.product(pid)


@app.delete("/api/products/{pid}/certs/{cert_no:path}")
def delete_cert(pid: str, cert_no: str, who: str = "담당자"):
    _need(pid)
    if not store.delete_cert(pid, cert_no, who):
        raise HTTPException(404, "해당 인증서가 없습니다")
    return store.product(pid)


class LeadIn(BaseModel):
    days: Optional[int] = None
    source: str = "공급사 회신"
    who: str = "담당자"


@app.post("/api/products/{pid}/lead-time")
def set_lead_time(pid: str, body: LeadIn):
    _need(pid)
    store.set_lead_time(pid, body.days, body.source, body.who)
    return store.product(pid)


def _run(path: Path, name: str, mode: str, part_type: str) -> Extraction:
    ex = extractor.run(path, name, mode)  # type: ignore[arg-type]
    extractor.check_part_type(ex, part_type)
    return ex


@app.post("/api/products/{pid}/documents")
def upload_document(pid: str, file: UploadFile = File(...), mode: Literal["auto", "llm", "cli", "rules"] = "auto"):
    product = _need(pid)
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "파일은 20MB 이하만 올릴 수 있습니다")
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "PDF 파일만 업로드할 수 있습니다")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or "document.pdf").stem)[:60] or "document"
    name = f"{uuid.uuid4().hex[:8]}_{safe}.pdf"
    path = UPLOADS / name
    path.write_bytes(data)
    try:
        return _run(path, name, mode, product.partType)
    except Exception as e:  # 손상된 PDF 등
        path.unlink(missing_ok=True)
        raise HTTPException(422, f"PDF를 읽을 수 없습니다: {e}")


@app.post("/api/products/{pid}/documents/sample")
def use_sample(pid: str, name: str = Body(..., embed=True), mode: Literal["auto", "llm", "cli", "rules"] = "auto"):
    product = _need(pid)
    src = SAMPLES / Path(name).name
    if not src.exists():
        raise HTTPException(404, "샘플 문서를 찾을 수 없습니다")
    dst = UPLOADS / f"{uuid.uuid4().hex[:8]}_{src.name}"
    shutil.copyfile(src, dst)
    return _run(dst, dst.name, mode, product.partType)


class ConfirmIn(BaseModel):
    specs: list[Spec] = []
    certs: list[Cert] = []
    restrictions: list[Restriction] = []
    confirmedBy: str = "담당자"


@app.post("/api/products/{pid}/confirm")
def confirm(pid: str, body: ConfirmIn):
    _need(pid)
    known = set(_files())
    for x in [*body.specs, *body.certs, *body.restrictions]:
        if x.file not in known:
            raise HTTPException(422, f"등록되지 않은 문서입니다: {x.file}")
    if not (body.specs or body.certs or body.restrictions):
        raise HTTPException(422, "확정할 항목이 없습니다")
    return store.confirm(pid, body.specs, body.certs, body.confirmedBy.strip() or "담당자", body.restrictions)


@app.get("/api/audit")
def audit(product_id: Optional[str] = None):
    return store.audit_log(product_id)


@app.post("/api/reset")
def reset():
    store.seed()
    for p in UPLOADS.glob("*.pdf"):
        p.unlink()
    return {"ok": True}


@app.get("/api/docs/{name}")
def get_doc(name: str):
    for d in (DOCS, UPLOADS, SAMPLES):
        p = d / Path(name).name
        if p.is_file() and p.suffix == ".pdf":
            return FileResponse(p, media_type="application/pdf")
    raise HTTPException(404, "문서를 찾을 수 없습니다")


@app.get("/healthz")
def healthz():
    return {"ok": True}


# 운영 배포: 빌드된 프론트엔드를 같은 서버에서 제공한다(같은 도메인이라 CORS·프록시가 필요 없다). 반드시 모든 API 라우트 뒤에 마운트한다.
_static = Path(__import__("os").environ.get("MARINE_STATIC_DIR", str(DATA.parent.parent / "dist")))
if _static.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_static, html=True), name="web")
