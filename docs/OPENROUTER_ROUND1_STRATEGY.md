# OpenRouter Round-1 Strategy

## Why OpenRouter for Round 1

Round 1 only requires **uploading a generated `pred.csv`** to the leaderboard —
there is no offline/Docker packaging requirement yet. So Round 1 uses the
**OpenRouter API** to generate predictions quickly, while the local/offline HF
and `adaptive_agent` paths (already implemented) are kept intact for the later
Docker/private rounds.

- **Only OpenRouter** is used — no OpenAI/Gemini/Claude direct APIs.
- The dataset is multiple-choice text already in the public file; only the
  question + choices are sent to the model.

## Why `qwen/qwen3.5-9b`

It is the **safest explicit match** to the organizer rule ("Qwen3.5 Series,
models ≤ 9B"). It is the default and only model used unless explicitly overridden.

## Architecture (ReAct-style node graph)

```
Input sample
  → profile_node      (deterministic features; no LLM)
  → evidence_node     (RAG-in-question: compress long context, keep choices)
  → route_node        (deterministic route: short/long/calc/law/safety/ambiguous)
  → answer_node       (LLM → strict JSON: answer/confidence/evidence/...)
  → verify_node       (valid label? supported? flagged?)
  → repair_node       (one stricter retry if invalid — optional)
  → self_consistency  (gated: only low-confidence; majority vote — OFF by default)
  → finalize_node     (guarantee a valid label)
  → pred.csv (qid,answer)
```

A small **built-in deterministic graph runner** executes these nodes. **LangGraph
is optional** (listed commented in `requirements-openrouter.txt`) and not
required — chosen to avoid a heavy dependency tree with uncertain Python 3.14
wheels and to keep tests dependency-free. It can be swapped in later.

## Paper → module mapping

| Research idea | Module / node |
|---|---|
| ReAct (observe → act → verify) | the node graph itself |
| Chain-of-Thought / scratchpad | internal reasoning allowed in prompt; **JSON-only** output |
| Self-consistency | `self_consistency_node` — gated, low-confidence only, OFF by default |
| PAL-lite | interface reserved (calculation route); **not enabled** this phase |
| RAG (in-question) | `evidence_node` via `passage_compressor` (no web retrieval) |
| Lost-in-the-Middle | compressed evidence placed next to question + choices preserved |
| Verification / Self-Refine | `verify_node` + one `repair_node` attempt |
| Confidence/margin | model-reported `confidence` + structural verifier signals |
| Structured output | `structured_answer` JSON schema + robust parser (fences/embedded/fallback) |
| Dynamic labels | labels sized to each sample (2–11), validated against choices |

No private chain-of-thought is logged — only concise evidence and the structural
trace.

## Setting `OPENROUTER_API_KEY`

```bash
export OPENROUTER_API_KEY="sk-or-..."        # environment, OR
printf 'OPENROUTER_API_KEY=sk-or-...\n' > .env   # git-ignored .env (do NOT commit)
```
The key is **never logged or committed**. `.env` is in `.gitignore`.

## Install + run

```bash
pip install -r requirements-openrouter.txt    # httpx + python-dotenv (langgraph optional)

# Smoke (first 3 samples) — once the key is set:
python run.py --solver openrouter_graph \
  --input public-test_1780368312.json \
  --output outputs/pred_phase2k0_openrouter_graph_limit3.csv \
  --limit 3 --save-raw --log-path outputs/run_phase2k0_openrouter_graph_limit3.jsonl
python scripts/validate_submission.py \
  --input public-test_1780368312.json \
  --submission outputs/pred_phase2k0_openrouter_graph_limit3.csv

# Full public run (later, when explicitly approved):
python run.py --solver openrouter_graph \
  --input public-test_1780368312.json \
  --output outputs/pred_openrouter_full.csv \
  --save-raw --log-path outputs/run_openrouter_full.jsonl
python scripts/validate_submission.py \
  --input public-test_1780368312.json --submission outputs/pred_openrouter_full.csv
```

Useful flags: `--openrouter-model`, `--openrouter-temperature`,
`--openrouter-max-tokens`, `--openrouter-timeout-sec`,
`--openrouter-self-consistency`, `--limit N`, `--resume FILE`.

## Limitations / risks for later stages

- **Round-1 only.** OpenRouter is an external API; the later Docker/private rounds
  likely require **offline/local** inference — use the existing `adaptive_agent` /
  `hf_option_score` local solvers (and the already-downloaded Qwen3.5-9B + 4-bit
  quantization) for those.
- **Network/cost/rate limits** apply; retries + timeout are built in.
- **Provider model identity** (`qwen/qwen3.5-9b`) is trusted from OpenRouter;
  confirm it remains the approved ≤9B Qwen3.5 variant.
- Do **not** commit `.env` or the key.
