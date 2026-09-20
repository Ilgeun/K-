"""카탈로그 이미지 읽기 벤치마크 — 글자 레이어가 있는 PDF를 '스캔본처럼' 읽혀 자동 채점한다.

정답: PDF 글자 레이어에서 규칙(정규식)으로 뽑은 표의 행. AI 도, 사람도 쓰지 않는다.
시험: 같은 쪽을 이미지로 만들어(맥의 sips) AI 가 이미지에서 표를 읽게 하고, 행 단위로 정답과 비교한다.
조건: clean(디지털 렌더링 그대로) / scan(해상도·JPEG 화질·기울기를 떨어뜨려 스캔본을 흉내 냄).
지표: 행 재현율(코드로 행을 찾음), 행 완전일치율, 토큰 재현율·정밀도(값 단위), 경고 검출률과 조용한 오류 행.
주의: 디지털 렌더링은 실제 스캔보다 깨끗하다(최선 조건). 정답 파서가 맞다는 보장은 없어 불일치 행은 사람이 원문으로 판정한다.

사용:
  python -m eval.catalog_bench run   PDF 쪽,쪽,... 조건 [--workers 3]     # AI 호출(CLI). 결과는 eval/cache_catalog/bench_*.json
  python -m eval.catalog_bench score PDF 쪽,쪽,... 조건
"""
import difflib
import io
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter

from eval.stats import wilson

CACHE = Path(__file__).parent / "cache_catalog"
ROW = re.compile(r"^\s*(\d{2,3})\s+(MV[0-9A-Z]+)\b.*$")
CODE = re.compile(r"^MV[0-9A-Z]+$")


# ---------------------------------------------------------------- 정답(글자 레이어)
def norm_tokens(s: str) -> list[str]:
    """비교용 토큰: 대문자, '4x M16' 같은 곱 표기를 '4 X M16' 으로 통일."""
    s = re.sub(r"[|│¦]", " ", s)                       # 표의 세로 구분선을 옮겨 적은 기호는 값이 아니다(사후에 정한 채점 규칙)
    s = re.sub(r"(?<=\d)\s*[xX×]\s*(?=[\dM])", " X ", s.upper())
    return s.split()


@dataclass
class TruthRow:
    page: int
    code: str
    tokens: list[str]


def truth_rows(page: int, text: str) -> list[TruthRow]:
    out = []
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            out.append(TruthRow(page, m.group(2), norm_tokens(line)))
    return out


# ---------------------------------------------------------------- 이미지 만들기
def render_page(pdf: Path, page: int, max_dim: int = 2400) -> bytes:
    """쪽을 흰 배경 JPEG 로 렌더링한다(macOS sips 필요)."""
    with tempfile.TemporaryDirectory() as tmp:
        one, png = Path(tmp) / "p.pdf", Path(tmp) / "p.png"
        w = PdfWriter()
        w.add_page(PdfReader(str(pdf)).pages[page - 1])
        w.write(str(one))
        subprocess.run(["sips", "-s", "format", "png", "-Z", str(max_dim), str(one), "--out", str(png)], capture_output=True, check=True)
        im = Image.open(png).convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))          # 투명 배경이 검게 나오지 않도록 흰색에 합성
        buf = io.BytesIO()
        bg.save(buf, "JPEG", quality=92)
        return buf.getvalue()


def degrade(jpeg: bytes, scale: float = 0.5, rotate: float = 0.6, quality: int = 45) -> bytes:
    """스캔본 흉내: 해상도를 줄이고 조금 기울이고 JPEG 화질을 낮춘다."""
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    im = im.rotate(rotate, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


# ---------------------------------------------------------------- 채점
def ai_rows(page_result: dict) -> list[dict]:
    """AI 결과(PageResult dict)의 표 행을 토큰으로 편다. 행에서 MV 코드를 찾아 키로 쓴다."""
    out = []
    for t in page_result.get("tables", []):
        flagged = {f["row"] for f in t.get("flags", [])}
        for ri, row in enumerate(t["rows"]):
            cells = [c for c in row if c]
            toks = norm_tokens(" ".join(cells))
            code = next((x for x in toks if CODE.match(x)), None)
            out.append({"code": code, "tokens": toks, "flagged": ri in flagged})
    return out


def match_tokens(a: list[str], b: list[str]) -> int:
    return sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())


def classify(truth: list[str], ai: list[str]) -> str:
    """틀린 행의 오류 유형."""
    if ai == truth[:-1]:
        return "마지막 값 누락"
    ops = [o for o in difflib.SequenceMatcher(None, truth, ai, autojunk=False).get_opcodes() if o[0] != "equal"]
    if all(o[0] == "replace" and (o[2] - o[1]) == (o[4] - o[3]) for o in ops):
        return "값 오독(치환)"
    if all(o[0] == "delete" for o in ops):
        return "값 누락"
    if all(o[0] == "insert" for o in ops):
        return "값 삽입"
    return "기타"


