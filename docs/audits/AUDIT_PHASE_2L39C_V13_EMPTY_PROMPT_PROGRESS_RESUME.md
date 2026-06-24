# Audit — Phase 2L.39C: Fix V13 Empty-Prompt Crash + Progress Logging + Incremental Resume

**Date:** 2026-06-24  **Branch:** `main`  **Status:** bug fix + hardening (no commit, no API)

## Files inspected

`src/v13_dynamic_layer.py`, `src/v12b_dynamic_layer.py`, `src/selective_api_client.py`,
`src/openrouter_client.py`, `src/fastmcq_system.py`, `src/dynamic_base_predictor.py`,
`scripts/final_infer.py`, `configs/run_profiles.json`, and the failed run dir
`scratch/runs/public_api50_20260624_005107/` (read-only).

## Root cause of the crash

`run_v13_layer` called `client.chat(_prompt(layer, s, route))`, but **`_prompt(...)` returns a
bare string** while `OpenRouterClient.build_payload` sets `"messages": messages` verbatim — the
API requires `messages` to be a **list of message objects**. V12B builds a proper list; V13 did
not. OpenRouter rejected the string-typed `messages` with `HTTP 400 "Input required: specify
'prompt' or 'messages'"`. The retry loop exhausted and raised `RuntimeError`, crashing the run.

