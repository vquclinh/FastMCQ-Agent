"""Research-grounded OpenRouter graph solver (Round 1).

A ReAct-style node graph over the OpenRouter API (default model
``qwen/qwen3.5-9b``). It reuses the existing deterministic profiler, router and
passage compressor, then asks the LLM for a **structured** answer, verifies it,
and repairs once if needed. Self-consistency is implemented but **gated off** by
default.

Node graph (executed by a small built-in runner; LangGraph is optional and not
required — see docs):

    profile → evidence → route → answer → verify → [repair] → [self_consistency]
            → finalize → valid label

Paper → module mapping:
  * ReAct           → the graph itself (profile/route = observe; nodes = act/verify)
  * CoT/scratchpad  → internal reasoning allowed in the prompt, JSON-only output
  * RAG (in-question)→ ``evidence_node`` via passage_compressor (no web retrieval)
  * Lost-in-the-Middle → compressed evidence placed next to the question/choices
  * Verification/Refine → ``verify_node`` + one ``repair_node`` attempt
  * Self-consistency → ``self_consistency_node`` (gated, low-confidence only)
  * Structured output → ``structured_answer`` schema + robust parser
  * Dynamic labels  → labels sized to each sample (2–11)

No private chain-of-thought is logged — only concise evidence/rationale and the
structural trace. Every final output is a valid label.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from .labels import index_to_label, is_valid_label, labels_for
from .openrouter_client import OpenRouterClient
from .openrouter_prompts import build_messages, repair_messages
from .passage_compressor import compress_passage
from .question_profiler import profile_question
from .question_router import route_question
from .solver_base import BaseSolver
from .structured_answer import parse_structured_answer, response_format_schema

_FALLBACK = index_to_label(0)  # "A"


@dataclass
class OpenRouterConfig:
    model: str = "qwen/qwen3.5-9b"
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 512
    timeout_sec: float = 60.0
    max_retries: int = 3
    structured_output: bool = True
    # Reasoning controls (for reasoning-capable models). Default OFF.
    reasoning_enabled: bool = False
    reasoning_effort: str | None = None
    reasoning_max_tokens: int | None = None
    reasoning_exclude: bool = True
    enable_verifier: bool = True
    enable_repair: bool = True
    # Speed policy: by default the verifier triggers a repair (2nd call) ONLY when
    # the first response yields no valid label. The model's own ``needs_review``
    # flag / a label-fallback recovery do NOT cost an extra call. Set False for a
    # more thorough (slower) pass that also repairs flagged/fallback answers.
    repair_only_on_invalid: bool = True
    enable_self_consistency: bool = False
    self_consistency_k: int = 3
    self_consistency_temperature: float = 0.7
    low_confidence_threshold: float = 0.5
    # API-call budget per sample (for transparency + a hard cap on the normal path).
    max_api_calls_per_sample_default: int = 1
    max_api_calls_per_sample_with_repair: int = 2
    max_context_chars: int = 3000
    compress_long_context: bool = True
    # Deterministic calculation helper (PAL-lite) for the calculation route.
    calc_enabled: bool = True
    calc_override_when_safe: bool = True
    calc_min_confidence: float = 0.95
    # In-question evidence reranking (long_context route). Lexical by default;
    # optional embedding/reranker model paths fail closed to lexical.
    evidence_reranker_enabled: bool = True
    evidence_reranker_method: str = "hybrid_lexical"
    evidence_reranker_top_k: int = 4
    evidence_reranker_max_chars: int = 4500
    evidence_reranker_global_context: bool = True
    evidence_reranker_global_context_chars: int = 800
    evidence_embedding_model: str | None = None
    evidence_reranker_model: str | None = None
    evidence_candidate_top_k: int = 12
    evidence_neural_fallback_to_lexical: bool = True
    # Selective second-pass MCQ verifier (off by default). One extra call, only on
    # hard/uncertain cases; never overrides a deterministic calculation answer.
    mcq_verifier_enabled: bool = False
    mcq_verifier_apply_routes: list = field(
        default_factory=lambda: ["long_context", "ambiguous", "law_admin", "safety_ethics"])
    mcq_verifier_min_confidence_to_override: float = 0.80
    mcq_verifier_trigger_below_confidence: float = 0.70
    mcq_verifier_trigger_on_partial_parse: bool = True
    mcq_verifier_trigger_on_repair: bool = True
    mcq_verifier_trigger_on_reranked_long_context: bool = True
    mcq_verifier_max_extra_calls: int = 1


class OpenRouterGraphSolver(BaseSolver):
    """LLM MCQA solver structured as a verifiable node graph over OpenRouter."""

    def __init__(self, *, config: OpenRouterConfig | None = None, client=None,
                 logger=None):
        self.cfg = config or OpenRouterConfig()
        self.logger = logger
        # Inject a client (real or mock) or build a real OpenRouter client.
        self.client = client or OpenRouterClient(
            model=self.cfg.model, temperature=self.cfg.temperature,
            top_p=self.cfg.top_p, max_tokens=self.cfg.max_tokens,
            timeout_sec=self.cfg.timeout_sec, max_retries=self.cfg.max_retries,
            reasoning_enabled=self.cfg.reasoning_enabled,
            reasoning_effort=self.cfg.reasoning_effort,
            reasoning_max_tokens=self.cfg.reasoning_max_tokens,
            reasoning_exclude=self.cfg.reasoning_exclude,
        )

    # -- BaseSolver entry -----------------------------------------------------
    def predict_one(self, sample: dict) -> str:
        start = time.perf_counter()
        state = self._init_state(sample)
        try:
            self._profile_node(state)
            self._evidence_node(state)
            self._route_node(state)
            # Deterministic calculation override (calculation route only). When a
            # high-confidence family matches, use it and SKIP the LLM call.
            if self._calculation_node(state):
                self._finalize_node(state)
                state["elapsed_sec"] = round(time.perf_counter() - start, 4)
                self._emit(state)
                return state["final_answer"] or _FALLBACK
            self._answer_node(state)
            self._verify_node(state)
            if (state["verifier_result"].get("needs_repair") and self.cfg.enable_repair
                    and state["api_calls"] < self.cfg.max_api_calls_per_sample_with_repair):
                self._repair_node(state)
            if self._should_self_consist(state):
                self._self_consistency_node(state)
            self._verifier_node(state)
            self._finalize_node(state)
        except Exception as exc:  # never let one sample crash the run
            state["errors"].append(f"{type(exc).__name__}: {exc}")
            state["final_answer"] = _FALLBACK
        state["elapsed_sec"] = round(time.perf_counter() - start, 4)
        self._emit(state)
        return state["final_answer"] or _FALLBACK

    # -- nodes ----------------------------------------------------------------
    def _profile_node(self, s):
        s["profile"] = profile_question(s["_sample"]).to_dict()

    def _evidence_node(self, s):
        sample = s["_sample"]
        # Decide compression up-front using the router's view of the route.
        decision = route_question(sample)
        if decision.route != "long_context":
            return

        # 1) Try in-question evidence reranking (generic; in-question only).
        if self.cfg.evidence_reranker_enabled:
            from .evidence_reranker import rerank_evidence_for_sample
            s["evidence_reranker_enabled"] = True
            s["evidence_reranker_method"] = self.cfg.evidence_reranker_method
            try:
                rr = rerank_evidence_for_sample(
                    sample, max_chars=self.cfg.evidence_reranker_max_chars,
                    top_k=self.cfg.evidence_reranker_top_k,
                    candidate_top_k=self.cfg.evidence_candidate_top_k,
                    method=self.cfg.evidence_reranker_method,
                    include_global_context=self.cfg.evidence_reranker_global_context,
                    global_context_chars=self.cfg.evidence_reranker_global_context_chars,
                    optional_embedding_model=self.cfg.evidence_embedding_model,
                    optional_reranker_model=self.cfg.evidence_reranker_model,
                    neural_fallback_to_lexical=self.cfg.evidence_neural_fallback_to_lexical)
            except Exception:
                rr = None
            if rr is not None and rr.matched:
                diag = rr.diagnostics
                s["compressed_question"] = rr.selected_text
                s["evidence_reranker_method"] = rr.method
                s["evidence_reranker_requested_method"] = diag.get("requested_method")
                s["evidence_reranker_effective_method"] = diag.get("effective_method")
                s["evidence_neural_available"] = diag.get("neural_available")
                s["evidence_neural_fallback_reason"] = diag.get("neural_fallback_reason")
                s["evidence_candidate_chunk_count"] = diag.get("candidate_chunk_count")
                s["evidence_selected_chunk_count"] = len(rr.selected_chunks)
                s["evidence_selected_chars"] = len(rr.selected_text)
                s["evidence_fallback_used"] = False
                s["compressed_context_stats"] = {"method": "evidence_reranker", **diag}
                return
            s["evidence_fallback_used"] = True  # reranker declined -> compressor

        # 2) Fall back to the existing deterministic lexical compressor.
        if self.cfg.compress_long_context:
            res = compress_passage(sample.get("question", ""), sample.get("choices", []),
                                   max_context_chars=self.cfg.max_context_chars)
            s["compressed_context_stats"] = res["stats"]
            if res["stats"]["was_compressed"]:
                s["compressed_question"] = res["compressed_question"]

    def _route_node(self, s):
        s["route"] = route_question(s["_sample"]).route

    def _calculation_node(self, s) -> bool:
        """Run the deterministic calculation helper on the calculation route.

        Records calc metadata in the trace. Returns True iff it produced a safe
        override (so the caller skips the LLM call). Never returns a bad label.
        """
        # Run on the calculation route AND on the ambiguous route (duplicate-choice
        # numeric questions land there). This is safe: a family only matches genuine
        # formula patterns and only overrides when safe_to_override; non-numeric text
        # never matches, so nothing is overridden spuriously.
        if not self.cfg.calc_enabled or s["route"] not in ("calculation", "ambiguous"):
            return False
        from .calculation_solver import solve_calculation_sample
        sample = s["_sample"]
        labels = labels_for(len(sample.get("choices", []) or []))
        res = solve_calculation_sample(sample, labels,
                                       min_confidence=self.cfg.calc_min_confidence)
        s["calculation_matched"] = res.matched
        s["calculation_method"] = res.method
        s["calculation_answer"] = res.answer
        s["calculation_confidence"] = res.confidence
        s["calculation_safe_to_override"] = res.safe_to_override
        s["calculation_rationale"] = res.rationale
        if (res.safe_to_override and self.cfg.calc_override_when_safe
                and res.answer in labels):
            s["final_answer"] = res.answer
            s["confidence"] = res.confidence
            s["strategy"] = f"calculation_override:{res.method}"
            return True
        return False

    def _answer_node(self, s):
        s["raw_response"], parsed = self._ask(s, mode="answer")
        s["parsed_answer"] = parsed.to_dict()
        if parsed.ok:
            s["final_answer"] = parsed.answer
            s["confidence"] = parsed.confidence

    def _verify_node(self, s):
        if not self.cfg.enable_verifier:
            s["verifier_result"] = {"valid": True, "needs_repair": False, "reason": "verifier_disabled"}
            return
        parsed = s["parsed_answer"]
        label = parsed.get("answer")
        valid = bool(parsed.get("ok")) and label is not None and is_valid_label(label, s["_sample"])
        # Default (repair_only_on_invalid): repair ONLY when there is no valid
        # label — so a valid answer is one call even if the model self-flagged
        # needs_review or we recovered the label via fallback. The thorough mode
        # additionally repairs flagged / fallback answers.
        if self.cfg.repair_only_on_invalid:
            needs_repair = not valid
            reason = "invalid_label" if not valid else "ok"
        else:
            flagged = bool(parsed.get("needs_review")) or parsed.get("source") == "label_fallback"
            needs_repair = (not valid) or flagged
            reason = ("invalid_label" if not valid else
                      ("flagged_needs_review" if needs_repair else "ok"))
        s["verifier_result"] = {"valid": valid, "needs_repair": needs_repair, "reason": reason}

    def _repair_node(self, s):
        s["repair_used"] = True
        s["raw_response"], parsed = self._ask(s, mode="repair")
        # Accept the repair only if it produced a valid label.
        if parsed.ok and is_valid_label(parsed.answer, s["_sample"]):
            s["parsed_answer"] = parsed.to_dict()
            s["final_answer"] = parsed.answer
            s["confidence"] = parsed.confidence
            s["verifier_result"]["valid"] = True
            s["verifier_result"]["reason"] = "repaired"

    def _self_consistency_node(self, s):
        s["self_consistency_used"] = True
        labels = labels_for(len(s["_sample"].get("choices", []) or []))
        votes = []
        # Re-sample a few times with temperature > 0 and majority-vote the label.
        for _ in range(max(1, self.cfg.self_consistency_k)):
            _, parsed = self._ask(s, mode="answer",
                                  temperature=self.cfg.self_consistency_temperature)
            if parsed.ok and is_valid_label(parsed.answer, s["_sample"]):
                votes.append(parsed.answer)
        if votes:
            winner, _count = Counter(votes).most_common(1)[0]
            s["final_answer"] = winner
            s["sc_votes"] = dict(Counter(votes))
            s["confidence"] = max(s.get("confidence", 0.0),
                                  _count / len(votes)) if (votes) else s.get("confidence", 0.0)
        # Keep labels referenced for clarity (no-op guard).
        s["_labels"] = labels

    def _verifier_node(self, s):
        """Selective second-pass verifier (one extra call; off by default)."""
        from .mcq_verifier import (build_verifier_messages, parse_verification,
                                   should_run_verifier, verifier_response_format_schema)
        run, reason = should_run_verifier(s, self.cfg)
        s["verifier_enabled"] = self.cfg.mcq_verifier_enabled
        s["verifier_triggered"] = run
        s["verifier_trigger_reason"] = reason
        if not run or s["api_calls"] >= 1 + self.cfg.mcq_verifier_max_extra_calls:
            return
        sample = s["_sample"]
        labels = labels_for(len(sample.get("choices", []) or []))
        original = s.get("final_answer")
        s["verifier_original_answer"] = original
        qtext = s.get("compressed_question") or sample.get("question", "")
        messages = build_verifier_messages(
            s["route"], qtext, sample.get("choices", []) or [], original,
            calc_meta={"method": s.get("calculation_method")},
            evidence_diag=s.get("compressed_context_stats"))
        s["api_calls"] = s.get("api_calls", 0) + 1
        try:
            result = self.client.chat(messages,
                                      response_format=verifier_response_format_schema())
            vr = parse_verification(result.content, labels, original)
        except Exception as exc:
            s["verifier_error"] = f"{type(exc).__name__}: {exc}"
            return
        s["verifier_answer"] = vr.verified_answer
        s["verifier_confidence"] = vr.confidence
        s["verifier_should_override"] = vr.should_override
        s["verifier_parse_source"] = vr.method
        if (vr.should_override and vr.verified_answer in labels
                and vr.verified_answer != original
                and vr.confidence >= self.cfg.mcq_verifier_min_confidence_to_override):
            s["final_answer"] = vr.verified_answer
            s["confidence"] = vr.confidence
            s["verifier_override_applied"] = True
            s["strategy"] = (s.get("strategy") or "") + "+verifier_override"
        else:
            s["verifier_override_applied"] = False

    def _finalize_node(self, s):
        label = s.get("final_answer")
        if label is None or not is_valid_label(label, s["_sample"]):
            s["errors"].append("final_label_invalid_or_missing")
            s["final_answer"] = _FALLBACK

    # -- helpers --------------------------------------------------------------
    def _ask(self, s, *, mode: str, temperature: float | None = None):
        sample = s["_sample"]
        qtext = s.get("compressed_question")  # None => use original question
        if mode == "repair":
            messages = repair_messages(s["route"], sample,
                                       s["parsed_answer"].get("answer"),
                                       question_text=qtext)
        else:
            messages = build_messages(s["route"], sample, question_text=qtext)
        response_format = response_format_schema() if self.cfg.structured_output else None
        s["api_calls"] = s.get("api_calls", 0) + 1  # count every LLM/API call
        result = self.client.chat(messages, response_format=response_format,
                                   temperature=temperature)
        valid_labels = labels_for(len(sample.get("choices", []) or []))
        parsed = parse_structured_answer(result.content, valid_labels)
        s["model"] = result.model or self.cfg.model
        return _concise(result.content), parsed

    def _should_self_consist(self, s) -> bool:
        if not self.cfg.enable_self_consistency:
            return False
        # Only for genuinely low-confidence / flagged cases (budget-gated).
        conf = s.get("confidence", 0.0) or 0.0
        return conf < self.cfg.low_confidence_threshold or \
            s["verifier_result"].get("needs_repair", False)

    def _init_state(self, sample: dict) -> dict:
        return {
            "_sample": sample,
            "qid": sample.get("qid", ""),
            "question_length": len(str(sample.get("question", "") or "")),
            "num_choices": len(sample.get("choices", []) or []),
            "profile": None,
            "route": None,
            "compressed_question": None,
            "compressed_context_stats": None,
            "evidence_reranker_enabled": False,
            "evidence_reranker_method": None,
            "evidence_reranker_requested_method": None,
            "evidence_reranker_effective_method": None,
            "evidence_neural_available": None,
            "evidence_neural_fallback_reason": None,
            "evidence_candidate_chunk_count": None,
            "evidence_selected_chunk_count": None,
            "evidence_selected_chars": None,
            "evidence_fallback_used": False,
            "prompt_version": "v1",
            "model": self.cfg.model,
            "strategy": None,
            "raw_response": None,
            "parsed_answer": None,
            "verifier_result": {},
            "repair_used": False,
            "self_consistency_used": False,
            "api_calls": 0,
            # Deterministic calculation helper metadata (calculation route only).
            "calculation_matched": False,
            "calculation_method": None,
            "calculation_answer": None,
            "calculation_confidence": None,
            "calculation_safe_to_override": False,
            "calculation_rationale": None,
            "verifier_enabled": False,
            "verifier_triggered": False,
            "verifier_trigger_reason": None,
            "verifier_original_answer": None,
            "verifier_answer": None,
            "verifier_confidence": None,
            "verifier_should_override": None,
            "verifier_override_applied": False,
            "verifier_parse_source": None,
            "verifier_error": None,
            "final_answer": None,
            "confidence": None,
            "errors": [],
            "elapsed_sec": None,
        }

    def _emit(self, s):
        if self.logger is None:
            return
        # Log a concise trace — never the full hidden reasoning.
        record = {k: v for k, v in s.items() if k != "_sample"}
        record["solver"] = "openrouter_graph"
        record.pop("_labels", None)
        try:
            self.logger.record_event(record)
        except Exception:
            pass


def _concise(text: str, limit: int = 500) -> str:
    """Trim a raw response for logging (we keep only a short, structured snippet)."""
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"
