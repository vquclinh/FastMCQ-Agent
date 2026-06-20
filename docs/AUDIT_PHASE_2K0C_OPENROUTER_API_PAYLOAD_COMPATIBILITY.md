# Audit — Phase 2K.0C: OpenRouter API Payload Compatibility Preflight

**Date:** 2026-06-19
**Branch:** `main` @ `d0f11d8` (+ uncommitted 2K.0B and 2K.0C changes)
**Scope:** Verify the OpenRouter request payload/headers for `qwen/qwen3.5-9b`,
confirm structured JSON output, ensure streaming/reasoning are off by default, and
that the key cannot leak. **No live API call, no inference, no leaderboard, not
committed.**

## 1. Repo / key guard

Branch `main`. Working tree carried the uncommitted Phase 2K.0B changes (the user
had not committed them); this phase stacks on top. `OPENROUTER_API_KEY` reported
**present: False** at guard time (no value printed). No live call made regardless.

## 2. Files inspected

`src/openrouter_client.py`, `src/openrouter_graph_solver.py`,
`src/openrouter_prompts.py`, `src/structured_answer.py`, `src/solver_factory.py`,
`run.py`, `configs/default.yaml`, `requirements-openrouter.txt`, `.gitignore`,
`docs/OPENROUTER_ROUND1_STRATEGY.md`, `docs/ARCHITECTURE.md`, OpenRouter tests.

## 3. Files modified / created

**Modified:**
| Path | Change |
|---|---|
| `src/openrouter_client.py` | Extracted `build_payload()` / `build_headers()` (pure, unit-testable). Payload now sets **`stream: false`** explicitly and still omits `reasoning`. Headers add optional `HTTP-Referer` only when `OPENROUTER_REFERER` is set. Behavior of the real HTTP path is otherwise unchanged. |
| `tests/test_openrouter_client.py` | +8 payload/header compatibility tests (no network). |
| `docs/OPENROUTER_ROUND1_STRATEGY.md` | Added an **API request contract** section (endpoint, headers, body, stream off, reasoning off, 1 call/sample). |

**Created:** `docs/AUDIT_PHASE_2K0C_OPENROUTER_API_PAYLOAD_COMPATIBILITY.md` (this file).

(Also still present from 2K.0B, uncommitted: the speed-hardening edits to
`openrouter_graph_solver.py`, `configs/default.yaml`, the mode-scoping doc edits,
and the 2K.0B audit.)

## 4. Endpoint / header / body compatibility

| Requirement | Result |
|---|---|
| Endpoint `https://openrouter.ai/api/v1/chat/completions` | ✓ (`base_url`) |
| Method `POST` | ✓ (`httpx ... client.post`) |
| `Authorization: Bearer <key>` | ✓ (`build_headers`) |
| `Content-Type: application/json` | ✓ |
| Optional `X-Title` / `HTTP-Referer` | ✓ X-Title always; HTTP-Referer only if `OPENROUTER_REFERER` set |
| Key from env/.env, never hard-coded | ✓ (`resolve_api_key`) |
| Key never logged | ✓ (client logs model/id/usage only) |
| Default model `qwen/qwen3.5-9b` | ✓ |
| Body has `model`, `messages`, `temperature`, `top_p`, `max_tokens` | ✓ |
| `stream` omitted or false | ✓ now **explicit `false`** |
| `reasoning` omitted by default | ✓ (never set) |
| `response_format` when structured output enabled | ✓ (included only then) |
| No `/responses` or `/messages`; no OpenAI/Gemini/Claude direct API | ✓ |

## 5. response_format result

`structured_answer.response_format_schema()` returns a `json_schema` response
format with the 5 fields (`answer`, `confidence`, `evidence`, `reason_type`,
`needs_review`; `answer` required). It is attached to the payload **only** when
`openrouter.structured_output` is true (default true). Verified by test.

## 6. stream / reasoning default decision

- **Streaming OFF** by default — `stream: false` is sent explicitly. Batch CSV
  generation reads the full response; streaming adds no value and complicates
  parsing.
- **Reasoning OFF** by default — the `reasoning` field is never sent. This keeps
  latency low and avoids storing private chain-of-thought; `reasoning_details`
  are never logged.

