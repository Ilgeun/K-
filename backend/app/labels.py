"""화면·사유 문구에 쓰는 한글 라벨."""

FIELD_LABEL = {
    "nominal_diameter": "구경", "design_pressure": "설계압력", "body_material": "본체 재질",
    "flange_standard": "플랜지 규격", "class_approval": "선급 형식승인", "temp_max": "최고 사용온도",
    "lead_time_days": "납기", "actuator_type": "구동 방식", "usage_restriction": "사용 제한(문서 기반)",
}
VALUE_LABEL = {
    "NAB": "니켈알루미늄청동(NAB)", "DUPLEX_SS": "듀플렉스 스테인리스", "DI_RUBBER_LINED": "고무라이닝 덕타일주철",
    "CAST_IRON": "주철", "DUCTILE_IRON": "덕타일주철", "WCB": "탄소강 주강(WCB)", "CF8": "스테인리스 주강(CF8)", "CF8M": "스테인리스 주강(CF8M)",
    "SS304": "스테인리스 304", "SS316": "스테인리스 316",
    "JIS_10K": "JIS 10K", "JIS_5K": "JIS 5K", "JIS_16K": "JIS 16K", "JIS_20K": "JIS 20K",
    "PN10": "EN PN10", "PN16": "EN PN16", "ASME_150": "ASME Class 150",
    "MANUAL_GEAR": "수동(기어)", "PNEUMATIC": "공압",
}
OP_TEXT = {"=": "일치", "gte": "이상", "lte": "이하", "in": "다음 중 하나", "includes": "보유"}


def label(v: str) -> str:
    return VALUE_LABEL.get(v, v)


def fmt_val(v: str, unit: str = "") -> str:
    u = unit.replace("degC", "°C").replace("day", "일")
    return f"{label(v)}{' ' + u if u else ''}"


def req_text(op: str, value: str, unit: str) -> str:
    if op == "in":
        return " / ".join(label(x) for x in value.split("|"))
    if op == "includes" and "|" in value:
        return " / ".join(value.split("|")) + " 중 하나 보유"
    return f"{fmt_val(value, unit)} {OP_TEXT[op]}"
