# Selective MCQ Verifier + Option Elimination

`src/mcq_verifier.py` adds an optional **second-pass verifier** for the OpenRouter
graph. Given the question/evidence actually used, the choices, and the original
answer, it asks the model to briefly assess each option and decide whether the
original answer is supported or another option is clearly better — then overrides
only when the verifier is confident.

## Why it helps MCQA accuracy

- MCQ LLMs suffer from option-order/option-ID bias and can pick plausible distractors.
- One-pass long-context answers can be wrong when evidence is noisy/incomplete.
- Per-option assessment + elimination is a **generic, private-test-safe** robustness
  step — not a qid-specific patch.

## Default OFF

`mcq_verifier.enabled: false` by default, so v1/v2 behavior is unchanged unless you
explicitly enable it. When enabled it makes **one extra call** and only on
hard/uncertain cases.

## Selective trigger policy (`should_run_verifier`)

Runs only when enabled AND `route ∈ apply_routes`
(`long_context, ambiguous, law_admin, safety_ethics`) AND at least one trigger:

- initial parser source is `partial_answer_key`,
- initial answer confidence `< trigger_below_confidence` (0.70),
- the answer used a repair pass,
- a long-context answer used reranked evidence.

**Never runs when:**
- the answer came from a **deterministic calculation safe-override** (the calc
  override returns before the verifier and `should_run_verifier` also guards it),
- there is no valid original answer (normal repair handles that first),
- the route is out of scope (e.g. high-confidence `short_knowledge`).

## JSON schema (structured, no chain-of-thought)

```json
{
  "original_answer_supported": true,
  "best_answer": "B",
  "should_override": false,
  "confidence": 0.82,
  "option_assessments": [
    {"label": "A", "status": "contradicted", "confidence": 0.7, "reason": "short"},
    {"label": "B", "status": "supported",    "confidence": 0.9, "reason": "short"}
  ],
  "rationale": "short final reason"
}
```

`status ∈ {supported, contradicted, irrelevant, uncertain}`. Reasons are capped
(~120–160 chars); no long reasoning is requested or logged. The parser reuses the
robust JSON extraction from `structured_answer` (strict/fenced/embedded).

## Override policy

The verifier overrides only when **all** hold:
- `should_override` is true, and
- `best_answer` is a **valid label** in the choices, and
- `best_answer != original_answer`, and
- `confidence >= min_confidence_to_override` (default 0.80).

Otherwise the original answer is kept. A failed call / unparseable output / invalid
label also keeps the original. The verifier **never** produces an out-of-range
label and **never** erases a calculation safe-override.

## Interaction with the other modules

- **Calculation solver:** a safe calc override answers first and **bypasses** the
  verifier entirely (and the guard double-checks the `calculation_override` strategy).
- **Evidence reranker:** when a long-context answer used reranked evidence, that is
  a verifier trigger; the verifier sees the same (reranked) evidence body.

## Config (`openrouter:` block)

```yaml
mcq_verifier:
  enabled: false
  apply_routes: ["long_context", "ambiguous", "law_admin", "safety_ethics"]
  min_confidence_to_override: 0.80
  trigger_below_confidence: 0.70
  trigger_on_partial_parse: true
  trigger_on_repair: true
  trigger_on_reranked_long_context: true
  max_extra_calls_per_sample: 1
```

CLI: `--mcq-verifier` / `--no-mcq-verifier`, `--mcq-verifier-threshold <float>`.

## No-hardcoding guarantees

No qid logic, no public-test answer table, no web retrieval, no `eval`/`exec`
(asserted by tests). The verifier reads only the sample's question/evidence +
choices + the original answer.

## Trace fields (JSONL)

`verifier_enabled`, `verifier_triggered`, `verifier_trigger_reason`,
`verifier_original_answer`, `verifier_answer`, `verifier_confidence`,
`verifier_should_override`, `verifier_override_applied`, `verifier_parse_source`,
`verifier_error`. (Light option-assessment data only; no full prompts/CoT.)

## Cost note (tunable)

On the v2 trace, default-on settings would trigger the verifier on **102/463**
samples (every reranked long-context + a few ambiguous) → +102 calls (~22%). To
make it more selective, set `trigger_on_reranked_long_context: false` so only
low-confidence / partial-parse / repair cases trigger (~11 samples).

## Limitations

- A second LLM opinion can be wrong too; the high override threshold limits harm
  (it only overrides on confident disagreement).
- No ground truth — net accuracy effect is confirmed only by the leaderboard.

## Running a future controlled experiment

Enable on a slice first, e.g.:

```bash
.venv/bin/python run.py --solver openrouter_graph --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 --openrouter-max-tokens 1024 \
  --calculation-solver --evidence-reranker --mcq-verifier \
  --input public-test_1780368312.json --limit 20 \
  --output output/pred_v3_verifier_smoke.csv --save-raw \
  --log-path output/run_v3_verifier_smoke.jsonl
```

Inspect `verifier_*` fields, then scale up — A/B against the v1/v2 leaderboard
scores before adopting.
