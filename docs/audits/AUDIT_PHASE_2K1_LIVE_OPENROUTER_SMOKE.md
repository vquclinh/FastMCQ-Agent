# Audit — Phase 2K.1: Live OpenRouter Smoke Test

**Date:** 2026-06-19
**Branch:** `main` @ `200bf0a`
**Result:** Live smoke ran (3 samples, real API). **NOT CLEAN — blocked.** Every
sample returned **empty content** and fell back to `A`; the model
`qwen/qwen3.5-9b` is a **reasoning model** that consumed the entire `max_tokens`
budget on hidden reasoning and emitted no JSON answer. **limit-20 NOT run** (per
the stop rule). No leaderboard upload, no full inference, no commit.

## 1. Repo state

Branch `main`; `200bf0a harden OpenRouter graph speed and API payload` (2K.0B/C
committed); working tree clean (outputs are git-ignored).

## 2. API key / .env

`OPENROUTER_API_KEY` **present: True** (value never printed). `.env` is
git-ignored (`.gitignore:15`) and untracked. No key appeared in any log (grep:
0 hits).

## 3. Dependencies installed

`requirements-openrouter.txt` already satisfied (`httpx`, `python-dotenv`). Nothing
new installed.

## 4. Model used

`qwen/qwen3.5-9b` (OpenRouter reported served revision `qwen/qwen3.5-9b-20260310`).

## 5. Exact commands

```bash
.venv/bin/python -m pip install -r requirements-openrouter.txt
.venv/bin/python run.py --solver openrouter_graph --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 --openrouter-max-tokens 512 \
  --input public-test_1780368312.json \
  --output outputs/pred_phase2k1_openrouter_graph_limit3.csv \
  --limit 3 --save-raw --log-path outputs/run_phase2k1_openrouter_graph_limit3.jsonl
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json \
  --submission outputs/pred_phase2k1_openrouter_graph_limit3.csv
```

## 6. limit-3 result

- Output: `outputs/pred_phase2k1_openrouter_graph_limit3.csv` → `test_0001..0003` all `A`.
- **All three are the safe fallback** (`A`), because the model returned **empty
  `content`**. Per-sample trace: `parsed ok=False`, `source=none`,
  `error=unparseable`, `raw_response=''`, `api_calls=2`, `repair_used=True`,
  `confidence=None`.
- The system behaved **safely** (never crashed; always emitted a valid label),
  but produced **no real answers**.

## 7. limit-20 result

**Not run.** The limit-3 smoke had parser/retry issues (empty content), so per the
stop rule limit-20 was skipped to avoid wasting API calls/cost.

## 8. Validation result

`RESULT: FAIL` — but **only** due to partial coverage: the limit-3 file has 3 of
463 qids, so the validator reports "missing predictions for 460 qids". The labels
present are valid. (Validation is designed for a *full* submission.)

## 9. Parser / repair behavior

Root cause identified from OpenRouter `usage`:

- Every call returned `completion_tokens: 512` (i.e. **hit the max_tokens cap**)
  with `reasoning_tokens` of 397–668. `qwen/qwen3.5-9b` is a **reasoning model**
  that spends the token budget on hidden reasoning; with `max_tokens=512` there
  was **no budget left to emit the JSON answer**, so `content` came back empty.
- Empty content → `parse_structured_answer` returns `unparseable` →
  `verify_node` flags invalid → `repair_node` makes a 2nd call → also empty →
  `finalize_node` falls back to `A`.
- So the **speed/repair machinery worked as designed** (capped at 2 calls,
  deterministic verifier, safe fallback), but the **content was unusable**.

## 10. Route distribution

`long_context`: 2, `calculation`: 1 (of the first 3 samples). Routing worked.

## 11. api_calls distribution

`[2, 2, 2]` — every sample used the repair path (target is ~1). Driven entirely
by the empty-content problem, not by a logic bug.

## 12. Latency observations

`elapsed_sec`: 34.2, 16.9, 17.8 (mean **22.98 s/sample**). This is **very slow**
— two calls per sample, each generating a full 512 reasoning-token budget.
Extrapolated to 463 samples this would be ~2.5–3 hours and ~2× the necessary cost.

## 13. Errors / retries / rate-limit / cost

- No HTTP errors, no rate-limiting, no transport retries — all 7 calls returned
  HTTP 200. The "retries" here are the **graph-level repair**, not network retries.
- Cost (OpenRouter `usage.cost`) for the 7 calls ≈ **$0.0013 total** for 3 samples
  (~$0.00043/sample at 2 calls). Cheap per sample, but doubled by repair and
  inflated by reasoning tokens.

## 14. Confirmations

- **No leaderboard upload.** **No full inference** (only 3 live samples).
- **API key not logged or committed**; `.env` ignored/untracked; no
  `reasoning_details`/private CoT stored (raw_response was empty anyway).
- No source/config files changed this phase; only git-ignored `outputs/*` and this
  audit were produced.

## 15. Blocker + recommended fix (next phase)

**Blocker:** `qwen/qwen3.5-9b` emits reasoning tokens by default and, at
`max_tokens=512`, returns empty answer content. The structured-JSON path needs the
answer to fit within the token budget.

**Recommended next phase — Phase 2K.2 (fix reasoning-model output), do BEFORE any
full run:**
1. **Raise `max_tokens`** well above the reasoning budget (e.g. 1024–2048) so the
   JSON answer is emitted after reasoning — simplest reliable fix; re-smoke limit 3.
2. **And/or control reasoning** via OpenRouter's `reasoning` parameter (e.g.
   `reasoning: {"effort": "low"}` or `{"max_tokens": <small>}`, or
   `{"exclude": true}` to drop reasoning from output) — add as an optional config
   `openrouter.reasoning_effort` / `openrouter.reasoning_max_tokens`, defaulting to
   a fast setting. (Note: OpenRouter also returns reasoning in a separate field;
   our parser only reads `content`, so suppressing or budgeting reasoning is what
   matters.)
3. Re-run the **limit-3 smoke**; require `parsed ok=True`, `api_calls≈1`,
   non-`A`-only answers, lower latency. Only then limit-20, then full.

Do **not** run the full public OpenRouter generation until the limit-3 smoke is
clean (real parsed answers, ~1 call/sample).

## 16. Git status

```
(clean — outputs/* are git-ignored; only this audit is new and untracked)
?? docs/AUDIT_PHASE_2K1_LIVE_OPENROUTER_SMOKE.md
```

All changes **uncommitted**. `.env`, `.venv/`, `outputs/`, model dirs remain out of git.
