# 추출 정확도 평가 — rules

- 문서 5건 · 채점 항목 39개 (표본이 작아 통계적 수치가 아님)
- 정답 31 · 오답 2 · 누락 4 · 없음 정답 2
- 값을 뽑은 항목 중 정확도(precision): 31/33 = 94%
- 정답이 있는 항목 중 재현율(recall): 31/37 = 84%
- 오답 중 경고(flagged)로 검출: 0 · **조용한 오류(경고 없음): 2**

| 문서 | cert.authority | cert.certNo | cert.validUntil | nominal_diameter | flange_standard | body_material | temp_max | design_pressure |
|---|---|---|---|---|---|---|---|---|
| unicom_DNV_TAP00000MH.pdf (rules) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓(없음) |
| victaulic_DNV_TAP000012E.pdf (rules) | ✓ | ✓ | ✓ | ✓ | ✓ | ∅ | ✗ | ✓ |
| xurox_DNV_type_approval.pdf (rules) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ∅ | ✓(없음) |
| abo_LR_type_approval_2E.pdf (rules) | ✓ | ✓ | ✓ | ✓ | ✗ | – | ∅ | ✓ |
| witzel_type_approval_55.pdf (rules) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ∅ | ✓ |

## 오답·누락 상세

- `victaulic_DNV_TAP000012E.pdf` · body_material: **MISSING** — -
- `victaulic_DNV_TAP000012E.pdf` · temp_max: **WRONG** — 120 (정답 82)
- `xurox_DNV_type_approval.pdf` · temp_max: **MISSING** — -
- `abo_LR_type_approval_2E.pdf` · flange_standard: **WRONG** — 누락 ['ASME_150'] / 초과 []
- `abo_LR_type_approval_2E.pdf` · temp_max: **MISSING** — -
- `witzel_type_approval_55.pdf` · temp_max: **MISSING** — -