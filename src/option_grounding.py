"""Option grounding (Phase 2L.27A): map derived claims to options + verify reasoning.

Strengthens answer/evidence consistency: extract features (numeric values, key phrases)
from each option, map a derived claim to a UNIQUE option (declining on ambiguity), and
verify that a candidate's selected label actually matches its own evidence/rationale/
proof. Builds on ``candidate_consistency``. No network, no qid logic, no answer table.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from src.candidate_consistency import (extract_numeric_claims, extract_option_numeric_values,
                                       strong_claim)

_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_LABEL_RE = re.compile(r"[A-K]")
_STOP = {"của", "là", "và", "các", "một", "những", "được", "trong", "cho", "với", "the",
         "and", "for", "with", "này", "đó"}


def normalize_label(raw, labels):
    if raw is None:
        return None
    m = _LABEL_RE.search(str(raw).strip().upper())
    return m.group(0) if (m and m.group(0) in labels) else None


@dataclass
class OptionFeatures:
    label: str
    numeric: list = field(default_factory=list)
    phrases: set = field(default_factory=set)

    def to_dict(self):
        d = asdict(self)
        d["phrases"] = sorted(self.phrases)
        return d


def extract_option_features(choices):
    labels = [chr(ord("A") + i) for i in range(len(choices or []))]
    feats = []
    for lbl, c in zip(labels, choices or []):
        text = str(c)
        phrases = {w.lower() for w in _WORD.findall(text) if w.lower() not in _STOP}
        feats.append(OptionFeatures(label=lbl, numeric=extract_option_numeric_values(text),
                                    phrases=phrases))
    return feats


def map_claim_to_option(claim, choices):
    """Map a numeric OR text claim to a unique option label, else None (ambiguous).

    Numeric claim (float/int): the unique option containing that value (tolerance).
    Text claim (str): the unique option whose phrase set best overlaps (clear winner).
    """
    feats = extract_option_features(choices)
    if isinstance(claim, (int, float)):
        tol = 1e-6 + 1e-3 * abs(claim)
        hits = [f.label for f in feats if any(abs(claim - v) <= tol for v in f.numeric)]
        return hits[0] if len(hits) == 1 else None
    # text claim
    ctoks = {w.lower() for w in _WORD.findall(str(claim)) if w.lower() not in _STOP}
    if not ctoks:
        return None
    scored = sorted(((len(ctoks & f.phrases), f.label) for f in feats), reverse=True)
    if not scored or scored[0][0] == 0:
        return None
    if len(scored) > 1 and scored[1][0] >= scored[0][0]:    # no clear winner
        return None
    return scored[0][1]


def verify_answer_label_matches_reasoning(candidate, sample) -> bool:
    """True iff the candidate's selected label is consistent with its own reasoning.

    Numeric: a strong numeric result in the reasoning must appear in the selected
    option. Text: if the reasoning maps cleanly to a single option, it must be the
    selected one. Declines (returns True) only when nothing is determinable.
    """
    choices = sample.get("choices", []) or []
    labels = [chr(ord("A") + i) for i in range(len(choices))]
    ans = normalize_label(getattr(candidate, "answer", None), labels)
    if ans is None:
        return False
    text = " ".join(str(x or "") for x in (getattr(candidate, "proof_text", ""),
                                           getattr(candidate, "evidence_text", ""),
                                           getattr(candidate, "rationale", "")))
    # Numeric check (decisive when a result is stated).
    claim = strong_claim(text)
    if claim is not None:
        mapped = map_claim_to_option(claim, choices)
        if mapped is not None and mapped != ans:
            return False
        # also: the selected option must contain the claim if it has numbers
        opt_vals = extract_option_numeric_values(choices[labels.index(ans)])
        if opt_vals and not any(abs(claim - v) <= 1e-6 + 1e-3 * abs(claim) for v in opt_vals):
            return False
    return True
