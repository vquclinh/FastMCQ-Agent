"""Candidate-answer object model for the answer factory (Phase 2L.25).

Pure-Python dataclasses — no network, no qid logic, no answer table. An
``AnswerCandidate`` is one proposed answer for a question (from the base LLM, a
deterministic tool, a knowledge card, etc.) carrying its source, confidence, risk,
and any proof/evidence. A ``CandidatePool`` collects candidates for one qid.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

RISK_LEVELS = ("low", "medium", "high")


@dataclass
class AnswerCandidate:
    qid: str
    answer: str | None
    source: str                      # e.g. "v10_base", "tool:physics", "formula_bank", "card"
    route: str = ""
    confidence: float = 0.0
    risk_level: str = "medium"
    rationale: str = ""
    evidence_text: str = ""
    proof_text: str = ""             # deterministic computation/proof, if any
    rule_id: str | None = None
    card_id: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CandidatePool:
    qid: str
    candidates: list = field(default_factory=list)

    def add(self, candidate: AnswerCandidate) -> None:
        if candidate is not None and candidate.answer is not None:
            self.candidates.append(candidate)

    def deduplicate(self) -> "CandidatePool":
        """Drop duplicate (source, answer) pairs, keeping the highest-confidence one."""
        best = {}
        for c in self.candidates:
            key = (c.source, c.answer)
            if key not in best or c.confidence > best[key].confidence:
                best[key] = c
        self.candidates = list(best.values())
        return self

    def answer_votes(self) -> dict:
        """label -> number of candidates proposing it."""
        return dict(Counter(c.answer for c in self.candidates if c.answer is not None))

    def sources(self) -> list:
        return sorted({c.source for c in self.candidates})

    def best_by_source(self, source: str):
        cands = [c for c in self.candidates if c.source == source]
        return max(cands, key=lambda c: c.confidence) if cands else None

    def to_dict(self) -> dict:
        return {"qid": self.qid, "candidates": [c.to_dict() for c in self.candidates],
                "answer_votes": self.answer_votes(), "sources": self.sources()}
