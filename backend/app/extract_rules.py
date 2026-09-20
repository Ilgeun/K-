"""규칙 기반 추출기 — API 키 없이도 동작하는 기본 경로이자 LLM 결과의 검증 기준.

원칙: 문서에 적힌 값만 뽑고, 값마다 원문 줄과 페이지를 함께 남긴다.
"""
import re
from typing import Optional

from .contexts import AUSTENITIC, CONTEXT_LABEL, STAINLESS
from .extract_types import Extraction, Note
from .labels import label
from .models import Cert, Restriction, Spec

AUTHORITIES = [
    ("DNV", r"\bDNV\b"), ("ABS", r"American Bureau of Shipping|\bABS\b"),
    ("KR", r"Korean Register|\bKR\b"), ("LR", r"Lloyd[’']?s Register|\bLR\b"),
    ("NK", r"Nippon Kaiji|ClassNK|\bNK\b"), ("BV", r"Bureau Veritas|\bBV\b"), ("CCS", r"China Classification"),
]
MATERIALS = [
    (r"\bCF-?8M\b", "CF8M"), (r"\bCF-?8\b(?!M)", "CF8"), (r"\bWCB\b", "WCB"),
    (r"Ni[\s\-]*Al(?:uminium|uminum)?[\s\-]*Bronze|\bNAB\b|C95[58]00|Alumin(?:i)?um[\s\-]*Bronze", "NAB"),
    (r"Duplex|\b2205\b|S3(?:1803|2205)|\bA182\s*F51\b", "DUPLEX_SS"),
    (r"SUS\s*304|SS\s*304|AISI\s*304", "SS304"), (r"SUS\s*316|SS\s*316|AISI\s*316", "SS316"),
    (r"cast[\s\-]*iron|\bGG-?25\b|\bFC200\b|\bGJL", "CAST_IRON"),
]
STAINLESS = {"CF8", "CF8M", "SS304", "SS316", "DUPLEX_SS"}


def _line_at(text: str, idx: int) -> str:
    start = text.rfind("\n", 0, idx) + 1
    end = text.find("\n", idx)
    return re.sub(r"\s+", " ", text[start: end if end != -1 else len(text)]).strip()[:200]


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], 1)}
DATE_RX = (r"(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[/.]\d{1,2}[/.]\d{4}|\d{1,2}\s+(?:"
           + "|".join(MONTHS) + r")\s+\d{4})")


def _iso(d: str) -> str:
    """ISO(YYYY-MM-DD)·DD/MM/YYYY·'10 November 2022' 형식을 ISO 로 바꾼다 (슬래시 형식은 일/월/연으로 해석)."""
    d = d.strip()
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", d)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", d)
    if m:
        return f"{int(m[3]):04d}-{int(m[2]):02d}-{int(m[1]):02d}"
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", d)
    return f"{int(m[3]):04d}-{MONTHS[m[2].lower()]:02d}-{int(m[1]):02d}"


def _fmt_num(x: float) -> str:
    return f"{x:.4f}".rstrip("0").rstrip(".")


def _spec(field, value, raw, page, unit="", display=None, note=None, rmin=None, rmax=None) -> Spec:
    return Spec(field=field, value=value, unit=unit, raw=raw, file="", page=page, display=display, note=note,
                rangeMin=rmin, rangeMax=rmax, extractedBy="rules", confirmed=False)


def _diameter(pages: list[str]):
    """DN 범위·목록('DN 50 – DN 600', 'DN40 to 1400', 'DN 32,40,...,1200', '(DN50) ... (DN300)')의 최소~최대."""
    token = re.compile(r"DN\s*\d{2,4}(?:\s*(?:,|&|to|–|-|and|/)\s*(?:DN\s*)?\d{2,4})*", re.I)
    vals: list[int] = []
    first = None
    for i, t in enumerate(pages, 1):
        for m in token.finditer(t):
            nums = [int(n) for n in re.findall(r"\d{2,4}", m[0])]
            vals += nums
            first = first or (i, _line_at(t, m.start()))
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return _spec("nominal_diameter", str(lo), first[1], first[0], "mm", display=f"DN{lo}")
    return _spec("nominal_diameter", f"{lo}-{hi}", first[1], first[0], "mm", display=f"DN{lo} ~ DN{hi} (승인 범위)", rmin=lo, rmax=hi)


