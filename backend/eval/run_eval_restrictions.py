"""사용 제한 조건 추출 평가. 사용: python -m eval.run_eval_restrictions [rules|cli] [--refresh]

라벨(labels_restrictions.json)과 의미 기준으로 대조한다:
  - 재현(TP): 라벨 L 에 대해 kind·contexts·(materials)·(scope_other) 조건을 만족하는 추출 항목이 있음
  - 누락(FN): 없음
  - 근거 없는 금지: 라벨의 PROHIBITED 어느 것과도 일치하지 않는 PROHIBITED 추출 — 판정에서 잘못 제외할 수 있어 가장 위험
"""
import json
import sys
from pathlib import Path

from app import extract as orchestrator
from app.extract_types import Extraction

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "data" / "eval"
LABELS = json.loads((Path(__file__).parent / "labels_restrictions.json").read_text(encoding="utf-8"))["docs"]


def matches(r, L) -> bool:
    if r.kind != L["kind"] or not set(r.contexts) & set(L["contexts_any"]):
        return False
    if L.get("materials_any") and not set(r.materials) & set(L["materials_any"]):
        return False
    if L.get("needs_scope_other") and not r.scope_other:
        return False
    return True


def effect(r_or_label) -> str:
    """판정 엔진에서의 효과 등급. BLOCK_ALL=제품 전체 금지, BLOCK_MAT=재질 범위 금지, CAUTION=그 외(조건부·특정 구성 한정 금지 포함)."""
    if isinstance(r_or_label, dict):     # 라벨
        kind, mats, other = r_or_label["kind"], r_or_label.get("materials_any"), r_or_label.get("needs_scope_other")
        ctx = set(r_or_label["contexts_any"])
    else:                                # 추출 항목
        kind, mats, other, ctx = r_or_label.kind, r_or_label.materials, r_or_label.scope_other, set(r_or_label.contexts)
    if kind != "PROHIBITED" or other:
        return "CAUTION"
    return "BLOCK_MAT" if mats else "BLOCK_ALL"


def decision_score(name: str, ex) -> dict:
    """판정에 영향을 주는 기준: 같은 효과 등급으로 같은 사용 상황(·재질)을 잡았는가, 그리고 근거 없는 '제외'를 만들었는가."""
    labels = LABELS[name]
    def hit(r, L):
        if not set(r.contexts) & set(L["contexts_any"]) or effect(r) != effect(L):
            return False
        return not L.get("materials_any") or bool(set(r.materials) & set(L["materials_any"]))
    tp = [L for L in labels if any(hit(r, L) for r in ex.restrictions)]
    block_labels = [L for L in labels if effect(L).startswith("BLOCK")]
    wrongful = [r for r in ex.restrictions if effect(r).startswith("BLOCK")
                and not any(set(r.contexts) & set(L["contexts_any"]) and (not L.get("materials_any") or set(r.materials) & set(L["materials_any"])) for L in block_labels)]
    return {"tp": tp, "fn": [L for L in labels if L not in tp], "wrongful_block": wrongful}


def score(name: str, ex) -> dict:
    labels = LABELS[name]
    tp = [L for L in labels if any(matches(r, L) for r in ex.restrictions)]
    fn = [L for L in labels if L not in tp]
    p_labels = [L for L in labels if L["kind"] == "PROHIBITED"]
    false_p = [r for r in ex.restrictions if r.kind == "PROHIBITED" and not any(matches(r, L) for L in p_labels)]
    p_ext = [r for r in ex.restrictions if r.kind == "PROHIBITED"]
    return {"tp": tp, "fn": fn, "false_p": false_p, "n_ext": len(ex.restrictions), "n_p": len(p_ext), "dec": decision_score(name, ex)}


def main(mode: str):
    rows, T = {}, {"tp": 0, "lab": 0, "false_p": 0, "n_ext": 0, "n_p": 0, "dtp": 0, "wrong_block": 0}
    for name in LABELS:
        cache = Path(__file__).parent / f"cache_r_{mode}" / f"{name}.json"
        if cache.exists() and "--refresh" not in sys.argv:
            ex = Extraction.model_validate_json(cache.read_text(encoding="utf-8"))
        else:
            ex = orchestrator.run(DOCS / name, name, mode)  # type: ignore[arg-type]
            cache.parent.mkdir(exist_ok=True); cache.write_text(ex.model_dump_json(indent=1), encoding="utf-8")
        sc = score(name, ex); rows[name] = (ex, sc)
        T["tp"] += len(sc["tp"]); T["lab"] += len(LABELS[name]); T["false_p"] += len(sc["false_p"]); T["n_ext"] += sc["n_ext"]; T["n_p"] += sc["n_p"]; T["dtp"] += len(sc["dec"]["tp"]); T["wrong_block"] += len(sc["dec"]["wrongful_block"])
    lines = [f"# 사용 제한 조건 추출 평가 — {mode}", "",
             f"- 문서 {len(LABELS)}건 · 정답 라벨 {T['lab']}건 (표본이 작아 통계적 수치가 아님)",
             f"- **재현율: {T['tp']}/{T['lab']} = {T['tp'] / T['lab']:.0%}**",
             f"- 추출한 제한 {T['n_ext']}건 중 금지(PROHIBITED) {T['n_p']}건",
             f"- 근거 없는 금지(라벨과 일치하지 않는 금지 추출, 엄격 기준): {T['false_p']}건", "",
             "### 판정 영향 기준 (결과를 본 뒤 추가한 지표 — 조건부/특정 구성 한정 금지는 엔진에서 ‘주의’로 같게 처리되므로 효과 등급으로 비교)", "",
             f"- **판정 효과 일치 재현율: {T['dtp']}/{T['lab']} = {T['dtp'] / T['lab']:.0%}**",
             f"- **근거 없는 ‘제외’(제품 전체·재질 범위 금지로 잘못 추출 → 판정에서 부당하게 제외될 수 있는 항목): {T['wrong_block']}건**", "",
             "| 문서 | 재현(엄격) | 재현(판정 효과) | 근거 없는 금지(엄격) | 근거 없는 ‘제외’ | 추출 수 |", "|---|---|---|---|---|---|"]
    for name, (ex, sc) in rows.items():
        lines.append(f"| {name} ({ex.method}) | {len(sc['tp'])}/{len(LABELS[name])} | {len(sc['dec']['tp'])}/{len(LABELS[name])} | {len(sc['false_p'])} | {len(sc['dec']['wrongful_block'])} | {sc['n_ext']} |")
    lines += ["", "## 근거 없는 ‘제외’ 항목(판정 효과 기준)", ""]
    for name, (ex, sc) in rows.items():
        for r in sc["dec"]["wrongful_block"]:
            lines.append(f"- `{name}` p.{r.page} {r.contexts} mat={r.materials}: “{r.quote[:90]}”")
    lines += ["", "## 누락(엄격 기준, 라벨 대비)", ""]
    for name, (ex, sc) in rows.items():
        for L in sc["fn"]:
            lines.append(f"- `{name}` {L['id']} [{L['kind'][:4]} {L['contexts_any']}]: {L['note']}")
    lines += ["", "## 근거 없는 금지(라벨과 불일치한 PROHIBITED)", ""]
    for name, (ex, sc) in rows.items():
        for r in sc["false_p"]:
            lines.append(f"- `{name}` p.{r.page} {r.contexts} mat={r.materials} other={r.scope_other!r}: “{r.quote[:90]}”")
    out = ROOT / "eval" / f"results_restrictions_{mode}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rules")
