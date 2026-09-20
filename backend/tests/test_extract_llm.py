"""LLM 경로는 실제 API 없이 스텁 클라이언트로 검증한다 (환각 차단·폴백 동작)."""
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx

from app import extract as orchestrator
from app.extract_llm import LLMCert, LLMResult, LLMSpec

REAL = Path(__file__).parent.parent / "data" / "docs" / "DNV_TAP00000MH_UnicomValve.pdf"


class Stub:
    def __init__(self, parsed, stop="end_turn", exc=None):
        self.parsed, self.stop, self.exc = parsed, stop, exc
        self.messages = self

    def parse(self, **kw):
        if self.exc:
            raise self.exc
        return SimpleNamespace(parsed_output=self.parsed, stop_reason=self.stop)


def good():
    return LLMResult(
        specs=[LLMSpec(field="nominal_diameter", value="50-600", unit="mm", display="DN50 ~ DN600", page=1,
                       quote="Sizes: DN 50 to DN 600", range_min=50, range_max=600)],
        certs=[LLMCert(authority="DNV", cert_no="TAP00000MH", valid_until="2021-06-30", page=1, quote="TAP00000MH")])


def test_grounded_items_are_kept():
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(good()))
    assert ex.method == "llm"
    assert ex.specs[0].extractedBy == "llm" and ex.specs[0].confirmed is False
    assert ex.certs[0].certNo == "TAP00000MH"


def test_hallucinated_quote_is_dropped():
    bad = good()
    bad.specs.append(LLMSpec(field="design_pressure", value="25", unit="bar", display="25 bar", page=1,
                             quote="Design pressure: 25 bar"))  # 문서에 없는 문장
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(bad))
    assert all(s.field != "design_pressure" for s in ex.specs)
    assert any("제외" in w and "design_pressure" in w for w in ex.warnings)


def test_wrong_page_is_dropped():
    bad = good()
    bad.specs[0].page = 3   # 인용은 1쪽에만 있음
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(bad))
    assert not ex.specs


def test_disagreement_with_rules_is_warned():
    bad = good()
    bad.specs[0].value = "50-300"
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(bad))
    assert any("규칙 추출" in w for w in ex.warnings)


def test_llm_only_value_is_flagged_not_silently_trusted():
    # 실제 CLI 호출에서 관찰된 오류: PN 등급(PN25)을 설계압력 25 bar로 해석
    bad = good()
    bad.specs.append(LLMSpec(field="design_pressure", value="25", unit="bar", display="PN10 ~ PN25", page=1,
                             quote="Max. working press.: PN10, PN16, PN20, PN25"))
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(bad))
    assert "design_pressure" in ex.flagged
    assert any("LLM만 추출" in w and "design_pressure" in w for w in ex.warnings)


def test_same_values_in_different_order_are_not_flagged():
    ok = good()
    ok.specs.append(LLMSpec(field="body_material", value="WCB|CF8|CF8M", unit="", display="x", page=2,
                            quote="Body: ASTM A216 Gr. WCB and ASTM A351 Gr. CF8/CF8M"))
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(ok))
    assert "body_material" not in ex.flagged and not any("body_material" in w for w in ex.warnings)


def test_disagreement_flags_the_field():
    bad = good()
    bad.specs[0].value = "50-300"
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(bad))
    assert "nominal_diameter" in ex.flagged


def test_refusal_falls_back_to_rules():
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(good(), stop="refusal"))
    assert ex.method == "rules" and ex.warnings[0].startswith("LLM 추출 실패")


def test_api_error_falls_back_to_rules():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None)
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(None, exc=err))
    assert ex.method == "rules" and ex.certs


def test_auto_without_key_or_cli_uses_rules(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(orchestrator, "cli_available", lambda: False)
    ex = orchestrator.run(REAL, REAL.name, mode="auto")
    assert ex.method == "rules" and "없어" in ex.warnings[0]


# ---- Claude CLI 경로 (subprocess 스텁)
import json
import subprocess

from app import extract_cli


def _fake_cli(monkeypatch, payload=None, is_error=False, raw=None):
    body = raw if raw is not None else json.dumps({"is_error": is_error, "result": "boom",
                                                   "modelUsage": {"claude-haiku-4-5": {"outputTokens": 5}, "claude-sonnet-5": {"outputTokens": 900}},
                                                   "structured_output": payload})
    monkeypatch.setattr(extract_cli.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, body, ""))


def test_cli_path_validates_quotes_like_api(monkeypatch):
    bad = good()
    bad.specs.append(LLMSpec(field="design_pressure", value="25", unit="bar", display="25 bar", page=1, quote="Design pressure: 25 bar"))
    _fake_cli(monkeypatch, bad.model_dump())
    ex = orchestrator.run(REAL, REAL.name, mode="cli")
    assert ex.method == "cli" and ex.model == "claude-sonnet-5"
    assert ex.certs[0].extractedBy == "cli"
    assert all(s.field != "design_pressure" for s in ex.specs)


def test_cli_error_falls_back_to_rules(monkeypatch):
    _fake_cli(monkeypatch, None, is_error=True)
    ex = orchestrator.run(REAL, REAL.name, mode="cli")
    assert ex.method == "rules" and ex.warnings[0].startswith("CLI 추출 실패")


