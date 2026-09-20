"""Claude 기반 추출기 (구조화 출력).

LLM 결과는 그대로 신뢰하지 않는다. 항목마다 원문 인용(quote)을 받아 실제 페이지 텍스트에 있는지
검증하고, 없으면 환각으로 보고 버린다. 규칙 추출기와 값이 다르면 경고로 남긴다.
"""
import base64
import os
import re
from pathlib import Path
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

from .extract_types import Extraction
from .labels import label
from .contexts import CONTEXTS
from .models import Cert, Restriction, Spec

MODEL = os.environ.get("MARINE_LLM_MODEL", "claude-opus-5")

Field = Literal["nominal_diameter", "design_pressure", "body_material", "flange_standard", "temp_max", "actuator_type"]

SYSTEM = """You extract technical specifications of marine valves from manufacturer datasheets and class-society type approval certificates.

Rules:
- Extract ONLY values that are explicitly stated in the document. Never infer, estimate, or use outside knowledge. If a value is not stated, omit it.
- Every item needs `page` (1-based, from the === PAGE n === markers) and `quote`: a short passage copied VERBATIM from that page that supports the value.
- Do not treat conditions or thresholds (e.g. "certificates are required for design pressure >= 16 bar") as product specifications.
- Canonical values:
  * nominal_diameter: millimetres as a number ("200"), or a range "50-600" for an approved size range.
  * design_pressure: ONLY when the document explicitly states a design or working pressure value for the product; bar as a number, convert MPa (x10) and kgf/cm2 (x0.98). NEVER derive it from PN, JIS K or ANSI/ASME class ratings: if only ratings are given, omit design_pressure.
  * body_material: pipe-separated codes from NAB, DI_RUBBER_LINED, DUCTILE_IRON, CAST_IRON, WCB, CF8, CF8M, SS304, SS316, DUPLEX_SS. Use UNKNOWN if the material is not one of these.
  * flange_standard: pipe-separated codes such as JIS_10K, JIS_16K, PN10, PN16, ASME_150.
  * temp_max: maximum service temperature in degC as a number; if it depends on seat material, use the lowest stated maximum and say so in `note`.
  * actuator_type: MANUAL_GEAR or PNEUMATIC.
- certs: one entry per type approval certificate: authority (DNV, ABS, KR, LR, NK, BV, CCS), certificate number, expiry date as YYYY-MM-DD.
- `display` is a short human-readable form of the value (e.g. "DN50 ~ DN600 (승인 범위)").

Usage restrictions (`restrictions`):
- Extract explicit limitations on where or how the product may be used, but ONLY those concerning one of these usage contexts:
  seawater, freshwater, ballast, bilge, fuel_oil, cargo_oil, lng_lpg, fire_safe (systems that require fire-safe/fire-resistant valves, fire mains), shipside (ship's side/bottom, sea chest, shell valves), collision_bulkhead, air (air piping), hydrocarbon (flammable liquids/oils). Ignore limitations about anything else.
- kind: PROHIBITED = the document says the product (or the named variant) must not be used/installed/fitted there, or the approval does not cover it. CONDITIONAL = allowed only under stated conditions. ADVISORY = a caution or recommendation.
  A plain permission or an application list without any condition (e.g. "may be used in sea water systems") is NOT a restriction: omit it.
- materials: body material codes (NAB, DI_RUBBER_LINED, DUCTILE_IRON, CAST_IRON, WCB, CF8, CF8M, SS304, SS316, DUPLEX_SS) if the restriction applies only to those materials (stainless steel -> CF8, CF8M, SS304, SS316, DUPLEX_SS; austenitic stainless / CF8M / 316 -> CF8, CF8M, SS304, SS316; grey cast iron -> CAST_IRON). Empty when it applies to the product as such.
- scope_other: when the restriction applies only to a particular configuration or situation that is NOT a body material (a seat or lining material, size, pressure or temperature threshold, ship type such as passenger ships, installation location such as inside tunnels or on tank walls, a particular valve type), describe it briefly in Korean. Use null only when the restriction applies to the whole product.
- Never turn a conditional, location-specific, ship-type-specific or threshold-specific prohibition into a blanket prohibition. If unsure, choose CONDITIONAL and explain in `note`.
- quote: a short contiguous passage copied VERBATIM from one page. For a bulleted list under a heading such as "shall not be used in:", quote the single list item (not the heading) and mention the heading in `note`.
- summary: one Korean sentence (about 60 characters or fewer) saying what is prohibited or required and where.
- note: brief Korean reasoning or uncertainty (optional)."""


class LLMSpec(BaseModel):
    field: Field
    value: str
    unit: str
    display: str
    page: int
    quote: str
    note: Optional[str] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None


class LLMCert(BaseModel):
    authority: str
    cert_no: str
    valid_until: str
    page: int
    quote: str


Context = Literal["seawater", "freshwater", "ballast", "bilge", "fuel_oil", "cargo_oil", "lng_lpg", "fire_safe",
                  "shipside", "collision_bulkhead", "air", "hydrocarbon"]
assert list(Context.__args__) == CONTEXTS, "contexts.CONTEXTS 와 LLM 스키마의 어휘가 다릅니다"
MATERIAL_CODES = {"NAB", "DI_RUBBER_LINED", "DUCTILE_IRON", "CAST_IRON", "WCB", "CF8", "CF8M", "SS304", "SS316", "DUPLEX_SS"}


