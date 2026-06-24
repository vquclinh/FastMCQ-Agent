# Adaptive Reasoning Orchestrator Architecture (Phase 2L.15A)

An additive orchestration layer over the existing v6b pipeline. It analyzes every
question (not only calculation), selects a branch, gathers **non-binding**
candidates, and records an `adaptive` diagnostics object. It is **OFF by default**
and, when enabled, runs in **`trace_only`** mode: it never changes a final answer,
never makes an extra API call, and never overwrites predictions. **v6b remains the
stable fallback and source of truth.**

## Why the pipeline is global (not calculation-only)

The 2L.13/2L.14A risk audit found risk spread across routes — first-100 P0/P1:
short_knowledge 11, calculation 11, long_context 2. A calculation-only fix leaves
most risk untouched. The orchestrator therefore covers the whole MCQ flow so each
route can get the right kind of help (deterministic formula, selective verifier,
evidence sufficiency, adjudication) behind independent safety gates.

## Conceptual flow

```text
question + choices
  → route / risk analysis        (src/adaptive_routing.py)
  → branch selection             (calculation | long_context | short_knowledge | law_admin | ambiguous)
  → branch-specific candidates   (non-binding; e.g. src/programmatic_solver.py)
  → validation / gating          (mode + per-branch allow_* flags)
  → final answer  OR  fallback to existing v6b answer
```

In `trace_only`, the last two steps always resolve to **fallback** — the orchestrator
is read-only w.r.t. answers.

## Branches

| Branch | 2L.15A behavior | Future phase |
|---|---|---|
| calculation | non-binding deterministic candidate via `programmatic_solver` (wraps `calculation_solver`); formula-card eligibility logged | 2L.15B programmatic executors + gated override |
| long_context | **unchanged** Qwen reranker; placeholder flag `evidence_check_pending` | 2L.15D evidence sufficiency |
| short_knowledge | risk flags (`low_confidence`, `domain_admin_or_policy`, `answer_has_uncertain_reasoning`, `verifier_recommended`); **no extra API**, no answer change | 2L.15C selective verifier |
| law_admin | flags incl. `source_grounding_recommended` | 2L.15C / source grounding |
| ambiguous | `needs_adjudication` + `adjudication_reason` | candidate/adjudicator |

## Formula Registry & Cards

`src/formula_cards/` holds **metadata** cards (trigger keywords, required variables,
`do_not_use_when`, `target_intents`, executor name, `implemented`). `formula_registry`
does metadata-only eligibility — it does **not** compute answers. The numeric
executors stay in `calculation_solver.py`; 2L.15B binds them to cards.

**Relativity disambiguation (the 2L.13 bug):** `relativistic_gamma` is eligible only
when γ / "hệ số Lorentz" is the asked quantity and is excluded when "động lượng"/
"năng lượng"/"động năng" appears; `relativistic_momentum` is eligible only for
momentum questions. Eligibility for a γ-question and a momentum-question is disjoint.

## Why Formula-RAG retrieves templates, not answers

A future Formula-RAG step should retrieve **formula templates / cards** (the *method*:
variables + equation + option-match policy) to widen coverage of formula families —
never retrieve or store *answers*. Retrieving answers would be a disguised answer
table (forbidden, and would not generalize to the private test). Templates keep the
solver deterministic and auditable.

## Why short-knowledge RAG is deferred

Short-knowledge errors are largely model-knowledge gaps. A retrieval step needs a
**trusted, license-clean knowledge base**; without one, RAG would inject unverified
text. Until a valid KB exists, short_knowledge is handled by a *selective verifier*
(2L.15C) that re-checks only flagged, uncertain answers — not by RAG.

## Safety gates

- **Mode gate:** `trace_only` forbids any answer change and any extra API call;
  `would_override` is always `False`.
- **Per-branch allow flags:** `calculation.allow_override`,
  `long_context.allow_answer_change` (both default `false`) gate future modes.
- **Confidence/margin gates** remain in the deterministic solver (override only when
  `safe_to_override`).
- **Backward compatibility:** when disabled, no `adaptive` key is added to traces.

## Trace schema (`adaptive` object, when enabled)

```json
{
  "adaptive": {
    "enabled": true, "mode": "trace_only", "route": "...",
    "risk_flags": [], "selected_branch": "...", "branch_candidates": [],
    "would_override": false, "override_allowed": false,
    "final_decision": "fallback_existing_answer"
  }
}
```

## Config & CLI

