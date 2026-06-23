# Audit — Phase 2L.34A: V12 Delta-Safe Verifier Experiment

**Date:** 2026-06-23  **Branch:** `main`  **Status:** experimental shadow pipeline (no commit, no API)

## Goal and safety boundaries

Build an **experimental v12 improvement layer** on top of the frozen v11 winner that proposes
conservative answer changes **only when there is strong independent evidence**. The production
default is untouched: `final_infer.py` / Docker still serve frozen v11 (78.4). All new code is
a *shadow* pipeline — it reads the v11 artifacts and writes to a new, gitignored shadow CSV.

Safety boundaries enforced:
- No change to `scripts/final_infer.py` default or the Docker default.
- Never writes `pred_v11_independent_rerun1.csv`, `pred_v10_…csv`, `pred_v8_…csv`, or
  `pred.csv` (hard `_PROTECTED_NAMES` guard in the selector; unit-tested).
- No ground truth / answer tables / hidden answers / external 3-LLM sheet used as truth.
- No qid/answer hardcoding (regex-tested across all four scripts).
- Only the competition-allowed Qwen3.5-≤9B model id; validated via `src.model_policy` before
  any client construction.
- **No API call in this phase** — verifier defaults to dry-run.

## Files created / changed

**Created (all untracked; nothing committed):**
- `scripts/build_v12_delta_plan.py` — offline delta candidate miner (Part A).
- `scripts/run_v12_delta_verifier.py` — specialist verifier runner, dry-run by default (Part B).
- `scripts/build_v12_delta_candidate.py` — conservative delta selector (Part C).
- `scripts/audit_v12_delta_candidate.py` — offline review tool (Part D).
- `tests/test_v12_delta_2l34a.py` — 13 tests (Part E).
- `docs/audits/AUDIT_PHASE_2L34A_…md` — this audit.
- `outputs/pred_v12_delta_candidate.csv` — shadow candidate (**gitignored** via `outputs/*`;
  in this dry-run it is byte-identical to v11).

**Changed:** none of the production/default files. No existing source edited.

## Why default v11 78.4 remains untouched

The selector starts from the v11 CSV and only *overrides* a qid when independent evidence
clears every gate; with **dry-run candidates (no model answers) it accepts 0 overrides**, so
the shadow CSV md5 == v11 md5 (`69f4e7c990e8c612e7bee53084d13b4d`). `final_infer.py`,
`docker_entrypoint_v11.sh`, and `configs/production_v11_independent.json`
(`default_mode=frozen_csv`, `current_best_csv=…pred_v11_independent_rerun1.csv`) are unchanged
(unit-tested: `test_final_infer_default_remains_frozen_v11`).

## Delta plan summary (Part F.1, offline)

`build_v12_delta_plan.py` over 463 qids → **457 planned** (opportunity_score > 0), 457 flagged
`needs_api`. Ranking is driven by fallback provenance, decision risk, v11≠v10 disagreement,
API-candidate disagreement, calc-without-deterministic-proof, many-choices, parse failures,
long-context. Top opportunities (highest score 16.0) are exactly the
`direct_fallback` + `risk:high` + `v11≠v10` calculation qids (e.g. `test_0043`, `test_0155`,
`test_0246`) — i.e. the current answers most likely to be guesses. No answer is changed by this
step; it only emits `scratch/v12_delta_verifier/v12_delta_plan.csv`.

## Dry-run verifier summary (Part F.2, NO API)

`run_v12_delta_verifier.py --max-qids 50 --dry-run`:
```
planned_qids        : 50
candidates_written  : 207   (offline stubs + dry-run model placeholders)
model_prompts_built : 118   (exact JSON-only prompts, recorded, NOT sent)
model_calls_made    : 0
mode                : dry_run
```
The model prompt contract is verified to force JSON-only with `selected_label`,
`selected_option_text` (verbatim copy), `evidence`, `equation` (calculation), and
`label_matches_option` self-check. Offline agents (`deterministic_solver`,
`numeric_consistency`, `option_grounding`) decline cleanly (`selected_label=null`) without API.

End-to-end on the dry-run candidates: selector → **0 accepted / 0 applied / 0 rejected /
changed_vs_v11 = 0**, validation PASS; audit tool confirms identical label distribution and
PASS validation.

## Conservative selector gates (Part C)