def _flange_tokens(line: str):
    jis, pn, asme = [], [], []
    for m in re.finditer(r"JIS[\s\w.]*?((?:\d{1,2}\s*K\s*(?:,|/|and|&)?\s*)+)", line):
        jis += [int(n) for n in re.findall(r"(\d{1,2})\s*K", m[1])]
    for m in re.finditer(r"\bPN\s*((?:\d{1,2}\s*(?:,|/)?\s*)+)", line):
        pn += [int(n) for n in re.findall(r"\d{1,2}", m[1])]
    for m in re.finditer(r"(?:ANSI|ASME)[\s\w.]*?(?:class\s*)?(150|300)\b|\bClass\s*(150|300)\b", line, re.I):
        asme.append(int(m[1] or m[2]))
    return jis, pn, asme


def _flange(pages: list[str]):
    """플랜지 라벨(flange/connection)이 있는 줄을 우선하고, 없으면 압력등급 줄에서 읽는다.
    '설계압력 16 bar (PN16)' 같은 줄은 압력 표기이므로 제외한다."""
    tiers: list[list] = [[], []]
    for i, t in enumerate(pages, 1):
        for line in t.splitlines():
            if re.match(r"\s*(Design|Working|Rated)\s*pressure", line, re.I):
                continue
            jis, pn, asme = _flange_tokens(line)
            if jis or pn or asme:
                tier = 0 if re.search(r"flange|connection", line, re.I) else 1
                tiers[tier].append((i, re.sub(r"\s+", " ", line).strip()[:200], jis, pn, asme))
    found = tiers[0] or tiers[1]
    if not found:
        return None
    jis = sorted({n for f in found for n in f[2]})
    pn = sorted({n for f in found for n in f[3]})
    asme = sorted({n for f in found for n in f[4]})
    vals = [f"JIS_{n}K" for n in jis] + [f"PN{n}" for n in pn] + [f"ASME_{n}" for n in asme]
    parts = ([f"JIS {'/'.join(f'{n}K' for n in jis)}"] if jis else []) + ([f"PN{'/'.join(map(str, pn))}"] if pn else []) \
        + ([f"ANSI {'/'.join(map(str, asme))}"] if asme else [])
    return _spec("flange_standard", "|".join(vals), found[0][1], found[0][0], display=", ".join(parts))


def _pressure(pages: list[str]):
    rx = (r"(?:Design|Max(?:imum)?\.?\s*(?:working|allowable|operating)?|Working|Rated|Operating)\s*press(?:ure|\.)?\s*[:：=]?\s*"
          r"(?:up\s*to\s*)?(\d+(?:[.,]\d+)?)\s*(bar|MPa|kgf/cm2|kg/cm2|psi)\b")
    for i, t in enumerate(pages, 1):
        m = re.search(rx, re.sub(r"\bba\s+r\b", "bar", t), re.I)
        if m:
            x, u = float(m[1].replace(",", ".")), m[2].lower()
            bar = x * {"bar": 1, "mpa": 10, "kgf/cm2": 0.980665, "kg/cm2": 0.980665, "psi": 0.0689476}[u]
            disp = f"{_fmt_num(bar)} bar" + ("" if u == "bar" else f" (원문 {_fmt_num(x)} {m[2]})")
            return _spec("design_pressure", _fmt_num(bar), _line_at(re.sub(r"\bba\s+r\b", "bar", t), m.start()), i, "bar", display=disp)
    return None


def _body_text(t: str):
    """'Body:' / 'Valve body:' / 'Body material:' 줄의 값과, 값이 다음 줄들에 이어지는 목록을 함께 모은다."""
    lines = t.splitlines()
    for n, line in enumerate(lines):
        m = re.match(r"\s*[•\-\*]?\s*(?:Valve\s+)?Body(?:\s+material)?\s*[:：]\s*(.*)$", line, re.I)
        if not m:
            continue
        parts = [m[1]]
        for nxt in lines[n + 1: n + 21]:
            if not nxt.strip() or re.match(r"\s*[•\-\*]?\s*(Disc|Shaft|Stem|Spindle|Seat|Seal|Lining|Application|Pressure)\b", nxt, re.I):
                break
            parts.append(nxt.strip())
        return " ".join(parts), line
    return None


