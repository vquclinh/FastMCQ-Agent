# AUDIT 64 — Forensic Reconstruction: Historical OpenRouter 79.7 Pipeline vs Current Local `--legacy-dynamic-full`

Audit number 64 (no prior `64-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD, working-tree state

- Date: 2026-07-10
- Branch: `selective-migration` (required branch; confirmed)
- HEAD: `1d791e303a061598f1d52ec6c284d780d94b3ac9` ("fix Docker shell script line endings")
- Working tree: **clean** (`git status --short` empty at start).
- Mode: read-only forensic investigation. Only this audit file was created. All history was read
  via `git show <commit>:<path>` / `git log`; no checkout, no restore, no ref change.

## 2. Executive summary

The reported **79.7 is a public-test leaderboard score** (463-qid public set), achieved on
2026-06-24 by an **OpenRouter `qwen/qwen3.5-9b-20260310`** pipeline that was **not** an end-to-end
run from raw input. It was the last link of an **incremental, frozen-artifact chain**:
v10 (77.75) → v11 independent (78.40) → V12B permutation "api30" (78.83) → **V13 multilayer "api30
from v12b" (79.7)**. V13 changed only **9 of 463 answers** versus V12B, using a **≤30-qid API
budget** on risk-ranked qids, with API-level **structured JSON output** (`response_format=
{"type":"json_object"}`), greedy decoding (temp 0), and a conservative selector.

The current `--legacy-dynamic-full` pipeline is a **structural imitation with preserved reasoning
prompts but a different backend and a different execution contract**: it runs local
**Qwen3-4B-Instruct** over arbitrary input from scratch (no frozen base, no leaderboard iteration,
no 30-qid hand-planned budget, no API structured-output guarantee). The V13 reasoning modules'
*logic and prompts are byte-identical* to the 79.7 era (only import paths changed); the Base prompt
and V12B system prompt are preserved. What changed is the **model** (9B→4B), the **structured-output
guarantee** (JSON-mode → best-effort text parse), the **Base source** (frozen CSV chain → local
formula-bank+model), the **budget/routing** (hand-built ≤30-qid plan → automatic `ceil(N/8)`), and
the **starting point** (V12B frozen predictions → local single-pass Base). It can execute every
named stage yet produce output equal to the local single-pass default because Base ≈ single-pass
(plus formula bank) and the conservative selector rarely accepts a local override.

Two concrete defects were found in current code (not to be fixed here): a **free-text label parser**
that returns the first `A–K` letter anywhere in the text (`"The answer is clearly option B."` → `A`;
`"Grace Hopper"` → `A`/`G`), and **selector thresholds calibrated for the stronger 9B JSON backend**.

## 3. Evidence-quality scale

- **Confirmed** — proven by a committed file/field or reproduced command output.
- **Strongly supported** — multiple independent committed sources agree; no contradiction.
- **Plausible** — consistent with code/artifacts but not directly proven.
- **Unverified** — no evidence either way.
- **Contradicted** — evidence conflicts.

## 4. Provenance of the 79.7 score

| Claim | Evidence path | Commit | Exact excerpt/field | Confidence |
|---|---|---|---|---|
| 79.7 is a **public leaderboard** score | `docs/audits/AUDIT_PHASE_2L38A_PROMOTE_V13_7970_OFFICIAL_DYNAMIC_SYSTEM.md` | 0a7b9d6 | "improved the **public leaderboard** to **79.7**, beating V12B 78.83 by +0.87 (9 qids changed)" | Strongly supported |
| 79.7 = public score of the V13 CSV | `experiments/best_candidate_manifest.json` | 0a7b9d6 | `current_best.public_score: 79.7`, `file: …pred_v13_multilayer_candidate_api30_from_v12b.csv` | Confirmed (as recorded) |
| Score is public-test, NOT private/BTC | `configs/production/default.json` (current) | 1d791e3 | "reproduce this 79.7 CSV ONLY when the input qid set matches the public test; they are NOT the private/BTC path" | Confirmed |
| Artifact md5 | 2L38A audit + config | 0a7b9d6 | `cb02fef569b31e7fb544abab46c0e282  …_api30_from_v12b.csv (NEW best)`; rows 463 | Confirmed |
| It is **historical**, not claimed for local | `docs/audits/AUDIT_60…md`, `configs/production/default.json` | 87d5d71/1d791e3 | "not claimed for the migrated local implementation until separately reproduced" | Confirmed |
| Score NOT in the experiment tracker CSV | `experiments/leaderboard_log.csv` @0a7b9d6 | 0a7b9d6 | only 3 baseline rows (phase1/hf_generate/hf_option_score); no v10–v13 | Confirmed |

Note: no raw leaderboard submission receipt/screenshot exists in the repo; the "public leaderboard"
nature rests on the team's own committed audit/manifest wording, which is internally consistent →
**Strongly supported**, not independently Confirmed against an external leaderboard.

## 5. Score → artifact → commit → model chain

```
qwen/qwen3.5-9b-20260310 (OpenRouter, JSON-mode, temp 0)
  → scripts/build_v13_multilayer_plan.py  (offline: risk-rank ≤30 qids over the V12B frozen CSV)
  → scripts/run_v13_multilayer_verifier.py --execute --max-qids 30 --budget-usd 0.50
        --current <V12B csv> --plan <plan csv>            (calls API per assigned layer per qid)
  → scripts/build_v13_multilayer_candidate.py             (applies accepted overrides onto V12B)
  → outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv  md5 cb02fef…  (463 rows, 9 changed)
  → public leaderboard 79.7
  → promoted at commit 0a7b9d6 (2026-06-24) as "official dynamic production system"
```

The 9 changed qids are enumerated identically in the manifest and `configs/production/default.json`:
`test_0034 A→B, test_0082 B→D, test_0103 E→A, test_0123 B→F, test_0155 F→A, test_0251 I→H,
test_0269 A→I, test_0388 A→C, test_0420 B→A`.

## 6. Deleted audit/file recovery log

All recovered **read-only** via `git show <commit>:<path>`; none restored to the working tree.

- Reachable-committed evidence (recovered and used): `experiments/best_candidate_manifest.json`,
  `configs/production_v13_multilayer_7970.json`, `configs/production_v12b_permutation_7883.json`,
  `scripts/run_v13_multilayer_verifier.py`, `scripts/build_v13_multilayer_plan.py`,
  `scripts/build_v13_multilayer_candidate.py`, `src/selective_api_client.py`,
  `src/openrouter_client.py`, `src/model_policy.py`,
  `docs/audits/AUDIT_PHASE_2L38A_PROMOTE_V13_7970_OFFICIAL_DYNAMIC_SYSTEM.md`,
  `experiments/leaderboard_log.csv` (baseline-only) — all at/near commit `0a7b9d6`.
- Deleted-file census: `git log --all --diff-filter=D` shows the OpenRouter migration (`d0d8c28`)
  and the earlier legacy retirement (`6fa2168`, `25e25ee`) deleted the `src/api/*` clients,
  `scripts/legacy/*` selective/build/plan/verifier runners, and `experiments/*` metadata.
  **109** deleted `docs/audits/AUDIT_PHASE_*` files are recoverable from history.
- Reflog-only / unreachable / dangling: not needed — all evidence was reachable from committed
  history; `git fsck` was not run (no ref modification desired).
- Current untracked local files: none relevant (working tree clean; only this audit added).

## 7. Historical command and run profile

Reconstructed from `run_v13_multilayer_verifier.py` (0a7b9d6):

```
python scripts/run_v13_multilayer_verifier.py \
    --input <public_test.json> \
    --current outputs/pred_v12b_permutation_candidate_api30.csv \  # V12B frozen base (78.83)
    --plan <v13_multilayer_plan.csv> \                             # ≤30 risk-ranked qids + layers
    --model qwen/qwen3.5-9b-20260310 \
    --max-qids 30 --budget-usd 0.50 --execute
# then: python scripts/build_v13_multilayer_candidate.py  (apply accepted overrides onto V12B CSV)
```

Run profile facts (Confirmed from source): **starting Base = V12B frozen CSV** (not raw inference);
**budget ≤30 qids**; **plan is a fixed CSV** of qids+`target_layers` built offline from v11/v12b
decision metadata (`build_v13_multilayer_plan.py`); output is the V12B CSV with ≤9 accepted changes.
This pipeline **depends on frozen artifacts not present in a clean run** (the V12B/v11 CSVs and
decision JSONLs) and on **public-leaderboard-informed iteration** (each version's public score was
measured before building the next).

## 8. Exact historical OpenRouter model configuration

From `configs/production_v13_multilayer_7970.json`, `run_v13_multilayer_verifier.py`,
`src/selective_api_client.py`, `src/openrouter_client.py`, `src/model_policy.py` (all @0a7b9d6):

| Parameter | Value | Source |
|---|---|---|
| Model ID | **`qwen/qwen3.5-9b-20260310`** (config `model`); client `DEFAULT_MODEL="qwen/qwen3.5-9b"` | config + runner `--model` default |
| Same model for Base/V12B/V13 | Yes — all selective runners default to the same id; allowlist permits only Qwen3.5 ≤9B | model_policy |
| Fallback model | None (a disallowed model cannot even construct the client) | `assert_allowed_llm_model` |
| Temperature | 0.0 (greedy) | `OpenRouterClient`/`SelectiveAPIClient` |
| top_p | 1.0 | `OpenRouterClient` |
| Seed | none (no seed field) | `OpenRouterClient` |
| Max tokens | 512 client default; **768** for selective calls | `SelectiveAPIClient(max_tokens=768)` |
| Timeout | 60 s | `OpenRouterClient(timeout_sec=60.0)` |
| Retries | client 3 + selective 2 (exp. backoff); retry on 408/409/429/5xx | both clients |
| Concurrency | serial (one qid/layer at a time) | runner loop |
| Response format | **`{"type":"json_object"}` (structured JSON enforced)** | `SelectiveAPIClient.chat` |
| Reasoning mode | OFF by default (`reasoning_enabled=False`, `reasoning_exclude=True`) | `OpenRouterClient` |
| Provider routing | none beyond OpenRouter defaults | `OpenRouterClient` |
| System/user prompt | per-layer builders (`build_content_first_prompt`, `build_ltm_constraint_prompt`, `build_programmatic_prompt`) | reasoning modules |
| Repair call | not in the V13 runner (a separate `openrouter_graph_solver` had a JSON-repair retry; not the 79.7 path) | runner + graph solver |
| Verifier call | V13 layers ARE the verifier (per-layer structured proposal) | runner |
| API call count | ≤ (#planned qids × #assigned layers), ≤ ~30×3; `model_calls_made` logged | runner summary |

Secrets: `OPENROUTER_API_KEY` resolved from env/`.env`, "never logged"; **no key value was read or
printed in this review**.

## 9. Historical call graph (79.7)

```
public_test.json
  + v11/v12b decision metadata (frozen)         [OFFLINE plan]
  → build_v13_multilayer_plan.py  → plan.csv (≤30 qids, each with target_layers ∈
        {programmatic_solver, content_first, least_to_most})
V12B frozen CSV (78.83)  = "current"            [FROZEN BASE, not recomputed]
  → run_v13_multilayer_verifier.py --execute:
      for qid in plan[:30]:
        for layer in target_layers:
          prompt = build_<layer>_prompt(sample, route)
          content,usage = SelectiveAPIClient(qwen3.5-9b).chat(messages, response_format=json_object)
          parsed = parse_json(content)                     # strict JSON object
          (label,text,conf,valid,reason,evidence) = _interpret(layer, sample, parsed)
          record candidate
  → build_v13_multilayer_candidate.py:
      unified conservative selector over {programmatic, content_first, least_to_most} vs current
      → apply ≤9 accepted overrides onto the V12B CSV
  → pred_v13_multilayer_candidate_api30_from_v12b.csv (79.7)
```

Per stage: **Base** = frozen V12B CSV (read, not inferred). **Routing** = offline risk plan.
**V12B** already baked into "current". **V13** = ≤30 qids × assigned layers, one API call each,
structured JSON, conf/evidence/valid fields parsed. **Selector** = conservative merge, ≤9 changes.
**Output** = 463 rows (exactly the public qids).

## 10. Historical Base reconstruction

The 79.7 Base was **the frozen V12B CSV** (itself v11→V12B). In `dynamic_full` at that era,
`src/dynamic_base_predictor.py` (per the 2L38A audit line "one valid label per qid; deterministic +
optional API") produced a label per qid with **deterministic solvers first, API only under
`--execute-api`**. But the actual 79.7 artifact did **not** recompute Base — it started from the
frozen V12B predictions. Precedence when Base did run: formula/deterministic → (optional API) →
conservative fallback. (Confirmed: manifest `generated_by … from V12B base`; audit "one valid label
per qid".)

## 11. Historical V12B reconstruction

From the manifest and `production_v12b_permutation_7883.json`: V12B ("v12b_option_permutation_
debiaser", 78.83) was itself an **"api30"** candidate built **over v11** — a ≤30-qid,
option-permutation debiasing pass via OpenRouter qwen3.5-9b, whose accepted overrides were applied
onto the v11 frozen CSV, then measured on the public leaderboard. Its output CSV then became V13's
"current" base. (V12B build/plan scripts `build_v12b_permutation_{plan,candidate}.py` were added in
0a7b9d6 and later deleted; recoverable but not exhaustively re-read here — the "api30 over v11" and
"becomes V13 base" facts are Confirmed from the manifest/config.)

## 12. Historical V13 reconstruction

Layers actually wired into 79.7 (Confirmed from `run_v13_multilayer_verifier.py`): **programmatic_
solver, content_first, least_to_most** only. Each: prompt built by the corresponding `src` module;
model = qwen3.5-9b (except programmatic could be deterministic); input candidate source = V12B
"current"; targets = ≤30 planned qids; ≤1 call per (qid,layer); output schema = structured JSON with
`answer/label/confidence/evidence`; merged by the unified conservative selector.

Components that existed in the repo but were **NOT** in the 79.7 V13 path: `openrouter_graph_solver`
(a separate LangGraph-style solver with JSON-repair + self-consistency + evidence reranker + MCQ
verifier), `mcq_verifier`, evidence reranker, calculation-override-in-graph, adaptive orchestrator,
short-knowledge/law-admin/ambiguous/self-consistency verifier samples. These were research
sidecars (each a `run_*` script), not the V13 candidate builder. (Confirmed: the runner imports only
PS/CF/LTM.)

## 13. Historical selector reconstruction

The 79.7 merge used the **unified conservative `system_candidate_selector`** (manifest
`official_layers` includes `system_candidate_selector`; build_v13_candidate applied it). Its logic —
V12B-first, then programmatic-unique, then cross-layer agreement, then strong-single-source with a
weak-current gate — matches the current selector (the current
`src/selector/system_candidate_selector.py` is byte-identical to the pre-migration selector; see
AUDIT 61). The **difference is the candidates fed to it**: in 79.7 they carried real 9B-model
`confidence`/`evidence` from JSON-mode; conservatism was tuned so ≤9 survived.

## 14. Current local `--legacy-dynamic-full` call graph

```
predict.py --legacy-dynamic-full
  → scripts/tools/final_infer.py  main(["--input",…,"--output",…,"--profile","local_selective_auto"])
  → run_fastmcq_system(samples, cfg):
      backend = get_local_qwen_backend(/models/qwen3-4b-instruct-2507, device=auto)   # ONE backend
      base = predict_base_answers(all qids):
          formula_bank_solver first → if hit, source=formula_bank
          else backend.predict_mcq()  (build_mcq_prompt + generate + parse_mcq_label) → dynamic_local_qwen (conf 0.6)
          else dynamic_fallback ('A', weak)
      v12b_targets = select_v12b_targets(...)[:ceil(N/8)]   # auto cap
      run_v12b_layer: 6 permutations/qid via backend.generate_text → parse_json_object → map back → conservative vote
      v13_targets = select_v13_targets(...)[:ceil(N/8)]
      run_v13_layer: programmatic (deterministic) / content_first / least_to_most via backend.generate_text → parse_json_object
      select_system_overrides(base, v12b, v13)  # same conservative selector
      write exactly-input-qids CSV
```

Confirmed facts: one shared backend object (AUDIT 61); model = local Qwen3-4B; Base runs over ALL
qids from scratch (no frozen CSV); V12B/V13 auto-capped at `ceil(N/8)`; V12B 6 permutations;
parser is best-effort (`parse_json_object` for layers, `parse_mcq_label` for Base/single-pass).

**Empirical runtime evidence (with caveat):** `scratch/fastmcq_run/` holds records from a prior run
in a **torch-less environment**: all 348 V12B records and all 101 V13 model-layer records are
`local_error: ModuleNotFoundError`; V13 programmatic produced 58 `no_deterministic_programmatic_
match`. So in that environment every model-backed layer failed closed → selector kept Base → output
= Base. This **demonstrates the fail-closed mechanism** but is **not** a real-GPU run and says
nothing about real-model quality.

## 15. Response-parser comparison (important)

| Aspect | Historical (79.7) | Current local |
|---|---|---|
| Layer output contract | API `response_format={"type":"json_object"}` → guaranteed JSON object | free-text generation, then `parse_json_object` best-effort (fenced/embedded JSON) |
| Base/single-pass label parse | JSON `answer` field via `_interpret` | **`parse_mcq_label`: first `A–K` char in the uppercased text that is an allowed label** |
| Structured fields (`answer/confidence/evidence/valid`) | present, from the 9B model | synthesized only if the local model emits valid JSON; else dropped as parse_error |

**Parser hazard (reproduced, current `src/local_model/local_qwen_backend.py:57-65`)**: because it
returns the first allowed `A–K` letter anywhere in the text:
- 4-choice, `"The answer is clearly option B."` → **`A`** (the "a" in "answer" precedes "B") — wrong.
- 4-choice, `"Grace Hopper"` → **`A`**; 10-choice → **`G`**.
- `"Đáp án: C"` → `C` (correct when the model is terse).
Severity: **High** for the BTC single-pass Base path when the local model emits prose instead of a
bare letter. The 9B JSON path was immune. (Do not fix here; recorded with file/line.)

## 16. Prompt/config comparison

- **Base prompt** (`build_mcq_prompt`): byte-identical pre/post migration (AUDIT 61). Answer-only
  Vietnamese instruction, all choices labeled, greedy, `max_new_tokens=64`.
- **V13 content_first / least_to_most / programmatic prompts**: reasoning modules differ from the
  79.7 era **only in import paths** (`src.X` → `src.utils/layers/evidence.X`); prompt text,
  parsing, confidence, and option-mapping logic are unchanged (md5 differs solely due to imports;
  functional diff shows only `from …` lines).
- **V12B permutation system prompt**: preserved (AUDIT 61 diff showed only backend swap + failure
  isolation; the system message string is unchanged).
- **Context/generation limits**: historical selective `max_tokens=768`; current
  `layer_max_new_tokens=768`, Base `max_new_tokens=64`. Long Vietnamese passages: neither path
  truncates the question explicitly in these builders; the local backend is bounded by the 4B
  model's context, historically by the 9B model's — **model-capacity difference, not prompt change**.

## 17. Frozen-artifact and public-replay analysis

The 79.7 workflow is a **frozen-artifact chain** (Confirmed): each version's CSV is the next
version's base, and the qid set is exactly the 463 public-test qids. `public_replay` /`frozen_csv`
modes simply **re-emit the frozen 79.7 CSV** when input qids match the public set — they are not the
private/BTC path and are not from-raw inference. The four frozen CSVs and the manifest are **absent
in the current tree** (deleted in migration), which is exactly why 16 tests fail with
`FileNotFoundError` (AUDIT 61/63). Therefore the 79.7 number is **not reproducible from raw input**
and **not portable to the private set** — it encodes public-leaderboard-informed, hand-budgeted
edits. This is a faithful description of the historical workflow, not automatically a defect.

## 18. Three-way comparison A/B/C

**A. Historical OpenRouter Base vs current local single-pass** — Historical "Base" in the 79.7
artifact was a *frozen CSV* (v11/V12B lineage built with 9B + deterministic solvers); current Base
is local 4B single-pass + formula bank over raw input. Model 9B→4B; effective calls: historical Base
= 0 live calls (frozen) vs current = 1 local call/qid. Answers differ because of model capability and
because current Base has no leaderboard-tuned lineage.

**B. Historical 79.7 V13/selective vs current `--legacy-dynamic-full`** — Same reasoning prompts and
same selector code, but: backend 9B-JSON→4B-text; base = frozen V12B (78.83) → local single-pass;
routing = hand-built ≤30-qid plan → automatic `ceil(N/8)` risk rank; structured output guaranteed →
best-effort; ≤~90 API calls → up to N·(1)+2·ceil(N/8)·(6 or 3) local calls. Expected answer
differences: large, because the strong starting base and the strong JSON model are both gone.
Likely quality: **below 79.7** on public, unknown on private.

**C. Current local single-pass vs current local `--legacy-dynamic-full`** — Same model, same Base
prompt/parser. Legacy adds formula-bank-first in Base plus V12B/V13 conservative overrides on
`ceil(N/8)` qids. Effective extra calls: formula bank (free) + up to 2·ceil(N/8) selective bursts.
Output equals single-pass wherever formula bank agrees/does-not-fire and the selector accepts no
override — which, given a conservative selector tuned for a stronger JSON backend and a weaker 4B
producing unstable/low-confidence structured votes, is the common case. Hence "executes all stages,
changes little to nothing." (Mechanism Confirmed from code; zero-change frequency Plausible, not
measured on GPU.)

## 19. Commit-level timeline

| Commit | Date | Message | Architectural consequence |
|---|---|---|---|
| `95975d0` | ~Jun | v10 | v10 baseline (77.75) frozen CSV |
| `92ef1fa` | ~Jun | v11: frozen independent v11 78.4 default | v11 independent base (78.40) |
| **`0a7b9d6`** | 2026-06-24 | v13: promote V13 multi-layer 79.7 as official dynamic production system | **Adds V12B+V13 build/plan/run scripts, `production_v13_multilayer_7970.json` (model `qwen/qwen3.5-9b-20260310`), manifest (79.7), frozen CSVs; promotes V13 79.7. The 79.7-era commit.** |
| `e2d8f5d`…`1b0f79a` | Jun–Jul | "finalize … Docker submission" series | src reorg (`src/` → `src/api`,`src/layers`,`src/selector`,…); Dockerization; profiles |
| `dd21ed8` | Jul | clean legacy configs and consolidate documentation | trims legacy configs/docs |
| `87d5d71` | Jul | remove obsolete experiment metadata | **pre-migration baseline (backup branch)**; deletes `leaderboard_log.csv` etc. |
| **`d0d8c28`** | 2026-07-09 | migrate selective reasoning pipeline to local Qwen | **Deletes `src/api/*`, OpenRouter clients/model-policy, selective build/plan/verifier scripts; rewires Base/V12B/V13 to local Qwen3-4B; removes structured-output guarantee.** |
| `1d791e3` | 2026-07-09 | fix Docker shell script line endings | CRLF/LF hardening (AUDIT 62/63); no runtime change |

(Evidence: `git log`, `git show --stat`; the V12B/V13 introduction and the 79.7 recording both land
in `0a7b9d6`; the local migration is `d0d8c28`.)

## 20. Ranked causes of quality loss (79.7 → current local)

| # | Cause | Evidence strength | Likely impact | Affected stage | How to test | Portable to local ≤5B? |
|---|---|---|---|---|---|---|
| 1 | **Different model** (9B qwen3.5 → 4B qwen3-4B) | Confirmed (config vs config) | High | all model stages | ablation E14 offline 9B refs vs local | inherent limit |
| 2 | **Frozen-artifact base removed** (79.7 built on V12B/v11 CSVs; current from raw) | Confirmed | High | Base | run current end-to-end on public qids, compare | yes (but base must be strong) |
| 3 | **Structured-output guarantee removed** (JSON-mode → best-effort text) | Confirmed | Med-High | V12B/V13 parse | count parse_error rate locally | yes (enforce JSON/grammar) |
| 4 | **Free-text label parser hazard** (`parse_mcq_label` first `A–K`) | Confirmed (reproduced) | Med-High | Base single-pass | unit-test prose outputs | yes (harden parser) |
| 5 | **Selector thresholds tuned for 9B JSON** (`_STRONG_CONF=0.6`, weak-gate) | Strongly supported | Medium | selector | recalibrate on local votes | yes |
| 6 | **Budget/routing changed** (hand ≤30-qid plan → auto `ceil(N/8)`) | Confirmed | Medium | V12B/V13 targeting | compare selected qids to weak set | yes |
| 7 | **Leaderboard-informed iteration gone** (public feedback per version) | Confirmed | Medium (public only) | whole workflow | n/a for private | no (no private labels) |
| 8 | **Disconnected verifier/evidence/graph solver** (not in 79.7 path anyway) | Confirmed | Low for 79.7 parity | n/a | optional reconnect | maybe |
| 9 | **Formula-bank over-trust in Base** (fires before model, conf may block override) | Plausible | Low-Med | Base | ablation E2 | yes |

No single cause is definitive; #1+#2 dominate and are structural.

## 21. Components deleted / disconnected / changed

- **Deleted (runtime):** `src/api/openrouter_client.py`, `selective_api_client.py`,
  `openrouter_graph_solver.py`, `openrouter_prompts.py`, `model_policy.py`, `api_candidate_agents.py`
  (moved to `src/local_model/candidate_agents.py`); `requirements-openrouter.txt`; selective
  build/plan/verifier/repair scripts under `scripts/legacy/`; the four frozen CSVs + manifest;
  OpenRouter tests.
- **Structured-output guarantee:** removed (JSON-mode → best-effort parse). Changed.
- **Base source:** frozen CSV chain → local formula-bank+model. Changed.
- **Budget/routing:** fixed ≤30-qid plan → automatic `ceil(N/8)`. Changed.
- **Present but not wired into either the 79.7 path or the current default:** `adaptive_orchestrator`
  (kept, zero tests — AUDIT 61 M3), `mcq_verifier`, evidence reranker, `openrouter_graph`
  replacement — library code with no runtime host.
- **Preserved (logic/prompts unchanged):** Base prompt+parser signature, V13 reasoning prompts
  (import-path only), V12B system prompt, `system_candidate_selector` (byte-identical).

## 22. Unknowns and contradictory evidence

- Real local-GPU quality of `--legacy-dynamic-full`: **Unknown** (no GPU run; scratch artifacts are
  torch-less).
- Whether 79.7 was posted to an external official leaderboard vs computed against a locally held
  public answer key: **Unverified** (repo says "public leaderboard"; no receipt).
- V12B's exact historical prompt/permutation count in the 79.7 build script: partially read
  (manifest Confirmed "api30 over v11"; the 0a7b9d6 build_v12b scripts recoverable but not
  line-audited here).
- No contradictions found among committed sources; the only tension is docs shorthand `qwen3.5-9b`
  vs the pinned `qwen/qwen3.5-9b-20260310` — the pinned id in the config governs (not a conflict).

## 23. Ablation matrix for architecture selection

Validation data constraint: **no organizer ground truth.** Use only self-annotated / synthetic /
weakly-labeled sets, or historical OpenRouter outputs as an *offline reference* (no new API calls).

| # | Experiment | Hypothesis | Components affected | Data/labels | Runtime cost | Diagnostic value |
|---|---|---|---|---|---|---|
| 1 | Local single-pass baseline | establishes floor | predict.py | small labeled val | 1×/qid | high (anchor) |
| 2 | Base, formula bank OFF | quantify formula-bank help/harm | dynamic_base | val | 1×/qid | med |
| 3 | Base, parser hardened (JSON/grammar or strict-letter) | fix cause #4 | local_qwen_backend parse | val | 1×/qid | high |
| 4 | Base + historical structured schema (force JSON answer/conf) | recover cause #3 | backend + prompt | val | 1×/qid | high |
| 5 | Base + V12B on router-selected qids | does permutation debias help locally | v12b layer | val | +6×/target | high |
| 6 | Base + V13 programmatic only | deterministic-only gain | v13 PS | val | ~0 | med |
| 7 | Base + content_first | label-error avoidance | v13 CF | val | +1×/target | high |
| 8 | Base + least_to_most | multi-condition elimination | v13 LTM | val | +1×/target | high |
| 9 | Reconnect verifier/evidence/calc | do sidecars help local | mcq_verifier/evidence | val | +calls | med |
| 10 | Selector with historical thresholds | baseline selector | selector | val | ~0 | med |
| 11 | Selector recalibrated for local votes | fix cause #5 | selector consts | val | ~0 | high |
| 12 | Larger selective budget (vary cap) on fixed val | budget vs accuracy curve | final_infer cap | val | scaling | high |
| 13 | Oracle routing on labeled val (analysis only) | upper bound of routing | plan | labeled val | analysis | high |
| 14 | Historical OpenRouter outputs as offline reference | agreement/gap vs 9B (no new API) | analysis | recovered JSONL if any | 0 | high |

Never use organizer public/private answers as local ground truth.

## 24. Decision-relevant recommendations

- Treat 79.7 as a **public-set, frozen-artifact, 9B-model** result — a *ceiling reference*, not a
  target reproducible by the local 4B from raw input.
- Before choosing an architecture, run ablations **1, 3, 4, 5, 7, 8, 11, 12** on a self-labeled
  validation set; they isolate the top causes (model, structured output, parser, selector, budget).
- Worth restoring/porting: **structured-output enforcement** (JSON/grammar-constrained decoding) and
  a **hardened label parser**; both are model-portable and directly address confirmed defects.
- Not worth restoring: the **frozen-artifact chain** and **public-leaderboard-tuned ≤30-qid plans**
  (not portable to private; not from-raw reproducible). OpenRouter runtime stays removed.
- Keep the shared single-backend design (AUDIT 61) and the conservative selector, but **recalibrate
  its thresholds** against the local model's actual confidence distribution.

## 25. Exact commands run (representative)

```
git branch --show-current; git rev-parse HEAD; git status --short; git log -1 --oneline --decorate
git remote -v; git branch -a; git tag --list
git grep -n -I -E '79[.,]7|0\.797' -- .
git log --all -S'79.7' --oneline --decorate
git show --stat 0a7b9d6
git show 0a7b9d6:experiments/best_candidate_manifest.json
git show 0a7b9d6:configs/production_v13_multilayer_7970.json
git show 0a7b9d6:scripts/run_v13_multilayer_verifier.py
git show 0a7b9d6:scripts/build_v13_multilayer_plan.py
git show 0a7b9d6:src/selective_api_client.py
git show 0a7b9d6:src/openrouter_client.py
git show 0a7b9d6:src/model_policy.py
git show 0a7b9d6:docs/audits/AUDIT_PHASE_2L38A_PROMOTE_V13_7970_OFFICIAL_DYNAMIC_SYSTEM.md
git log --all --diff-filter=D --name-only ...            # deleted-file census
git log --all --oneline --name-status -- experiments/leaderboard_log.csv
# read-only artifact inspection: scratch/fastmcq_run/{progress.json,v12b_*,v13_*}
# parser reproduction + module md5/functional diffs (content_first / least_to_most / programmatic)
```

No OpenRouter/API/network call was made; no API key value was read or printed; no model downloaded;
no Docker build/push; no commit/push; no file restored to the working tree.

## 26. Current `git status --short`

```
(empty before this audit; after creating this file:)
?? docs/audits/64-forensic-reconstruction-openrouter-79-7-vs-local-legacy.md
```

## 27. Explicit confirmations

- No production code was modified (only this audit file was created).
- No OpenRouter/API request was made.
- No API key value was printed or stored.
- No model weights were downloaded.
- No Docker image was built or pushed.
- No Git commit or push was performed; no branch/commit checkout altered the working tree; no file
  was restored/deleted.
```
