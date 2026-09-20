# 사용 제한 조건 추출 평가 — rules

- 문서 5건 · 정답 라벨 35건 (표본이 작아 통계적 수치가 아님)
- **재현율: 27/35 = 77%**
- 추출한 제한 32건 중 금지(PROHIBITED) 20건
- 근거 없는 금지(라벨과 일치하지 않는 금지 추출, 엄격 기준): 6건

### 판정 영향 기준 (결과를 본 뒤 추가한 지표 — 조건부/특정 구성 한정 금지는 엔진에서 ‘주의’로 같게 처리되므로 효과 등급으로 비교)

- **판정 효과 일치 재현율: 27/35 = 77%**
- **근거 없는 ‘제외’(제품 전체·재질 범위 금지로 잘못 추출 → 판정에서 부당하게 제외될 수 있는 항목): 6건**

| 문서 | 재현(엄격) | 재현(판정 효과) | 근거 없는 금지(엄격) | 근거 없는 ‘제외’ | 추출 수 |
|---|---|---|---|---|---|
| unicom_DNV_TAP00000MH.pdf (rules) | 3/3 | 3/3 | 0 | 0 | 3 |
| victaulic_DNV_TAP000012E.pdf (rules) | 5/8 | 5/8 | 3 | 3 | 9 |
| xurox_DNV_type_approval.pdf (rules) | 4/5 | 4/5 | 0 | 0 | 5 |
| abo_LR_type_approval_2E.pdf (rules) | 5/7 | 5/7 | 0 | 0 | 3 |
| witzel_type_approval_55.pdf (rules) | 10/12 | 10/12 | 3 | 3 | 12 |

## 근거 없는 ‘제외’ 항목(판정 효과 기준)

- `victaulic_DNV_TAP000012E.pdf` p.2 ['hydrocarbon'] mat=[]: “Under static head fitted on external wall  of tanks for fuel and flammable oils”
- `victaulic_DNV_TAP000012E.pdf` p.2 ['ballast', 'cargo_oil'] mat=[]: “Ballast lines to forward tanks through cargo oil tanks”
- `victaulic_DNV_TAP000012E.pdf` p.2 ['ballast', 'bilge'] mat=[]: “Bilge and ballast piping in tunnels in double bottom”
- `witzel_type_approval_55.pdf` p.3 ['hydrocarbon'] mat=['CAST_IRON']: “Fitted to tanks containing flammable oil under static pressure.”
- `witzel_type_approval_55.pdf` p.4 ['bilge'] mat=[]: “Application in bilge system of passengerships is not allowed.”
- `witzel_type_approval_55.pdf` p.4 ['hydrocarbon'] mat=[]: “Application of ‘fire-tested’ butterfly valve in flammable liquid systems (with f.p. > 60 d”

## 누락(엄격 기준, 라벨 대비)

- `victaulic_DNV_TAP000012E.pdf` V6 [PROH ['ballast']]: 화물유 탱크를 통과해 선수 탱크로 가는 밸러스트 라인(위치 조건)
- `victaulic_DNV_TAP000012E.pdf` V7 [PROH ['bilge']]: 이중저 터널 내 빌지·밸러스트 배관(위치 조건)
- `victaulic_DNV_TAP000012E.pdf` V8 [PROH ['fuel_oil', 'hydrocarbon']]: 연료·인화성 유 탱크 외벽 정수두 위치(위치 조건)
- `xurox_DNV_type_approval.pdf` X4 [PROH ['hydrocarbon']]: EPDM·HYPALON 시트는 탄화수소 서비스 불가(시트 재질 조건)
- `abo_LR_type_approval_2E.pdf` A2 [COND ['cargo_oil', 'lng_lpg']]: 화물 라인은 in-line 밸브로, 압력·온도·매체에 따라
- `abo_LR_type_approval_2E.pdf` A3 [COND ['fuel_oil']]: 윤활유·연료유 배관은 화재 위험이 낮은 구역, 금속·내화 시트
- `witzel_type_approval_55.pdf` W6 [PROH ['bilge']]: 여객선의 빌지 계통 적용 불가(선종 조건, p.4)
- `witzel_type_approval_55.pdf` W7 [COND ['bilge']]: 빌지 주관·지관 적용은 기관실 펌프 흡입 등으로 제한(p.4)

## 근거 없는 금지(라벨과 불일치한 PROHIBITED)

- `victaulic_DNV_TAP000012E.pdf` p.2 ['hydrocarbon'] mat=[] other=None: “Under static head fitted on external wall  of tanks for fuel and flammable oils”
- `victaulic_DNV_TAP000012E.pdf` p.2 ['ballast', 'cargo_oil'] mat=[] other=None: “Ballast lines to forward tanks through cargo oil tanks”
- `victaulic_DNV_TAP000012E.pdf` p.2 ['ballast', 'bilge'] mat=[] other=None: “Bilge and ballast piping in tunnels in double bottom”
- `witzel_type_approval_55.pdf` p.3 ['hydrocarbon'] mat=['CAST_IRON'] other=None: “Fitted to tanks containing flammable oil under static pressure.”
- `witzel_type_approval_55.pdf` p.4 ['bilge'] mat=[] other=None: “Application in bilge system of passengerships is not allowed.”
- `witzel_type_approval_55.pdf` p.4 ['hydrocarbon'] mat=[] other=None: “Application of ‘fire-tested’ butterfly valve in flammable liquid systems (with f.p. > 60 d”