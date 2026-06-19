# Audit — Phase 2H.0: Local Model Discovery + Real-Run Preflight

**Date:** 2026-06-19
**Branch:** `main` @ `bb734bc`
**Scope:** Discover whether a compliant local model exists, validate it safely,
and prepare for Phase 2H. **No downloads, no remote APIs, no full inference.**
**Outcome:** No compliant local generation model found → **Phase 2H remains
blocked**. No model was loaded; `MODEL_PATH` stays empty.

## 1. Repo status and latest commits

```
$ git status --short      # (clean)
$ git log --oneline -5
bb734bc implement adaptive multi-agent MCQA solver
9b371dc add model compliance and LLM environment setup
f1181ea Merge pull request #1 from vquclinh/deployment
137269d add competitive local LLM solver framework
ad1f477 add dataset profiling and experiment tracking
```

**Follow-up commit after `4c2ac00`?** No. The two Claude-authored commits
(`4c2ac00` + `2dff905`) were removed in the previous task and the user
re-committed the work as a single commit **`bb734bc` "implement adaptive
multi-agent MCQA solver"** (lowercase, user-authored). There is no follow-up
commit after it; the working tree is clean.

## 2. Environment status

```
torch         : 2.12.1+cu130
CUDA available: True
  GPU[0]     : NVIDIA GeForce RTX 4060 Laptop GPU (7.6 GB VRAM)
transformers  : 5.12.1
LLM-ready     : YES
```

Installed LLM packages: `torch 2.12.1`, `transformers 5.12.1`, `accelerate 1.14.0`,
`sentencepiece 0.2.1`, `safetensors 0.8.0`. **`bitsandbytes` is NOT installed**
(needed for 4-bit quantization to fit a 7B model in 7.6 GB).

## 3. MODEL_PATH status

- **Before:** empty.
- **After:** empty (unchanged). No compliant candidate was found, so `MODEL_PATH`
  was deliberately **not** set — not fabricated.

## 4. Local model candidates found

Searched `/mnt`, `/home`, the repo, the HuggingFace cache, and common locations
(`~/models`, `/models`, `/opt/models`, `~/.ollama`, `~/.cache/modelscope`).
No loose model directories were found anywhere outside the HF cache.

The HF cache (`~/.cache/huggingface/hub`) contains exactly two models, **neither a
generation LLM**:

| Cached model | Type | Architecture | Usable as causal LM? | Compliant? |
|---|---|---|---|---|
| `ProsusAI/finbert` | sentiment classifier | BERT (`model_type: bert`, 12 layers, vocab 30522) | **No** (encoder, not `AutoModelForCausalLM`) | **No** |
| `sentence-transformers/all-MiniLM-L6-v2` | embedding model | MiniLM (sentence-transformer) | **No** | **No** (and would only ever be an embedding helper) |

Neither belongs to an allowed generation family (Qwen3.5 ≤ 9B / Gemma-4), and
neither is a decoder LM the solvers can use.

## 5. Compliance check results (`--strict`)

```
ProsusAI/finbert                         -> FAIL (no allowed-family match)
sentence-transformers/all-MiniLM-L6-v2   -> FAIL (no allowed-family match)
Qwen3.5-7B-Instruct (hypothetical name)  -> PASS   (contrast / sanity check)
```

The checker behaves correctly: it rejects the present non-compliant models and
would pass a compliant Qwen3.5 name.

## 6. Tokenizer load results

**Not attempted.** Task 6 runs the tokenizer preflight only "for the best
compliant candidate"; there is **no** compliant candidate, so no tokenizer/model
load was performed. (Loading finbert/MiniLM would be pointless — they cannot drive
the MCQA solvers.)

## 7. Was model load / inference attempted?

**No.** None of the Phase-2H preconditions were met:

- ❌ a compliant candidate exists — **none found**,
- (therefore) tokenizer-load preflight skipped,
- (therefore) model-load fit check skipped,
- (therefore) the `--limit 1` smoke test was **not** run.

No `outputs/pred_phase2h0_*` files were created. No real inference occurred.

**Exact reason Phase 2H is blocked:** there is no compliant local generation
model (Qwen3.5 ≤ 9B or Gemma-4) on this machine, and downloading one is not
permitted in this phase.

## 8. VRAM risks (for when a model is provided)

- **7.6 GB VRAM** cannot hold a 7B model in fp16 (~14 GB). Options:
  1. a **4-bit quantized** Qwen3.5-7B (install `bitsandbytes`, add to
     `requirements-llm.txt`), or
  2. a **smaller** compliant checkpoint (e.g. a ~1.5–3B Qwen3.5), or
  3. CPU offload / CPU-only (much slower; risky for any time budget).
- `bitsandbytes` is not yet installed, so option (1) needs a dependency add first.
- The option-scoring path runs ~1 forward pass per choice (≈10 for 10-choice
  items) plus fallbacks — keep `max_input_tokens` and `max_fallbacks_per_sample`
  modest on first runs to avoid OOM and long latency.

## 9. Recommended next phase

**Still Phase 2H, but blocked on a model.** To unblock:
1. Place a compliant local model on disk (Qwen3.5 ≤ 9B; prefer a 4-bit or smaller
   variant for 7.6 GB) — provided by the user, not downloaded by the agent.
2. `export MODEL_PATH=<dir>` and run
   `scripts/check_llm_env.py --model-path "$MODEL_PATH" --load-tokenizer` and
   `scripts/check_model_compliance.py --model-path "$MODEL_PATH" --strict`.
3. If both pass and the model fits, run the `--limit 1` smoke (hf_option_score),
   then the staged ablation in Phase 2H.

If a 7B is the only option, first add `bitsandbytes` to `requirements-llm.txt` and
load in 4-bit (a small, isolated change — flagged for a separate review).

## 10. Git status

Working tree was clean before this phase. The only change is this audit file
(`docs/AUDIT_PHASE_2H0_MODEL_DISCOVERY_PREFLIGHT.md`). **No code or config
changed.** `.venv/`, `outputs/`, model directories, and the HF cache remain
outside git (the HF cache lives in `~/.cache`, not the repo).
