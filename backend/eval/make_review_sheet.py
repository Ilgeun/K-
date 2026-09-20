"""사람 검수용 표본 시트를 만든다. 사용: python -m eval.make_review_sheet 결과.json 출력폴더 [--cells 120] [--facts 30] [--skip-pages 9]

- 검수 대상: 표 셀(경고가 뜬 셀 전부 + 경고 없는 셀의 쪽별 층화 무작위 표본)과 목록 사실(무작위).
- 검수 시트(review_sheet.csv)에는 경고 여부를 넣지 않는다(검수자가 경고 셀만 더 꼼꼼히 보는 편향을 막기 위해).
  경고 여부는 answer_key.csv(채점용)에만 있다. 채점은 python -m eval.score_review 를 쓴다.
- 정답표가 이미 있는 쪽(예: 9쪽)은 --skip-pages 로 뺀다.
"""
import argparse
import csv
import json
import random
import re
from collections import Counter
from pathlib import Path


def _resolved_blank(f: dict) -> bool:
    vals = f["values"]
    top, cnt = Counter(vals).most_common(1)[0]
    return cnt * 2 > len(vals)


def cell_universe(result: dict, skip: set[int]) -> list[dict]:
    cells = []
    for p in result["pages"]:
        if p["page"] in skip:
            continue
        for ti, t in enumerate(p["tables"]):
            flagged = {(f["row"], f["column"]) for f in t["flags"]}
            unresolved = {(f["row"], f["column"]) for f in t["flags"] if not f.get("resolved", _resolved_blank(f))}
            # 행 이름: 크기·번호·부품명 같은 식별 열이 있으면 그것, 없으면 앞의 두 열
            id_cols = [i for i, c in enumerate(t["columns"]) if re.search(r"size|no\.|part|name|section", c, re.I)] or [0, 1]
            for ri, row in enumerate(t["rows"]):
                label = " | ".join(str(row[i]) for i in id_cols if i < len(row) and row[i]) or f"행{ri + 1}"
                for ci, col in enumerate(t["columns"]):
                    cells.append({"page": p["page"], "table": t["caption"], "ti": ti, "ri": ri, "row": label, "column": col,
                                  "ai": row[ci] if ci < len(row) else None,
                                  "flagged": (ri, col) in flagged, "unresolved": (ri, col) in unresolved})
    return cells


def sample(result: dict, n_cells: int, n_facts: int, skip: set[int], seed: int = 20260921) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    cells = cell_universe(result, skip)
    flagged = [c for c in cells if c["flagged"]]
    plain = [c for c in cells if not c["flagged"]]
    by_page = Counter(c["page"] for c in plain)
    picked = []
    for pg, cnt in sorted(by_page.items()):
        k = min(cnt, max(5, round(n_cells * cnt / len(plain))))
        picked += rng.sample([c for c in plain if c["page"] == pg], k)
    for c in flagged:
        c["stratum"] = "flagged"
    for c in picked:
        c["stratum"] = "plain"
    facts = [{"page": p["page"], "kind": "fact", "category": f["category"], "availability": f["availability"], "statement": f["statement"]}
             for p in result["pages"] if p["page"] not in skip for f in p["facts"]]
    facts = rng.sample(facts, min(n_facts, len(facts)))
    for f in facts:
        f["stratum"] = "fact"
    return flagged + picked, facts


def write(out: Path, cells: list[dict], facts: list[dict], universe: dict[str, int]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = sorted(cells, key=lambda c: (c["page"], c["ti"], c["ri"], c["column"])) + sorted(facts, key=lambda f: (f["page"], f["statement"]))
    for i, r in enumerate(rows, 1):
        r["id"] = f"R{i:03d}"
    with open(out / "review_sheet.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "종류", "쪽", "표/분류", "행", "열/구분", "AI가 읽은 값", "검수(맞으면 O, 틀리면 올바른 값. 빈칸이어야 하면 '없음')", "메모"])
        for r in rows:
            if r.get("kind") == "fact":
                w.writerow([r["id"], "사실", r["page"], r["category"], r["availability"], r["statement"], "(위 문장이 원문과 일치하는가: O/X)", "", ""])
            else:
                w.writerow([r["id"], "셀", r["page"], r["table"], r["row"], r["column"], r["ai"] if r["ai"] is not None else "(빈칸)", "", ""])
    with open(out / "answer_key.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "stratum", "flagged", "unresolved", "ai_value"])
        for r in rows:
            w.writerow([r["id"], r["stratum"], int(r.get("flagged", False)), int(r.get("unresolved", False)), r.get("ai", r.get("statement", ""))])
    with open(out / "population.json", "w", encoding="utf-8") as f:
        json.dump(universe, f, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result"); ap.add_argument("out")
    ap.add_argument("--cells", type=int, default=120); ap.add_argument("--facts", type=int, default=30)
    ap.add_argument("--skip-pages", default="9")
    a = ap.parse_args()
    skip = {int(x) for x in a.skip_pages.split(",") if x.strip()}
    result = json.loads(Path(a.result).read_text(encoding="utf-8"))
    cells, facts = sample(result, a.cells, a.facts, skip)
    universe_cells = cell_universe(result, skip)
    universe = {"flagged": sum(c["flagged"] for c in universe_cells), "plain": sum(not c["flagged"] for c in universe_cells),
                "fact": sum(len(p["facts"]) for p in result["pages"] if p["page"] not in skip)}
    write(Path(a.out), cells, facts, universe)
    print(f"셀 {len(cells)}(경고 {sum(c['stratum'] == 'flagged' for c in cells)} + 무작위 {sum(c['stratum'] == 'plain' for c in cells)}), 사실 {len(facts)} → {a.out}")
    print("모집단:", universe)


if __name__ == "__main__":
    main()
