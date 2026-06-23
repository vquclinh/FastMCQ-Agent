# Audit — Phase 2L.37A: Integrate V13 Multi-Layer Reasoning into the Dynamic System

**Date:** 2026-06-23  **Branch:** `main`  **Status:** integration (no commit, no API, default unchanged)

## Files created / changed

**Created:**
- `src/v13_dynamic_layer.py` — `V13Target`, `V13LayerResult`, `select_v13_targets`
  (feature-based), `run_v13_layer` (API only under `execute_api`; deterministic arithmetic path
  offline).
- `src/system_candidate_selector.py` — `SystemOverrideDecision`, `select_system_overrides`
  (unified conservative V12B+V13 combiner).
- `tests/test_v13_dynamic_integration_2l37a.py` — 16 tests.
- `docs/audits/AUDIT_PHASE_2L37A_…md` — this audit.

**Changed:**
- `src/fastmcq_system.py` — wires V13 (`select_v13_targets`/`run_v13_layer`) after V12B and
  routes ALL overrides through `select_system_overrides`; config gains `v13_max_qids`,
  `system_policy`, `max_overrides`; report fills real V13 targets/overrides/executed. (Replaces
  the old visibility-only `v13_layer_registry` call.)
- `scripts/final_infer.py` — new flags `--v13-max-qids`, `--system-policy`, `--max-overrides`
  (existing flags preserved); richer logs (V13 targets/overrides + system overrides).
- `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`, `README.md`, manifest — document V13 integration,
  enable command, and the experimental V13 run; note legacy V13 scripts are superseded by
  `final_infer.py --mode dynamic_full --enable-v13`.

## How V13 is now wired into the real dynamic architecture

`run_fastmcq_system`: validate → dynamic base predictions → V12B targets+layer →
**(if `enable_v13`)** V13 targets+layer → **unified `select_system_overrides`** over base +
V12B + V13 → apply accepted overrides → validate exact-input qids → write. V13 is **off by
default**; V12B stays on by default; no API unless `execute_api=True`.

## How the three V13 methods are targeted (feature-based, no qid hardcoding)

`select_v13_targets` assigns layers per qid from features:
- **programmatic_solver** — numeric/formula domain (`classify_programmatic_domain`), route
  `calculation`, or numeric question + numeric options.
- **content_first** — proverb/term/definition keywords or routes `short_knowledge/long_context/
  ambiguous/law_admin`.
- **least_to_most** — multi-condition hints ("đúng/sai/phát biểu/chọn câu/ngoại trừ/…") or
  routes `law_admin/long_context`.
Priority is boosted by weak/low-confidence base, ≥5 options, and long questions.

## How the unified selector combines V12B + V13

`select_system_overrides` (conservative), per qid, proposes a label ≠ current and valid for the
sample, in priority order: (1) valid V12B conservative result; (2) programmatic unique
deterministic match; (3) cross-layer agreement (content+ltm / content+v12b / programmatic+
content); (4) content-first alone with strong confidence AND (weak current OR another layer);
(5) least-to-most single survivor with (weak current OR another layer). Rejects single weak
model-only source, parse failure, ambiguous/no match, invalid label, label/option or numeric
mismatch. `--max-overrides` keeps the strongest reasons first.

## V13 default status

Disabled by default (`enable_v13=False`; CLI `--disable-v13` default). Enable with
`--enable-v13`. Model-dependent V13 layers require `--execute-api`; without API they report
`skipped_no_api`. The deterministic programmatic arithmetic path runs offline.

## No-api smoke results (Part I)

3-sample mixed private input (`private_v13_0001` numeric, `_0002` multi-condition CSDL,
`_0003` proverb):
- **V13 disabled** → `resolved mode: dynamic_full`, V13 targets=0 overrides=0, 3 qids, all `A`
  (matches 2L.36B), status PASS.
- **V13 enabled (no API)** → V13 targets=3, **1 override** (deterministic programmatic solved
  "2 + 2" → **B**); qids 2/3 stay `A` (`skipped_no_api`); exactly 3 qids; **no API**; PASS.
  Output: `n1=B, m1=A, p1=A`.

## Public replay smoke result (Part I)

```
final_infer.py --input public-test_1780368312.json --mode public_replay
  resolved mode: public_replay   md5: 075646adb4ec7d2db1b234186b091f70   status: PASS
md5 == outputs/pred_v12b_permutation_candidate_api30.csv  ✓
```

## Tests and model-policy results (Part H)

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_v13_dynamic_integration_2l37a.py`: **16 passed**
- `pytest -q` (full suite): **705 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Confirmations

- **No API calls** during coding or smokes — V13 model layers/base/V12B construct a client only
  under `--execute-api`; a disallowed model raises via `model_policy` before any call (tested).
- **No ground truth / hidden answers / answer tables / external 3-LLM sheet.**
- **No qid/answer hardcoding** — `v13_dynamic_layer.py` and `system_candidate_selector.py`
  regex-clean and contain no frozen-CSV path (tested).
- **V12B 78.83 remains public best / public_replay artifact** — md5
  `075646adb4ec7d2db1b234186b091f70` unchanged; v11 `69f4e7c9…`, v10 `c12e32fd…` unchanged.
- **Arbitrary private inputs still output exactly input qids** (smoke + tests
  `test_dynamic_full_v13_enabled_outputs_exact_qids`).
- **Not committed.**

## Git status

```
 M experiments/best_candidate_manifest.json  FINAL_RUN.md  DOCKER_SUBMISSION.md  README.md
 M scripts/final_infer.py  src/fastmcq_system.py
?? src/v13_dynamic_layer.py  src/system_candidate_selector.py
?? tests/test_v13_dynamic_integration_2l37a.py
?? docs/audits/AUDIT_PHASE_2L37A_INTEGRATE_V13_MULTILAYER_INTO_DYNAMIC_SYSTEM.md
   (plus untracked 2L.34–2L.36B src/scripts/tests/docs from prior phases; `scratch/`, `outputs/pred.csv` gitignored)
```
Nothing committed.

## Next step

Run `dynamic_full --execute-api --enable-v12b --enable-v13` on the public test with a limited
budget and compare the result to the **78.83** `public_replay` artifact. Promote V13 into the
default only if the full dynamic+V13 run beats 78.83 on the leaderboard.