**Failed-run evidence (read-only):** exactly **745** `openrouter ok` calls completed (base 445 +
V12B 300 — matching the earlier reconstruction), `work/v12b_dynamic_records.jsonl` was written,
then the crash hit the **first V13 call (#746)** at `v13_dynamic_layer.py:200`. No
`v13_dynamic_records.jsonl`, no `pred.csv`. The framing "empty/invalid prompt" was the symptom;
the true cause was a **string passed where a messages list was required** (and no empty-prompt
guard existed).

### Part A answers
1. Any V13 layer could send a malformed prompt — all three builders return strings, and the
   call site never wrapped them in a messages list. Unknown layer names previously fell through
   to the LTM builder.
2. `_prompt(...)` never returned literally `""`, but it returned a **string** (wrong type for
   `messages`) — and an empty/whitespace builder output would have been sent unchecked.
3. **No** — `SelectiveAPIClient.chat` did not validate the prompt before sending.
4. **No** — `openrouter_client` did not validate messages; it sent `{"messages": <string>}`.
5. Failed run produced **`work/v12b_dynamic_records.jsonl` only**; **no** `v13_dynamic_records.jsonl`,
   **no** `pred.csv`.
6. **745** API calls completed before failure.
7. **No** — `--resume` was accepted but unused (no skip of completed qids).

## Files changed + behavior before/after

- **`src/selective_api_client.py`** — added `_valid_messages(...)` + a guard at the **top of
  `chat()`** (before the retry loop) that raises `ValueError("empty prompt passed to
  SelectiveAPIClient.chat …")` for `None` / empty-or-whitespace string / empty list / list with
  no non-empty content. *Before:* empty/invalid prompt reached the network and 400'd after
  retries. *After:* it fails fast locally, never calling the API.
- **`src/v13_dynamic_layer.py`** — `_prompt` now returns a safe generic prompt for unknown
  layers; new `build_messages(layer, sample, route) -> (messages_list | None, prompt_len)`
  validates non-empty and wraps in a proper messages list. `run_v13_layer` builds + validates
  before any call; an invalid prompt is recorded as `skipped_empty_prompt` and the loop
  continues. *Before:* string passed as messages → crash. *After:* always a valid messages list
  or a clean skip.
- **`src/v12b_dynamic_layer.py`** — incremental JSONL + resume (see below); progress logs.
- **`src/dynamic_base_predictor.py`** — per-sample `[BASE] i/N qid=… source=…` logging.
- **`src/fastmcq_system.py`** — `[FASTMCQ]`/`[SELECTOR]` logs, `progress.json` stage writes,
  `profile` config field, and a best-effort `failed` progress marker on exception.
- **`scripts/final_infer.py`** — passes `profile` into `FastMCQSystemConfig`.

## How incremental JSONL works (Part D)

Each layer opens its JSONL (`<work_dir>/v12b_dynamic_records.jsonl` /
`v13_dynamic_records.jsonl`) and **appends one JSON object per completed unit, flushing after
each write**. So if the process dies mid-layer, the JSONL already holds every finished unit and
remains valid line-delimited JSON (a partial trailing line is tolerated on load). On a clean
(non-resume) run the file is truncated first; the in-memory result list returned to the selector
is unchanged in shape.

## How resume works (Part E)

With `resume=True` and an existing JSONL, the layer loads completed units keyed by
**V12B `(qid, permutation_id)`** / **V13 `(qid, layer)`**, reopens the file in **append** mode,
**skips** already-completed units (reusing their records in the returned results, no duplicate
lines, no new API call), and only runs the missing units. `skipped_empty_prompt`/`skipped_no_api`
records count as completed. Logs: `[V12B] resume loaded=<n> skipped=<n>` /
`[V13] resume loaded=<n> skipped=<n>`. (Verified by tests: 0 new calls + unchanged line count on
the second pass.)

## Progress / status JSON (Part F)

`<work_dir>/progress.json` is updated (best-effort, never required for correctness) at
`base_start`, `base_done`, `v12b_start/done`, `v13_start/done`, `selector_done`,
`output_written`, and `failed` — each with a stage, UTC timestamp, and stage-specific counts.

## Exact monitoring commands for future runs

```bash
RUN_DIR=$(ls -td scratch/runs/public_api50_* | head -1)
tail -f "$RUN_DIR/run.log"                                   # live [BASE]/[V12B]/[V13]/[SELECTOR] lines
cat "$RUN_DIR/work/progress.json"                            # current stage + counts
wc -l "$RUN_DIR/work/"*.jsonl                                # records produced so far (incremental)
grep -c "openrouter ok" "$RUN_DIR/run.log"                   # API calls completed
```

## Tests run and results (Part H)

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_api_progress_resume_2l39c.py`: **9 passed**
- `pytest -q` (full suite): **731 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

Coverage: empty `chat("")`/None/empty-list raise before API (dummy client never called); V13
empty prompt skipped (0 API calls); V13 + V12B incremental JSONL; V13 resume skips `(qid,layer)`;
V12B resume skips `(qid,permutation)`; no duplicate records after resume; progress logs contain
`qid`/`layer`/index; no qid/answer hardcoding. No real API in any test (fake client injected).

## Confirmations

- **No API calls** — all work used injected fakes / offline paths; the guard is verified to
  fail before any network call.
- **No qid/answer hardcoding** — changed modules regex-clean (tested).
- **Official V13 79.7 artifact unchanged** — `outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv`
  md5 still `cb02fef569b31e7fb544abab46c0e282`.
- **Failed run directory not modified/deleted** — `scratch/runs/public_api50_20260624_005107/`
  still has only `run.log` + `work/v12b_dynamic_records.jsonl` (no new files written by me).
- **No model-policy rules changed.**
- **Not committed.**

## Git status

```
 M src/selective_api_client.py  src/v12b_dynamic_layer.py  src/v13_dynamic_layer.py
 M src/dynamic_base_predictor.py  src/fastmcq_system.py  scripts/final_infer.py
?? tests/test_api_progress_resume_2l39c.py
?? docs/audits/AUDIT_PHASE_2L39C_V13_EMPTY_PROMPT_PROGRESS_RESUME.md
```
(`scratch/` and `outputs/pred.csv` remain gitignored.) Nothing committed.

## Recommended rerun command after patch

```bash
# resumes from the partial run's JSONL if you point --work-dir at an existing run dir;
# otherwise starts a fresh timestamped run. Requires OPENROUTER_API_KEY.
bash scripts/run_public_api50.sh public-test_1780368312.json
# or to resume the crashed run's V12B records and only do the remaining V13 work, run directly:
.venv/bin/python scripts/final_infer.py --profile public_api50 \
  --input public-test_1780368312.json \
  --output scratch/runs/public_api50_resume/pred.csv \
  --work-dir scratch/runs/public_api50_20260624_005107/work --resume
```
(The second form reuses the existing `v12b_dynamic_records.jsonl` so V12B is skipped and only
V13 + selector run.)
