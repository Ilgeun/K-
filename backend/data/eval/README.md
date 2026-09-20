# 평가용 실제 승인서 (저장소에는 PDF를 넣지 않음)

`backend/eval/` 의 정확도 평가(`python -m eval.run_eval`, `python -m eval.run_eval_restrictions`)는 이 폴더의 PDF 5건을 사용한다.
제3자(선급·제조사)가 공개한 문서라 **저장소에는 넣지 않았다**(`.gitignore`). 재현하려면 아래 출처에서 받아 아래 파일명으로 이 폴더에 둔다.

| 파일명 | 발행 | 제품 | 출처 |
|---|---|---|---|
| `unicom_DNV_TAP00000MH.pdf` | DNV | Korea Unicomvalve High-Seal (버터플라이) | https://approvalfinder.dnv.com/api/approval/document?id=TAP00000MH (`backend/data/docs/` 에 동일 문서가 있음) |
| `victaulic_DNV_TAP000012E.pdf` | DNV | Victaulic Series 716/716H (체크 밸브) | https://assets.victaulic.com/assets/uploads/literature/Approvals/Maritime_DNVGL_TAP000012E_716_716H.pdf |
| `xurox_DNV_type_approval.pdf` | DNV GL | COVALMA XUROX (버터플라이) | https://xurox.com/wp-content/uploads/2020/02/DNV-GL-TYPE-APPROVAL-.pdf |
| `abo_LR_type_approval_2E.pdf` | Lloyd's Register | ABO valve Series 2E (버터플라이) | https://www.abovalve.com/media/cache/file/14/ABO-Lloyds-Registr-Serie-2E.pdf |
| `witzel_type_approval_55.pdf` | Lloyd's Register | Wouter Witzel EV 시리즈 (버터플라이) | https://wouterwitzel.nl/wp-content/uploads/2021/10/55.pdf |

- 링크는 2026-09-19 시점에 받은 곳이며, 이후 바뀌었을 수 있다.
- 정답 라벨: `backend/eval/labels.json`, `backend/eval/labels_restrictions.json` (사람 검수 전).
- `witzel_type_approval_55.pdf` 는 AES 암호화되어 있어 `cryptography` 패키지가 필요하다(`requirements.txt` 에 포함).
