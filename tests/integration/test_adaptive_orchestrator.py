"""Tests for the adaptive reasoning orchestrator (Phase 2L.15A) — trace-only.

No network, no real model, no qid logic. Synthetic samples + a fake client.
Runnable with pytest, or standalone: ``python tests/test_adaptive_orchestrator.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.layers.adaptive_orchestrator import AdaptiveConfig, AdaptiveOrchestrator  # noqa: E402
from src.solvers.formula_registry import all_formula_ids, eligible_formula_ids  # noqa: E402
from src.api.openrouter_graph_solver import OpenRouterConfig, OpenRouterGraphSolver  # noqa: E402

_EXPECTED_FORMULAS = {
    "relativistic_gamma", "relativistic_momentum", "henderson_hasselbalch_buffer",
    "z_score_one_sample", "t_statistic_one_sample", "supply_demand_price_control",
    "cobb_douglas_isoquant_scaling", "accrued_simple_interest",
    "operating_margin_asset_turnover", "nuclear_binding_energy_release",
    "linear_total_equation",
}


class _FakeResult:
    content = '{"answer":"A","confidence":0.9,"reason_type":"lookup","needs_review":false,"evidence":["x"]}'
    model = "qwen/qwen3.5-9b"
    response_id = "m"
    usage = {"completion_tokens": 10, "total_tokens": 50}
    raw: dict = {}


class _FakeClient:
    def __init__(self):
        self.calls = 0

    def chat(self, *a, **k):
        self.calls += 1
        return _FakeResult()


_SK = {"qid": "s1", "question": "Thủ đô của Pháp là gì?", "choices": ["Paris", "Lyon", "Nice", "Hue"]}


def test_config_default_off():
    assert OpenRouterConfig().adaptive_reasoning_enabled is False
    assert AdaptiveConfig().enabled is False and AdaptiveConfig().mode == "trace_only"


def test_registry_loads_all_expected_formula_ids():
    assert set(all_formula_ids()) == _EXPECTED_FORMULAS


def test_gamma_vs_momentum_metadata_eligibility_distinct():
    gq = "Một hạt chuyển động với 0,6c. Hệ số Lorentz của hạt là bao nhiêu?"
    mq = ("Một hạt chuyển động với 0,6c. Động lượng tương đối p của hạt là bao nhiêu "
          "nếu khối lượng nghỉ là m₀?")
    assert eligible_formula_ids(gq) == ["relativistic_gamma"]
    assert eligible_formula_ids(mq) == ["relativistic_momentum"]


def test_trace_only_never_overrides():
    orch = AdaptiveOrchestrator(AdaptiveConfig(enabled=True, mode="trace_only"))
    s = {"qid": "c1", "question": "Tính dh/dt cho bể hình trụ bán kính 5 cm đổ 50 cm³/s.",
         "choices": ["0.2 cm/s", "0.4 cm/s", "0.6 cm/s", "0.8 cm/s"]}
    tr = orch.analyze(s, existing_answer="A")
    assert tr.would_override is False
    assert tr.override_allowed is False
    assert tr.final_decision == "fallback_existing_answer"


def test_legal_admin_count_not_deterministic_override():
    orch = AdaptiveOrchestrator(AdaptiveConfig(enabled=True, mode="trace_only"))
    s = {"qid": "l1", "question": "Theo Luật Bảo vệ môi trường 2020, có bao nhiêu nguyên tắc?",
         "choices": ["5", "6", "7", "8"]}
    tr = orch.analyze(s, existing_answer="A")
    assert tr.would_override is False
    # No deterministic calc candidate proposes a safe override for a legal count.
    for c in tr.branch_candidates:
        assert not c.get("would_change_answer")


def test_short_knowledge_verifier_recommended_is_trace_flag_only():
    orch = AdaptiveOrchestrator(AdaptiveConfig(enabled=True, mode="trace_only"))
    state = {"confidence": 0.4, "parsed_answer": {"needs_review": True}}
    s = {"qid": "s2", "question": "Theo chính sách quy định hiện hành thì sao?",
         "choices": ["A", "B", "C", "D"]}
    tr = orch.analyze(s, existing_answer="A", state=state)
    # verifier_recommended appears as a flag, but nothing changes and no override.
    assert "verifier_recommended" in tr.risk_flags or tr.selected_branch != "short_knowledge"
    assert tr.would_override is False


def test_disabled_is_backward_compatible_no_adaptive_key():
    client = _FakeClient()
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client)
    state = solver._init_state(_SK)
    state["route"] = "short_knowledge"
    state["final_answer"] = "A"
    solver._adaptive_node(state)
    assert "adaptive" not in state


def test_enabled_trace_only_attaches_adaptive_without_changing_answer_or_calls():
    client = _FakeClient()
    solver = OpenRouterGraphSolver(
        config=OpenRouterConfig(adaptive_reasoning_enabled=True), client=client)
    ans = solver.predict_one(_SK)
    assert ans == "A"            # answer unchanged vs the LLM result
    assert client.calls == 1     # no EXTRA api call from the orchestrator


def test_enabled_trace_only_preserves_answer_field():
    client = _FakeClient()
    solver = OpenRouterGraphSolver(
        config=OpenRouterConfig(adaptive_reasoning_enabled=True), client=client)
    state = solver._init_state(_SK)
    state["route"] = "short_knowledge"
    state["final_answer"] = "C"
    solver._adaptive_node(state)
    assert state["final_answer"] == "C"          # invariant: answer untouched
    assert state["adaptive"]["would_override"] is False
    assert state["adaptive"]["enabled"] is True


def test_long_context_branch_answer_unchanged_vs_disabled():
    # Enabling adaptive (trace_only) must not change the chosen answer on any route.
    lc = {"qid": "lc1",
          "question": ("Đoạn thông tin:\n[1] Tiêu đề: A\nNội dung: " + "x " * 50 +
                       "\nCâu hỏi: Thủ đô của Ai Cập là gì?"),
          "choices": ["Cairo", "Paris", "Lyon", "Hue"]}
    a_off = OpenRouterGraphSolver(config=OpenRouterConfig(), client=_FakeClient()).predict_one(lc)
    a_on = OpenRouterGraphSolver(
        config=OpenRouterConfig(adaptive_reasoning_enabled=True), client=_FakeClient()).predict_one(lc)
    assert a_off == a_on


def _assist():
    return AdaptiveOrchestrator(AdaptiveConfig(
        enabled=True, mode="assist",
        calculation_programmatic_enabled=True, calculation_allow_override=True))


_CALC = {"qid": "c1",
         "question": ("Một bể hình trụ bán kính 5 cm được đổ nước 50 cm³/s. Tốc độ "
                      "tăng mực nước dh/dt là bao nhiêu?"),
         "choices": ["0.2 cm/s", "0.4 cm/s", "0.6 cm/s", "0.8 cm/s"]}  # det -> C


def test_assist_mode_only_changes_calculation_branch():
    # A short_knowledge sample under assist mode must never be override-eligible.
    tr = _assist().analyze(_SK, existing_answer="B")
    assert tr.selected_branch != "calculation"
    assert tr.override_allowed is False and tr.would_override is False


def test_assist_mode_overrides_only_safe_calc_candidate():
    tr = _assist().analyze(_CALC, existing_answer="A")   # det answer C, safe
    assert tr.selected_branch == "calculation"
    assert tr.would_override is True
    cand = tr.branch_candidates[0]
    assert cand["answer"] == "C" and cand["would_change_answer"] is True


def test_assist_mode_no_override_when_calc_agrees_with_base():
    tr = _assist().analyze(_CALC, existing_answer="C")   # base already correct
    assert tr.would_override is False                    # nothing to change


def test_assist_mode_no_override_when_no_calc_match():
    s = {"qid": "c2", "question": "Tính giá trị biểu thức $2x+3$ khi $x=4$?",
         "choices": ["9", "11", "13", "15"]}             # no family matches
    tr = _assist().analyze(s, existing_answer="A")
    assert tr.would_override is False


def test_trace_only_never_overrides_even_for_safe_calc():
    orch = AdaptiveOrchestrator(AdaptiveConfig(
        enabled=True, mode="trace_only", calculation_allow_override=True))
    tr = orch.analyze(_CALC, existing_answer="A")
    assert tr.would_override is False and tr.override_allowed is False


def test_patch_script_has_no_network_qid_or_external_sheet():
    import re as _re
    base = Path(__file__).resolve().parents[2] / "scripts" / "legacy"
    for name in ("apply_programmatic_assist_to_predictions.py",
                 "compare_v7_programmatic_assist_pseudo.py"):
        src = next(iter(base.glob(f"**/{name}"))).read_text()
        for bad in ("import requests", "import urllib", "import socket", "openrouter",
                    "OPENROUTER", "eval(", "exec(", ".env"):
            assert bad not in src, f"unexpected '{bad}' in {name}"
        for pat in (r'qid\s*==', r'==\s*["\']test_0'):
            assert not _re.search(pat, src), f"qid hardcoding in {name}"
    # The patch script must NOT read the external answer sheet (no filename / arg ref).
    patch = next(iter(base.glob("**/apply_programmatic_assist_to_predictions.py"))).read_text()
    assert "first100_external_3llm" not in patch
    assert "--external" not in patch and "external_sheet" not in patch


# --- Phase 2L.15C: short-knowledge selective verifier ------------------------

from src.layers.adaptive_routing import sk_verifier_eligibility  # noqa: E402


def _sk_orch():
    return AdaptiveOrchestrator(AdaptiveConfig(
        enabled=True, mode="assist", short_knowledge_verifier_enabled=True,
        sk_allow_override=False, sk_trigger_confidence_max=0.95))


def test_sk_verifier_default_off():
    assert AdaptiveConfig().short_knowledge_verifier_enabled is False
    assert AdaptiveConfig().sk_allow_override is False
    assert AdaptiveConfig().sk_max_verifier_calls == 0


def test_sk_eligibility_requires_short_knowledge_route():
    # A calculation-routed sample is never SK-verifier eligible.
    calc = {"qid": "c", "question": "Tính dh/dt bể trụ bán kính 5cm đổ 50 cm³/s?",
            "choices": ["0.2", "0.4", "0.6", "0.8"]}
    elig, reasons = sk_verifier_eligibility(calc, "calculation",
                                            state={"final_answer": "C", "confidence": 0.5})
    assert elig is False and reasons == []


def test_sk_eligibility_triggers_on_low_confidence():
    elig, reasons = sk_verifier_eligibility(
        _SK, "short_knowledge", state={"final_answer": "A", "confidence": 0.9})
    assert elig is True
    assert "confidence_below_max" in reasons and "verifier_recommended" in reasons


def test_sk_eligibility_triggers_on_admin_policy():
    s = {"qid": "l", "question": "Theo quy định pháp luật, nguyên tắc nào đúng?",
         "choices": ["A", "B", "C", "D"]}
    elig, reasons = sk_verifier_eligibility(
        s, "short_knowledge", state={"final_answer": "A", "confidence": 1.0})
    assert elig is True and "domain_admin_or_policy" in reasons


def test_sk_eligibility_skips_when_no_answer():
    elig, reasons = sk_verifier_eligibility(
        _SK, "short_knowledge", state={"final_answer": None, "confidence": 0.5})
    assert elig is False


def test_sk_orchestrator_never_overrides_and_no_candidate():
    # SK verifier enabled, assist mode: orchestrator computes eligibility only,
    # makes NO candidate (no API) and NEVER sets would_override.
    tr = _sk_orch().analyze(_SK, existing_answer="A",
                            state={"final_answer": "A", "confidence": 0.9})
    assert tr.selected_branch == "short_knowledge"
    assert tr.would_override is False and tr.override_allowed is False
    assert tr.branch_candidates == []
    assert tr.extra["sk_verifier_eligible"] is True


def test_sk_runner_dry_run_is_default_and_makes_no_api_call():
    import re as _re
    src = (next(iter((Path(__file__).resolve().parents[2] / "scripts" / "legacy").glob("**/run_short_knowledge_verifier_sample.py")))).read_text()
    # dry_run defaults true; the OpenRouter client import is lazy (only under --execute).
    assert 'default=False' in src and "--execute" in src
    assert "from src.api.openrouter_client import OpenRouterClient" in src
    # No top-level (module-import-time) client construction / network / env access.
    assert ".env" not in src and "OPENROUTER_API_KEY" not in src
    for pat in (r'qid\s*==', r'==\s*["\']test_0'):
        assert not _re.search(pat, src)
    assert "first100_external" not in src


def test_no_qid_or_network_in_adaptive_source():
    import re as _re
    base = Path(__file__).resolve().parents[2] / "src"
    for name in ("adaptive_orchestrator.py", "adaptive_routing.py", "adaptive_types.py",
                 "formula_registry.py", "programmatic_solver.py"):
        src = next(iter(base.glob(f"**/{name}"))).read_text()
        for bad in ("import requests", "import urllib", "import socket", "import httpx",
                    "eval(", "exec(", "__import__", "gemini", "claude", "chatgpt"):
            assert bad not in src, f"unexpected '{bad}' in {name}"
        for pat in (r'\[\s*["\']qid', r'\.get\(\s*["\']qid', r'qid\s*=='):
            assert not _re.search(pat, src), f"qid access in {name}"


if __name__ == "__main__":
    failures = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {nm}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {nm}: {exc}")
    raise SystemExit(1 if failures else 0)
