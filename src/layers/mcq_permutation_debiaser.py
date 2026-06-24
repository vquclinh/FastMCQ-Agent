"""MCQ option-permutation debiasing core (Phase 2L.34C).

Pure, deterministic, unit-testable logic for the V12B option-permutation debiaser. It builds
deterministic option permutations, maps a model's permuted-space choice back to the ORIGINAL
option label, validates records, tallies cross-permutation votes, and decides conservative /
balanced overrides.

This module makes **no** API/OpenRouter calls and constructs **no** client — the CLI scripts
own prompting and I/O. Nothing here uses ground truth or hardcodes qids/answers.
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass, field

from src.utils.labels import index_to_label, label_to_index, labels_for

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_STRONG_CONF = 0.6


# --------------------------------------------------------------------------- dataclasses
@dataclass
class OptionPermutation:
    permutation_id: str
    original_labels: list
    permuted_labels: list
    permuted_to_original: dict
    original_to_permuted: dict
    permuted_choices: list  # list[{"label","text","original_label"}]


@dataclass
class PermutationMapResult:
    selected_label: str | None
    selected_option_text: str | None
    mapped_original_label: str | None
    label_option_match: bool
    parse_status: str
    valid: bool
    failure_reason: str


@dataclass
class PermutationVoteSummary:
    qid: str
    current_answer: str
    valid_records: int
    vote_counts: dict
    current_votes: int
    top_non_current_label: str | None
    top_non_current_votes: int
    mismatch_count: int
    parse_failure_count: int
    mean_support_confidence: float | None


@dataclass
class PermutationOverrideDecision:
    qid: str
    accept: bool
    proposed_answer: str | None
    policy: str
    reason: str
    vote_summary: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- normalization
def normalize_option_text(text) -> str:
    """Normalize option text for robust matching: NFKD unicode fold (drop combining marks),
    casefold, strip punctuation, collapse whitespace. 'Héllo, World!' -> 'hello world'."""
    if text is None:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold()
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


# --------------------------------------------------------------------------- permutations
def _index_permutations(m, seed):
    base = list(range(m))
    cand = [
        ("original", base[:]),
        ("reverse", base[::-1]),
        ("rotate+1", base[1:] + base[:1]),
        ("rotate+2", base[2:] + base[:2]),
    ]
    for k in (1, 2):
        rng = random.Random(seed + k)
        shuf = base[:]
        rng.shuffle(shuf)
        cand.append((f"random_seed{k}", shuf))
    return cand


def build_option_permutations(sample: dict, n: int = 6, seed: int = 42):
    """Return up to ``n`` deterministic OptionPermutations (deduped by ordering).

    Supports any label count the dataset uses (beyond H). Permuted position j shows the
    original option at index perm[j] under the j-th label.
    """
    choices = sample.get("choices") or []
    m = len(choices)
    original_labels = labels_for(m)
    out, seen = [], set()
    for pid, perm in _index_permutations(m, seed):
        key = tuple(perm)
        if key in seen:
            continue
        seen.add(key)
        permuted_labels = labels_for(m)
        permuted_to_original, original_to_permuted, permuted_choices = {}, {}, []
        for j, orig_idx in enumerate(perm):
            plab = permuted_labels[j]
            olab = original_labels[orig_idx]
            permuted_to_original[plab] = olab
            original_to_permuted[olab] = plab
            permuted_choices.append({"label": plab, "text": choices[orig_idx],
                                     "original_label": olab})
        out.append(OptionPermutation(
            permutation_id=pid, original_labels=original_labels,
            permuted_labels=permuted_labels, permuted_to_original=permuted_to_original,
            original_to_permuted=original_to_permuted, permuted_choices=permuted_choices))
        if len(out) >= n:
            break
    return out


def _norm_label(raw, valid_labels):
    if raw is None:
        return None
    try:
        idx = label_to_index(str(raw))
    except (ValueError, TypeError):
        return None
    lab = index_to_label(idx) if 0 <= idx < len(valid_labels) else None
    return lab if (lab in valid_labels) else None


def map_permuted_answer_to_original(sample, permutation, selected_label,
                                    selected_option_text, label_matches_option=None):
    """Map a permuted-space choice to its ORIGINAL option label, validating consistency.

    Invalid when: label out of range; the model's own label/option self-check is False;
    the copied option text does not match the selected option after normalization; or the
    option text clearly matches a DIFFERENT option than the selected label.
    """
    perm_labels = permutation.permuted_labels
    plabel = _norm_label(selected_label, perm_labels)
    if plabel is None:
        return PermutationMapResult(selected_label, selected_option_text, None, False,
                                    "ok", False, "label_out_of_range")
    mapped = permutation.permuted_to_original.get(plabel)
    if label_matches_option is False:
        return PermutationMapResult(selected_label, selected_option_text, mapped, False,
                                    "ok", False, "self_label_option_conflict")

    text_match = True
    if selected_option_text not in (None, ""):
        want = {pc["label"]: normalize_option_text(pc["text"]) for pc in permutation.permuted_choices}
        got = normalize_option_text(selected_option_text)
        chosen = want.get(plabel, "")
        same = got and (got == chosen or got in chosen or chosen in got)
        if not same:
            # Does the text instead match some OTHER option? -> conflict; else -> no-match.
            other = [lab for lab, t in want.items() if t and (got == t or got in t or t in got)]
            reason = "label_text_conflict" if other else "option_text_no_match"
            return PermutationMapResult(selected_label, selected_option_text, mapped, False,
                                        "ok", False, reason)
    return PermutationMapResult(selected_label, selected_option_text, mapped, bool(text_match),
                                "ok", True, "")


# --------------------------------------------------------------------------- records / votes
def validate_permutation_record(record: dict):
    """(valid, reason) for a stored permutation record (as written by the runner)."""
    if (record.get("parse_status") or "") != "ok":
        return False, f"parse_status={record.get('parse_status')}"
    if not record.get("mapped_original_label"):
        return False, "no_mapped_label"
    if record.get("label_option_match") is not True:
        return False, "label_option_mismatch"
    if record.get("valid") is False:
        return False, record.get("failure_reason") or "marked_invalid"
    return True, "ok"


def summarize_permutation_votes(qid, current_answer, records):
    valid, mismatch, parse_fail = [], 0, 0
    for r in records:
        if (r.get("parse_status") or "") != "ok":
            parse_fail += 1
            continue
        if r.get("label_option_match") is not True:
            mismatch += 1
            continue
        ok, _ = validate_permutation_record(r)
        if ok:
            valid.append(r)
    counts = {}
    for r in valid:
        counts[r["mapped_original_label"]] = counts.get(r["mapped_original_label"], 0) + 1
    alt = {l: c for l, c in counts.items() if l != current_answer}
    top_label = max(alt, key=lambda L: (alt[L], -ord(L))) if alt else None
    top_votes = alt.get(top_label, 0) if top_label else 0
    confs = [r.get("confidence") for r in valid
             if r.get("mapped_original_label") == top_label
             and isinstance(r.get("confidence"), (int, float))]
    mean_conf = (sum(confs) / len(confs)) if confs else None
    return PermutationVoteSummary(
        qid=qid, current_answer=current_answer, valid_records=len(valid),
        vote_counts=counts, current_votes=counts.get(current_answer, 0),
        top_non_current_label=top_label, top_non_current_votes=top_votes,
        mismatch_count=mismatch, parse_failure_count=parse_fail,
        mean_support_confidence=mean_conf)


def select_permutation_override(summary: PermutationVoteSummary, policy: str = "conservative"):
    s = summary
    vs = {"valid_records": s.valid_records, "vote_counts": s.vote_counts,
          "current_votes": s.current_votes, "top_non_current_label": s.top_non_current_label,
          "top_non_current_votes": s.top_non_current_votes,
          "mean_support_confidence": s.mean_support_confidence}

    def _decision(accept, reason):
        return PermutationOverrideDecision(
            qid=s.qid, accept=accept,
            proposed_answer=s.top_non_current_label if accept else None,
            policy=policy, reason=reason, vote_summary=vs)

    if not s.top_non_current_label:
        return _decision(False, "no non-current votes")
    # Supporters are drawn only from VALID records (parse ok + label/option match), so the
    # "no supporter mismatch/parse failure" rule is satisfied by construction.
    n, best, cur = s.valid_records, s.top_non_current_votes, s.current_votes

    if n >= 5 and best >= 4 and cur <= 1:
        return _decision(True, f"conservative: {best}/{n} stable, current={cur}")
    if policy == "balanced" and cur <= 1 and (
            (n == 5 and best >= 3) or (n >= 6 and best >= 4)) \
            and (s.mean_support_confidence or 0) >= _STRONG_CONF:
        return _decision(True, f"balanced: {best}/{n} stable, conf={s.mean_support_confidence:.2f}")
    return _decision(False, f"insufficient stable votes ({best}/{n}, current={cur})")
