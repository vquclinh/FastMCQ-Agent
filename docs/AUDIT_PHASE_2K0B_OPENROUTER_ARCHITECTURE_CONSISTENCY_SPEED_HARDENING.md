# Audit — Phase 2K.0B: OpenRouter Architecture Consistency + Speed Hardening

**Date:** 2026-06-19
**Branch:** `main` @ `d0f11d8`
**Scope:** Consistency, speed, and security review of the Round-1 OpenRouter graph
solver before the first live smoke. **No API call, no inference, no leaderboard,
not committed.** Small, targeted code fixes made (speed policy); no rewrite.

## 1. Repo / key guard

Branch `main`; OpenRouter solver committed (`d0f11d8`); tree clean at start. A
`.env` now exists with an `OPENROUTER_API_KEY` line — **git-ignored and untracked**
(verified). The key value was never printed or logged. (This phase still performs
no live call.)

## 2. Files inspected

`docs/ARCHITECTURE.md`, `docs/OPENROUTER_ROUND1_STRATEGY.md`,
`docs/RESEARCH_STRATEGY.md`, `docs/METHOD.md`, `src/openrouter_graph_solver.py`,
`src/openrouter_client.py`, `src/openrouter_prompts.py`, `src/structured_answer.py`,
`src/solver_factory.py`, `configs/default.yaml`, `requirements-openrouter.txt`,
`.gitignore`, OpenRouter tests.

## 3. Files modified / created

**Modified (no new files this phase):**
| Path | Change |
|---|---|
| `src/openrouter_graph_solver.py` | **Speed fix**: `repair_only_on_invalid` (default true) so a valid answer never triggers a 2nd call from the model's own `needs_review`/`label_fallback`; added `api_calls` counter + budget cap on repair; config fields. |
| `configs/default.yaml` | Added `repair_only_on_invalid`, `max_api_calls_per_sample_default: 1`, `max_api_calls_per_sample_with_repair: 2`; clarified comments. |
| `docs/ARCHITECTURE.md` | Added a **Two operating modes** banner (Mode A = Round-1 OpenRouter; Mode B = offline local); scoped "offline" to Mode B. |
| `docs/METHOD.md` | Added operating-modes note; scoped "no external API" to Mode B. |
| `docs/RESEARCH_STRATEGY.md` | Clarified: external *retrieval* always avoided, but Round-1 OpenRouter API is used (Mode A); offline mode uses no API. |
| `tests/test_openrouter_graph_solver.py` | +7 speed/security tests; made `test_factory_without_key_raises` hermetic vs a real `.env`. |
| `tests/test_openrouter_client.py` | Made `test_missing_key_raises_clearly` hermetic vs a real `.env`. |

## 4. Documentation contradictions found / fixed

The design docs described an **offline / no-external-API** system, which now
contradicts the Round-1 OpenRouter mode. Fixed by introducing an explicit
**two-mode** framing in `ARCHITECTURE.md`, `METHOD.md`, and `RESEARCH_STRATEGY.md`:

- **Mode A — Round 1:** `openrouter_graph`, OpenRouter API, `qwen/qwen3.5-9b`,
  structured JSON, fast graph runner. **Not** offline.
- **Mode B — later Docker/local:** offline `hf_*` / `adaptive_agent`, local
  quantized model, no external API.

The offline architecture was **kept**, not deleted; "offline / no external API"
statements are now explicitly scoped to Mode B. `OPENROUTER_ROUND1_STRATEGY.md`
already documented Mode A correctly.

## 5. Paper → module mapping

The mapping table already exists in `OPENROUTER_ROUND1_STRATEGY.md` and remains
accurate (ReAct→graph; CoT→internal/JSON-only; Self-Consistency→gated/off;
PAL→reserved/sandbox-only; RAG→in-question evidence; Lost-in-the-Middle→evidence
placement; Self-Refine→one repair, no loop; Debate/ToT/GoT→future/capped;
structured output→parser/schema; dynamic labels→2–11 validated). No accuracy
claimed. No changes required beyond the mode framing.

## 6. LangGraph decision

