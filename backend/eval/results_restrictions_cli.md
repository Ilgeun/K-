# 사용 제한 조건 추출 평가 — cli

- 문서 5건 · 정답 라벨 35건 (표본이 작아 통계적 수치가 아님)
- **재현율: 31/35 = 89%**
- 추출한 제한 49건 중 금지(PROHIBITED) 19건
- 근거 없는 금지(라벨과 일치하지 않는 금지 추출, 엄격 기준): 4건

### 판정 영향 기준 (결과를 본 뒤 추가한 지표 — 조건부/특정 구성 한정 금지는 엔진에서 ‘주의’로 같게 처리되므로 효과 등급으로 비교)

- **판정 효과 일치 재현율: 33/35 = 94%**
- **근거 없는 ‘제외’(제품 전체·재질 범위 금지로 잘못 추출 → 판정에서 부당하게 제외될 수 있는 항목): 0건**

| 문서 | 재현(엄격) | 재현(판정 효과) | 근거 없는 금지(엄격) | 근거 없는 ‘제외’ | 추출 수 |
|---|---|---|---|---|---|
| unicom_DNV_TAP00000MH.pdf (cli) | 3/3 | 3/3 | 0 | 0 | 5 |
| victaulic_DNV_TAP000012E.pdf (cli) | 4/8 | 7/8 | 0 | 0 | 8 |
| xurox_DNV_type_approval.pdf (cli) | 5/5 | 5/5 | 0 | 0 | 9 |
| abo_LR_type_approval_2E.pdf (cli) | 7/7 | 7/7 | 1 | 0 | 9 |
| witzel_type_approval_55.pdf (cli) | 12/12 | 11/12 | 3 | 0 | 18 |

## 근거 없는 ‘제외’ 항목(판정 효과 기준)


## 누락(엄격 기준, 라벨 대비)

- `victaulic_DNV_TAP000012E.pdf` V4 [PROH ['fire_safe']]: 비금속 시트는 내화 아님, 내화 요구 계통에 설치 불가
- `victaulic_DNV_TAP000012E.pdf` V6 [PROH ['ballast']]: 화물유 탱크를 통과해 선수 탱크로 가는 밸러스트 라인(위치 조건)
- `victaulic_DNV_TAP000012E.pdf` V7 [PROH ['bilge']]: 이중저 터널 내 빌지·밸러스트 배관(위치 조건)
- `victaulic_DNV_TAP000012E.pdf` V8 [PROH ['fuel_oil', 'hydrocarbon']]: 연료·인화성 유 탱크 외벽 정수두 위치(위치 조건)

## 근거 없는 금지(라벨과 불일치한 PROHIBITED)

- `abo_LR_type_approval_2E.pdf` p.2 ['air'] mat=[] other='공기 수용기(air receiver)의 정지밸브 용도로는 승인 범위에서 제외됨': “Air piping (except as stop valves for air receivers) having a working  
           pressur”
- `witzel_type_approval_55.pdf` p.3 ['shipside'] mat=[] other='웨이퍼형, 러그형(플랜지리스) 밸브 타입': “Application of flangeless types (wafer, lug) is not allowed.”
- `witzel_type_approval_55.pdf` p.4 ['fire_safe'] mat=[] other='원격 폐쇄 요구 위치(예: 탱크 격리밸브)': “Application of ‘fire-tested’ EV-type butterfly valve, in positions where required to be  c”
- `witzel_type_approval_55.pdf` p.5 ['fire_safe'] mat=['CAST_IRON'] other='Fire Main Isolating Valve 적용, EVS/EVL/EVML/EVBS/EVTLS/EVFS, 50-400mm': “Valve body to be a ductile material with min. elongation of 12%.  
(Grey Cast Iron is not ”