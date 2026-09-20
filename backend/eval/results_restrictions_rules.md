# 사용 제한 조건 추출 평가 — rules

- 문서 5건 · 정답 라벨 35건 (표본이 작아 통계적 수치가 아님)
- **재현율: 31/35 = 89%**
- 추출한 제한 32건 중 금지(PROHIBITED) 19건
- 근거 없는 금지(라벨과 일치하지 않는 금지 추출, 엄격 기준): 1건

### 판정 영향 기준 (결과를 본 뒤 추가한 지표 — 조건부/특정 구성 한정 금지는 엔진에서 ‘주의’로 같게 처리되므로 효과 등급으로 비교)

- **판정 효과 일치 재현율: 30/35 = 86%**
- **근거 없는 ‘제외’(제품 전체·재질 범위 금지로 잘못 추출 → 판정에서 부당하게 제외될 수 있는 항목): 1건**

| 문서 | 재현(엄격) | 재현(판정 효과) | 근거 없는 금지(엄격) | 근거 없는 ‘제외’ | 추출 수 |
|---|---|---|---|---|---|
| unicom_DNV_TAP00000MH.pdf (rules) | 3/3 | 3/3 | 0 | 0 | 3 |
| victaulic_DNV_TAP000012E.pdf (rules) | 8/8 | 7/8 | 0 | 0 | 8 |
| xurox_DNV_type_approval.pdf (rules) | 4/5 | 4/5 | 0 | 0 | 5 |
| abo_LR_type_approval_2E.pdf (rules) | 5/7 | 5/7 | 0 | 0 | 3 |
| witzel_type_approval_55.pdf (rules) | 11/12 | 11/12 | 1 | 1 | 13 |

## 근거 없는 ‘제외’ 항목(판정 효과 기준)

- `witzel_type_approval_55.pdf` p.3 ['hydrocarbon'] mat=['CAST_IRON']: “Fitted to tanks containing flammable oil under static pressure.”

## 누락(엄격 기준, 라벨 대비)

- `xurox_DNV_type_approval.pdf` X4 [PROH ['hydrocarbon']]: EPDM·HYPALON 시트는 탄화수소 서비스 불가(시트 재질 조건)
- `abo_LR_type_approval_2E.pdf` A2 [COND ['cargo_oil', 'lng_lpg']]: 화물 라인은 in-line 밸브로, 압력·온도·매체에 따라
- `abo_LR_type_approval_2E.pdf` A3 [COND ['fuel_oil']]: 윤활유·연료유 배관은 화재 위험이 낮은 구역, 금속·내화 시트
- `witzel_type_approval_55.pdf` W7 [COND ['bilge']]: 빌지 주관·지관 적용은 기관실 펌프 흡입 등으로 제한(p.4)

## 근거 없는 금지(라벨과 불일치한 PROHIBITED)

- `witzel_type_approval_55.pdf` p.3 ['hydrocarbon'] mat=['CAST_IRON'] other=None: “Fitted to tanks containing flammable oil under static pressure.”