def _material(pages: list[str], notes_text: list[tuple[int, str]]):
    for i, t in enumerate(pages, 1):
        found = _body_text(t)
        if not found:
            continue
        s, line = found
        codes: list[str] = []
        for rx, code in MATERIALS:
            if re.search(rx, s, re.I):
                codes.append(code)
        if re.search(r"ductile|\bDI\b|GGG|GJS|EN-JS|A395|A536|nodular|QT\s?\d", s, re.I):
            codes.append("DI_RUBBER_LINED" if re.search(r"rubber|EPDM|ebonite|lined", s, re.I) else "DUCTILE_IRON")
        raw = re.sub(r"\s+", " ", line).strip()[:200]
        if not codes:
            return _spec("body_material", "UNKNOWN", raw, i, display=s.strip()[:80],
                         note="재질 코드를 인식하지 못했습니다. 담당자 확인 필요")
        note = None
        if STAINLESS & set(codes):
            for _, sent in notes_text:
                if re.search(r"stainless|austenitic", sent, re.I) and re.search(r"sea\s?water", sent, re.I):
                    note = f"승인서: {sent}"
        return _spec("body_material", "|".join(codes), raw, i, display=" / ".join(label(c) for c in codes), note=note)
    return None


def _temperature(pages: list[str]):
    seat, first_seat = [], None
    top = None
    for i, t in enumerate(pages, 1):
        m = re.search(r"Max(?:imum)?\.?\s*(?:operating|working|allowable|service)?\s*temp(?:erature)?\s*[:：]?\s*\+?(-?\d{2,3})\s*°?\s*C\b", t, re.I)
        if m and not top:
            top = (i, _line_at(t, m.start()), int(m[1]), False)
        m = re.search(r"Temperature range\s*[:：]?\s*([+-]?\d+)\s*°?\s*C\s*[,\s~–to-]*\s*([+-]?\d+)\s*°?\s*C(\s*\(dependent[^)\n]*)?", t, re.I)
        if m and not top:
            top = (i, _line_at(t, m.start()), int(m[2]), bool(m[3]))
        if re.search(r"Maximum permissible temperatures", t, re.I):
            vals = [int(x) for x in re.findall(r"\+\s*(\d{3})\s*°C", t)]
            if vals:
                seat += vals
                first_seat = first_seat or (i, _line_at(t, re.search(r"\+\s*\d{3}\s*°C", t).start()))
    if seat:
        lo, hi = min(seat), max(seat + ([top[2]] if top else []))
        page, raw = first_seat
        return _spec("temp_max", str(lo), raw, page, "degC", display=f"{lo} °C 이상 (시트별 상이, 최대 {hi} °C)",
                     note="시트 재질에 따라 최고 온도가 달라 가장 낮은 값을 사용")
    if top:
        page, raw, v, dep = top
        return _spec("temp_max", str(v), raw, page, "degC", display=f"{v} °C",
                     note="시트 재질에 따라 상이 — 확인 필요" if dep else None)
    return None


def _actuator(pages: list[str]):
    for i, t in enumerate(pages, 1):
        m = re.search(r"pneumatic\s*actuator", t, re.I)
        if m:
            return _spec("actuator_type", "PNEUMATIC", _line_at(t, m.start()), i, display=label("PNEUMATIC"))
        m = re.search(r"gear[\s-]*operated|worm\s*gear|hand[\s-]*wheel", t, re.I)
        if m:
            return _spec("actuator_type", "MANUAL_GEAR", _line_at(t, m.start()), i, display=label("MANUAL_GEAR"))
    return None


def _cert_no(t: str) -> Optional[str]:
    m = re.search(r"Certificate\s*No\.?\s*[:：]?\s*((?=[A-Z0-9\-/.]*\d)[A-Z0-9][A-Z0-9\-/.]{3,})", t, re.I)
    if m:
        return m[1]
    # 표 형태로 레이블과 값이 떨어져 추출되는 문서(Lloyd's 양식): 레이블 뒤 200자 안의 영문+숫자 번호
    m = re.search(r"Certificate\s*No\.?[\s\S]{0,200}?\b([A-Z]{1,4}\d{5,}[A-Z]{0,3})\b", t)
    return m[1] if m else None


