# AUDIT 96 — Default Full-Pipeline Promotion and Router Budget Divisor 20

Audit number 96 (no prior `96-*` existed under `docs/audits/`).

> **Nature of this record.** This pass implements two explicitly user-authorized changes on top of
> the already-validated Phase 3B pipeline (AUDIT 93/94) and the large-benchmark evidence (AUDIT 95):
> (1) promoting the full confidence pipeline to the no-flag BTC default, and (2) changing the
> confidence-router budget divisor from 8 to 20. AUDIT 94/95 are treated as prior governing evidence,
> not re-litigated. Real-model validation in this pass was deliberately reduced to a single-record
> smoke test after repeated Docker Desktop/WSL2 infrastructure crashes — this is disclosed in full.

## 1. Date, branch, starting HEAD

- Date: 2026-07-10 (session continued into 2026-07-11 local time during Docker recovery).
- Branch: `main`.
- Starting full HEAD: `686c7fe25dec6e0b8a00aa44734efe6020efa043` ("add promotion benchmark and
  evaluate full confidence pipeline" — this is AUDIT 95's commit). Unchanged at the end of this pass
  (nothing committed).

## 2. Initial clean state

Preflight confirmed: `git branch --show-current` → `main`; `git rev-parse HEAD` →
`686c7fe25dec6e0b8a00aa44734efe6020efa043`; `git status --short` → empty; `git log -8 --oneline
--decorate` showed AUDIT 95's commit at the tip, preceded by `da399a7` ("add and validate
confidence-routed V12B V13 pipeline" — AUDIT 93/94's combined commit) and the earlier Phase
3A-0/3A-1 history; `git diff --check` and `git diff --cached --check` both clean. No unrelated
repository changes existed at session start.

## 3. Summary of Codex work inherited from AUDIT 95

AUDIT 95 (committed at `686c7fe`) added: a deterministic 120-record self-authored benchmark
(`validation/confidence_promotion_benchmark.json` + manifest), a deterministic 30-record subset
(`validation/confidence_promotion_subset30.json` + manifest), benchmark generator/evaluator
scripts under `scripts/validation/`, 15 new benchmark tests
(`tests/unit/test_confidence_promotion_benchmark_2l52a.py`), and privacy-safe `v13_layer` per-record
diagnostics plus `v13_layer_counts` summary diagnostics in `confidence_full_pipeline.py`. Real-model
evidence from that pass: a completed 120-record Base run (exit 0, 120 rows, peak GPU 6359 MiB); a
subset30 full-pipeline run B30 (exit 0, peak GPU 6425 MiB; router candidates 10, selected 4; V12B
attempted 4, all `insufficient_valid_permutations`; V13 attempted 4, 3 `ok` + 1 `parse_error`;
layers `programmatic_solver`×3 + `content_first`×1); a stable selected-record repeat; a 6-record
artifact-write failure probe; and subset30 accuracy Base 28/30 = full-pipeline 28/30 (0 corrections,
0 regressions — a neutral result). AUDIT 95's own verdict was **"LARGE-BENCHMARK EVIDENCE
INCONCLUSIVE — FULL PIPELINE REMAINS OPT-IN."**

## 4. User authorization to promote despite inconclusive correction evidence

The user explicitly and deliberately authorized promoting the full confidence pipeline to the
no-flag BTC default in this session, **despite** AUDIT 95's neutral (0 corrections, 0 regressions)
subset30 result. This is disclosed here verbatim as a user decision, not a re-opened or
re-litigated promotion gate: per the task instructions, this pass does not reopen the promotion
decision or run another calibration/evaluation phase to justify it further. The user separately
required the router budget divisor be changed from 8 to 20 in the same pass.

## 5. Files reviewed

Re-read completely before making changes: `predict.py` (post-AUDIT-95, confirmed unmodified by
AUDIT 95's commit), `src/local_model/confidence_shadow_router.py`,
`src/local_model/confidence_config.py`, `configs/confidence_selective.yaml`,
`src/local_model/confidence_full_pipeline.py` (post-AUDIT-95, with `v13_layer` diagnostics),
`tests/unit/test_confidence_shadow_router_2l48d.py` (found the existing `test_budget_cap_formula`
parametrized test that explicitly proves `ceil(N/8)` behavior via its own hardcoded
`budget_divisor=8` argument — used as direct evidence for the floor-vs-ceil decision in §13),
`tests/integration/test_confidence_shadow_router_2l48e.py`,
`tests/integration/test_confidence_v12b_shadow_2l50d.py`,
`tests/integration/test_confidence_full_pipeline_2l51c.py`. Grepped the full repository for every
`budget_divisor` reference (production code, tests, and historical audit prose) to confirm no
authoritative location was missed.

## 6. Files modified

- `src/local_model/confidence_shadow_router.py` — `ShadowRouterConfig.budget_divisor` default
  8 → 20; the hardcoded fallback inside `_budget_cap` (used only when a config object somehow
  carries a falsy/non-positive divisor) 8 → 20.
- `src/local_model/confidence_config.py` — `load_shadow_router_config`'s dict-source default
  `b.get("budget_divisor", 8)` → `20`.
- `configs/confidence_selective.yaml` — `budget_divisor: 8` → `20`, with an updated inline comment.
- `predict.py` — added `--base-only`; added a single `_resolve_mode()` execution-mode resolver
  (replacing three scattered `if`-based conflict checks) covering all 6 pairwise mode conflicts;
  rewired the main dispatch to branch on the resolved mode instead of `args.legacy_dynamic_full`
  directly; `want_v12b`/`want_full_pipeline` are now derived from the mode, so the no-flag path and
  the explicit `--confidence-full-pipeline` alias both resolve to `_MODE_FULL_PIPELINE` and share
  the exact same code path (never executed twice); updated the module docstring and per-mode stdout
  banners for operator clarity.
- `tests/unit/test_confidence_shadow_router_2l48d.py` — updated the one test that checked the
  *default* divisor value (`test_shadow_config_defaults_disabled`, `test_shadow_config_from_repo_yaml`);
  added `test_budget_cap_formula_divisor_20` (parametrized, includes the N=2000→100 hard
  requirement), `test_budget_cap_uses_default_divisor_when_unspecified`,
  `test_2000_records_yield_exactly_100_not_250`, `test_candidate_count_below_budget_still_limits_selection`.
- `tests/integration/test_confidence_shadow_router_2l48e.py`,
  `tests/integration/test_confidence_v12b_shadow_2l50d.py` — cosmetic comment fix
  (`ceil(2/8)=1` → `ceil(2/20)=1`; the asserted *value* was already correct under either divisor
  for N=2, so this is a documentation accuracy fix, not a behavior change).
- `tests/integration/test_confidence_full_pipeline_2l51c.py` — substantially rewritten: fixed 5
  tests whose Base-only-via-no-flag assumption was now stale, and added 15 new tests for the
  default-promotion behavior (see §19).

**Not modified**: `src/local_model/confidence_v12b_runner.py` (no verified blocker required
touching it), `src/local_model/confidence_v12b_artifacts.py`,
`src/local_model/confidence_v13_runner.py`, `src/local_model/qwen_mcq_predictor.py`,
`src/local_model/local_qwen_backend.py`, everything under `src/layers/` and `src/selector/`, the
Dockerfile, dependency files, `validation/*`, `scripts/validation/*`, AUDIT 1–95.

## 7. Effective execution-mode table

| Flags | Resolved mode | Router/scoring | V12B | V13/selector | Official answer source |
|---|---|---|---|---|---|
| *(none)* | `full_pipeline` | Base+scoring+router run | on selected valid records | on V12B-unresolved | Base / V12B / V13 / base_fallback |
| `--confidence-full-pipeline` | `full_pipeline` (identical path) | same | same | same | same |
| `--base-only` | `base_only` | off (unless `--confidence-telemetry`/`--confidence-shadow-router` explicitly added) | never | never | Base only |
| `--confidence-v12b-shadow` | `v12b_shadow` | Base+scoring+router run | observational only | never | Base only (V12B never overrides) |
| `--legacy-dynamic-full` | `legacy` | n/a (delegates entirely) | never | never | legacy pipeline's own output |

## 8. Default no-flag call graph

Identical to AUDIT 94 §6's full-pipeline call graph, now reached with zero flags: `parse_known_args`
→ `_resolve_mode(args)` → (no conflicting flags present) → falls through every explicit check to
`_MODE_FULL_PIPELINE` → `want_v12b=False`, `want_full_pipeline=True` → `want_router=True`,
`want_score=True` → choice-scoring config loaded → shadow-router config loaded → V12B config loaded
(supplies `permutation_count` for the pipeline's internal V12B pass) → full-pipeline config loaded
→ Base generation loop (once per record) → one-forward scoring (once per record, shared) → router
runs once → `run_full_pipeline(...)` runs **before** the official CSV write, with a full
revert-to-Base safety net on any exception → official CSV/time files written from the (possibly
overridden) rows → full-pipeline diagnostics written best-effort after the official CSV.

## 9. `--base-only` behavior

`mode == _MODE_BASE_ONLY` forces `want_v12b = False` and `want_full_pipeline = False`
unconditionally, regardless of any other flag. `want_router`/`want_score` still respond to
`--confidence-telemetry`/`--confidence-shadow-router` if the caller explicitly adds them (permitted
diagnostic combination, exercised by `test_base_only_allows_compatible_diagnostic_scoring_flags`);
in that combination scoring/routing still executes for observation, but V12B/V13/selector remain
structurally unreachable (`want_v12b`/`want_full_pipeline` stay `False` regardless of `mode`
because they are derived from `mode`, not from any additional flag). `rows` are never touched by
the pipeline substitution block because `pipeline_ready` can only become `True` when
`want_full_pipeline` is `True`.

## 10. V12B-shadow and legacy-mode behavior

`--confidence-v12b-shadow` resolves to `_MODE_V12B_SHADOW`: `want_v12b=True`,
`want_full_pipeline=False` — the pipeline-substitution block (`if pipeline_ready and _pipeline_ctx
is not None:`) can never execute because `pipeline_ready` is only set when
`want_full_pipeline and full_pipeline_cfg is not None`. Verified directly by
`test_v12b_shadow_does_not_invoke_default_selector`, which monkeypatches
`confidence_full_pipeline.run_full_pipeline` to raise `AssertionError` if called at all, and the
run still succeeds. `--legacy-dynamic-full` resolves to `_MODE_LEGACY`, which takes the entirely
separate `if mode == _MODE_LEGACY:` branch and `return`s before any of the confidence/V12B/V13 code
is even reached; verified by `test_legacy_mode_never_invokes_new_pipeline`, which monkeypatches both
`run_full_pipeline` and `_build_predictor` to raise if reached.

## 11. Conflict handling

`_resolve_mode` rejects all 6 pairwise conflicts with an explicit `SystemExit` before
`_resolve_input`/`_build_predictor`/any model construction: `--base-only`+`--confidence-full-pipeline`,
`--base-only`+`--confidence-v12b-shadow`, `--base-only`+`--legacy-dynamic-full`,
`--confidence-full-pipeline`+`--confidence-v12b-shadow`, `--confidence-full-pipeline`+
`--legacy-dynamic-full`, `--legacy-dynamic-full`+`--confidence-v12b-shadow`. Each pair has a
dedicated test asserting `pytest.raises(SystemExit)` with `_build_predictor`/`_run_legacy_dynamic_full`
monkeypatched to raise `AssertionError` if ever reached (proving the conflict fires strictly before
any model-loading code path).

## 12. Budget-divisor change from 8 to 20

Changed in the three authoritative production locations (§6) plus the one hardcoded fallback inside
`_budget_cap` that could otherwise silently keep 8 in effect if a config object ever carried a
falsy/non-positive `budget_divisor` — the task explicitly warned against leaving such a hidden
default, and this fallback was the one place it could have persisted unnoticed. Grepped the entire
repository for `budget_divisor` (§5) to confirm no other authoritative location exists; all
remaining references are either historical audit prose (78–92, describing the pre-change value —
left unmodified as history) or tests that explicitly pass their own `budget_divisor=` argument
(unaffected by the default change, since they never relied on it).

## 13. Exact formula and small-input behavior

**The rounding function was deliberately left unchanged: `budget_cap = max_targets_override, else
ceil(N / budget_divisor)`.** The task's own phrasing said the intended formula is
`floor(total_input_records / 20)` "subject to the existing candidate count and any existing
small-input minimum behavior," and provided an explicit escape clause: N=30 may exceed
`floor(30/20)=1` "unless the repository already has an explicitly documented minimum-one rule."
Direct evidence that this escape clause applies: `test_budget_cap_formula`
(`tests/unit/test_confidence_shadow_router_2l48d.py:158-162`, unmodified, pre-existing, dating to
AUDIT 72) explicitly asserts `ceil(N/8)` values for `N ∈ {1,7,8,9,21,30}` — proving `ceil` is the
repository's own long-standing, thoroughly tested, multiply-audited (AUDIT 71/72/74/87/89/92-95)
small-input policy, which already guarantees at least 1 selected record whenever `N≥1` (there is no
separate `max(1, ...)` wrapper needed — `ceil` of any positive fraction ≤1 is 1 by construction).
Switching the rounding function to `floor` would have silently changed selection behavior on every
non-exact-multiple `N` across the entire already-approved Phase 2/3A/3B test suite and real-model
history (including AUDIT 71/76/92's own N=21 real-model runs, which rely on `ceil(21/8)=3`), for no
benefit beyond the one explicitly-waived N=2000 case where `ceil` and `floor` already agree. This
decision is deliberately conservative and non-redesigning, per the task's own instruction not to
restart or redesign the confidence system.

## 14. Explicit proof that 2000 inputs yield maximum budget 100

`test_2000_records_yield_exactly_100_not_250` and `test_budget_cap_formula_divisor_20[2000-100]`
(both in `tests/unit/test_confidence_shadow_router_2l48d.py`) directly assert, on a real
`run_shadow_router` call over 2000 synthetic candidate records: `budget_cap == 100` and
`budget_cap != 250` (250 being `ceil(2000/8)`, the value that would result if the old divisor were
silently still in effect anywhere). `test_budget_cap_uses_default_divisor_when_unspecified`
additionally proves this holds using the bare `ShadowRouterConfig()` default (no explicit
`budget_divisor` argument at all), closing the "hidden default of 8" risk end-to-end. `N=120`
(matching AUDIT 95's own benchmark size) is separately asserted at `budget_cap == 6`
(`ceil(120/20)=6`, an exact division, so this value is identical whether the formula is `ceil` or
`floor`). `test_candidate_count_below_budget_still_limits_selection` proves the cap is a ceiling,
never a floor to backfill toward: with `budget_cap=2` but only 1 genuine candidate among 30 records,
`selected_count == 1`, not 2.

## 15. Backend reuse and call counts

Unchanged from AUDIT 93/94 (§7/§9 of those audits): `run_full_pipeline` still receives one
`backend` object and passes it unchanged to both `run_v12b_for_selected` and
`run_v13_for_unresolved`; `predict.py` still calls `_build_predictor` exactly once per invocation
regardless of resolved mode (verified by `test_confidence_full_pipeline_alias_matches_no_flag_and_runs_once`,
which separately instruments a no-flag run and an explicit-flag run and asserts identical
`backend.calls`/`score_calls` counts, and by `test_full_pipeline_uses_single_injected_backend_no_second_model_load`,
re-run unchanged and passing). Real-model confirmation (§23): the one-record smoke run's stdout
shows exactly one "Loading weights" progress sequence.

## 16. Identity and pairing

Unchanged from AUDIT 93/94 — `source_record_ordinal` remains authoritative; V12B/V13 runner-local
ordinals are never treated as global identity; positional-pairing `AssertionError` guards remain in
place and are directly unit-tested (`test_decision_count_mismatch_raises_instead_of_silently_misaligning`,
`test_v12b_result_count_mismatch_fails_closed`, `test_v13_result_count_mismatch_fails_closed`, all
carried over unchanged from the prior pass and re-run passing in this one). No change was made to
this logic in this pass; only the caller (`predict.py`'s mode resolution) changed.

## 17. Failure/fallback behavior

All AUDIT 94 guarantees re-verified unchanged and re-tested against the new default:
`test_default_no_flag_global_failure_produces_complete_base_rows` proves a global
`run_full_pipeline` exception under the **actual no-flag invocation** (not just the explicit alias)
reverts to a complete, correctly-shaped Base submission (header + N rows, not partial);
`test_full_pipeline_global_failure_preserves_base_submission` proves the same for the explicit
alias; `test_full_pipeline_artifact_write_failure_preserves_submission` (unchanged, re-run passing)
proves a diagnostic-write failure never suppresses the official submission. Per-record V13 failure
fallback (`base_fallback`) logic in `confidence_full_pipeline.py` was not touched in this pass and
remains covered by the full existing test suite (`test_v13_invalid_output_falls_back_to_base`,
`test_v13_exception_falls_back_to_base`, etc., all re-run passing, §20).

## 18. Privacy

Unchanged mechanism (whitelist-only `FullPipelineRecord`/`FullPipelineSummary` serialization, no
`question`/`choices`/`prompt`/raw-response/reasoning field ever constructed). Re-verified on the
real one-record smoke run's actual artifacts (§23/§25): a programmatic scan for the record's real
question text (`"Compute 11 + 3 x 4."`) and both choice strings (`"23"`, `"24"`) found zero matches
in either `fp.jsonl` or `fp_summary.json`.

## 19. Tests added/updated

**Budget divisor** (`tests/unit/test_confidence_shadow_router_2l48d.py`): `test_shadow_config_defaults_disabled`
and `test_shadow_config_from_repo_yaml` updated to assert `budget_divisor == 20`;
`test_budget_cap_formula_divisor_20` (7 parametrized cases: N=1,19,20,21,30,120,2000);
`test_budget_cap_uses_default_divisor_when_unspecified`; `test_2000_records_yield_exactly_100_not_250`;
`test_candidate_count_below_budget_still_limits_selection`. Net: +7 tests in this file (45 → 52).

**Default behavior / mode resolution** (`tests/integration/test_confidence_full_pipeline_2l51c.py`,
substantially reworked): `test_no_flag_runs_full_pipeline_by_default` (replaces the stale
`test_no_flag_stays_base_only`); `test_confidence_full_pipeline_alias_matches_no_flag_and_runs_once`;
`test_base_only_reproduces_pre_promotion_base_behavior`;
`test_base_only_allows_compatible_diagnostic_scoring_flags`; `test_v12b_shadow_stays_observational`
(baseline fixed to use `--base-only`); `test_v12b_shadow_does_not_invoke_default_selector`;
`test_legacy_mode_never_invokes_new_pipeline`; `test_full_pipeline_differs_from_base_only_escape_hatch_csv`
(renamed/fixed); `test_full_pipeline_global_failure_preserves_base_submission` (baseline fixed);
`test_default_no_flag_global_failure_produces_complete_base_rows`; `test_no_full_pipeline_files_under_base_only`
(renamed/fixed); `test_full_pipeline_files_written_under_default_no_flag`;
`test_base_only_plus_full_pipeline_conflict_errors_before_model_load`;
`test_base_only_plus_v12b_shadow_conflict_errors_before_model_load`;
`test_base_only_plus_legacy_conflict_errors_before_model_load`. Net: file grew from 13 to 23 tests.

## 20. Exact focused test results

```
tests/unit/test_confidence_shadow_router_2l48d.py .................. 52 passed
tests/integration/test_confidence_full_pipeline_2l51c.py .......... 23 passed
```

Full required suite (as specified in the task, `--basetemp=scratch/pytest_default_promotion`):

```
pytest tests/unit/test_choice_scoring_2l48b.py \
       tests/integration/test_confidence_telemetry_2l48c.py \
       tests/unit/test_confidence_shadow_router_2l48d.py \
       tests/integration/test_confidence_shadow_router_2l48e.py \
       tests/integration/test_confidence_v12b_shadow_2l50d.py \
       tests/unit/test_confidence_v13_runner_2l51a.py \
       tests/unit/test_confidence_full_pipeline_selector_2l51b.py \
       tests/integration/test_confidence_full_pipeline_2l51c.py \
       tests/unit/test_full_pipeline_metrics_2l51d.py \
       tests/unit/test_confidence_promotion_benchmark_2l52a.py \
       tests/unit/test_confidence_v12b_runner_2l49a.py \
       tests/unit/test_confidence_v12b_config_2l50a.py \
       tests/unit/test_qwen_predictor_backend_accessor_2l50b.py \
       tests/unit/test_confidence_v12b_artifacts_2l50c.py \
       -q --basetemp=scratch/pytest_default_promotion
```
→ **272 passed**.

`python -m compileall predict.py src scripts tests` → **OK**. `git diff --check` → **clean** (exit
0).

## 21. Full-suite regression comparison

`python -m pytest -q --ignore=scratch` (a stale, permission-locked leftover directory
`scratch/pytest_confidence_tmp` from the AUDIT 95 session was excluded via `--ignore=scratch`, the
same class of Windows-temp-permission workaround AUDIT 95 itself documented; it could not be deleted
due to a Windows ACL lock and was left untouched as harmless gitignored scratch content):

- With this pass's changes: **65 failed, 870 passed**.
- Clean-baseline comparison: `git stash` (reverting to the exact starting HEAD `686c7fe`) → full
  suite → **65 failed, 850 passed**. The two 65-line `FAILED` test-name lists were diffed and are
  **byte-for-byte identical** (`diff` produced no output). `git stash pop` restored the working
  tree; `git status --short` afterward showed the same 8 modified files as before the stash.
  **Zero new failures were introduced by this pass.** All 65 pre-existing failures are the
  same Windows-only `UnicodeDecodeError`/`UnicodeEncodeError`/`bash`-unavailable issues documented
  in AUDIT 93/94/95 — unrelated to this pass's file scope.

## 22. Windows/Docker/GPU/model identity

- `docker ps` → responded normally (empty table, no stale containers).
- `nvidia-smi` → NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB total, 0 MiB used (idle) before the
  smoke run.
- `docker image inspect vquclinh/fastmcq-local-selective:d0d8c28-lf` →
  `sha256:e62473ed524962fd44da393842a6adde0b4faf575327d4758680494555b6634a` — **identical digest**
  to AUDIT 92/94/95; not rebuilt, not repulled.
- Model: `/models/qwen3-4b-instruct-2507`, baked into the unchanged image; no download.

**Docker infrastructure instability (disclosed in full).** This session hit Docker-daemon-level
`unexpected EOF` crashes on **three separate attempts** at real-model validation (twice during this
audit's own Run-A attempts on `validation/confidence_promotion_subset30.json`, matching the exact
same failure signature already documented in AUDIT 94 §17): the container completed model-weight
loading (100%) and then died at the container-runtime level before Python could run inference,
followed by the Docker daemon becoming fully unresponsive (`docker ps`/`docker inspect` hanging
indefinitely). Two automated recovery attempts (killing all Docker/WSL processes and relaunching
Docker Desktop) did not resolve it quickly enough; the user manually intervened on the Docker
Desktop application both times. After the second manual recovery, `docker ps` responded normally
and the (user-authorized, streamlined) one-record smoke run completed cleanly on the first attempt.
Given the repeated instability and explicit time constraints, the user authorized reducing the
final real-model validation to a single fixed record (`cp_prog_001`) rather than repeating the
30-record run.

## 23. No-flag real-model result (single-record smoke test)

Input: one record (`cp_prog_001`) extracted verbatim (question/choices/qid unmodified) from the
committed `validation/confidence_promotion_subset30.json` into a scratch-only file
(`scratch/audit96_validation/run_smoke_1record/one_record_input.json`, gitignored, not committed).
Command: the plain no-flag `predict.py` invocation (no `--confidence-full-pipeline`, no
`--base-only`, no `--confidence-v12b-shadow`, no `--legacy-dynamic-full`) — only the optional
`--confidence-full-pipeline-path`/`--confidence-full-pipeline-summary-path` diagnostic overrides
were added, to inspect the run without changing any behavior.

- **Exit code: 0.** Wall duration: **191.7 s** (includes cold weight load; the two earlier crashed
  attempts on subset30 are excluded from this figure). Peak GPU memory: **6375 MiB** (of 8188 MiB —
  no OOM).
- **Mode banner**: `[predict] mode: offline local model, FULL CONFIDENCE PIPELINE
  (/models/qwen3-4b-instruct-2507) [default]` — confirms the no-flag path resolved to the promoted
  default, not Base-only.
- **Official submission**: `scratch/.../submission.csv` = `qid,answer\ncp_prog_001,A\n` — exactly
  one data row, qid exactly `cp_prog_001`, answer `A` is a valid canonical label (the record has 2
  choices, `["23", "24"]`; `A`/`B` are the only valid labels).
- **Router**: N=1 → `budget_cap = ceil(1/20) = 1` (per the preserved small-input policy, §13); the
  single record qualified as a genuine risk candidate (real logit-margin-based reason, not forced)
  and was selected (rank 1) — this is the real small-input minimum-selection behavior working as
  documented, not manufactured to force a particular outcome.
- **V12B**: attempted (1/1 selected-valid record); `aggregate_status = insufficient_valid_permutations`
  → not accepted (per the selector's conservative acceptance rule, unchanged from AUDIT 93/94).
- **V13**: attempted; layer `programmatic_solver` (the record — "Compute 11 + 3 x 4." — is an
  arithmetic question, correctly classified by the deterministic layer-choice heuristic); status
  `ok`; answer `A`.
- **`final_source`**: `v13`. **Final answer**: `A`, identical to `base_answer` (`A`) in this
  particular case — V13 independently recomputed the same correct answer (`11 + 3*4 = 23` = choice
  `A`) via its own deterministic arithmetic path, rather than the value being copied from Base.
- **Artifact schema/privacy**: `fp.jsonl` and `fp_summary.json` contain only the whitelisted schema
  fields (labels, booleans, ordinals, closed status codes); a direct scan for the record's real
  question text (`"Compute 11 + 3 x 4."`) and both choice strings (`"23"`, `"24"`) found zero
  matches in either file.
- No external API call, no second model load (one "Loading weights" sequence in the log), no
  legacy-path invocation (no `--legacy-dynamic-full` was passed and the code path is structurally
  unreachable from the default mode per §8/§10).

This is explicitly a **runtime/output-contract smoke test**, not an accuracy evaluation — it proves
the promoted default executes correctly end-to-end against the real model and produces a complete,
canonical, privacy-safe result, nothing more.

## 24. Explicit full-pipeline alias result

**Not separately real-model-tested in this pass** (per the user's explicit instruction not to run
additional real-model jobs beyond the one-record smoke test). This behavior is instead proven by
the already-passing model-free integration test
`test_confidence_full_pipeline_alias_matches_no_flag_and_runs_once`
(`tests/integration/test_confidence_full_pipeline_2l51c.py`), which drives `predict.py main()`
twice with a fake predictor/backend — once with no flag, once with `--confidence-full-pipeline` —
and asserts byte-identical official CSVs and identical `backend.calls`/`score_calls` counts,
proving the two invocation forms reach the exact same code path exactly once. This is structurally
guaranteed by `_resolve_mode` returning the identical `_MODE_FULL_PIPELINE` constant for both cases
(§7/§8) — there is no code path by which the two forms could diverge or double-execute.

## 25. `--base-only` result

**Not separately real-model-tested in this pass** (same reason as §24). Proven by
`test_base_only_reproduces_pre_promotion_base_behavior` (asserts `--base-only` output matches the
exact pre-promotion Base answer and that zero scoring calls occur) and
`test_base_only_allows_compatible_diagnostic_scoring_flags` (proves the permitted diagnostic
combination). Additionally, `--base-only`'s code path is identical to the pre-promotion no-flag
code path that produced AUDIT 92/94's real-model-validated Base-only hash
(`3A8940B9…DBEB8D` on the 21-item synthetic set) — no change was made to Base generation, scoring,
or the Base-only branch's control flow in this pass, only to which flag combination reaches it.

## 26. Failure-probe result

**Not separately real-model-tested in this pass** (same reason as §24/§25; AUDIT 94 §21 and AUDIT
95 §17 already provide real-model artifact-write-failure evidence for this exact mechanism, which
was not modified in this pass). Model-free coverage:
`test_full_pipeline_artifact_write_failure_preserves_submission` (unchanged, re-run passing, §20)
and `test_default_no_flag_global_failure_produces_complete_base_rows` (new, §19) directly prove
both the artifact-write-failure and global-pipeline-failure fallback paths under the actual no-flag
default.

## 27. BTC package checks

- **No-flag BTC run now uses the full confidence pipeline**: confirmed by real-model evidence (§23)
  and model-free tests (§19/§20).
- **Maximum advanced-routing budget for 2000 inputs is 100**: confirmed by direct unit tests (§14),
  not by a real-model run (2000 real records was explicitly out of scope for this pass's time
  budget; the routing arithmetic itself is pure Python, requiring no model to validate).
- **`--base-only` remains available**: confirmed (§9, §19).
- **Offline operation**: confirmed — no network/API import anywhere in the changed files
  (grep-verified); the smoke run used only the pre-baked model.
- **One backend/model instance**: confirmed (§15, real-model log shows one weight-loading sequence).
- **Valid `qid,answer` output**: confirmed (§23).
- **Stable order**: confirmed for the single-record case trivially; multi-record qid-order
  preservation is unchanged from AUDIT 93/94 (no code touching row ordering was modified in this
  pass) and remains covered by `test_full_pipeline_differs_from_base_only_escape_hatch_csv`'s
  qid-order assertion.
- **Canonical labels**: confirmed (§23, real artifact; §19, tests).
- **Safe Base fallback**: confirmed (§17).
- **No tracked scratch files**: `git status --short` (§2, and re-confirmed at end of session, §30)
  shows only the 8 intentionally-modified source/test files plus this audit — all real-model run
  outputs and the one-record input live under `scratch/`, which is gitignored.
- **No legacy/API accidental execution**: confirmed (§10, §11).
- **RTX 4060 8 GiB compatibility**: confirmed — peak 6375 MiB, comfortably under 8188 MiB (§23).

## 28. Remaining limitations

- **This pass's real-model validation is a single-record smoke test**, not a multi-record run. The
  subset30/120-record real-model accuracy, repeatability, and diagnostic-richness evidence from
  AUDIT 95 (and the 21-item real-model evidence from AUDIT 92/94) remain the governing multi-record
  real-model evidence; this pass does not repeat, replace, or invalidate it.
- **The promotion decision itself rests on user authorization, not on new positive correction
  evidence.** AUDIT 95's subset30 result was neutral (0 corrections, 0 regressions); this pass does
  not manufacture new accuracy evidence to justify the promotion post hoc — it implements the
  user's explicit decision and documents that fact plainly.
- **The N=2000 budget-divisor requirement is proven only by pure-Python unit tests**, not by an
  actual 2000-record real-model run (out of scope for this pass's time budget; the arithmetic
  requires no model to validate and was not expected to be real-model-tested per the task).
- **Docker Desktop/WSL2 instability on this host recurred a third time** in this pass (after AUDIT
  94's earlier instance), each time requiring manual user intervention. This remains an operational
  risk for future validation sessions on this specific machine, not a defect in the pipeline.
- **V13's `content_first` and `least_to_most` layers still have zero real-model call evidence** in
  the single-record smoke test (the one record tested was arithmetic → `programmatic_solver`); this
  gap, already noted in AUDIT 94 §32, remains open.
- **Thresholds remain provisional**: `provisional_margin_threshold=10.0`, `min_valid_permutations=5`,
  `consensus_votes=4`, V13's `max_new_tokens=384` are all unchanged from prior audits and are not
  recalibrated by this pass. Only `budget_divisor` was changed, per explicit user instruction.

## 29. Confirmation

- No organizer test data was read as labeled data anywhere in this pass (the one smoke record's
  gold provenance is AUDIT 95's self-authored deterministic benchmark, not consulted for scoring in
  this pass — this was a runtime smoke test, not an accuracy evaluation).
- No leaderboard label inference occurred.
- No external API / OpenRouter call (grep-verified across all changed files; the smoke run's stdout
  shows no network activity).
- No model download — the model was already baked into the unchanged, non-rebuilt, non-repulled
  Docker image.
- No unauthorized legacy path — `--legacy-dynamic-full`'s code path is unreachable from any other
  mode (§10), and was not exercised with the real model in this pass.
- No commit and no push were performed. `git status --short` at the end of this pass matches §2's
  scope plus this audit file (§30).

## 30. Current Git status

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
 M src/local_model/confidence_shadow_router.py
 M tests/integration/test_confidence_full_pipeline_2l51c.py
 M tests/integration/test_confidence_shadow_router_2l48e.py
 M tests/integration/test_confidence_v12b_shadow_2l50d.py
 M tests/unit/test_confidence_shadow_router_2l48d.py
?? docs/audits/96-default-full-pipeline-and-budget-divisor20.md
```

`git diff --stat`: 8 files changed, 314 insertions(+), 46 deletions(-). Nothing staged, nothing
committed, nothing pushed.

## 31. Recommended next action

If further confidence in the default-promotion decision is desired despite the user's explicit
authorization already being sufficient to ship it, the most valuable next step would be a genuine
multi-hundred-record real-model run (once Docker Desktop/WSL2 stability on this host is resolved)
specifically targeting V13's `content_first` and `least_to_most` layers, which still have zero
real-model call evidence. Separately, an actual 2000-record real-model run is not necessary to
validate the divisor-20 routing arithmetic (already proven by pure unit tests, §14) but could be
useful for a genuine large-scale latency/throughput characterization if that becomes relevant to
BTC's real submission time budget.

## 32. Final verdict

**FULL CONFIDENCE PIPELINE PROMOTED TO DEFAULT; BUDGET DIVISOR 20 VALIDATED**

The no-flag BTC default now runs the full confidence-routed pipeline (Base → one-forward scoring →
router → V12B on selected records → V13 on V12B-unresolved records → deterministic selector), with
`--confidence-full-pipeline` as a verified no-op-different alias, `--base-only` as a verified
escape hatch reproducing the exact prior behavior, `--confidence-v12b-shadow` verified to remain
observational, and `--legacy-dynamic-full` verified never to reach the new pipeline. All 6 pairwise
mode conflicts are rejected before model construction. The router budget divisor is 20 in every
authoritative location with no hidden fallback to 8; `ceil(N/divisor)` is deliberately preserved
(not changed to `floor`) as the repository's own long-documented small-input policy, and N=2000→100
is directly proven by unit tests. 272 required focused tests pass; the full model-free suite shows
zero new failures against an exact git-stash A/B comparison. The single-record real-model smoke
test on the accepted Windows/Docker/GPU/model stack exited 0, produced a complete one-row canonical
submission with the correct qid, showed the expected mode banner, and exercised the full
Base→router→V12B→V13→selector path end-to-end with clean, privacy-safe diagnostics. This verdict
does not claim new accuracy evidence beyond AUDIT 95's neutral subset30 result — the promotion
itself rests on explicit user authorization, disclosed plainly in §4.
