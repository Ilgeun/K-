"""사람이 채운 검수 시트로 정확도를 계산한다. 사용: python -m eval.score_review 검수폴더 [채워진시트.csv]

- 검수 칸이 비어 있는 행은 '미검수'로 빼고 그 수를 보고한다.
- 정답 판정: 'O'(또는 OK) 이거나 검수 값이 AI 값과 같으면 맞음. 그 밖에는 틀림(검수 값이 올바른 값).
- 보고: 층(경고 셀 / 경고 없는 셀)별 정확도와 Wilson 95% 구간, 경고의 적중률(경고 셀 중 실제 오류 비율),
  조용한 오류율(경고 없는 셀 중 오류 비율), 전체 셀 정확도(층화 추정), 사실 정밀도.
"""
import csv
import json
import sys
from pathlib import Path

from app.catalog_checks import normalize
from eval.stats import stratified, wilson

OK = {"O", "OK", "ㅇ", "0"}


def is_correct(review: str, ai: str) -> bool:
    r = review.strip()
    if r.upper() in OK:
        return True
    if r in ("없음", "빈칸", "(빈칸)", "-"):
        return ai in ("", "(빈칸)", None) or normalize(ai) is None
    return normalize(r) == normalize(ai) and normalize(r) is not None


def load(folder: Path, sheet: Path) -> list[dict]:
    key = {r["id"]: r for r in csv.DictReader(open(folder / "answer_key.csv", encoding="utf-8-sig"))}
    rows = []
    for r in csv.DictReader(open(sheet, encoding="utf-8-sig")):
        review = next((v for k, v in r.items() if k and k.startswith("검수")), "") or ""
        k = key[r["id"]]
        rows.append({"id": r["id"], "stratum": k["stratum"], "review": review.strip(), "ai": k["ai_value"], "unresolved": k["unresolved"] == "1"})
    return rows


def score(rows: list[dict], population: dict[str, int]) -> dict:
    out = {"unreviewed": sum(1 for r in rows if not r["review"]), "strata": {}}
    for s in ("flagged", "plain", "fact"):
        rs = [r for r in rows if r["stratum"] == s and r["review"]]
        k = sum(is_correct(r["review"], r["ai"]) for r in rs)
        lo, hi = wilson(k, len(rs))
        out["strata"][s] = {"n": len(rs), "correct": k, "acc": (k / len(rs)) if rs else None, "ci": (lo, hi), "population": population.get(s, 0)}
    f, p = out["strata"]["flagged"], out["strata"]["plain"]
    out["flag_precision"] = (1 - f["acc"]) if f["n"] else None                 # 경고 셀 중 실제로 틀린 비율
    out["silent_error_rate"] = (1 - p["acc"]) if p["n"] else None              # 경고 없는 셀 중 틀린 비율
    st = [(f["population"], f["n"], f["correct"]), (p["population"], p["n"], p["correct"])]
    out["overall_cell_accuracy"] = stratified([s for s in st if s[1] > 0]) if any(s[1] for s in st) else None
    return out


def main() -> None:
    folder = Path(sys.argv[1])
    sheet = Path(sys.argv[2]) if len(sys.argv) > 2 else folder / "review_sheet.csv"
    population = json.loads((folder / "population.json").read_text(encoding="utf-8"))
    res = score(load(folder, sheet), population)
    print(f"미검수 {res['unreviewed']}행")
    names = {"flagged": "경고가 뜬 셀", "plain": "경고 없는 셀(무작위)", "fact": "목록 사실(원문 일치)"}
    for s, v in res["strata"].items():
        if v["n"]:
            print(f"{names[s]}: {v['correct']}/{v['n']} = {v['acc']:.1%} (95% 구간 {v['ci'][0]:.0%}~{v['ci'][1]:.0%}) · 모집단 {v['population']}")
    if res["overall_cell_accuracy"]:
        e, lo, hi = res["overall_cell_accuracy"]
        print(f"전체 셀 정확도(추정): {e:.1%} (근사 95% 구간 {lo:.1%}~{hi:.1%})")
    if res["flag_precision"] is not None:
        print(f"경고 적중률(경고 셀 중 실제 오류): {res['flag_precision']:.0%}")
    if res["silent_error_rate"] is not None:
        print(f"조용한 오류율(경고 없는 셀 중 오류): {res['silent_error_rate']:.1%}")


if __name__ == "__main__":
    main()