```yaml
openrouter:
  adaptive_reasoning:
    enabled: false
    mode: "trace_only"
    calculation_programmatic: { enabled: true, allow_override: false }
    short_knowledge_verifier: { enabled: false }
    long_context_evidence_check: { enabled: true, allow_answer_change: false }
    self_consistency: { enabled: false }
```

CLI: `--adaptive-reasoning` (enables, trace_only). Overlay file:
`configs/adaptive_reasoning.yaml`. In 2L.15A only `enabled` + `mode` affect the
solver; the sub-blocks document intended 2L.15B–E behavior and stay inert under
`trace_only`.

## Completed branch calibration (Phase 2L.16)

All five branches now have **proposal/calibration-first** tooling. Every runner is
**dry-run by default**, calls OpenRouter only under explicit `--execute`, and patches
an answer only under explicit `--allow-override` AND the single shared override gate
(`src/adaptive_proposal_common.override_gate`). **v7 remains the current best
candidate; no v8 is built until proposal quality is reviewed.**

### Long-context evidence sufficiency (`src/evidence_sufficiency.py`)

Deterministic, no-API lexical scoring of the reranked/compressed evidence vs the
question + chosen option: `question_coverage`, `current_answer_support`,
`best_other_support`, `multiple_equally_supported`, `evidence_chars` →
`status ∈ {sufficient, weak, insufficient, unknown}` + a recommendation
(keep current / reranker top_k sweep / evidence expansion). It **never changes an
answer**; cross-option ambiguity is reported but routed to the `ambiguous` branch.
Public set: 87 sufficient / 13 weak; neither long_context P0/P1 is evidence-weak.

### Law-admin verifier (proposal-only)

`audit_law_admin_verifier_candidates.py` + `run_law_admin_verifier_sample.py`. All
law_admin items warrant **source grounding**; the verifier prompt forbids external
sheets and inventing legal sources, returns strict JSON with
`evidence_type ∈ {legal_admin_knowledge, option_elimination, uncertain}`, and keeps
current when uncertain. Gate: route==law_admin ∧ valid ∧ ≠current ∧ should_override ∧
confidence≥0.90 ∧ non-empty reason ∧ evidence_type≠uncertain ∧ allow_override.

### Ambiguous adjudicator (proposal-only)

`audit_ambiguous_adjudicator_candidates.py` + `run_ambiguous_adjudicator_sample.py`.
Adjudicator compares the look-alike options, returns strict JSON with
`uncertainty_reason` and `evidence_type ∈ {option_elimination, internal_reasoning,
uncertain}`, and prefers keeping current. Same gate shape.

### Selective self-consistency / best-of-N (proposal-only)

`audit_self_consistency_candidates.py` aggregates triggers (SK verifier recommended,
ambiguous route, law_admin source-grounding, long_context weak/insufficient, low
confidence, parse-review, calc deterministic disagreement) →
`self_consistency_candidates.csv`. `run_selective_self_consistency_sample.py` would
draw `n_samples` at low temperature and aggregate a majority vote
(`vote_distribution`, `majority_answer`, `consensus_strength`, `would_change_answer`).
**Override is NOT implemented this phase** — `override_applied` is always False.

### Unified analyzer

`analyze_adaptive_branch_proposals.py` combines any available proposal/audit CSVs,
reports per-branch proposed changes, confidence/evidence distributions, first-100
P0/P1 overlap, toward/away vs the diagnostic majority (with the not-ground-truth
warning), and how many proposals pass the override gate — then recommends *no v8 yet*
/ *v8 candidate possible* / *needs manual review*. It patches nothing.

## Why all new branches are proposal/calibration first

We have no ground truth on the public test (the external 3-LLM sheet is only a risk
signal). Before any branch is trusted to change answers we must measure its proposal
quality (change-rate, confidence, evidence_type, agreement patterns). Enabling
overrides prematurely risks regressing the validated v7. So every branch ships as
dry-run + proposal-only with a strict, shared, unit-tested override gate that stays
OFF by default.

## v7 remains current best until v8 is explicitly built

`output/pred_v7_programmatic_assist_from_v6b.csv` (v6b + 2 safe deterministic
calculation overrides, validated PASS) is the current best candidate. A v8 will be
built only in a later phase, after reviewing proposal batches, into a NEW file and
A/B'd vs v7 — no leaderboard claim without validation.

## Next phases

- Run controlled **proposal batches** (`--execute`, no `--allow-override`) per branch.
- Review with the unified analyzer; only then consider a gated **v8**.