A proposed label ≠ current is applied only if it passes ALL guards and an acceptance rule:
- **Guards:** verifier must have produced a concrete label, `parse_status==ok`, and
  `label_matches_option != false`; any explicit label/option (numeric) mismatch for the
  proposed label aborts the override.
- **Conservative acceptance:** ≥2 independent (distinct-agent) non-current sources agree on the
  same new label; **or** deterministic-solver proof + a grounded verifier; **or** judge +
  grounded verifier agree.
- **Balanced** additionally allows a single strong deterministic proof.
All gates are unit-tested (reject weak model-only single source; accept 2 independent; accept
deterministic low-risk; reject numeric mismatch).

## Tests run and results (Part E)

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_v12_delta_2l34a.py`: **13 passed**
- `pytest -q` (full suite): **631 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Model policy audit result

**PASS** — the only model id referenced (`qwen/qwen3.5-9b-20260310`) is allowed
(`is_allowed_llm_model` True, ≤9B Qwen3.5); no GPT/Claude/Gemini/DeepSeek/Llama.

## Confirmations

- **No API calls** — verifier ran in dry-run; `model_calls_made = 0`; the API client is never
  constructed unless `--execute` is passed (and a disallowed model would raise before any call).
- **No outputs overwritten** — v11 winner md5 still `69f4e7c990e8c612e7bee53084d13b4d`; v10
  (`c12e32fd…`) and `pred.csv` (`002a0f73…`) unchanged. Shadow candidate written only to the
  gitignored `outputs/pred_v12_delta_candidate.csv`.
- **No qid hardcoding** — regex-tested across all four scripts; no answer tables / ground truth.
- **Default unchanged** — frozen v11 remains the production/Docker default.
- **Not committed.**

## Exact human command — run a small v12 verifier pilot (REAL API; opt-in)

> Requires `OPENROUTER_API_KEY` in the environment / `.env`. This spends budget — run only when
> you explicitly want the pilot. Build the plan first if not present.
```bash
.venv/bin/python scripts/build_v12_delta_plan.py \
  --input public-test_1780368312.json \
  --current outputs/pred_v11_independent_rerun1.csv \
  --v10 outputs/pred_v10_full_production_user_run.csv \
  --decisions scratch/full_v11_independent_rerun1/v11_independent_decisions_repaired.csv \
  --candidates scratch/full_v11_independent_rerun1/v11_independent_candidates.jsonl \
  --output scratch/v12_delta_verifier/v12_delta_plan.csv

.venv/bin/python scripts/run_v12_delta_verifier.py \
  --input public-test_1780368312.json \
  --current outputs/pred_v11_independent_rerun1.csv \
  --plan scratch/v12_delta_verifier/v12_delta_plan.csv \
  --work-dir scratch/v12_delta_verifier \
  --model qwen/qwen3.5-9b-20260310 \
  --max-qids 30 --budget-usd 0.50 --execute
```

## Exact human command — build a v12 candidate CSV (offline, from verifier output)

```bash
.venv/bin/python scripts/build_v12_delta_candidate.py \
  --input public-test_1780368312.json \
  --current outputs/pred_v11_independent_rerun1.csv \
  --candidates scratch/v12_delta_verifier/v12_delta_candidates.jsonl \
  --output outputs/pred_v12_delta_candidate.csv \
  --review-dir scratch/v12_delta_verifier/review \
  --policy conservative

.venv/bin/python scripts/audit_v12_delta_candidate.py \
  --input public-test_1780368312.json \
  --current outputs/pred_v11_independent_rerun1.csv \
  --candidate outputs/pred_v12_delta_candidate.csv \
  --plan scratch/v12_delta_verifier/v12_delta_plan.csv \
  --candidates scratch/v12_delta_verifier/v12_delta_candidates.jsonl \
  --output-dir scratch/v12_delta_verifier/audit
```
(The shadow candidate is for evaluation only; it is **not** wired into `final_infer.py` and
must beat v11 on held-out evidence before any future promotion.)

## Git status

```
?? scripts/audit_v12_delta_candidate.py
?? scripts/build_v12_delta_candidate.py
?? scripts/build_v12_delta_plan.py
?? scripts/run_v12_delta_verifier.py
?? tests/test_v12_delta_2l34a.py
?? docs/audits/AUDIT_PHASE_2L34A_V12_DELTA_SAFE_VERIFIER_EXPERIMENT.md
```
(`outputs/pred_v12_delta_candidate.csv` and `scratch/v12_delta_verifier/` are gitignored.)
Nothing committed.