def _certs(pages: list[str], warnings: list[str]) -> list[Cert]:
    out: dict[str, Cert] = {}
    pending: list[str] = []
    for i, t in enumerate(pages, 1):
        if not re.search(r"TYPE APPROVAL CERTIFICATE|CERTIFICATE OF (?:TYPE )?APPROVAL", t, re.I):
            continue
        no = _cert_no(t)
        val = re.search(r"(?:valid\s*(?:until|to)|expiry\s*date|expires?(?:\s*on)?)\s*[:：]?\s*" + DATE_RX, t, re.I)
        auth = next((a for a, rx in AUTHORITIES if re.search(rx, t)), None)
        if not (no and val and auth):
            pending.append(f"p.{i}: 인증서로 보이지만 번호·유효기간·선급 중 일부를 찾지 못했습니다. 담당자 확인 필요")
            continue
        if no in out:
            continue
        if re.fullmatch(r"\d{1,2}[/.]\d{1,2}[/.]\d{4}", val[1]):
            warnings.append(f"인증서 {no}: 유효기간 '{val[1]}'을 일/월/연(DD/MM/YYYY)으로 해석했습니다. 원문 확인 필요")
        out[no] = Cert(authority=auth, certNo=no, validUntil=_iso(val[1]), file="", page=i,
                       extractedBy="rules", confirmed=False)
    if not out:          # 이미 인증서를 찾았다면, 같은 제목이 반복되는 뒤쪽 쪽(연속 페이지)에 대한 경고는 소음이므로 내지 않는다
        warnings.extend(pending)
    return list(out.values())


def _product_type(pages: list[str]) -> Optional[str]:
    """인증서가 다루는 제품 종류(예: 'Butterfly Valves', 'Check Valve')."""
    for t in pages[:2]:
        m = re.search(r"That the\s+([A-Za-z\- ]+?)\s+with type designation", t) \
            or re.search(r"(?:PRODUCT DESCRIPTION|\bType)\s+([A-Z][A-Za-z\- ]+?Valves?)\b", t)
        if m:
            return m[1].strip()
    return None


def _restrictions(pages: list[str]) -> list[tuple[int, str]]:
    res = []
    for i, t in enumerate(pages, 1):
        flat = re.sub(r"\s+", " ", t)
        for sent in re.split(r"(?<=[.!?])\s+", flat):
            if re.search(r"not permitted|not allowed|not accepted|shall not|prohibited", sent, re.I) and len(sent) < 220:
                res.append((i, sent.strip()))
        # 'shall not be used in:' 뒤에 항목이 줄바꿈 목록으로 이어지는 형식 — 해수 계통이 포함되면 별도 표시
        m = re.search(r"shall not be used in\s*:([\s\S]{0,700})", t, re.I)  # 콜론이 있는 목록형만(재질 한정 문장은 제외)
        if m and re.search(r"sea\s?water", m[1], re.I):
            res.append((i, "해수(Seawater) 계통 사용 불가로 명시된 승인서 — 'shall not be used in: … Seawater applications'"))
    return res


def extract(pages: list[str], file: str) -> Extraction:
    warnings: list[str] = []
    if not any(p.strip() for p in pages):
        return Extraction(file=file, method="rules", pageCount=len(pages),
                          warnings=["텍스트를 읽을 수 없는 PDF입니다(스캔본 추정). OCR 또는 LLM 추출이 필요합니다."])
    restr = _restrictions(pages)
    specs = [s for s in (_diameter(pages), _pressure(pages), _material(pages, restr), _flange(pages),
                         _temperature(pages), _actuator(pages)) if s]
    for s in specs:
        s.file = file
    certs = _certs(pages, warnings)
    for c in certs:
        c.file = file
    if not specs and not certs:
        warnings.append("인식된 사양·인증 정보가 없습니다. 다른 문서이거나 형식이 다를 수 있습니다.")
    restrictions = _restriction_items(pages)
    for r in restrictions:
        r.file = file
    ptype = _product_type(pages)
    return Extraction(file=file, method="rules", pageCount=len(pages), specs=specs, certs=certs,
                      notes=[Note(page=p, text=t) for p, t in restr[:6]], warnings=warnings, productType=ptype, restrictions=restrictions,
                      flagged=[f"restriction:{r.key}" for r in restrictions])


