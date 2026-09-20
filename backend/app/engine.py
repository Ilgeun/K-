"""요구조건 대조 엔진.

수치·단위·필수조건·인증 유효기간은 AI가 아니라 이 규칙으로 판정한다.
자료가 없으면 추측하지 않고 UNKNOWN 으로 남긴다.
"""
from datetime import date
from typing import Optional

from .contexts import CONTEXT_LABEL
from .labels import FIELD_LABEL, fmt_val, req_text
from .models import (Delivery, Evaluation, Evidence, Product, ReqResult, Requirement,
                     RestrictionFinding, Spec)

LEAD_FIELD = "lead_time_days"
RESTRICTION_FIELD = "usage_restriction"


def _ev(file: str, page: int, raw: str, by: Optional[str], who: Optional[str], at: Optional[str]) -> Evidence:
    return Evidence(file=file, page=page, raw=raw, extractedBy=by, confirmedBy=who, confirmedAt=at)


def _judge(req: Requirement, s: Spec) -> bool:
    v = s.value
    if req.op == "=":
        if s.rangeMin is not None and s.rangeMax is not None:
            return s.rangeMin <= float(req.value) <= s.rangeMax
        return req.value in v.split("|")
    if req.op == "gte":
        return float(v) >= float(req.value)
    if req.op == "lte":
        return float(v) <= float(req.value)
    if req.op == "in":
        allowed = req.value.split("|")
        return any(x in allowed for x in v.split("|"))
    return False


def _eval_cert(p: Product, req: Requirement, today: str) -> ReqResult:
    """요구 값은 인정하는 선급 목록('DNV' 또는 'DNV|KR'). 인정 선급 중 하나라도 유효한 형식승인이 있으면 충족."""
    name = FIELD_LABEL["class_approval"]
    allowed = req.value.split("|")
    shown = " / ".join(allowed)
    if not p.certs:
        return ReqResult(req=req, status="UNKNOWN", actual="자료 없음",
                         reason=f"{name} 자료가 등록되지 않았습니다. 인증서 요청이 필요합니다.")
    mine = [c for c in p.certs if c.authority in allowed]
    valid = [c for c in mine if c.validUntil >= today]
    if valid:
        c0 = min(valid, key=lambda c: allowed.index(c.authority))   # 인정 목록에서 앞선 선급 우선
        others = sorted({c.authority for c in valid} - {c0.authority})
        ev = _ev(c0.file, c0.page, f"{c0.authority} 형식승인 {c0.certNo} (유효 {c0.validUntil})", c0.extractedBy, c0.confirmedBy, c0.confirmedAt)
        extra = f" · {', '.join(others)}도 유효" if others else ""
        return ReqResult(req=req, status="PASS", actual=f"{c0.authority} 보유",
                         reason=f"{c0.authority} 형식승인 확인 ({c0.certNo}, 유효 {c0.validUntil}까지){extra}" + (f" — 인정 선급: {shown}" if len(allowed) > 1 else ""), evidence=ev)
    if mine:   # 인정 선급의 승인서는 있지만 모두 만료
        c0 = max(mine, key=lambda c: c.validUntil)
        ev = _ev(c0.file, c0.page, f"{c0.authority} 형식승인 {c0.certNo} (유효 {c0.validUntil})", c0.extractedBy, c0.confirmedBy, c0.confirmedAt)
        return ReqResult(req=req, status="FAIL", actual=f"{c0.authority} 만료 ({c0.validUntil})",
                         reason=f"{c0.authority} 형식승인서({c0.certNo})가 {c0.validUntil}에 만료되었습니다. 갱신본을 등록하면 재평가합니다.", evidence=ev)
    c0 = p.certs[0]
    held = ", ".join(sorted({c.authority for c in p.certs}))
    ev = _ev(c0.file, c0.page, f"{c0.authority} 형식승인 {c0.certNo} (유효 {c0.validUntil})", c0.extractedBy, c0.confirmedBy, c0.confirmedAt)
    return ReqResult(req=req, status="FAIL", actual=f"보유: {held}",
                     reason=f"인정 선급({shown}) 형식승인이 없습니다 (보유: {held}).", evidence=ev)


def _eval_req(p: Product, req: Requirement, today: str) -> ReqResult:
    if req.field == "class_approval":
        return _eval_cert(p, req, today)
    name = FIELD_LABEL.get(req.field, req.field)
    s = next((x for x in p.specs if x.field == req.field), None)
    if s is None:
        return ReqResult(req=req, status="UNKNOWN", actual="자료 없음", reason=f"{name} 사양이 문서에서 확인되지 않았습니다.")
    ok = _judge(req, s)
    actual = s.display or fmt_val(s.value, s.unit)
    rt = req_text(req.op, req.value, req.unit)
    reason = (f"{name} {actual} — 요구조건({rt}) 충족" if ok else
              f"{name} {actual} — 요구조건({rt})에 부합하지 않음" + (f" · {s.note}" if s.note else ""))
    return ReqResult(req=req, status="PASS" if ok else "FAIL", actual=actual, reason=reason,
                     evidence=_ev(s.file, s.page, s.raw, s.extractedBy, s.confirmedBy, s.confirmedAt))


def eval_delivery(p: Product, need: float) -> Delivery:
    if p.leadTime is None:
        return Delivery(status="UNKNOWN", days=None, need=need, reason="공급사 확인 필요", source="정보 없음")
    ok = p.leadTime <= need
    reason = (f"납기 {p.leadTime}일 (필요 {need:g}일 이내)" if ok else
              f"납기 {p.leadTime}일 — 필요 납기 {need:g}일을 {p.leadTime - need:g}일 초과")
    return Delivery(status="PASS" if ok else "FAIL", days=p.leadTime, need=need, reason=reason,
                    source=f"{p.leadTimeSource} · {p.leadTimeCheckedAt} 확인")


