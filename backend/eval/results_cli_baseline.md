# 추출 정확도 평가 — cli

- 문서 5건 · 채점 항목 39개 (표본이 작아 통계적 수치가 아님)
- 정답 35 · 오답 0 · 누락 2 · 없음 정답 2
- 값을 뽑은 항목 중 정확도(precision): 35/35 = 100%
- 정답이 있는 항목 중 재현율(recall): 35/37 = 95%
- 오답 중 경고(flagged)로 검출: 0 · **조용한 오류(경고 없음): 0**

| 문서 | cert.authority | cert.certNo | cert.validUntil | nominal_diameter | flange_standard | body_material | temp_max | design_pressure |
|---|---|---|---|---|---|---|---|---|
| unicom_DNV_TAP00000MH.pdf (cli) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓(없음) |
| victaulic_DNV_TAP000012E.pdf (cli) | ✓ | ✓ | ✓ | ✓ | ∅ | ✓ | ✓ | ✓ |
| xurox_DNV_type_approval.pdf (cli) | ✓ | ✓ | ✓ | ✓ | ✓ | ∅ | ✓ | ✓(없음) |
| abo_LR_type_approval_2E.pdf (cli) | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ |
| witzel_type_approval_55.pdf (cli) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## 오답·누락 상세

- `victaulic_DNV_TAP000012E.pdf` · flange_standard: **MISSING** — -
- `xurox_DNV_type_approval.pdf` · body_material: **MISSING** — -