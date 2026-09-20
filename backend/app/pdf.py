from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from pypdf import PdfReader


def read_pages(path: Path) -> list[str]:
    """페이지별 텍스트. 스캔본이면 빈 문자열이 나온다."""
    reader = PdfReader(str(path))
    return [(p.extract_text() or "") for p in reader.pages]


def is_scanned(pages: list[str]) -> bool:
    """글자 레이어가 사실상 없으면(모든 쪽이 거의 비어 있으면) 스캔 문서로 본다."""
    return not any(len(p.strip()) > 20 for p in pages)


@dataclass
class PageImage:
    page: int          # 1부터
    mime: str
    data: bytes


_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def page_images(path: Path, pages: Optional[Iterable[int]] = None) -> list[PageImage]:
    """쪽마다 들어 있는 이미지 중 가장 큰 것을 꺼낸다(스캔 PDF는 보통 쪽마다 이미지 1장).

    PDF를 새로 그려서(렌더링) 이미지로 만드는 것은 아니다 — 쪽에 이미지가 없거나 지원하지 않는 형식이면 그 쪽은 건너뛴다.
    """
    want = set(pages) if pages is not None else None
    out: list[PageImage] = []
    for i, p in enumerate(PdfReader(str(path)).pages, 1):
        if want is not None and i not in want:
            continue
        try:
            imgs = list(p.images)
        except Exception:      # 손상되었거나 지원하지 않는 이미지 필터
            continue
        best = max(imgs, key=lambda im: len(im.data), default=None)
        mime = _MIME.get(Path(best.name).suffix.lower()) if best else None
        if best and mime:
            out.append(PageImage(i, mime, best.data))
    return out