# ================= 사용 제한 조건(규칙 기반 키워드 해석 — LLM 경로의 기준선·폴백) =================
CONTEXT_RX = [
    ("seawater", r"sea\s?water"), ("freshwater", r"fresh\s?water"), ("ballast", r"ballast"), ("bilge", r"bilge"),
    ("fuel_oil", r"fuel\s+oil|oil\s+fuel|diesel|\bHFO\b|\bMDO\b|lubricating"),
    ("cargo_oil", r"cargo\s+(?:oil|lines?|piping)|crude"), ("lng_lpg", r"\bLNG\b|\bLPG\b|liquefied\s+gas"),
    ("fire_safe", r"fire[\s-]*safe|fire\s+main|fire\s+protection"),
    ("shipside", r"ship[’']?s?\s+side|shipside|sea\s+chest|hull\s+plating|shell\s+valve"),
    ("collision_bulkhead", r"collision\s*bulkhead"), ("air", r"air\s+piping|compressed\s+air"),
    ("hydrocarbon", r"hydrocarbon|flammable"),
]
PROHIBIT_RX = re.compile(r"not\s+permitted|not\s+allowed|not\s+accepted|shall\s+not|must\s+not|prohibited|not\s+to\s+be\s+(?:fitted|used|installed)|does\s+not\s+cover|not\s+(?:be\s+)?considered", re.I)
COND_RX = re.compile(r"\bonly\b|limited\s+to|provided\s+(?:that|the)|subject\s+to|may\s+be\s+used|restricted\s+to", re.I)
LIST_HEADER = re.compile(r"(?:shall\s+not\s+be\s+used\s+in|shall\s+not\s+be\s+installed\s+in|not\s+to\s+be\s+(?:fitted|used|installed)\s+(?:on|in)|not\s+permitted\s+to\s+be\s+fitted\s+on|not\s+permitted\s+(?:in|on|for)|not\s+allowed\s+(?:in|on|for))\s*[:：]\s*-?\s*$", re.I)
BULLET = re.compile(r"^\s*[\uf0b7•\-\*▪●]\s*")
ABBREV = {"e.g", "i.e", "gr", "no", "nr", "approx", "max", "min", "fig", "ca", "vs"}


def _split_sentences(text: str) -> list[str]:
    """약어(e.g., Gr.)에서 끊지 않는 문장 분리."""
    out, start = [], 0
    for m in re.finditer(r"[.;]\s+(?=[A-Z0-9‘“(])", text):
        word = re.search(r"([A-Za-z.]+)$", text[start:m.start()])
        if word and word.group(1).lower().strip(".") in ABBREV:
            continue
        out.append(text[start:m.end()].strip()); start = m.end()
    out.append(text[start:].strip())
    return [x for x in out if x]


def _contexts_in(text: str) -> list[str]:
    return [c for c, rx in CONTEXT_RX if re.search(rx, text, re.I)]


def _materials_in(text: str) -> list[str]:
    if re.search(r"austenitic", text, re.I):
        return list(AUSTENITIC)
    if re.search(r"stainless", text, re.I):
        return list(STAINLESS)
    out = []
    if re.search(r"(?:grey|gray)\s+cast\s+iron", text, re.I):
        out.append("CAST_IRON")
    for rx, code in ((r"\bCF-?8M\b", "CF8M"), (r"\b316\b", "SS316"), (r"\bCF-?8\b(?!M)", "CF8"), (r"\b304\b", "SS304")):
        if re.search(rx, text) and code not in out:
            out.append(code)
    return out


