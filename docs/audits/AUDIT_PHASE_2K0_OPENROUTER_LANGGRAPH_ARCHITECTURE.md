# Audit — Phase 2K.0: OpenRouter Research-Grounded Graph Architecture

**Date:** 2026-06-19
**Branch:** `main` @ `1fd1d97`
**Scope:** Build a paper-grounded, modular OpenRouter graph solver for Round 1
(CSV-upload only). Code/tests/docs implemented; **no live API call** (key
missing); no full inference; no leaderboard upload; **not committed**.

## 1. Repo guard result

Branch `main`; working tree clean; adaptive + quantization committed
(`1fd1d97`, `487db5d`). `OPENROUTER_API_KEY` **absent** → implemented everything
but skipped the live smoke. No `.env` present; `.env` rule added to `.gitignore`.

## 2. Files inspected

`run.py`, `configs/default.yaml`, `src/solver_base.py`, `src/solver_factory.py`,
`src/adaptive_agent_solver.py`, `src/question_profiler.py`,
`src/question_router.py`, `src/passage_compressor.py`, `src/confidence.py`,
`src/output_parser.py`, `src/prompting.py`, `src/run_logger.py`,
`scripts/validate_submission.py`, tests, and architecture/research docs.

## 3. Dependencies added

`requirements-openrouter.txt` (new): `httpx>=0.27`, `python-dotenv>=1.0` (active);
`langgraph` listed **commented/optional**. Installed `python-dotenv` (httpx
already present). **LangGraph NOT installed** — see §6.

## 4. Files created / modified

### Created
| Path | Purpose |
|---|---|
| `src/openrouter_client.py` | `OpenRouterClient` (default `qwen/qwen3.5-9b`): key from env/.env (never logged), retries+backoff, timeout, mock/responder mode, `ChatProvider` abstraction. |
| `src/structured_answer.py` | `StructuredAnswer` + robust parser (strict JSON / ```fences``` / embedded object / label fallback), label validation, `response_format_schema()`. |
| `src/openrouter_prompts.py` | Vietnamese prompt families per route; JSON-only contract; preserves choices; answer ∈ labels; `build_messages` / `repair_messages`. |
| `src/openrouter_graph_solver.py` | `OpenRouterGraphSolver(BaseSolver)` + `OpenRouterConfig`; node graph profile→evidence→route→answer→verify→[repair]→[self_consistency]→finalize; concise trace logging. |
| `requirements-openrouter.txt` | Optional Round-1 deps. |
| `docs/OPENROUTER_ROUND1_STRATEGY.md` | Strategy, architecture, paper→module map, key setup, run commands. |
| `tests/test_openrouter_client.py` (5), `tests/test_structured_answer.py` (10), `tests/test_openrouter_graph_solver.py` (9) | 24 new tests, no live API. |
| `docs/AUDIT_PHASE_2K0_OPENROUTER_LANGGRAPH_ARCHITECTURE.md` | This audit. |

### Modified
| Path | Change |
|---|---|
| `src/solver_factory.py` | Added `openrouter_graph` (clear error if no key; builds `OpenRouterConfig` from known keys); existing solvers unchanged. |
| `run.py` | Added `--openrouter-*` CLI flags + config resolution → `openrouter_config`; existing CLI preserved. |
| `configs/default.yaml` | Added `openrouter:` block (default model `qwen/qwen3.5-9b`, self-consistency off). |
| `.gitignore` | Ignore `.env` / `.env.*`, `models/`, `.hf-cache/`, `.tmp/`. |

## 5. Architecture implemented

ReAct-style node graph over OpenRouter with a **built-in deterministic graph
runner** (no LangGraph dependency). Reuses the existing deterministic profiler,
router, and `passage_compressor`. Structured JSON output with a defensive parser;
verifier + one repair attempt; gated self-consistency (off by default). Every
final output is a valid dynamic label (2–11 choices). No private chain-of-thought
is logged — only concise evidence + structural trace.

## 6. Paper → module mapping

ReAct→graph; CoT→internal-reasoning/JSON-only; RAG→`evidence_node`
(`passage_compressor`, no web); Lost-in-the-Middle→evidence placed by question +
choices preserved; Verify/Refine→`verify_node`+`repair_node`; Self-consistency→
gated `self_consistency_node` (off); PAL-lite→interface reserved, not enabled;
Structured output→`structured_answer`; Confidence→model `confidence` + verifier;
Dynamic labels→`labels_for` validated against choices.

