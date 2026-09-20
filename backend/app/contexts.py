"""사용 제한 해석에 쓰는 '사용 상황(context)' 어휘와, 선박 사용 계통 → 상황 매핑.

주의: 계통→상황 매핑은 개발팀의 가정이다(현업 검증 전). 화면에서 그대로 보여 주고 사용자가 판단하게 한다.
"""

CONTEXT_LABEL = {
    "seawater": "해수", "freshwater": "청수", "ballast": "밸러스트", "bilge": "빌지", "fuel_oil": "연료유",
    "cargo_oil": "화물유", "lng_lpg": "LNG·LPG", "fire_safe": "내화(화재 안전) 요구 계통", "shipside": "선측·해수 흡입구(sea chest)",
    "collision_bulkhead": "충돌 격벽", "air": "공기 배관", "hydrocarbon": "탄화수소·인화성 유체",
}
CONTEXTS = list(CONTEXT_LABEL)

# 선박의 '사용 계통'(선박 등록 화면의 선택지) → 그 계통에서 해당하는 사용 상황
SYSTEM_CONTEXTS = {
    "해수 냉각": ["seawater"],
    "청수 냉각": ["freshwater"],
    "밸러스트": ["ballast", "seawater"],
    "소화": ["fire_safe"],
    "연료유": ["fuel_oil", "hydrocarbon"],
    "LNG 연료": ["lng_lpg"],
    "기타": [],
}

# 재질 범위 표기에 쓰는 코드 묶음
STAINLESS = ["CF8", "CF8M", "SS304", "SS316", "DUPLEX_SS"]
AUSTENITIC = ["CF8", "CF8M", "SS304", "SS316"]


def contexts_of(system: str) -> list[str]:
    return list(SYSTEM_CONTEXTS.get(system, []))