**Kept the built-in deterministic graph runner; LangGraph not installed.**
Rationale recorded: simpler, dependency-light, easier to test under Python 3.14,
faster init, and the graph is acyclic/simple. LangGraph remains an optional future
swap-in if workflows become cyclic/branch-heavy, need persistence/checkpointing,
or add parallel self-consistency/debate nodes. (Documented in the strategy doc and
`requirements-openrouter.txt`.)

## 7. Speed / API-call budget policy (verified + hardened)

| Property | Status |
|---|---|
| Default path = **1 API call/sample** | **Fixed** — valid answer is now always 1 call (was 2 when model set `needs_review`). |
| `verify_node` deterministic (no LLM) | Yes — structural only. |
| Repair conditional | Yes — only when no valid label (default), capped by `max_api_calls_per_sample_with_repair=2`. |
| Repair ≤ 1 per sample | Yes — single `repair_node`, plus a hard `api_calls` budget guard. |
| Self-consistency OFF by default | Yes — gated to low-confidence only when explicitly enabled. |
| No hidden 2nd model call | Confirmed. |
| `max_tokens` not excessive | 512 (reasonable for a JSON answer). |
| Timing/call logging | `elapsed_sec` + new **`api_calls`** in the JSONL trace. |
| Resume support | `--resume` in `run.py`. |
| Bounded retries | client `max_retries` (transient HTTP only); graph has no loops. |

## 8. Implementation-quality checks

- **API key never logged**; client logs model/id/usage only. ✓
- `.env` / `.env.*` git-ignored; `.env` untracked. ✓
- Client reads key from env/.env; missing key → clear error (hermetic test). ✓
- Structured parser handles strict JSON / fences / embedded / invalid label /
  duplicate-choice-by-label. ✓ (existing tests)
- Final-answer guard always returns a valid label. ✓
- No private chain-of-thought in logs — only a concise `raw_response` snippet +
  evidence. ✓
- `save_raw` does not leak the key (new `test_no_api_key_in_logs`). ✓
- Baseline / HF / adaptive solvers unchanged. ✓

## 9. Tests added / updated

+7 in `test_openrouter_graph_solver.py`: normal path = 1 call; `needs_review`
doesn't force repair (default); repair path ≤ 2 calls; repair capped by budget;
thorough mode repairs flagged answers; `api_calls` logged; **no API key in logs**.
Two existing key-absence tests made hermetic (disable `.env` loading) so they pass
whether or not a real `.env` is present.

## 10. Validation commands / results

```bash
.venv/bin/python -m compileall -q src tests scripts     # OK
.venv/bin/python -m pytest -q                            # 126 passed
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_phase2k0b_baseline.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_phase2k0b_baseline.csv  # PASS
```

- **compileall:** OK. **pytest:** **126 passed** (119 prior + 7 new).
- **Baseline:** 463 rows, `always_a`, **validate PASS** (unchanged).
- **No live OpenRouter call** was made.

## 11. Were code changes made?

**Yes — small and targeted:** one genuine speed bug fixed (valid answers could
cost 2 API calls), plus the `api_calls` budget counter/cap, config keys, doc
mode-scoping, and test hardening. No solver rewrite; no LangGraph install.

## 12. Remaining risks

- OpenRouter path still **unexercised end-to-end** (fake client only); real JSON
  adherence, latency, and the actual calls/sample distribution are unverified
  until the live smoke.
- `qwen/qwen3.5-9b` provider identity trusted from OpenRouter.
- Confidence thresholds / self-consistency tuning deferred to evidence.

## 13. Recommended next phase

**Phase 2K.1 — Live OpenRouter smoke.** With `.env` key present: run the
`--limit 3` smoke, inspect the JSONL trace (route, `api_calls`, repair_used,
confidence), confirm ~1 call/sample, then — on explicit approval — the full public
run → validate → upload `pred.csv`.

## 14. Git status (uncommitted)

```
 M configs/default.yaml
 M docs/ARCHITECTURE.md
 M docs/METHOD.md
 M docs/RESEARCH_STRATEGY.md
 M src/openrouter_graph_solver.py
 M tests/test_openrouter_client.py
 M tests/test_openrouter_graph_solver.py
?? docs/AUDIT_PHASE_2K0B_OPENROUTER_ARCHITECTURE_CONSISTENCY_SPEED_HARDENING.md
```

All changes **uncommitted**, left for user review. `.env`, `.venv/`, `outputs/`,
and model dirs remain out of git.