def score_page(truth: list[TruthRow], ai: list[dict]) -> dict:
    by_code: dict[str, list[dict]] = {}
    for r in ai:
        if r["code"]:
            by_code.setdefault(r["code"], []).append(r)
    truth_codes = {t.code for t in truth}
    # 정답 파서가 못 읽은 표의 행(정답에 없는 코드)은 정밀도 계산에서 뺀다. 이미지로 확인하면 실제로 있는 행일 수 있다(36쪽)
    res = {"rows": len(truth), "found": 0, "exact": 0, "truth_tokens": 0, "matched_tokens": 0,
           "ai_tokens": sum(len(r["tokens"]) for r in ai if r["code"] in truth_codes),
           "wrong_rows": [], "missing": [], "extra": 0, "duplicates": 0, "wrong_flagged": 0, "wrong_silent": 0}
    res["extra"] = sum(1 for r in ai if r["code"] not in truth_codes)
    res["duplicates"] = sum(len(v) - 1 for v in by_code.values() if len(v) > 1)
    for t in truth:
        res["truth_tokens"] += len(t.tokens)
        cand = by_code.get(t.code)
        if not cand:
            res["missing"].append(t.code)
            continue
        res["found"] += 1
        best = max(cand, key=lambda r: match_tokens(t.tokens, r["tokens"]))
        m = match_tokens(t.tokens, best["tokens"])
        res["matched_tokens"] += m
        if best["tokens"] == t.tokens:
            res["exact"] += 1
        else:
            res["wrong_rows"].append({"page": t.page, "code": t.code, "truth": " ".join(t.tokens), "ai": " ".join(best["tokens"]),
                                      "flagged": best["flagged"], "kind": classify(t.tokens, best["tokens"])})
            res["wrong_flagged" if best["flagged"] else "wrong_silent"] += 1
    return res


def summarize(pages: dict[int, dict]) -> dict:
    tot = {k: sum(p[k] for p in pages.values()) for k in ("rows", "found", "exact", "truth_tokens", "matched_tokens", "ai_tokens", "extra", "duplicates", "wrong_flagged", "wrong_silent")}
    tot["wrong_rows"] = [w for p in pages.values() for w in p["wrong_rows"]]
    tot["missing"] = [c for p in pages.values() for c in p["missing"]]
    tot["row_exact_ci"] = wilson(tot["exact"], tot["rows"])
    tot["row_found_ci"] = wilson(tot["found"], tot["rows"])
    tot["token_recall"] = tot["matched_tokens"] / tot["truth_tokens"] if tot["truth_tokens"] else 0.0
    tot["token_precision"] = tot["matched_tokens"] / tot["ai_tokens"] if tot["ai_tokens"] else 0.0
    return tot


# ---------------------------------------------------------------- 실행
def truth_for(pdf: Path, pages: list[int]) -> dict[int, list[TruthRow]]:
    rd = PdfReader(str(pdf))
    return {p: truth_rows(p, rd.pages[p - 1].extract_text() or "") for p in pages}


def cache_path(pdf: Path, page: int, condition: str) -> Path:
    return CACHE / f"bench_{pdf.stem[:20]}_{condition}_p{page}.json"


def run(pdf: Path, pages: list[int], condition: str, workers: int = 3) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from app import catalog_read as cr
    from app.pdf import PageImage
    reader = cr.CliReader()
    CACHE.mkdir(exist_ok=True)

    def one(p: int) -> str:
        img = render_page(pdf, p)
        if condition == "scan":
            img = degrade(img)
        res = cr.read_page(PageImage(p, "image/jpeg", img), reader)
        cache_path(pdf, p, condition).write_text(res.model_dump_json(indent=1), encoding="utf-8")
        return f"p{p} kind={res.kind} 표={len(res.tables)} 경고={len(res.warnings)}"
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for line in ex.map(one, pages):
            print(line, flush=True)


def score(pdf: Path, pages: list[int], condition: str) -> dict:
    truth = truth_for(pdf, pages)
    per = {}
    for p in pages:
        cp = cache_path(pdf, p, condition)
        per[p] = score_page(truth[p], ai_rows(json.loads(cp.read_text(encoding="utf-8"))) if cp.exists() else [])
    return {"pages": per, "total": summarize(per)}


def report(res: dict, condition: str) -> None:
    t = res["total"]
    print(f"\n[조건: {condition}] 정답 행 {t['rows']}개, 정답 토큰 {t['truth_tokens']}개")
    print(f"  행 재현율(코드로 찾은 행): {t['found']}/{t['rows']} = {t['found'] / t['rows']:.1%}  (95% {t['row_found_ci'][0]:.1%}~{t['row_found_ci'][1]:.1%})")
    print(f"  행 완전일치율:           {t['exact']}/{t['rows']} = {t['exact'] / t['rows']:.1%}  (95% {t['row_exact_ci'][0]:.1%}~{t['row_exact_ci'][1]:.1%})")
    print(f"  토큰 재현율 / 정밀도:     {t['token_recall']:.2%} / {t['token_precision']:.2%}")
    print(f"  틀린 행 {len(t['wrong_rows'])}개 = 경고로 표시 {t['wrong_flagged']} + 경고 없이(조용한 오류) {t['wrong_silent']} | 없는 행 {len(t['missing'])} | 정답 파서에 없는 AI 행(정답 밖, 채점 제외) {t['extra']} | 중복 {t['duplicates']}")
    from collections import Counter
    print("  틀린 행의 유형:", dict(Counter(w["kind"] for w in t["wrong_rows"])))
    print("  쪽별 행 완전일치:", {p: f"{v['exact']}/{v['rows']}" for p, v in res["pages"].items()})


def main() -> None:
    cmd, pdf, pages, cond = sys.argv[1], Path(sys.argv[2]), [int(x) for x in sys.argv[3].split(",")], sys.argv[4]
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 3
    if cmd == "run":
        run(pdf, pages, cond, workers)
    report(score(pdf, pages, cond), cond)


if __name__ == "__main__":
    main()
