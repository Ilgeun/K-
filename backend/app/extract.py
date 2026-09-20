"""추출 오케스트레이터: LLM(가능하면) → 규칙 기반 폴백, 두 결과 교차검증."""
import os
from pathlib import Path
from typing import Literal

import anthropic

from . import extract_cli, extract_llm, extract_rules
from .extract_types import Extraction
from .pdf import is_scanned, read_pages

Mode = Literal["auto", "llm", "cli", "rules"]


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _same(a: str, b: str) -> bool:
    return set(a.split("|")) == set(b.split("|"))


def _cross_check(primary: Extraction, rules: Extraction) -> None:
    """LLM 결과를 규칙 추출과 교차검증한다. 불일치·LLM 단독 항목은 flagged 로 표시해 기본 선택에서 뺀다."""
    by_field = {s.field: s for s in rules.specs}
    for s in primary.specs:
        r = by_field.get(s.field)
        if s.value == "UNKNOWN":
            primary.flagged.append(s.field)
        elif r is None:
            primary.flagged.append(s.field)
            primary.warnings.append(f"{s.field}: LLM만 추출했고 규칙 기반에서는 확인되지 않았습니다({s.value}). 원문과 반드시 대조하세요")
        elif not _same(r.value, s.value):
            primary.flagged.append(s.field)
            primary.warnings.append(f"{s.field}: LLM 값({s.value})과 규칙 추출 값({r.value})이 다릅니다. 원문 확인 필요")
    llm_fields = {s.field for s in primary.specs}
    for r in rules.specs:
        if r.field not in llm_fields:
            primary.warnings.append(f"{r.field}: 규칙 추출에서만 발견됨({r.value}). 원문 확인 필요")
    rule_certs = {c.certNo: c for c in rules.certs}
    for c in primary.certs:
        r = rule_certs.get(c.certNo)
        if r and r.validUntil != c.validUntil:
            primary.flagged.append(f"cert:{c.certNo}")
            primary.warnings.append(f"인증서 {c.certNo}: 유효기간이 LLM({c.validUntil})과 규칙({r.validUntil})에서 다릅니다. 원문 확인 필요")


def cli_available() -> bool:
    return extract_cli.available()


def run(path: Path, file_name: str, mode: Mode = "auto", client=None) -> Extraction:
    """auto: Claude API 키가 있으면 API, 없으면 Claude CLI, 둘 다 없으면 규칙 기반."""
    pages = read_pages(path)
    rules = extract_rules.extract(pages, file_name)
    if is_scanned(pages) and mode in ("auto", "cli", "rules"):
        # 글자 레이어가 없는 스캔본: 텍스트 추출 경로로는 읽을 수 없다. 카탈로그 읽기(이미지) 경로로 안내한다.
        rules.scanned = True
        rules.warnings.insert(0, "스캔 이미지 PDF입니다(글자 없음). 이 경로로는 읽을 수 없으니 ‘스캔 카탈로그 읽기’(쪽을 골라 이미지로 읽기)를 사용하세요.")
        return rules
    if mode == "auto":
        mode = "llm" if (client is not None or llm_available()) else "cli" if cli_available() else "rules"
        if mode == "rules":
            rules.warnings.insert(0, "Claude API 키와 CLI가 없어 규칙 기반 추출을 사용했습니다.")
    if mode == "rules":
        return rules
    def call() -> Extraction:
        return (extract_cli.extract(pages, file_name) if mode == "cli"
                else extract_llm.extract(pages, file_name, client=client, pdf_path=path))

    try:
        out = call()
    except (anthropic.APIError, RuntimeError, OSError) as e:  # 인증 실패·거절·잘림·CLI 오류는 규칙 추출로 폴백
        rules.warnings.insert(0, f"{'CLI' if mode == 'cli' else 'LLM'} 추출 실패({type(e).__name__}: {e}) — 규칙 기반 추출로 대체했습니다.")
        return rules
    if not out.restrictions and any(r.kind == "PROHIBITED" for r in rules.restrictions):
        # 규칙 기반은 금지 후보를 찾았는데 AI가 하나도 못 찾았다면 LLM의 비결정적 누락일 수 있다 → 1회만 재시도
        try:
            retry = call()
            if retry.restrictions:
                retry.warnings.insert(0, "AI 해석이 처음에는 사용 제한을 찾지 못해 1회 재시도했습니다.")
                out = retry
        except (anthropic.APIError, RuntimeError, OSError):
            pass
    _cross_check(out, rules)
    covered = {c for r in out.restrictions for c in r.contexts if r.kind == "PROHIBITED"}
    for r in rules.restrictions:      # AI 해석이 놓친 금지 조건 후보를 경고로 알린다(항목으로 추가하지는 않는다)
        if r.kind == "PROHIBITED" and not set(r.contexts) & covered:
            out.warnings.append(f"규칙 추출에서만 발견된 금지 조건 후보(p.{r.page}, {'/'.join(r.contexts)}): “{r.quote[:60]}” — 원문 확인")
    out.productType = rules.productType   # 제품 종류·사용 제한은 규칙 추출이 문서 전체에서 읽은 값을 공유한다
    if not out.notes:
        out.notes = rules.notes
    return out


PART_KEYWORDS = {"버터플라이 밸브": "butterfly", "게이트 밸브": "gate", "글로브 밸브": "globe", "체크 밸브": "check"}


def check_part_type(ex: Extraction, part_type: str) -> None:
    """문서의 제품 종류가 등록 제품의 부품 종류와 다르면 경고한다(예: 체크 밸브 승인서를 버터플라이 제품에 업로드)."""
    want = PART_KEYWORDS.get(part_type)
    if ex.productType and want and want not in ex.productType.lower():
        ex.warnings.insert(0, f"이 문서의 제품 종류는 '{ex.productType}'로 보입니다. 이 제품({part_type})의 자료가 아닐 수 있으니 확인하세요.")
