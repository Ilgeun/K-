from typing import Optional

from pydantic import BaseModel, Field

from .models import Cert, Restriction, Spec


class Note(BaseModel):
    page: int
    text: str


class Extraction(BaseModel):
    file: str
    method: str                       # rules | llm
    pageCount: int
    specs: list[Spec] = Field(default_factory=list)
    certs: list[Cert] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list)
    restrictions: list[Restriction] = Field(default_factory=list)   # 사용 제한 조건(해석 결과, 확정 전)
    warnings: list[str] = Field(default_factory=list)
    flagged: list[str] = Field(default_factory=list)   # 규칙 추출과 불일치하거나 LLM 단독인 항목(field) — 기본 선택 해제
    model: Optional[str] = None
    scanned: bool = False                  # 글자 레이어가 없는 스캔 PDF(규칙·텍스트 추출로는 읽을 수 없음)
    productType: Optional[str] = None      # 문서가 다루는 제품 종류(예: Butterfly Valves, Check Valve)