## 7. Speed / API-call budget confirmation

- Normal valid-JSON path = **exactly 1** client call (test).
- Invalid-JSON / invalid-label repair path = **at most 2** calls, capped by
  `max_api_calls_per_sample_with_repair=2` (tests).
- `verify_node` is deterministic/structural — **not** an LLM call.
- `self_consistency` **off by default**.
- Retries bounded (`max_retries`, transient HTTP only); no graph loops.
- `timeout_sec` configurable (default 60).
- `max_tokens` default 512 — not excessive for a JSON answer.
- JSONL trace includes `elapsed_sec` and `api_calls`.

## 8. Structured-output checks

- Fields: `answer`, `confidence`, `evidence`, `reason_type`, `needs_review`. ✓
- Final answer must be one available label (validated against the sample). ✓
- Parser handles strict JSON / markdown fences / embedded JSON / invalid label /
  malformed response (tests). ✓
- Fallback always returns a valid label (finalize + outer guard). ✓
- `pred.csv` contains only `qid,answer` (`write_predictions`). ✓

## 9. Tests added / updated

+8 in `test_openrouter_client.py`: endpoint is chat/completions (not
responses/messages); payload uses `qwen/qwen3.5-9b`; `stream` false; `reasoning`
omitted; `response_format` present iff structured / absent otherwise; core fields
present; headers carry Authorization + Content-Type + X-Title; HTTP-Referer only
when env set. (Speed/no-key-in-logs tests already added in 2K.0B remain.)

## 10. Validation commands / results

```bash
.venv/bin/python -m compileall -q src tests scripts     # OK
.venv/bin/python -m pytest -q                            # 134 passed
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_phase2k0c_baseline.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_phase2k0c_baseline.csv  # PASS
```

- **compileall:** OK. **pytest:** **134 passed** (126 prior + 8 new payload tests).
- **Baseline:** 463 rows, `always_a`, **validate PASS** (unchanged).

## 11. Confirmations

- **No live OpenRouter call.** **No full inference.** **No leaderboard upload.**
- **API key not logged / not committed.** Key-string scan of `src/`, `docs/`,
  `configs/` found none (only a dummy `sk-or-SECRETVALUE123` lives in a test that
  asserts keys do **not** leak into logs). `.env` git-ignored + untracked.
- Default model unchanged (`qwen/qwen3.5-9b`); LangGraph not installed; graph
  runner unchanged.

## 12. Remaining risks

- **Still not exercised against the live API** — real response shape, JSON
  adherence, latency, and the actual calls/sample distribution are verified only
  with a fake client. The `--limit 3` smoke is the real test.
- Provider model identity (`qwen/qwen3.5-9b` ≤9B Qwen3.5) trusted from OpenRouter.
- `response_format` json_schema support depends on the provider honoring it; the
  parser tolerates non-JSON output regardless.

## 13. Recommended next phase

**Phase 2K.1 — Live OpenRouter smoke.** With the key set in `.env`: run the
`--limit 3` smoke, inspect the JSONL trace (route, `api_calls`≈1, repair_used,
confidence, elapsed), confirm payload behaves, then — on explicit approval — the
full public run → validate → upload `pred.csv`.

## 14. Git status (uncommitted)

```
 M configs/default.yaml
 M docs/ARCHITECTURE.md
 M docs/METHOD.md
 M docs/OPENROUTER_ROUND1_STRATEGY.md
 M docs/RESEARCH_STRATEGY.md
 M src/openrouter_client.py
 M src/openrouter_graph_solver.py
 M tests/test_openrouter_client.py
 M tests/test_openrouter_graph_solver.py
?? docs/AUDIT_PHASE_2K0B_OPENROUTER_ARCHITECTURE_CONSISTENCY_SPEED_HARDENING.md
?? docs/AUDIT_PHASE_2K0C_OPENROUTER_API_PAYLOAD_COMPATIBILITY.md
```

All changes **uncommitted** (Phase 2K.0B + 2K.0C together), left for user review.
`.env`, `.venv/`, `outputs/`, and model dirs remain out of git.