**LangGraph decision:** not used. It pulls a heavy dependency tree (langchain-core
etc.) with uncertain Python 3.14 wheels, adds no value without a live API this
phase, and would burden the test suite. The built-in runner implements the same
node graph and LangGraph can be added later (commented in requirements).

## 7. Model selected

Default `qwen/qwen3.5-9b` (safest explicit match to "Qwen3.5 ≤ 9B"). Overridable
via `--openrouter-model` / config, but no other model is used by default.

## 8. API key present? / live smoke

`OPENROUTER_API_KEY` **absent** → **live smoke skipped**. The solver factory
raises a clear error for `openrouter_graph` without a key (verified; exit 2, no
output file). Command to run later (when the key is set):

```bash
python run.py --solver openrouter_graph --input public-test_1780368312.json \
  --output outputs/pred_phase2k0_openrouter_graph_limit3.csv \
  --limit 3 --save-raw --log-path outputs/run_phase2k0_openrouter_graph_limit3.jsonl
python scripts/validate_submission.py \
  --input public-test_1780368312.json \
  --submission outputs/pred_phase2k0_openrouter_graph_limit3.csv
```

## 9. Validation commands / results

```bash
.venv/bin/python -m compileall -q src tests scripts     # OK
.venv/bin/python -m pytest -q                            # 119 passed
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_phase2k0_baseline.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_phase2k0_baseline.csv  # PASS
```

- **compileall:** OK. **pytest:** **119 passed** (95 prior + 24 new).
- **Baseline:** 463 rows, `always_a`, **validate PASS** (unchanged).
- Mock-client tests cover: valid answer accepted; invalid→repair; final always
  valid; self-consistency off by default; gated SC majority vote; 10-choice
  dynamic label; logging excludes raw sample; factory registers `openrouter_graph`
  and errors without a key.

## 10. Output / log paths

Baseline check: `outputs/pred_phase2k0_baseline.csv` (git-ignored). No OpenRouter
prediction/log files created (no key). Smoke would write
`outputs/pred_phase2k0_openrouter_graph_limit3.csv` + `.jsonl`.

## 11. Security notes

- **API key never logged** (client logs model/id/usage only) and **never
  committed**. `.env` and `.env.*` are git-ignored; no `.env` exists yet.
- Grep confirmed **no `sk-or-…` strings** in `src/`, `docs/`, `tests/`, `configs/`.
- Only OpenRouter is contacted; no OpenAI/Gemini/Claude direct APIs.

## 12. Confirmations

- **No leaderboard upload.** **No full public inference.** **No live API call**
  (key absent). Existing baseline/HF/`adaptive_agent`/Docker untouched and passing.
- `.venv/`, `outputs/`, `.env`, model dirs, and HF cache remain out of git.

## 13. Risks / caveats

- The OpenRouter path is **wired and unit-tested with a fake client only** —
  end-to-end behavior (real JSON adherence, latency, cost) is unverified until a
  key is provided and the `--limit 3` smoke runs.
- transformers 5.x / Python 3.14 unaffected here (OpenRouter path needs neither).
- LangGraph intentionally absent (documented); built-in runner is the execution
  engine.

## 14. Recommended next phase

**Phase 2K.1 — Live OpenRouter smoke + Round-1 generation.** Set
`OPENROUTER_API_KEY`, run the `--limit 3` smoke, inspect the JSONL trace
(routes/repair/confidence), then (on explicit approval) the full public run,
validate, and upload `pred.csv` to the leaderboard. Keep the local/offline
solvers for the later Docker/private rounds.

## 15. Git status (uncommitted)

```
 M .gitignore
 M configs/default.yaml
 M run.py
 M src/solver_factory.py
?? docs/OPENROUTER_ROUND1_STRATEGY.md
?? docs/AUDIT_PHASE_2K0_OPENROUTER_LANGGRAPH_ARCHITECTURE.md
?? requirements-openrouter.txt
?? src/openrouter_client.py
?? src/openrouter_graph_solver.py
?? src/openrouter_prompts.py
?? src/structured_answer.py
?? tests/test_openrouter_client.py
?? tests/test_openrouter_graph_solver.py
?? tests/test_structured_answer.py
```

All changes **uncommitted**, left for the user to review and commit manually.
Model files remain outside the repo (`/mnt/vquclinh/models`, git-ignored).
