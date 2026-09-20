export const FIELD_LABEL: Record<string, string> = {
  nominal_diameter: "구경", design_pressure: "설계압력", body_material: "본체 재질", flange_standard: "플랜지 규격",
  class_approval: "선급 형식승인", temp_max: "최고 사용온도", lead_time_days: "납기", actuator_type: "구동 방식", usage_restriction: "사용 제한(문서 기반)",
};
const VALUE_LABEL: Record<string, string> = {
  NAB: "니켈알루미늄청동(NAB)", DUPLEX_SS: "듀플렉스 스테인리스", DI_RUBBER_LINED: "고무라이닝 덕타일주철",
  CAST_IRON: "주철", DUCTILE_IRON: "덕타일주철", WCB: "탄소강 주강(WCB)", CF8: "스테인리스 주강(CF8)", CF8M: "스테인리스 주강(CF8M)", SS304: "스테인리스 304", SS316: "스테인리스 316", JIS_10K: "JIS 10K", PN16: "EN PN16", ASME_150: "ASME Class 150",
  MANUAL_GEAR: "수동(기어)", PNEUMATIC: "공압",
};
export const label = (v: string) => VALUE_LABEL[v] ?? v;
export const MATERIALS = ["NAB", "DI_RUBBER_LINED", "DUPLEX_SS", "CAST_IRON"];
export const FLANGES = ["JIS_10K", "PN16", "ASME_150"];
export const AUTHORITIES = ["DNV", "KR", "ABS", "LR", "NK", "BV"];
export const fmtVal = (v: string, unit: string) => `${label(v)}${unit ? " " + unit.replace("degC", "°C").replace("day", "일") : ""}`;
export const OP_TEXT: Record<string, string> = { "=": "일치", gte: "이상", lte: "이하", in: "다음 중 하나", includes: "보유" };
export const reqText = (r: { op: string; value: string; unit: string }) =>
  r.op === "in" ? r.value.split("|").map(label).join(" / ")
  : r.op === "includes" && r.value.includes("|") ? `${r.value.split("|").join(" / ")} 중 하나 보유`
  : `${fmtVal(r.value, r.unit)} ${OP_TEXT[r.op]}`;
/** 비교표·요구조건 머리말용 짧은 표기 (≥, ≤ 기호 포함) */
export const reqShort = (r: { op: string; value: string; unit: string }) =>
  r.op === "in" ? r.value.split("|").map(label).join(" / ")
  : r.op === "includes" ? r.value.split("|").join(" / ") + (r.value.includes("|") ? " 중 하나" : "")
  : `${r.op === "gte" ? "≥ " : r.op === "lte" ? "≤ " : ""}${fmtVal(r.value, r.unit)}`;
export const STATUS_TEXT = { MATCH: "조건 충족", CHECK: "확인 필요", EXCLUDED: "필수조건 미충족" } as const;
export const CHECK_TEXT = { PASS: "충족", FAIL: "미충족", UNKNOWN: "확인 필요" } as const;
export const KIND_TEXT = { PROHIBITED: "사용 불가", CONDITIONAL: "조건부", ADVISORY: "주의" } as const;
export const ctxText = (ctx: Record<string, string>, tags: string[]) => tags.map((t) => ctx[t] ?? t).join("·");
