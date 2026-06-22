"""Option-aware evidence packing for long_context (Phase 2L.21) — no API, deterministic.

Generic improvement over single-query reranking: score the in-question evidence
chunks against ``question stem + EACH option`` separately, keep the top chunks per
option, then merge/deduplicate into one compact evidence pack (chunks restored to
reading order). This only improves the CONTEXT given to the base solver — it NEVER
selects or overrides an answer. Lexical-only (dependency-free); if a neural reranker
is wired elsewhere it is unaffected. No qid logic, no ground truth, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.evidence_reranker import (chunk_context, extract_question_stem,
                                    _score_chunks_lexical)


@dataclass
class OptionEvidencePack:
    matched: bool
    pack_text: str = ""
    evidence_selected_by_option: dict = field(default_factory=dict)   # label -> [chunk_id]
    top_option_evidence_scores: dict = field(default_factory=dict)    # label -> [score]
    evidence_pack_size: int = 0
    kept_chunk_ids: list = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"matched": self.matched, "evidence_pack_size": self.evidence_pack_size,
                "evidence_selected_by_option": self.evidence_selected_by_option,
                "top_option_evidence_scores": self.top_option_evidence_scores,
                "kept_chunk_ids": self.kept_chunk_ids, "diagnostics": self.diagnostics}


def build_option_aware_evidence_pack(sample: dict, *, per_option_top_k: int = 1,
                                     max_chars: int = 4500) -> OptionEvidencePack:
    """Build a compact, deduplicated evidence pack covering every option.

    For each option we keep its top ``per_option_top_k`` chunks (scored against the
    stem + that option's text), then union them in reading order within ``max_chars``.
    Deterministic: ties broken by chunk index. Declines (matched=False) when there is
    no chunkable context.
    """
    question = str(sample.get("question", "") or "")
    choices = [str(c) for c in (sample.get("choices", []) or [])]
    if not question or not choices:
        return OptionEvidencePack(False, diagnostics={"reason": "empty"})

    stem = extract_question_stem(question)
    context = question[: question.rfind(stem)] if stem and stem in question else question
    context = context.strip() or question
    try:
        chunks = chunk_context(context)
    except Exception as exc:
        return OptionEvidencePack(False, diagnostics={"reason": f"chunk_error:{type(exc).__name__}"})
    if len(chunks) < 2:
        return OptionEvidencePack(False, diagnostics={"reason": "insufficient_chunks",
                                                      "chunks": len(chunks)})

    labels = [chr(ord("A") + i) for i in range(len(choices))]
    selected_by_option, scores_by_option = {}, {}
    union_idx = []  # preserve first-seen order across options
    for lbl, opt in zip(labels, choices):
        query = f"{stem} {opt}"
        scored = _score_chunks_lexical(chunks, query, [opt])
        order = sorted(range(len(chunks)),
                       key=lambda i: (scored[i]["score"], -i), reverse=True)
        top = order[: max(1, per_option_top_k)]
        selected_by_option[lbl] = [chunks[i].chunk_id for i in top]
        scores_by_option[lbl] = [round(scored[i]["score"], 4) for i in top]
        for i in top:
            if i not in union_idx:
                union_idx.append(i)

    # Pack the union in reading order within the char budget.
    union_idx_sorted = sorted(union_idx)
    parts, used, kept = [], 0, []
    for i in union_idx_sorted:
        c = chunks[i]
        if used + len(c.text) + 2 > max_chars:
            continue
        parts.append(c.text)
        used += len(c.text) + 2
        kept.append(c.chunk_id)
    if not parts:
        parts = [chunks[union_idx_sorted[0]].text[:max_chars]]
        kept = [chunks[union_idx_sorted[0]].chunk_id]

    pack_text = ("[BẰNG CHỨNG THEO TỪNG PHƯƠNG ÁN]\n" + "\n\n".join(parts)
                 + "\n\n[CÂU HỎI]\n" + stem)
    return OptionEvidencePack(
        matched=True, pack_text=pack_text,
        evidence_selected_by_option=selected_by_option,
        top_option_evidence_scores=scores_by_option,
        evidence_pack_size=len(pack_text), kept_chunk_ids=kept,
        diagnostics={"chunks_total": len(chunks), "options": len(choices)})