def _scope_other(text: str) -> Optional[str]:
    """조건이 붙은 금지를 제품 전체 금지로 오인하지 않도록, 조건 표현이 보이면 적용 조건으로 표시한다(보수적)."""
    if re.search(r"\bEPDM\b|HYPALON|VITON|\bseat\b|seals?\b|elastomer|gasket|non-metallic", text, re.I):
        return "시트·시일 등 특정 구성 재질"
    if re.search(r"\d\s*bar|\d\s*°\s*C|exceeding|greater\s+than|f\.p\.", text, re.I):
        return "압력·온도 등 수치 조건"
    if re.search(r"passenger|tanker|cargo\s+ships?|vessels?\b", text, re.I):
        return "특정 선종에 한정"
    if re.search(r"\btunnels?\b|double\s+bottom|external\s+wall|static\s+head|\bthrough\b|inside|machinery\s+spaces?|accommodation|forward\s+tanks?|pump\s+rooms?", text, re.I):
        return "설치 위치·구역 조건"
    if re.search(r"fire[\s-]*tested|EV-type|wafer|lug\b|flangeless|valve\s+types?", text, re.I):
        return "특정 밸브 형식에 한정"
    return None


def _summary(kind: str, contexts: list[str], materials: list[str]) -> str:
    where = "·".join(CONTEXT_LABEL[c] for c in contexts)
    mat = f" ({'/'.join(materials)} 재질)" if materials else ""
    return f"{where}: " + {"PROHIBITED": "사용 불가", "CONDITIONAL": "조건부 사용", "ADVISORY": "주의"}[kind] + mat


def _mk(kind, contexts, materials, scope_other, quote, page, note) -> Restriction:
    return Restriction(kind=kind, contexts=contexts, materials=materials, scope_other=scope_other,
                       summary=_summary(kind, contexts, materials), quote=quote[:300], file="", page=page, note=note,
                       extractedBy="rules", confirmed=False)


def _restriction_items(pages: list[str]) -> list[Restriction]:
    out: list[Restriction] = []
    for pno, t in enumerate(pages, 1):
        lines = t.splitlines()
        used: set[int] = set()
        for n, line in enumerate(lines):          # 1) '…shall not be used in:' 다음의 글머리 목록
            if not LIST_HEADER.search(line.strip()):
                continue
            header = line.strip()
            # 머리 문장(이전 줄 포함)에서 재질 범위를 읽는다: 'Grey Cast Iron valves are not permitted to be fitted on:-'
            head_text = " ".join(x.strip() for x in lines[max(0, n - 1): n + 1])
            mats = _materials_in(head_text)
            items, cur = [], None
            for m in range(n + 1, min(n + 25, len(lines))):
                ln = lines[m]
                if not ln.strip():
                    break
                if BULLET.match(ln):
                    cur = [BULLET.sub("", ln).strip()]; items.append(cur); used.add(m)
                elif cur and ln.strip()[0].islower() and not cur[-1].rstrip().endswith((".", ";")):   # 줄바꿈으로 이어진 항목은 소문자로 이어진다
                    cur.append(ln.strip()); used.add(m)
                else:
                    break
            used.add(n)
            for parts in items:
                txt = " ".join(parts)
                ctx = _contexts_in(txt)
                if ctx:
                    out.append(_mk("PROHIBITED", ctx, mats, _scope_other(txt), txt, pno, f"목록형 제한 — 머리 문구: {header[:80]}"))
        # 2) 나머지는 문장 단위. 목록으로 소비된 줄·빈 줄은 문장 경계(¶)로 두어 서로 다른 문단이 합쳐지지 않게 한다
        rest = " ".join("¶" if (i in used or not ln.strip()) else re.sub(r"\s+", " ", ln).strip() for i, ln in enumerate(lines))
        pieces = [q for chunk in re.split(r"¶+", rest) for q in re.split(r"\s(?=\d{1,2}\.\s+[A-Z])", chunk)]   # 번호 목록 항목도 분리
        for sent in (x for piece in pieces for x in _split_sentences(piece.strip())):
            if len(sent) > 320:
                continue
            ctx = _contexts_in(sent)
            if not ctx:
                continue
            if PROHIBIT_RX.search(sent):
                kind = "CONDITIONAL" if re.match(r"\s*(?:When|If|Where|Unless)\b", sent) else "PROHIBITED"
            elif COND_RX.search(sent):
                kind = "CONDITIONAL"
            else:
                continue
            out.append(_mk(kind, ctx, _materials_in(sent), _scope_other(sent), sent, pno, "규칙 기반 키워드 해석"))
    seen, uniq = set(), []
    for r in out:
        if (r.page, r.quote) not in seen:
            seen.add((r.page, r.quote)); uniq.append(r)
    return uniq