def restriction_findings(p: Product, contexts: list[str]) -> list[RestrictionFinding]:
    """확정된 사용 제한을 이 선박의 사용 상황·이 제품의 재질에 규칙으로 대조한다.

    BLOCK(제외)은 '제품 전체에 대한 명확한 금지'일 때만. 특정 구성(시트·크기 등)에만 해당하거나 일부 재질에만 해당하거나
    조건부·주의 사항은 CAUTION 으로 표시하고 제외하지 않는다.
    """
    body = next((sp for sp in p.specs if sp.field == "body_material"), None)
    mats = set(body.value.split("|")) - {"UNKNOWN"} if body else set()
    out: list[RestrictionFinding] = []
    for r in p.restrictions:
        hit = [c for c in r.contexts if c in contexts]
        if not hit:
            continue
        label = "·".join(CONTEXT_LABEL.get(c, c) for c in hit)
        if r.kind == "PROHIBITED":
            scope = set(r.materials)
            if r.scope_other:
                level, why = "CAUTION", f"특정 구성에만 해당({r.scope_other}) — 이 제품의 해당 여부 확인 필요"
            elif scope and not mats:
                level, why = "CAUTION", "재질 조건이 붙은 금지 조건인데 이 제품의 본체 재질이 확인되지 않았습니다"
            elif scope and mats <= scope:
                level, why = "BLOCK", f"이 제품의 본체 재질({', '.join(sorted(mats))})은 모두 금지 대상입니다"
            elif scope and mats & scope:
                level, why = "CAUTION", f"일부 구성({', '.join(sorted(mats & scope))})만 금지 대상입니다 — 구성 선택 시 주의"
            elif scope:
                continue        # 금지 대상 재질이 아님 → 이 제품과 무관
            else:
                level, why = "BLOCK", "제품 전체에 대한 금지 조건입니다"
        else:
            level, why = "CAUTION", "조건부 사용" if r.kind == "CONDITIONAL" else "주의 사항"
        out.append(RestrictionFinding(level=level, kind=r.kind, summary=r.summary, reason=f"{label} 계통 — {why}", contexts=hit,
                                      quote=r.quote, file=r.file, page=r.page, extractedBy=r.extractedBy,
                                      confirmedBy=r.confirmedBy, confirmedAt=r.confirmedAt))
    return out


def _restriction_item(p: Product, contexts: list[str], findings: list[RestrictionFinding]) -> ReqResult:
    reviewed = len(p.restrictions)
    req = Requirement(id="RX", field=RESTRICTION_FIELD, op="includes", value="|".join(contexts) or "-",
                      mandatory=reviewed > 0, note="문서의 사용 제한 조건 ↔ 선박 사용 계통")
    blocks = [f for f in findings if f.level == "BLOCK"]
    if reviewed == 0:
        return ReqResult(req=req, status="UNKNOWN", actual="문서 미분석",
                         reason="사용 제한 문구를 분석·확정한 문서가 없습니다(제한이 없다는 뜻이 아닙니다).")
    if blocks:
        b = blocks[0]
        return ReqResult(req=req, status="FAIL", actual=f"사용 불가 {len(blocks)}건",
                         reason="사용 제한: " + " / ".join(f"{x.summary} ({x.reason})" for x in blocks),
                         evidence=_ev(b.file, b.page, b.quote, b.extractedBy, b.confirmedBy, b.confirmedAt))
    if findings:
        f = findings[0]
        return ReqResult(req=req, status="PASS", actual=f"주의 {len(findings)}건",
                         reason=f"금지 조건은 없으나 조건부·주의 사항 {len(findings)}건이 있습니다.",
                         evidence=_ev(f.file, f.page, f.quote, f.extractedBy, f.confirmedBy, f.confirmedAt))
    return ReqResult(req=req, status="PASS", actual="해당 제한 없음",
                     reason=f"확정된 사용 제한 {reviewed}건 중 이 선박의 사용 계통에 해당하는 것이 없습니다.")


def evaluate(p: Product, reqs: list[Requirement], today: Optional[str] = None,
             contexts: Optional[list[str]] = None) -> Evaluation:
    """contexts: 선박 사용 계통에서 온 사용 상황 목록. None 이면 사용 제한 항목을 평가하지 않는다."""
    today = today or date.today().isoformat()
    lead = next((r for r in reqs if r.field == LEAD_FIELD), None)
    items = [_eval_req(p, r, today) for r in reqs if r.field != LEAD_FIELD]
    findings: list[RestrictionFinding] = []
    if contexts is not None:
        findings = restriction_findings(p, contexts)
        items.append(_restriction_item(p, contexts, findings))
    failed = [i for i in items if i.status == "FAIL" and i.req.mandatory]
    unknown = [i for i in items if i.status == "UNKNOWN" and i.req.mandatory]
    optional_miss = [i for i in items if i.status != "PASS" and not i.req.mandatory and i.req.field != RESTRICTION_FIELD]
    overall = "EXCLUDED" if failed else "CHECK" if unknown else "MATCH"
    return Evaluation(items=items, overall=overall, failed=failed, unknown=unknown, optionalMiss=optional_miss,
                      delivery=eval_delivery(p, float(lead.value) if lead else 9999),
                      restrictions=findings, restrictionsReviewed=len(p.restrictions))
