"""카탈로그(스캔 이미지)에서 읽은 표를 검증하는 순수 함수들 — LLM을 호출하지 않는다.

이미지 읽기는 값을 '조용히' 틀릴 수 있다(예: 바로 아래 행의 값을 가져옴). 두 가지 장치를 둔다.

1. check_table  : 표의 구조 검사(크기 짝·순서·열 단조성·열 간 종속). **값이 그럴듯하게 틀린 경우는 못 잡는다.**
2. compare_reads: 같은 이미지를 여러 번 읽은 결과를 셀 단위로 비교한다. 서로 다른 셀만 경고하고, 과반이 있으면
                  그 값을 제안한다. 세 번 모두 같은 오답이면 못 잡는다(체계적 오류).

시험 결과와 한계는 eval/REPORT_catalog.md 를 본다.
"""
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Optional

# 밸브 호칭경 inch ↔ DN(mm)
DN_BY_INCH = {3: 80, 4: 100, 5: 125, 6: 150, 8: 200, 10: 250, 12: 300, 14: 350, 16: 400, 18: 450, 20: 500, 24: 600}


@dataclass(frozen=True)
class Issue:
    kind: str        # size_pair | order | duplicate | monotonic | dependency
    severity: str    # error(추출 오류 가능성 높음) | review(원본 이상값일 수 있어 사람이 확인)
    table: str
    row: str
    column: str
    detail: str


def to_number(v: Any) -> Optional[float]:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def normalize(v: Any) -> Any:
    """비교용 정규화: 빈칸·'-'는 None, 숫자는 실수, 나머지는 공백 정리 문자열."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "-", "—", "–"):
        return None
    n = to_number(s)
    return round(n, 3) if n is not None else " ".join(s.split())


def check_table(name: str, rows: list[dict], *, size_inch: str = "size_inch", size_mm: str = "size_mm",
                monotonic: Iterable[str] = ()) -> list[Issue]:
    """한 표의 구조를 검사한다. monotonic 은 크기가 커질수록 줄어들면 안 되는 열 이름들."""
    out: list[Issue] = []
    mms = []
    for r in rows:
        inch, mm = to_number(r.get(size_inch)), to_number(r.get(size_mm))
        rid = str(r.get(size_mm))
        if inch is None or mm is None or DN_BY_INCH.get(int(inch)) != mm:
            out.append(Issue("size_pair", "error", name, rid, size_mm, f'{r.get(size_inch)}" 와 {r.get(size_mm)}mm 가 맞지 않음'))
        mms.append(mm)
    known = [m for m in mms if m is not None]
    if known != sorted(known):
        out.append(Issue("order", "error", name, "-", size_mm, "크기가 오름차순이 아님"))
    if len(set(known)) != len(known):
        out.append(Issue("duplicate", "error", name, "-", size_mm, "같은 크기의 행이 중복됨"))
    for col in monotonic:
        prev = None
        for r in rows:
            v = to_number(r.get(col))
            if v is None:
                continue
            if prev is not None and v < prev[1]:
                out.append(Issue("monotonic", "review", name, str(r.get(size_mm)), col,
                                 f"{prev[1]:g}({prev[0]}mm) → {v:g}: 크기가 커졌는데 값이 줄어듦(원본 표의 값일 수도 있음)"))
            prev = (r.get(size_mm), v)
    return out


def check_dependency(tables: dict[str, list[dict]], key: str, dependents: Iterable[str], size_mm: str = "size_mm") -> list[Issue]:
    """문서 전체에서 key 열의 같은 값(예: 장착 플랜지 TYPE)은 dependents 열들도 같아야 한다."""
    deps = tuple(dependents)
    seen: dict[Any, dict[tuple, list[str]]] = {}
    for tname, rows in tables.items():
        for r in rows:
            k = normalize(r.get(key))
            if k is None:
                continue
            combo = tuple(normalize(r.get(d)) for d in deps)
            seen.setdefault(k, {}).setdefault(combo, []).append(f"{tname}/{r.get(size_mm)}")
    out = []
    for k, combos in seen.items():
        if len(combos) > 1:
            # 가장 많이 나온 조합을 기준으로 삼고 나머지를 경고한다
            base = max(combos, key=lambda c: len(combos[c]))
            for combo, where in combos.items():
                if combo != base:
                    for w in where:
                        t, _, row = w.partition("/")
                        out.append(Issue("dependency", "error", t, row, key,
                                         f"{key}={k} 는 보통 {dict(zip(deps, base))} 인데 {dict(zip(deps, combo))} 로 읽힘"))
    return out


@dataclass(frozen=True)
class CellVote:
    values: tuple            # 읽기별 값(순서 유지)
    flagged: bool            # 읽기끼리 값이 다름
    majority: Any = None     # 과반(>n/2)이 일치한 값. 없으면 None → 담당자 확인
    has_majority: bool = False


def flatten(tables: list[dict], columns: Iterable[str], *, table_key: str = "class", rows_key: str = "rows",
            row_id: str = "size_mm") -> dict[tuple, Any]:
    """{'tables':[{'class':..,'rows':[..]}]} 형태를 {(표, 행, 열): 정규화된 값} 으로 편다."""
    cols = tuple(columns)
    out = {}
    for t in tables:
        tn = str(t[table_key]).upper().replace(" ", "")
        for r in t[rows_key]:
            rid = normalize(r.get(row_id))
            for c in cols:
                out[(tn, rid, c)] = normalize(r.get(c))
    return out


def compare_reads(reads: list[dict[tuple, Any]]) -> dict[tuple, CellVote]:
    """여러 번 읽은 셀 값을 비교한다. 읽기가 2번이면 어긋난 셀은 과반이 없어 '확인 필요'가 된다."""
    if not reads:
        return {}
    n = len(reads)
    keys = set().union(*[r.keys() for r in reads])
    votes = {}
    for k in keys:
        vals = tuple(r.get(k) for r in reads)          # 한 읽기에 아예 없던 셀은 None(빈칸과 구분되지 않음에 주의)
        top, cnt = Counter(vals).most_common(1)[0]
        flagged = len(set(vals)) > 1
        votes[k] = CellVote(vals, flagged, top if cnt * 2 > n else None, cnt * 2 > n)
    return votes


def flagged_cells(votes: dict[tuple, CellVote]) -> list[tuple]:
    return sorted((k for k, v in votes.items() if v.flagged), key=str)


def needs_more_reads(votes: dict[tuple, CellVote]) -> bool:
    """어긋난 셀 중 과반이 없는 것이 있으면 읽기를 더 해야 한다(2회 읽기에서 어긋난 경우)."""
    return any(v.flagged and not v.has_majority for v in votes.values())
