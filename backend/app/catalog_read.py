"""스캔 카탈로그 읽기 파이프라인: 페이지 이미지 → 종류 분류 → 표/목록 읽기 → 검증 → 페이지별 결과.

- 표: 같은 이미지를 독립적으로 여러 번 읽어 셀 단위로 비교한다(catalog_checks.compare_reads). 어긋난 셀은 경고하고
  과반이 있으면 그 값을 채택, 없으면 값을 비우고 담당자 확인으로 남긴다. 표 구조 검사(크기 짝·순서·열 단조성)도 한다.
- 목록/서술: 한 번 읽고, 추출 목록과 이미지를 다시 대조하는 '누락 확인' 패스로 빠진 문장을 찾는다.
- 이미지 안의 글은 신뢰할 수 없는 데이터다. CLI 는 임시 폴더에서 Read 도구만 허용해 실행한다.
- 시험 결과와 한계: eval/REPORT_catalog.md. **API(이미지 입력) 경로는 실제 호출로 검증하지 못했다.**
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal, Optional, Protocol, TypeVar

from pydantic import BaseModel, Field

from .catalog_checks import Issue, check_table, compare_reads, flagged_cells, needs_more_reads, normalize, to_number
from .extract_cli import parse_output
from .pdf import PageImage

TIMEOUT = int(os.environ.get("MARINE_CLI_TIMEOUT", "240"))
MODEL = os.environ.get("MARINE_LLM_MODEL", "claude-opus-5")
CLI_MODEL = os.environ.get("MARINE_CLI_MODEL")

# ---------------------------------------------------------------- 모델이 채우는 형식
PageType = Literal["cover", "narrative", "spec_list", "dimension_table", "drawing", "contact", "other"]


class PageKind(BaseModel):
    kind: PageType = Field(description="the main content of the page")
    has_table: bool = Field(description="the page contains a numeric data table (rows and columns of values)")
    has_text: bool = Field(description="the page contains descriptive sentences, bullets or lists of standards, materials, options or features that are NOT part of a data table. "
                                       "Table titles, column headers, unit labels and NOTE/footnote lines under a table do not count")


class CatalogTable(BaseModel):
    caption: str = Field(description="table title exactly as printed")
    unit: Optional[str] = None
    columns: list[str] = Field(description="one label per column, exactly as printed. If a group header spans several columns, write 'GROUP / column'")
    rows: list[list[Optional[str]]] = Field(description="one list per table row, same length and order as columns. null for '-' or empty cells")


class TablePage(BaseModel):
    tables: list[CatalogTable]
    notes: list[str] = Field(default_factory=list, description="NOTE lines and footnotes under the tables, exactly as printed")


class CatalogFact(BaseModel):
    category: str = Field(description="section heading, e.g. face-to-face (wafer/lug), end flange, operating, testing, body, disc")
    availability: Literal["STANDARD", "OPTION", "NOT_STATED"] = Field(description="which column the item is in when the page has STANDARD and OPTION columns")
    statement: str = Field(description="the item or sentence exactly as printed")
    standard: Optional[str] = Field(default=None, description="standard/spec name incl. table numbers, if the item names one")
    classes: list[str] = Field(default_factory=list, description="pressure classes / K / PN ratings listed for this item")
    size_range_inch: Optional[str] = None
    note: Optional[str] = None


class FactPage(BaseModel):
    facts: list[CatalogFact]


class Uncovered(BaseModel):
    text: str = Field(description="the sentence, bullet or heading exactly as printed")
    contains_spec_info: bool
    reason: str


class UncoveredPage(BaseModel):
    uncovered: list[Uncovered]


PROMPTS = {
    "classify": ("You classify one scanned page of a manufacturer valve catalog. Judge only what is printed on the page.", PageKind),
    "table": ("You transcribe tables from a scanned catalog page image. Copy every cell exactly as printed. Use null for cells that show '-' or are empty. "
              "Never guess or compute a value; if a digit is unclear give your best reading. Return every row of every table, and the NOTE lines under the tables.", TablePage),
    "facts": ("You extract structured facts from a scanned manufacturer catalog page image. The page may show STANDARD and OPTION columns; record which column each item belongs to "
              "(NOT_STATED when the page has no such columns). Copy statements, standard names, table numbers, classes and size ranges exactly as printed. "
              "Do not add information that is not on the page, and do not infer pressure or temperature ratings. "
              "Create one fact per distinct item: per (standard, class group, size range) for rating lists, and one per statement for sentences, bullets and design features.", FactPage),
    "audit": ("You audit an extraction. You are given a scanned catalog page image and the list of facts already extracted from it. "
              "List every printed sentence, bullet or heading on the page that is NOT represented in the extracted list, copied exactly as printed. "
              "For each, say whether it states a technical specification, design requirement or product feature relevant to selecting a valve. "
              "Do not repeat items that are already covered. Do not invent text.", UncoveredPage),
}

M = TypeVar("M", bound=BaseModel)


class Reader(Protocol):
    name: str

    def call(self, kind: str, image: PageImage, model: type[M], extra: str = "") -> M: ...


# ---------------------------------------------------------------- 읽기 구현
class CliReader:
    """`claude -p` 로 읽는다: 임시 폴더에 이미지를 두고 Read 도구만 허용한다."""
    name = "cli"

    @staticmethod
    def available() -> bool:
        return shutil.which("claude") is not None

    def call(self, kind: str, image: PageImage, model: type[M], extra: str = "") -> M:
        system, _ = PROMPTS[kind]
        tmp = tempfile.mkdtemp(prefix="catalog_")
        try:
            f = Path(tmp) / f"page_{image.page}.{'png' if image.mime == 'image/png' else 'webp' if image.mime == 'image/webp' else 'jpg'}"
            f.write_bytes(image.data)
            cmd = ["claude", "-p", "--output-format", "json", "--tools", "Read", "--allowedTools", "Read", "--add-dir", tmp,
                   "--no-session-persistence", "--system-prompt", system, "--json-schema", json.dumps(model.model_json_schema())]
            if CLI_MODEL:
                cmd += ["--model", CLI_MODEL]
            prompt = f"Read the image file {f} with the Read tool and follow the instructions.{extra}"
            try:
                proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT, cwd=tmp)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"CLI 응답 시간 초과({TIMEOUT}초)")
            try:
                res = parse_output(proc.stdout)
            except json.JSONDecodeError:
                raise RuntimeError(f"CLI 출력을 해석하지 못했습니다: {(proc.stderr or proc.stdout)[:200]}")
            if res.get("is_error") or res.get("structured_output") is None:
                raise RuntimeError(f"CLI 실행 실패: {str(res.get('result') or proc.stderr)[:200]}")
            return model.model_validate(res["structured_output"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ApiReader:
    """Claude API(이미지 입력)로 읽는다. 서버 배포용 — 스텁 테스트만 했고 실제 호출은 검증하지 못했다."""
    name = "api"

    def __init__(self, client=None):
        self.client = client

    def call(self, kind: str, image: PageImage, model: type[M], extra: str = "") -> M:
        import anthropic
        client = self.client or anthropic.Anthropic()
        system, _ = PROMPTS[kind]
        content = [{"type": "image", "source": {"type": "base64", "media_type": image.mime,
                                                "data": base64.standard_b64encode(image.data).decode("utf-8")}},
                   {"type": "text", "text": f"Follow the instructions for this page image.{extra}"}]
        resp = client.messages.parse(model=MODEL, max_tokens=16000, system=system,
                                     messages=[{"role": "user", "content": content}], output_format=model)
        if resp.stop_reason == "refusal":
            raise RuntimeError("모델이 요청을 거절했습니다(refusal)")
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            raise RuntimeError("모델 응답이 잘렸거나 형식을 만족하지 못했습니다")
        return resp.parsed_output


# ---------------------------------------------------------------- 결과
class CellFlag(BaseModel):
    row: int
    column: str
    values: list[Optional[str]]          # 읽기별 값
    majority: Optional[str] = None       # 과반 값. 과반이 '빈칸'이면 None 이지만 resolved=True
    resolved: bool = True                # False 면 과반이 없어 값을 비웠다(담당자 확인 필요)


class TableResult(BaseModel):
    caption: str
    unit: Optional[str] = None
    columns: list[str]
    rows: list[list[Optional[str]]]      # 과반 값으로 채운 표. 과반이 없는 셀은 None
    flags: list[CellFlag] = Field(default_factory=list)
    issues: list[dict] = Field(default_factory=list)   # 구조 검사 결과(Issue)
    reads: int = 1


class PageResult(BaseModel):
    page: int
    kind: str
    tables: list[TableResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    facts: list[CatalogFact] = Field(default_factory=list)
    missing: list[Uncovered] = Field(default_factory=list)   # 누락 확인에서 추출 목록에 없다고 나온 사양 관련 문장
    warnings: list[str] = Field(default_factory=list)


class CatalogResult(BaseModel):
    file: str
    method: str
    pageCount: int
    pages: list[PageResult]
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- 표 합의
def _raw(v) -> Optional[str]:
    """표시용 원문 표기(공백 정리). 빈칸·'-'는 None."""
    return None if normalize(v) is None else " ".join(str(v).split())


def _size_cols(columns: list[str]) -> tuple[Optional[int], Optional[int]]:
    inch = next((i for i, c in enumerate(columns) if "inch" in c.lower()), None)
    mm = next((i for i, c in enumerate(columns) if c.lower().strip().endswith("mm") and "inch" not in c.lower()), None)
    return inch, mm


def merge_table_reads(reads: list[CatalogTable]) -> TableResult:
    """같은 표를 여러 번 읽은 결과를 합친다. 행·열 수가 가장 많이 나온 형태를 기준으로 삼는다."""
    shape = Counter((len(t.columns), len(t.rows)) for t in reads).most_common(1)[0][0]
    use = [t for t in reads if (len(t.columns), len(t.rows)) == shape]
    base = use[0]
    warnings = []
    if len(use) < len(reads):
        warnings.append({"kind": "shape", "severity": "error", "detail": f"읽기 {len(reads)}회 중 {len(reads) - len(use)}회는 행·열 수가 달라 비교에서 제외했습니다"})
    ncol = shape[0]
    flat = [{(0, r, c): normalize(t.rows[r][c] if c < len(t.rows[r]) else None) for r in range(len(t.rows)) for c in range(ncol)} for t in use]
    raw = [{(0, r, c): _raw(t.rows[r][c] if c < len(t.rows[r]) else None) for r in range(len(t.rows)) for c in range(ncol)} for t in use]
    votes = compare_reads(flat)

    def show(key, val):      # 채택한 값의 원문 표기(200.0 을 200 으로 바꾸지 않는다)
        return next((r[key] for f, r in zip(flat, raw) if f[key] == val and r[key] is not None), None if val is None else str(val))

    rows: list[list[Optional[str]]] = [[None] * ncol for _ in range(shape[1])]
    flags = []
    for key, v in votes.items():
        _, r, c = key
        rows[r][c] = None if v.flagged and not v.has_majority else show(key, v.majority if v.flagged else v.values[0])
        if v.flagged:
            flags.append(CellFlag(row=r, column=base.columns[c], values=[r_[key] for r_ in raw], resolved=v.has_majority,
                                  majority=None if not v.has_majority else show(key, v.majority)))
    flags.sort(key=lambda f: (f.row, f.column))
    # 구조 검사: inch/mm 열이 있는 표만
    issues: list[Issue] = []
    inch_i, mm_i = _size_cols(base.columns)
    if inch_i is not None and mm_i is not None:
        recs = [{"size_inch": r[inch_i], "size_mm": r[mm_i], **{base.columns[c]: r[c] for c in range(ncol)}} for r in rows]
        numeric = [base.columns[c] for c in range(ncol) if c not in (inch_i, mm_i)
                   and all(to_number(r[c]) is not None for r in rows if r[c] is not None) and any(r[c] is not None for r in rows)]
        issues = check_table(base.caption, recs, monotonic=numeric)
    return TableResult(caption=base.caption, unit=base.unit, columns=base.columns, rows=rows, flags=flags,
                       issues=warnings + [i.__dict__ for i in issues], reads=len(use))


def merge_tables(pages: list[TablePage]) -> tuple[list[TableResult], list[str]]:
    """읽기 여러 회(TablePage 목록)를 표 순서대로 짝지어 합친다. 표 개수가 다르면 가장 많이 나온 개수만 쓴다."""
    ntab = Counter(len(p.tables) for p in pages).most_common(1)[0][0]
    use = [p for p in pages if len(p.tables) == ntab]
    warn = [] if len(use) == len(pages) else [f"읽기 {len(pages)}회 중 {len(pages) - len(use)}회는 표 개수가 달라 제외했습니다"]
    return [merge_table_reads([p.tables[i] for p in use]) for i in range(ntab)], warn


# ---------------------------------------------------------------- 파이프라인
def _parallel(fn, n: int) -> list:
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(lambda _: fn(), range(n)))


def _table_shape_warnings(tables: list[TableResult]) -> list[str]:
    """행·열 수가 어긋난 읽기와, 같은 종류의 표(Class만 다른 표)끼리 열 수가 다른 경우를 경고한다.
    다수가 같은 실수를 하면 맞는 소수 읽기가 제외될 수 있으므로(예: 열 하나를 통째로 빠뜨림) 조용히 넘기지 않는다."""
    out = []
    for t in tables:
        for i in t.issues:
            if i.get("kind") == "shape":
                out.append(f"표 '{t.caption}': {i['detail']}. 제외된 쪽이 맞을 수 있으니 열·행 수를 원문과 대조하세요")
    groups: dict[str, list[TableResult]] = {}
    for t in tables:
        groups.setdefault(re.sub(r"CLASS\s*\d+", "", t.caption, flags=re.I).strip(" -/"), []).append(t)
    for key, ts in groups.items():
        if len(ts) > 1 and len({len(t.columns) for t in ts}) > 1:
            shapes = ", ".join(f"{t.caption.rsplit('/', 1)[-1].strip()}: {len(t.columns)}열" for t in ts)
            out.append(f"같은 종류의 표('{key}')인데 열 수가 서로 다릅니다({shapes}). 열이 빠졌을 수 있으니 원문과 대조하세요")
    return out


def read_page(image: PageImage, reader: Reader, *, table_reads: int = 2) -> PageResult:
    kind = reader.call("classify", image, PageKind)
    out = PageResult(page=image.page, kind=kind.kind)
    if kind.kind in ("cover", "contact"):      # 표지·연락처에는 후보 판정에 쓸 사양이 없다
        return out
    if kind.has_table:
        reads = _parallel(lambda: reader.call("table", image, TablePage), max(2, table_reads))
        tables, warn = merge_tables(reads)
        out.warnings += warn
        if any(not f.resolved for t in tables for f in t.flags):      # 2회 읽기에서 어긋나 과반이 없음 → 세 번째로 과반을 만든다
            reads.append(reader.call("table", image, TablePage))
            tables, warn = merge_tables(reads)
            out.warnings += warn
        out.tables = tables
        out.warnings += _table_shape_warnings(tables)
        out.notes = [n for p in reads[:1] for n in p.notes]
        for t in tables:
            bad = [f for f in t.flags if not f.resolved]
            if bad:
                out.warnings.append(f"표 '{t.caption}': 읽기끼리 끝내 일치하지 않은 셀 {len(bad)}개를 비워 두었습니다. 원문 확인 필요")
    if kind.has_text:
        facts = reader.call("facts", image, FactPage).facts
        out.facts = facts
        digest = "\n".join(f"{f.availability} | {f.category} | {f.statement} | {','.join(f.classes)} | {f.size_range_inch or ''}" for f in facts)
        unc = reader.call("audit", image, UncoveredPage, extra=f"\n\nAlready extracted facts:\n{digest or '(none)'}").uncovered
        out.missing = [u for u in unc if u.contains_spec_info]
        if out.missing:
            out.warnings.append(f"추출에서 빠진 사양 관련 문장 {len(out.missing)}개가 있습니다(missing). 원문 확인 필요")
    return out


def read_catalog(images: list[PageImage], reader: Reader, file: str, *, page_count: int, table_reads: int = 2, workers: int = 3) -> CatalogResult:
    """images 의 각 쪽을 읽는다. 쪽별 실패는 그 쪽의 경고로 남기고 나머지는 계속한다."""
    def one(img: PageImage) -> PageResult:
        try:
            return read_page(img, reader, table_reads=table_reads)
        except Exception as e:   # noqa: BLE001 — 쪽 하나의 실패가 전체를 막지 않게
            return PageResult(page=img.page, kind="error", warnings=[f"이 쪽을 읽지 못했습니다({type(e).__name__}: {e})"])
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        pages = list(ex.map(one, images))
    warnings = [] if images else ["이미지를 꺼낼 수 있는 쪽이 없습니다(스캔 PDF가 아니거나 지원하지 않는 이미지 형식)."]
    warnings.append("스캔 카탈로그를 AI가 이미지로 읽은 결과입니다. 표시된 셀·누락 문장과 후보로 확정하는 값은 원문과 대조하세요.")
    return CatalogResult(file=file, method=reader.name, pageCount=page_count, pages=pages, warnings=warnings)


def api_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def pick_reader(mode: str = "auto") -> Optional[Reader]:
    """auto: API 키가 있으면 API, 없으면 로그인된 CLI. 사용할 수 있는 방법이 없으면 None."""
    if mode == "api" or (mode == "auto" and api_available()):
        return ApiReader() if api_available() else None
    if mode in ("cli", "auto") and CliReader.available():
        return CliReader()
    return None


def parse_pages(spec: str, page_count: int) -> Optional[list[int]]:
    """'3,9,12-14' → [3, 9, 12, 13, 14]. 빈 문자열이면 None(전체). 범위를 벗어나면 ValueError."""
    spec = (spec or "").strip()
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if lo < 1 or hi > page_count or lo > hi:
            raise ValueError(f"쪽 번호 '{part}' 가 문서 범위(1~{page_count})를 벗어났습니다")
        out += range(lo, hi + 1)
    return sorted(set(out))
