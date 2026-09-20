"""도메인 모델. 필드명은 프론트엔드 JSON과 동일(camelCase)하게 유지한다."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field

Op = Literal["=", "gte", "lte", "in", "includes"]
Status = Literal["PASS", "FAIL", "UNKNOWN"]
Overall = Literal["MATCH", "CHECK", "EXCLUDED"]


class Requirement(BaseModel):
    id: str
    field: str
    op: Op
    value: str
    unit: str = ""
    mandatory: bool = True
    note: str = ""


class Spec(BaseModel):
    field: str
    value: str
    unit: str = ""
    raw: str = ""
    file: str = ""
    page: int = 1
    display: Optional[str] = None
    rangeMin: Optional[float] = None
    rangeMax: Optional[float] = None
    note: Optional[str] = None
    extractedBy: str = "seed"      # seed | rules | llm | manual
    confirmed: bool = True
    confirmedBy: Optional[str] = None
    confirmedAt: Optional[str] = None


class Cert(BaseModel):
    authority: str
    certNo: str
    validUntil: str
    file: str = ""
    page: int = 1
    extractedBy: str = "seed"
    confirmed: bool = True
    confirmedBy: Optional[str] = None
    confirmedAt: Optional[str] = None


RestrictionKind = Literal["PROHIBITED", "CONDITIONAL", "ADVISORY"]


class Restriction(BaseModel):
    """문서의 사용 제한 문장을 구조화한 것. 확정된 것만 판정에 쓴다."""
    kind: RestrictionKind                       # 금지 / 조건부 / 주의
    contexts: list[str]                         # 해당하는 사용 상황(contexts.CONTEXTS 어휘)
    materials: list[str] = Field(default_factory=list)   # 이 제한이 적용되는 본체 재질 코드(비면 제품 전체)
    scope_other: Optional[str] = None           # 본체 재질이 아닌 특정 구성에만 해당할 때(예: 시트 재질, 크기, 압력) 그 설명
    summary: str                                # 한국어 한 줄 요약(AI 해석)
    quote: str                                  # 근거 원문(문서에서 그대로)
    file: str = ""
    page: int = 1
    note: Optional[str] = None                  # 해석 근거·불확실성
    extractedBy: str = "seed"
    confirmed: bool = True
    confirmedBy: Optional[str] = None
    confirmedAt: Optional[str] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def key(self) -> str:
        import hashlib
        return hashlib.sha1(f"{self.file}|{self.page}|{self.quote}".encode()).hexdigest()[:10]


class RealSource(BaseModel):
    label: str
    url: str


class Product(BaseModel):
    id: str
    manufacturer: str
    model: str
    leadTime: Optional[int] = None
    leadTimeSource: str = ""
    leadTimeCheckedAt: str = ""
    scenario: str = ""
    expected: Optional[Literal["MATCH", "CHECK", "EXCLUDED"]] = None
    synthetic: bool = True
    partType: str = "버터플라이 밸브"
    real: Optional[RealSource] = None
    specs: list[Spec] = Field(default_factory=list)
    certs: list[Cert] = Field(default_factory=list)
    restrictions: list[Restriction] = Field(default_factory=list)


class Project(BaseModel):
    project_id: str
    ship_name: str
    class_society: str
    system: str
    part_type: str
    need_by_date: str
    ship_type: str = ""
    hull_no: str = ""
    replace_model: str = "A사 기존 모델"     # 교체 대상 기존 모델
    replace_reason: str = "납품 지연"        # 교체 사유
    is_synthetic: str = "true"


class Evidence(BaseModel):
    file: str
    page: int
    raw: str
    extractedBy: Optional[str] = None
    confirmedBy: Optional[str] = None
    confirmedAt: Optional[str] = None


class ReqResult(BaseModel):
    req: Requirement
    status: Status
    actual: str
    reason: str
    evidence: Optional[Evidence] = None


class Delivery(BaseModel):
    status: Status
    days: Optional[int]
    need: float
    reason: str
    source: str


class RestrictionFinding(BaseModel):
    level: Literal["BLOCK", "CAUTION"]
    kind: RestrictionKind
    summary: str
    reason: str
    contexts: list[str]
    quote: str
    file: str
    page: int
    extractedBy: Optional[str] = None
    confirmedBy: Optional[str] = None
    confirmedAt: Optional[str] = None


class Evaluation(BaseModel):
    restrictions: list[RestrictionFinding] = Field(default_factory=list)
    restrictionsReviewed: int = 0               # 판정에 쓴(확정된) 제한 조건 수
    items: list[ReqResult]
    overall: Overall
    failed: list[ReqResult]
    unknown: list[ReqResult]
    optionalMiss: list[ReqResult]
    delivery: Delivery