def test_cli_garbage_output_falls_back(monkeypatch):
    _fake_cli(monkeypatch, raw="not json")
    assert orchestrator.run(REAL, REAL.name, mode="cli").method == "rules"


def test_cli_missing_binary_falls_back(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("claude")
    monkeypatch.setattr(extract_cli.subprocess, "run", boom)
    assert orchestrator.run(REAL, REAL.name, mode="cli").method == "rules"


def test_auto_prefers_cli_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(orchestrator, "cli_available", lambda: True)
    _fake_cli(monkeypatch, good().model_dump())
    assert orchestrator.run(REAL, REAL.name, mode="auto").method == "cli"


def test_range_given_only_as_value_string_is_normalised():
    # 실제 CLI 평가에서 발견: 모델이 "50-600"만 주고 range_min/max를 비우면 엔진이 범위로 인식하지 못했다
    r = good()
    r.specs[0].range_min = r.specs[0].range_max = None
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(r))
    d = ex.specs[0]
    assert (d.rangeMin, d.rangeMax) == (50.0, 600.0)
    from app.engine import evaluate
    from app.models import Product, Requirement
    p = Product(id="T", manufacturer="m", model="x", specs=[d])
    e = evaluate(p, [Requirement(id="R", field="nominal_diameter", op="=", value="200", unit="mm")])
    assert e.items[0].status == "PASS"


# ---- 사용 제한 조건 해석(LLM 경로)
from app.extract_llm import LLMRestriction


def _with_restrictions(*rs):
    r = good()
    r.restrictions = list(rs)
    return r


def _lr(**kw):
    base = dict(kind="PROHIBITED", contexts=["seawater"], materials=["CF8", "CF8M"], scope_other=None, summary="스테인리스는 해수 불가",
                quote="Stainless steel valves are not permitted in seawater systems.", page=2, note=None)
    return LLMRestriction(**{**base, **kw})


def test_restriction_with_verified_quote_is_kept_unconfirmed():
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(_with_restrictions(_lr())))
    r = ex.restrictions[0]
    assert (r.kind, r.contexts, r.materials) == ("PROHIBITED", ["seawater"], ["CF8", "CF8M"])
    assert r.extractedBy == "llm" and r.confirmed is False and r.file == REAL.name and r.page == 2


def test_restriction_with_hallucinated_quote_is_dropped():
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(_with_restrictions(_lr(quote="Valves are forbidden in all seawater."))))
    assert not ex.restrictions and any("사용 제한의 원문 인용" in w for w in ex.warnings)


def test_restriction_on_wrong_page_is_dropped():
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(_with_restrictions(_lr(page=1))))
    assert not ex.restrictions


def test_unknown_material_codes_are_removed_with_warning():
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(_with_restrictions(_lr(materials=["CF8M", "UNOBTANIUM"]))))
    assert ex.restrictions[0].materials == ["CF8M"] and any("UNOBTANIUM" in w for w in ex.warnings)


def test_rules_only_prohibition_is_warned_when_llm_missed_it():
    # AI 해석이 금지 조건을 놓쳤을 때, 규칙 추출이 찾은 금지 후보를 경고로 알린다
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=Stub(good()))
    assert any("규칙 추출에서만 발견된 금지 조건" in w and "seawater" in w for w in ex.warnings)


def test_cli_path_carries_restrictions(monkeypatch):
    _fake_cli(monkeypatch, _with_restrictions(_lr()).model_dump())
    ex = orchestrator.run(REAL, REAL.name, mode="cli")
    assert ex.method == "cli" and ex.restrictions[0].extractedBy == "cli"


# ---- 비결정적 누락 대응: 규칙이 금지 후보를 찾았는데 AI가 0건이면 1회 재시도
class SeqStub:
    def __init__(self, *results):
        self.results, self.calls, self.messages = list(results), 0, self

    def parse(self, **kw):
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return SimpleNamespace(parsed_output=r, stop_reason="end_turn")


def test_empty_restrictions_with_rules_prohibition_triggers_one_retry():
    stub = SeqStub(good(), _with_restrictions(_lr()))
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=stub)
    assert stub.calls == 2 and ex.restrictions and any("1회 재시도" in w for w in ex.warnings)


def test_retry_happens_at_most_once():
    stub = SeqStub(good(), good(), _with_restrictions(_lr()))
    ex = orchestrator.run(REAL, REAL.name, mode="llm", client=stub)
    assert stub.calls == 2 and not ex.restrictions                      # 두 번째도 비면 포기하고 경고만 남긴다
    assert any("규칙 추출에서만 발견된 금지 조건" in w for w in ex.warnings)


def test_no_retry_when_ai_found_restrictions_or_rules_found_none():
    stub = SeqStub(_with_restrictions(_lr()))
    orchestrator.run(REAL, REAL.name, mode="llm", client=stub)
    assert stub.calls == 1
    from app.extract_rules import extract as rx
    no_rules = Path(__file__).parent.parent / "data" / "samples" / "SYNTHETIC_BS-2000_datasheet_rev2.pdf"   # 제한 문구 없는 문서
    stub2 = SeqStub(good())
    orchestrator.run(no_rules, no_rules.name, mode="llm", client=stub2)
    assert stub2.calls == 1
