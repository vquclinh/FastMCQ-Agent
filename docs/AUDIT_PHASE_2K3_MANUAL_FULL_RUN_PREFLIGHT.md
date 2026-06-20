# Audit — Phase 2K.3-Preflight: Manual Full-Run Readiness Check

**Date:** 2026-06-19
**Branch:** `main` @ `ea2b672`
**Result:** Repository is **READY** for the user to run full OpenRouter
generation manually. **No API call, no full inference, no CSV generated, no
leaderboard upload, no commit.**

## 1. Repo / key guard

- Branch `main`; working tree clean.
- Latest commit: `ea2b672 fix OpenRouter reasoning output for Qwen` (Phase 2K.2
  committed by the user).
- `OPENROUTER_API_KEY` **present: True** (value never printed).
- `.env` git-ignored (`.gitignore:15`).

## 2. Local validation results

```bash
.venv/bin/python -m compileall -q src tests scripts   # OK
.venv/bin/python -m pytest -q                          # 141 passed
```

## 3. Config readiness checks (verified with NO network call)

Built the request payload via a mock client (`build_payload`) and read the config:

| Check | Value | OK |
|---|---|---|
| default model (config) | `qwen/qwen3.5-9b` | ✓ |
| default model (client `DEFAULT_MODEL`) | `qwen/qwen3.5-9b` | ✓ |
| endpoint | `https://openrouter.ai/api/v1/chat/completions` | ✓ |
| `reasoning` (default) | `{"enabled": false}` (explicitly disabled) | ✓ |
| `stream` | `false` | ✓ |
| structured output | `response_format` present; `structured_output: true` | ✓ |
| `max_tokens` from CLI | payload shows `1024` when `--openrouter-max-tokens 1024` | ✓ |
| key logging | key never logged (client logs model/id/usage only) | ✓ |
| outputs git-ignored | `outputs/*` ignored (`.gitignore:32`) | ✓ |

`OpenRouterConfig()` defaults: model `qwen/qwen3.5-9b`, `reasoning_enabled=False`,
`structured_output=True`, `max_tokens=512` (the manual command overrides to 1024).

## 4. Exact manual command for the user (full run)

> Run this yourself in the terminal — this agent did **not** execute it.

```bash
.venv/bin/python run.py \
  --solver openrouter_graph \
  --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 \
  --openrouter-max-tokens 1024 \
  --input public-test_1780368312.json \
  --output outputs/pred_phase2k3_openrouter_full.csv \
  --save-raw \
  --log-path outputs/run_phase2k3_openrouter_full.jsonl
```

Optional (safe to resume if interrupted): add
`--resume outputs/pred_phase2k3_openrouter_full.csv` to skip already-predicted qids.

Notes: reasoning is disabled by default (no flag needed); ~1 API call/sample;
expect ~3–4 s/sample (≈25–35 min for 463 samples, network-dependent) and a small
cost. The run never prints the API key.

## 5. Validation command for the user (after the run)

```bash
.venv/bin/python scripts/validate_submission.py \
  --input public-test_1780368312.json \
  --submission outputs/pred_phase2k3_openrouter_full.csv
```

Expect **RESULT: PASS** (463 rows, full coverage, all valid labels). Optionally
review the `partial_answer_key` rate and latency in the JSONL log:

```bash
.venv/bin/python - <<'PY'
import json, collections, statistics
rows=[json.loads(x) for x in open("outputs/run_phase2k3_openrouter_full.jsonl") if x.strip()]
rows=[r for r in rows if not r.get("_summary")]
src=collections.Counter((r.get("parsed_answer") or {}).get("source") for r in rows)
print("n",len(rows),"sources",dict(src),
      "mean_elapsed",round(statistics.mean([r["elapsed_sec"] for r in rows]),2),
      "repairs",sum(1 for r in rows if r.get("repair_used")))
PY
```

## 6. Confirmations

- **No OpenRouter API call** was made in this phase (config verified via a mock
  client + `build_payload`; no network).
- **No full inference run**; **no full `pred.csv` created**
  (`outputs/pred_phase2k3_openrouter_full.csv` does not exist).
- **No leaderboard upload.**
- **API key not logged or committed**; `.env` ignored/untracked.
- `.venv/`, `outputs/`, model dirs, and caches untouched.

## 7. Git status (uncommitted)

```
?? docs/AUDIT_PHASE_2K3_MANUAL_FULL_RUN_PREFLIGHT.md
```

(Working tree was otherwise clean; only this audit is new.) All changes
**uncommitted**, for user review.

## 8. Recommended next step

User runs the §4 command to generate the full CSV, then the §5 validation. If it
PASSes with full coverage and an acceptable `partial_answer_key` rate, upload
`outputs/pred_phase2k3_openrouter_full.csv` to the leaderboard (Round 1). Keep the
local/offline solvers for the later Docker/private rounds.
