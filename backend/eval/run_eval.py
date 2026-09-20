"""추출 정확도 평가. 사용: python -m eval.run_eval [rules|cli|llm]

채점 규칙(항목별): CORRECT / WRONG(값이 틀림 또는 없는 값을 지어냄) / MISSING(값을 못 뽑음) / ABSENT_OK(없는 게 정답이고 안 뽑음)
LLM 경로는 flagged(교차검증 경고) 여부도 함께 집계한다: 틀린 값이 flagged 되면 '검출됨', 아니면 '조용한 오류'.
"""
import json
import sys
from pathlib import Path

from app import extract as orchestrator
from app.extract_types import Extraction

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "data" / "eval"
LABELS = json.loads((Path(__file__).parent / "labels.json").read_text(encoding="utf-8"))["docs"]
FIELDS = ["cert.authority", "cert.certNo", "cert.validUntil", "nominal_diameter", "flange_standard", "body_material", "temp_max", "design_pressure"]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def score_doc(name: str, ex) -> dict:
    lab = LABELS[name]
    spec = {s.field: s for s in ex.specs}
    out: dict[str, tuple[str, str, bool]] = {}   # field -> (verdict, detail, flagged)

    cert = lab["cert"]
    got = next((c for c in ex.certs if c.certNo == cert["certNo"]), ex.certs[0] if ex.certs else None)
    for f, key in (("cert.authority", "authority"), ("cert.certNo", "certNo"), ("cert.validUntil", "validUntil")):
        if got is None:
            out[f] = ("MISSING", "-", False)
        else:
            v = getattr(got, key)
            out[f] = ("CORRECT" if v == cert[key] else "WRONG", f"{v} (정답 {cert[key]})" if v != cert[key] else v, f"cert:{got.certNo}" in ex.flagged)

    s = spec.get("nominal_diameter")
    if s is None or s.value == "UNKNOWN":
        out["nominal_diameter"] = ("MISSING", "-", False)
    else:
        lo, hi = (s.rangeMin, s.rangeMax) if s.rangeMin is not None else ((_num(s.value),) * 2)
        if lo is None:
            out["nominal_diameter"] = ("WRONG", f"해석 불가 값 {s.value!r}", "nominal_diameter" in ex.flagged)
            lo = hi = None
        want = tuple(lab["nominal_diameter"])
        if lo is not None:
            ok = (lo, hi) == want
            out["nominal_diameter"] = ("CORRECT" if ok else "WRONG", f"{lo:g}-{hi:g}" + ("" if ok else f" (정답 {want[0]}-{want[1]})"), "nominal_diameter" in ex.flagged)

    for f in ("flange_standard", "body_material"):
        l = lab[f]
        if l.get("skip"):
            continue
        s = spec.get(f)
        req, extra = set(l["required"]), set(l.get("allowed_extra", []))
        if s is None or s.value == "UNKNOWN":
            out[f] = ("MISSING", "-", False)
        else:
            got_set = set(s.value.split("|"))
            ok = req <= got_set <= (req | extra)
            det = "|".join(sorted(got_set)) if ok else f"누락 {sorted(req - got_set)} / 초과 {sorted(got_set - req - extra)}"
            out[f] = ("CORRECT" if ok else "WRONG", det, f in ex.flagged)

    l = lab["temp_max"]; s = spec.get("temp_max")
    out["temp_max"] = ("MISSING", "-", False) if s is None else (("CORRECT" if _num(s.value) == l["value"] else "WRONG"), f"{s.value} (정답 {l['value']})", "temp_max" in ex.flagged)

    l = lab["design_pressure"]; s = spec.get("design_pressure")
    if l.get("absent"):
        out["design_pressure"] = ("ABSENT_OK", "-", False) if s is None else ("WRONG", f"{s.value} (문서에 수치 없음 → 지어낸 값)", "design_pressure" in ex.flagged)
    else:
        out["design_pressure"] = ("MISSING", "-", False) if s is None else (("CORRECT" if _num(s.value) == l["value"] else "WRONG"), f"{s.value} (정답 {l['value']})", "design_pressure" in ex.flagged)
    return out


def main(mode: str):
    rows, tally = {}, {"CORRECT": 0, "WRONG": 0, "MISSING": 0, "ABSENT_OK": 0}
    wrong_flagged = wrong_silent = 0
    for name in LABELS:
        cache = Path(__file__).parent / f"cache_{mode}" / f"{name}.json"
        if cache.exists() and "--refresh" not in sys.argv:   # LLM 호출 비용을 아끼기 위해 결과를 캐시한다
            ex = Extraction.model_validate_json(cache.read_text(encoding="utf-8"))
        else:
            ex = orchestrator.run(DOCS / name, name, mode)  # type: ignore[arg-type]
            cache.parent.mkdir(exist_ok=True)
            cache.write_text(ex.model_dump_json(indent=1), encoding="utf-8")
        sc = score_doc(name, ex)
        rows[name] = (ex, sc)
        for v, _, fl in sc.values():
            tally[v] += 1
            if v == "WRONG":
                wrong_flagged += bool(fl); wrong_silent += not fl
    n = sum(tally.values())
    extracted = tally["CORRECT"] + tally["WRONG"]
    lines = [f"# 추출 정확도 평가 — {mode}", "", f"- 문서 {len(LABELS)}건 · 채점 항목 {n}개 (표본이 작아 통계적 수치가 아님)",
             f"- 정답 {tally['CORRECT']} · 오답 {tally['WRONG']} · 누락 {tally['MISSING']} · 없음 정답 {tally['ABSENT_OK']}",
             f"- 값을 뽑은 항목 중 정확도(precision): {tally['CORRECT']}/{extracted} = {tally['CORRECT'] / max(extracted, 1):.0%}",
             f"- 정답이 있는 항목 중 재현율(recall): {tally['CORRECT']}/{tally['CORRECT'] + tally['WRONG'] + tally['MISSING']} = "
             f"{tally['CORRECT'] / max(tally['CORRECT'] + tally['WRONG'] + tally['MISSING'], 1):.0%}",
             f"- 오답 중 경고(flagged)로 검출: {wrong_flagged} · **조용한 오류(경고 없음): {wrong_silent}**", "",
             "| 문서 | " + " | ".join(FIELDS) + " |", "|---|" + "---|" * len(FIELDS)]
    icon = {"CORRECT": "✓", "WRONG": "✗", "MISSING": "∅", "ABSENT_OK": "✓(없음)"}
    for name, (ex, sc) in rows.items():
        lines.append(f"| {name} ({ex.method}) | " + " | ".join(icon[sc[f][0]] + (" ⚠" if f in sc and sc[f][2] and sc[f][0] == "WRONG" else "") if f in sc else "–" for f in FIELDS) + " |")
    lines += ["", "## 오답·누락 상세", ""]
    for name, (ex, sc) in rows.items():
        for f, (v, det, fl) in sc.items():
            if v in ("WRONG", "MISSING"):
                lines.append(f"- `{name}` · {f}: **{v}** — {det}{' (경고로 검출)' if fl and v == 'WRONG' else ''}")
    out = ROOT / "eval" / f"results_{mode}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rules")
