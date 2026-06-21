"""Deterministic, no-API evidence-sufficiency scoring for long_context (Phase 2L.16).

Given a question, its choices, the current answer label, and the selected/compressed
evidence text (from the v6b reranker, when available), compute lexical diagnostic
signals and a sufficiency status. It NEVER changes an answer, calls no network/LLM,
uses no ground truth, and reads no qid for decisions. Purely lexical — a heuristic to
flag where the reranked evidence may be too thin to support the chosen option.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

_WORD = re.compile(r"\w+", re.UNICODE)
# Vietnamese function words / generic stems to drop from coverage signals.
_STOP = {
    "là", "và", "của", "có", "không", "các", "một", "những", "được", "cho", "với",
    "trong", "đến", "này", "đó", "khi", "thì", "ra", "vào", "về", "theo", "hay",
    "hoặc", "nào", "gì", "bao", "nhiêu", "sao", "vì", "để", "bằng", "trên", "dưới",
    "câu", "hỏi", "sau", "đây", "phương", "án", "đúng", "nhất", "the", "a", "an",
    "of", "to", "is", "in", "and", "or", "what", "which",
}


def _tokens(text: str) -> set:
    return {t for t in (w.lower() for w in _WORD.findall(text or "")) if t not in _STOP and len(t) > 1}


@dataclass
class EvidenceSufficiency:
    status: str = "unknown"                 # sufficient | weak | insufficient | unknown
    recommendation: str = "keep current"
    question_coverage: float = 0.0          # fraction of question content tokens in evidence
    current_answer_support: float = 0.0     # token overlap of current option with evidence
    best_other_support: float = 0.0         # best overlap among the other options
    multiple_equally_supported: bool = False
    evidence_chars: int = 0
    has_evidence: bool = True
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def compute_evidence_sufficiency(question: str, choices, current_label,
                                 evidence_text, *, labels=None) -> EvidenceSufficiency:
    ev = str(evidence_text or "").strip()
    if not ev:
        return EvidenceSufficiency(status="unknown", recommendation="keep current",
                                   has_evidence=False, evidence_chars=0)
    ev_tokens = _tokens(ev)
    q_tokens = _tokens(question)
    coverage = (len(q_tokens & ev_tokens) / len(q_tokens)) if q_tokens else 0.0

    labels = labels or [chr(ord("A") + i) for i in range(len(choices))]
    supports = []
    for i, c in enumerate(choices):
        ct = _tokens(str(c))
        ov = (len(ct & ev_tokens) / len(ct)) if ct else 0.0
        supports.append((labels[i], ov))
    by_label = dict(supports)
    cur_support = by_label.get(current_label, 0.0)
    others = sorted((ov for lbl, ov in supports if lbl != current_label), reverse=True)
    best_other = others[0] if others else 0.0
    # Genuine ambiguity = the current answer is strongly supported AND another option
    # is a near-tie. Kept strict so it is a rare, meaningful signal (not the default).
    multiple_equal = bool(cur_support >= 0.5 and best_other >= cur_support - 0.02
                          and best_other >= 0.5)

    # Status is driven by coverage + current-answer support. (Cross-option ambiguity
    # is reported via `multiple_equally_supported` but routed to the dedicated
    # `ambiguous` branch, not folded into long_context status — lexical overlap of
    # short option texts over long evidence is too coarse to adjudicate here.)
    if coverage < 0.20 or len(ev) < 200:
        status, rec = "insufficient", "needs evidence expansion"
    elif coverage >= 0.40 and cur_support >= 0.15:
        status, rec = "sufficient", "keep current"
    else:
        status, rec = "weak", "needs reranker top_k/candidate_top_k sweep"

    return EvidenceSufficiency(
        status=status, recommendation=rec,
        question_coverage=round(coverage, 4),
        current_answer_support=round(cur_support, 4),
        best_other_support=round(best_other, 4),
        multiple_equally_supported=multiple_equal,
        evidence_chars=len(ev), has_evidence=True,
        signals={"q_token_count": len(q_tokens), "ev_token_count": len(ev_tokens)},
    )
