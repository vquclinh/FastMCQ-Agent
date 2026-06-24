"""Independent answer selector (Phase 2L.30B).

Selects ONE final answer per question from a candidate pool WITHOUT any v10 base answer.
Unlike ``answer_ranker.select_answer`` (which keeps v10 unless beaten), this selector has
no base to fall back to — it must always produce a label from the candidates themselves,
or, as a last resort, from a high-risk direct fallback candidate. It never reads or uses a
v10 answer.

Selection order:
  1. exactly one deterministic low-risk tool answer  -> use it
  2. deterministic answers conflict                  -> judge (if valid) else mark conflict
  3. >=2 consistent independent sources agree + evidence -> consensus
  4. a single strongest consistent evidence candidate passing option grounding -> use it
  5. conflicting consistent candidates + valid judge -> judge
  6. otherwise                                       -> direct fallback (high risk)
"""

from __future__ import annotations

from src.selector.answer_ranker import _is_deterministic, score_candidate
from src.selector.candidate_consistency import is_candidate_consistent
from src.evidence.option_grounding import verify_answer_label_matches_reasoning

_MIN_CONSENSUS_SOURCES = 2          # independent system: 2 agreeing independent sources suffice


def _evidence(c):
    return (c.proof_text or c.evidence_text or "") if c else ""


def _decision(answer, source, route, risk, *, winner=None, candidate_count=0, rejected=0,
              judge_used=False, fallback_used=False, parse_summary=None, note="",
              needs_direct_fallback=False):
    return {
        "final_answer": answer, "final_source": source, "route": route, "risk": risk,
        "evidence_summary": (_evidence(winner))[:160],
        "proof_summary": (winner.proof_text if winner else "")[:160],
        "candidate_count": candidate_count, "rejected_count": rejected,
        "judge_used": judge_used, "fallback_used": fallback_used,
        "parse_status_summary": parse_summary or {}, "note": note,
        "needs_direct_fallback": needs_direct_fallback,
    }


def _judge_valid(judge):
    return bool(judge) and judge.get("answer") and judge.get("parse_status") == "ok"


def select_independent_answer(pool, sample, *, route="", judge=None, fallback=None,
                              parse_summary=None):
    """Return (final_answer, decision). Never uses a v10 answer; fallback is a last resort."""
    cands = list(pool.candidates)
    labels = set()
    for i in range(len(sample.get("choices", []) or [])):
        labels.add(chr(ord("A") + i))
    n = len(cands)

    # Consistency partition (deterministic tool answers are trusted without the text guard).
    consistent = [c for c in cands if _is_deterministic(c) or is_candidate_consistent(c, sample)]
    rejected = n - len(consistent)

    # 1/2) Deterministic tool answers.
    det = [c for c in cands if _is_deterministic(c)]
    det_answers = {c.answer for c in det}
    if len(det_answers) == 1:
        winner = max(det, key=lambda c: score_candidate(c, pool, sample))
        return winner.answer, _decision(winner.answer, winner.source, route, "low", winner=winner,
                                        candidate_count=n, rejected=rejected,
                                        parse_summary=parse_summary,
                                        note="unique deterministic tool answer")
    if len(det_answers) > 1:
        if _judge_valid(judge) and judge["answer"] in det_answers:
            return judge["answer"], _decision(judge["answer"], "pairwise_judge", route, "medium",
                                              candidate_count=n, rejected=rejected, judge_used=True,
                                              parse_summary=parse_summary,
                                              note="deterministic conflict resolved by judge")
        winner = max(det, key=lambda c: score_candidate(c, pool, sample))
        return winner.answer, _decision(winner.answer, winner.source, route, "high", winner=winner,
                                        candidate_count=n, rejected=rejected,
                                        parse_summary=parse_summary,
                                        note="deterministic conflict, no valid judge -> best-scored")

    # 3) Consensus among consistent non-deterministic sources with evidence.
    by_answer = {}
    for c in consistent:
        if _is_deterministic(c):
            continue
        by_answer.setdefault(c.answer, []).append(c)
    for ans, group in by_answer.items():
        sources = {c.source for c in group}
        if len(sources) >= _MIN_CONSENSUS_SOURCES and any(_evidence(c) for c in group):
            winner = max(group, key=lambda c: (bool(_evidence(c)), c.confidence))
            return ans, _decision(ans, "consensus", route, "medium", winner=winner,
                                  candidate_count=n, rejected=rejected, parse_summary=parse_summary,
                                  note=f"{len(sources)} independent sources agree with evidence")

    # 4) Single strongest evidence candidate passing option grounding.
    grounded = [c for c in consistent if not _is_deterministic(c) and _evidence(c)
                and verify_answer_label_matches_reasoning(c, sample)]
    if grounded:
        winner = max(grounded, key=lambda c: (len(_evidence(c)), c.confidence))
        # require it to be a clear single best (no equally-strong competitor on another label)
        others = {c.answer for c in grounded if c.answer != winner.answer}
        if not others:
            return winner.answer, _decision(winner.answer, winner.source, route, "medium",
                                            winner=winner, candidate_count=n, rejected=rejected,
                                            parse_summary=parse_summary,
                                            note="single grounded evidence candidate")
        # 5) conflicting grounded candidates -> judge if valid
        if _judge_valid(judge):
            return judge["answer"], _decision(judge["answer"], "pairwise_judge", route, "medium",
                                              candidate_count=n, rejected=rejected, judge_used=True,
                                              parse_summary=parse_summary,
                                              note="evidence conflict resolved by judge")

    # 6) Direct fallback (last resort, high risk). Never v10.
    if fallback and fallback.get("answer") and fallback["answer"] in labels:
        return fallback["answer"], _decision(fallback["answer"], "direct_fallback", route, "high",
                                             candidate_count=n, rejected=rejected, fallback_used=True,
                                             parse_summary=parse_summary,
                                             note="no strong candidate -> direct fallback")

    # 7) Best VALID-label candidate (any parsed candidate with a real option label), high
    #    risk. Prefer consistent candidates, then any. Never returns a None/invalid label.
    valid_label = [c for c in cands if c.answer in labels]
    pool_choice = sorted([c for c in valid_label if c in consistent] or valid_label,
                         key=lambda c: c.confidence, reverse=True)
    if pool_choice:
        w = pool_choice[0]
        return w.answer, _decision(w.answer, w.source or "weak", route, "high", winner=w,
                                   candidate_count=n, rejected=rejected, parse_summary=parse_summary,
                                   note="no strong candidate and no fallback -> weakest valid-label choice")

    # 8) No candidate has a valid label. The selector MUST NOT emit a None answer silently;
    #    it signals the runner to call the direct allowed-model fallback (never v10).
    return None, _decision(None, "needs_fallback", route, "high", candidate_count=n,
                           rejected=rejected, parse_summary=parse_summary,
                           note="no valid-label candidate -> direct fallback required",
                           needs_direct_fallback=True)
