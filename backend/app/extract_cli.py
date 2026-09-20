"""Claude Code CLI(`claude -p`) 기반 추출기 — API 키 없이 로그인된 Claude 계정으로 동작한다.

구조화 출력(--json-schema)을 쓰고, 결과는 API 경로와 같은 검증(원문 인용 확인)을 거친다.
도구는 모두 끄고(--tools "") 세션을 남기지 않으며, 프로젝트 파일을 읽지 않도록 임시 폴더에서 실행한다.
"""
import json
import os
import shutil
import subprocess
import tempfile

from .extract_llm import SYSTEM, LLMResult, build_extraction
from .extract_types import Extraction

TIMEOUT = int(os.environ.get("MARINE_CLI_TIMEOUT", "240"))
MODEL = os.environ.get("MARINE_CLI_MODEL")  # 비우면 CLI 기본 모델


def parse_output(stdout: str) -> dict:
    """CLI 표준출력에서 결과 JSON 을 꺼낸다. CLI 가 JSON 앞뒤에 로그 한 줄을 섞어 내보내는 경우가 간헐적으로 있어
    (예: 'Client.listTools() called but server does not advertise tools capability'), 통째로 파싱하지 않고 첫 JSON 객체만 읽는다."""
    text = stdout.lstrip()
    start = text.find("{")
    if start < 0:
        raise json.JSONDecodeError("JSON 객체가 없습니다", text, 0)
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def available() -> bool:
    return shutil.which("claude") is not None


def extract(pages: list[str], file: str) -> Extraction:
    if not any(p.strip() for p in pages):
        raise RuntimeError("스캔 PDF는 CLI 경로에서 지원하지 않습니다(텍스트 없음)")
    text = "\n\n".join(f"=== PAGE {i} ===\n{t}" for i, t in enumerate(pages, 1))
    cmd = ["claude", "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
           "--system-prompt", SYSTEM, "--json-schema", json.dumps(LLMResult.model_json_schema())]
    if MODEL:
        cmd += ["--model", MODEL]
    prompt = f"Document text:\n\n{text}\n\nExtract the specifications and certificates."
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT, cwd=tempfile.gettempdir())
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"CLI 응답 시간 초과({TIMEOUT}초)")
    try:
        res = parse_output(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"CLI 출력을 해석하지 못했습니다: {(proc.stderr or proc.stdout)[:200]}")
    if res.get("is_error") or res.get("structured_output") is None:
        raise RuntimeError(f"CLI 실행 실패: {str(res.get('result') or proc.stderr)[:200]}")
    usage = res.get("modelUsage", {})  # 여러 모델이 쓰일 수 있어 출력이 가장 많은 모델을 표기
    model = max(usage, key=lambda m: usage[m].get("outputTokens", 0), default=MODEL or "claude-cli")
    return build_extraction(LLMResult.model_validate(res["structured_output"]), pages, file, "cli", model)