class LLMRestriction(BaseModel):
    kind: Literal["PROHIBITED", "CONDITIONAL", "ADVISORY"]
    contexts: list[Context]
    materials: list[str]
    scope_other: Optional[str] = None
    summary: str
    quote: str
    page: int
    note: Optional[str] = None


class LLMResult(BaseModel):
    specs: list[LLMSpec]
    certs: list[LLMCert]
    restrictions: list[LLMRestriction] = []


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _has(page_text: str, quote: str) -> bool:
    return bool(quote.strip()) and _flat(quote) in _flat(page_text)


def _content(pages: list[str], pdf_path: Optional[Path]) -> list[dict]:
    blocks: list[dict] = []
    if not any(p.strip() for p in pages) and pdf_path:  # 스캔본: PDF 자체를 모델에 전달
        data = base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")
        blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}})
        blocks.append({"type": "text", "text": "Extract the specifications and certificates from this scanned document."})
        return blocks
    text = "\n\n".join(f"=== PAGE {i} ===\n{t}" for i, t in enumerate(pages, 1))
    blocks.append({"type": "text", "text": f"Document text:\n\n{text}\n\nExtract the specifications and certificates."})
    return blocks


def build_extraction(out: LLMResult, pages: list[str], file: str, method: str, model: str) -> Extraction:
    """LLM 출력을 검증해 Extraction 으로 변환한다 (API·CLI 공통). 원문에서 확인되지 않는 항목은 버린다."""
    verifiable = any(p.strip() for p in pages)
    warnings: list[str] = []
    if not verifiable:
        warnings.append("스캔 PDF라 원문 인용 검증을 할 수 없습니다. 모든 값을 담당자가 원본과 대조해야 합니다.")

    specs: list[Spec] = []
    for s in out.specs:
        ok_page = 1 <= s.page <= len(pages)
        if verifiable and not (ok_page and _has(pages[s.page - 1], s.quote)):
            warnings.append(f"원문에서 인용을 확인하지 못해 제외: {s.field}={s.value} (p.{s.page})")
            continue
        if s.value.strip().upper() == "UNKNOWN":
            warnings.append(f"{s.field} 값을 분류하지 못했습니다. 담당자 확인 필요 (p.{s.page})")
        rmin, rmax = s.range_min, s.range_max
        rng = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[-~–]\s*(\d+(?:\.\d+)?)\s*", s.value)
        if s.field == "nominal_diameter" and rng and rmin is None and rmax is None:
            rmin, rmax = float(rng[1]), float(rng[2])   # 모델이 범위를 값 문자열로만 준 경우 정규화
        specs.append(Spec(field=s.field, value=s.value, unit=s.unit, raw=s.quote.strip()[:200], file=file, page=s.page,
                          display=s.display or (label(s.value) if "|" not in s.value else None), note=s.note,
                          rangeMin=rmin, rangeMax=rmax, extractedBy=method, confirmed=False))
    certs: list[Cert] = []
    for c in out.certs:
        ok_page = 1 <= c.page <= len(pages)
        if verifiable and not (ok_page and _has(pages[c.page - 1], c.cert_no)):
            warnings.append(f"인증서 번호를 원문에서 확인하지 못해 제외: {c.cert_no} (p.{c.page})")
            continue
        certs.append(Cert(authority=c.authority, certNo=c.cert_no, validUntil=c.valid_until, file=file, page=c.page,
                          extractedBy=method, confirmed=False))
    rests: list[Restriction] = []
    for r in out.restrictions:
        ok_page = 1 <= r.page <= len(pages)
        if verifiable and not (ok_page and _has(pages[r.page - 1], r.quote)):
            warnings.append(f"사용 제한의 원문 인용을 확인하지 못해 제외: “{r.quote[:50]}” (p.{r.page})")
            continue
        mats = [m for m in r.materials if m in MATERIAL_CODES]
        if len(mats) != len(r.materials):
            warnings.append(f"사용 제한의 재질 코드 일부를 인식하지 못해 뺐습니다: {sorted(set(r.materials) - MATERIAL_CODES)} (p.{r.page})")
        rests.append(Restriction(kind=r.kind, contexts=list(r.contexts), materials=mats, scope_other=(r.scope_other or None),
                                 summary=r.summary, quote=r.quote.strip()[:300], file=file, page=r.page, note=r.note,
                                 extractedBy=method, confirmed=False))
    return Extraction(file=file, method=method, pageCount=len(pages), specs=specs, certs=certs,
                      restrictions=rests, warnings=warnings, model=model)


def extract(pages: list[str], file: str, client: Optional[anthropic.Anthropic] = None,
            pdf_path: Optional[Path] = None) -> Extraction:
    client = client or anthropic.Anthropic()
    resp = client.messages.parse(
        model=MODEL, max_tokens=16000, system=SYSTEM,
        messages=[{"role": "user", "content": _content(pages, pdf_path)}],
        output_format=LLMResult,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("모델이 요청을 거절했습니다(refusal)")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise RuntimeError("모델 응답이 잘렸거나 형식을 만족하지 못했습니다")
    return build_extraction(resp.parsed_output, pages, file, "llm", MODEL)
