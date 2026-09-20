from pathlib import Path

from pypdf import PdfReader


def read_pages(path: Path) -> list[str]:
    """페이지별 텍스트. 스캔본이면 빈 문자열이 나온다."""
    reader = PdfReader(str(path))
    return [(p.extract_text() or "") for p in reader.pages]
