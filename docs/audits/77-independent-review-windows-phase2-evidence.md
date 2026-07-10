# AUDIT 77 — Independent Documentation Review of the Phase 2 Windows Real-Model Evidence Record (AUDIT 76)

Audit number 77 (no prior `77-*` existed under `docs/audits/`).

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `7b8134cc8ada80fc4c0a5e15d45601bca7316364` ("add confidence-aware shadow router")

## 2. Initial working-tree state

`git status --short` shows exactly one entry: `?? docs/audits/76-windows-real-model-validation-phase2-shadow-router.md`.
`git diff --check` clean; `git diff --stat` empty (no tracked modifications). AUDIT 71–75 are
committed. This matches the expected state; nothing was staged, reset, discarded, committed, or
pushed.

## 3. Independence / read-only statement

This is a **documentation-only** review of AUDIT 76's accuracy, internal consistency, and caveating.
It does **not** rerun the Windows GPU/model commands (this Linux environment has no torch/transformers/
model) and does not independently certify the external runtime numbers. Verification was limited to:
cross-checking transcribed values for internal arithmetic/consistency, comparing them against the
prior audits (71/72/74), and confirming AUDIT 76's terminology/scope match the committed Phase 2
implementation. No file was modified.

## 4. Evidence available vs unavailable to the reviewer

- **Available:** AUDIT 71–76 text; the committed Phase 2 source (router, config, predict.py, tests).
- **Unavailable (external, cannot re-verify):** the Windows GPU run, the model, the CSV/JSONL/summary
  artifacts under `/workspace/fastmcq/scratch`, and the raw SHA-256 computation. These are accepted as
  user-supplied and checked only for internal consistency and code-compatibility.

## 5. Files reviewed

`docs/audits/71–76`; and for terminology/scope compatibility (read-only):
`src/local_model/confidence_shadow_router.py`, `src/local_model/confidence_config.py`,
`src/local_model/local_qwen_backend.py`, `predict.py`, `configs/confidence_selective.yaml`, and the
two shadow test files.

## 6. Evidence-provenance review — ACCURATE

AUDIT 76 explicitly states: the user ran the Windows Docker validation (§2); the Linux environment did
**not** rerun the GPU/model commands and only records supplied evidence (§2, header note); values were
transcribed from the user-supplied run (header note); the dataset was self-created synthetic diagnostic
data (§2); no organizer labels/ground truth (§2); no external API/OpenRouter (§2); the model was
already inside the image (§3); no model download (§2/§3). Nowhere does it present the evidence as
independently reproduced in Linux. **No false-provenance claim found.**

## 7. Repository-identity review — ACCURATE

Branch `main`; full HEAD `7b8134cc8ada80fc4c0a5e15d45601bca7316364`; short `7b8134c`; title "add
confidence-aware shadow router" — all match the live repo. AUDIT 71–75 are committed; AUDIT 76 is the
only new untracked file. AUDIT 76 does **not** claim it was already committed (§20 shows it untracked).

## 8. Runtime-environment transcription review — CONSISTENT

Image `vquclinh/fastmcq-local-selective:d0d8c28-lf`, model `/models/qwen3-4b-instruct-2507`, RTX 4060,
CUDA true, mount `/workspace/fastmcq`, baked weights — all presented as supplied runtime evidence
(§3), not as newly verified Linux facts. Internally consistent.

## 9. Input-preparation review — CONSISTENT

Input `scratch/phase2_real/synthetic21_input.json`, 21 items, first `syn_001_addition_3`, last
`syn_021_pills` (§4). Consistent with the 21-item synthetic set and with the input-index values in §12
(see §15 below).

## 10. PowerShell count-check caveat review — HANDLED HONESTLY

AUDIT 76 §5 records the `Expected 21 input records; found 1` warning, attributes it to a PowerShell
array-wrapping quirk in one count expression, explicitly states it is **not** a model/router/dataset/
repo defect, notes both runs processed 21 samples and both CSVs had 21 rows by independent checks, and
**explicitly does not claim the faulty expression itself passed** ("only that the actual runs and
outputs were verified to be 21 records"). Technically plausible and appropriately cautious.

## 11. Baseline record review — SUPPORTED FACTS ONLY

§6: no-shadow mode, model loaded, 21 predicted, 0 fallbacks, 21 rows, mirrored path, ≈37.153 s, PASS.
The note "must not be used to estimate model-load time or per-question latency" is present. No
over-interpretation.

## 12. Shadow record review — SUPPORTED FACTS ONLY

§7: explicit flag, observational/no-answer-change/no-V12B-V13 log, model loaded, 21 predicted, 0
fallbacks, 21 decisions, selected 3 of cap 3, 21 rows, JSONL/summary/CSV paths, ≈27.154 s, PASS. The
note correctly forbids interpreting the totals as model-load time, per-question latency, exact shadow
overhead, or proof shadow is faster.

## 13. Hash / official-output invariance review — CONSISTENT

§8 transcribes identical baseline/shadow SHA-256 `3A8940B9…D5DBEB8D`. §9 draws only supported
conclusions: non-empty, identical, 21 rows each, qid order identical, answers identical, no add/drop/
reorder, shadow did not change official predictions. It does **not** claim byte invariance for
unrelated files. (The reviewer cannot recompute the external hash; it is checked only for internal
consistency — both values are identical and well-formed 64-hex SHA-256.)

## 14. Router-summary consistency review — CONSISTENT WITH CODE

§10/§11: `n_input=21`, `budget_cap=3`, `provisional_threshold=10.0`, `candidate_count=4`,
`selected_count=3`, `scoring_method=next_token_logits_one_forward`. Verified against the committed
router: `_budget_cap` uses `ceil(n/divisor)` → `ceil(21/8)=3` ✓; `selected_count (3) ≤ cap (3)` ✓;
`candidate_count (4) > selected_count (3)` is consistent with threshold-filter-then-cap and the
no-backfill policy ✓; `SCORING_METHOD = "next_token_logits_one_forward"` matches the code constant ✓;
threshold 10.0 is described as provisional/shadow-only, matching the config default and prior audits ✓.

## 15. Selected-record transcription review — ACCURATE

§12 lists the three selected records: `syn_020_sequence`(idx 19, C, C/D, margin 0.0, ent≈0.500023),
`syn_008_speed`(idx 7, A, A/C, 4.25, ≈0.053332), `syn_001_addition_3`(idx 0, A, A/C, 7.75, ≈0.004552),
all reason `low_logit_margin`, ranks 1/2/3. Cross-checks:
- The qids, margins (0.0/4.25/7.75), top1/top2, and entropies match AUDIT 71 (0.50002295/0.05333236/
  0.00455163, rounded) and the AUDIT 72/74 replay (which recorded the selected set **by qid**). ✓
- **Input-index self-consistency:** the real input is ordered `syn_001…syn_021`, so `syn_00N` sits at
  index `N-1`; the audit's indices (0, 7, 19) match exactly (syn_001→0, syn_008→7, syn_020→19). ✓
- Ranks are unique and ordered by ascending margin. ✓
- The runtime table **excludes** expected answers and correctness (correctly deferred to AUDIT 71's
  synthetic-diagnostic discussion). ✓
- The audit does **not** claim these three items prove a calibrated production policy. ✓

Note (Informational I1): "exactly match the prior metadata-only 21-record replay" is accurate for the
**selected qids / margins / ranks** (what AUDIT 72/74 recorded); the `input_index` values (19/7/0) come
from the real input ordering and were not fields recorded by the prior replay. This is a basis-of-
comparison nuance, not an error.

## 16. Artifact-size / schema / privacy review — CONSISTENT WITH CODE

§13/§14: CSV 476 B (both), JSONL 9490 B, summary 3247 B, 21 decisions, 3 selected, ranks 1/2/3, all
`next_token_logits_one_forward`, `selected_items` = {qid, input_index, selected_rank}. Verified:
`selected_items` schema matches the code (line 234); the decision `as_dict` contains **no** question/
choices/prompt/expected/correctness field (confirmed by inspection); the writer uses `allow_nan=False`
for both JSONL and summary, so NaN/±Inf cannot appear (consistent with the "no NaN/Infinity" claim).
The privacy list is **narrowly scoped to the named fields** and does **not** claim every conceivable
secret type was exhaustively ruled out. ✓

## 17. Forward-count wording review (high-priority) — CORRECT

AUDIT 76 §7 note, §16, §17, and §18 consistently state that this shadow-only run **did not instrument
the exact number of model-forward calls**; that one-forward choice scoring was established by prior
Phase 1 real-model validation (AUDIT 71) and code/tests; that combined telemetry-plus-shadow score
reuse was established by integration tests (AUDIT 72/74); and that this run "must not" be used as
direct runtime proof of combined-mode forward count. **No statement implies this run itself measured
one forward per record.** Correct and appropriately limited.

## 18. Phase 2 completion-scope review — PROPERLY BOUNDED

The mandated verdict says "PHASE 2 COMPLETE", but §16–§18 and §22 limit it to the observational
shadow-router stage (committed implementation + independent review AUDIT 73 + corrective review AUDIT
75 + Windows smoke). §17 explicitly lists what is **not** established: final threshold, calibrated
accuracy, leaderboard improvement, V12B/V13/selector effectiveness, combined-mode forward count, exact
overhead, Phase 3 correctness, default-promotion readiness; and §22 states "Phase 3 has not been
implemented or validated." "Phase 2 complete" is therefore materially bounded and non-misleading —
Low/Informational only.

## 19. Interpretation-limits review — COMPLETE

§17/§18 explicitly disclaim: final production threshold, calibrated accuracy, leaderboard improvement,
V12B/V13/selector effectiveness, exact shadow overhead, combined-mode forward count, Phase 3
correctness, default-promotion readiness; and describe the 21-item set as diagnostic-only and
insufficient for final calibration. Complete and accurate.

## 20. Git / scope review — ACCURATE

`git diff --check` clean; `git diff --stat` empty; `git status --short` shows only untracked AUDIT 76.
No production source, test, config, or audit 71–75 changed; no prompt/parser/formula/model/Docker/
dependency/V12B/V13/selector/output-contract change; no commit/push. AUDIT 76 §15/§19/§20 accurately
reflect this.

## 21. Internal-consistency review — CONSISTENT (one minor wording nuance)

No material contradiction found: selected count 3 = 3 selected records; 21 decisions = 21 inputs;
threshold called provisional throughout (never final); "Phase 3 planning" (not execution); no claim
of committed runtime artifacts; timing explicitly disavowed as an overhead measure. **Minor wording
nuance (L1):** §1 line 10 states "Working tree: clean" as a current fact, while §20 correctly lists
AUDIT 76 as the sole untracked file. Read as the preflight/starting state (clean at HEAD, before this
audit existed) with §20 as the ending state, this is the standard non-contradictory audit pattern; but
the bare word "clean" in §1 would read more precisely as "no tracked modifications (this audit is the
only new untracked file)." Documentation clarity only.

## 22. Findings (ordered by severity)

No **Critical**, **High**, or **Medium** findings.

| ID | Sev | Section | Evidence | Impact | Blocks committing AUDIT 76? | Recommended correction |
|---|---|---|---|---|---|---|
| L1 | Low | AUDIT 76 §1 | "Working tree: clean" is not qualified for the untracked AUDIT 76 (fully disclosed in §20) | Minor read ambiguity; §20 resolves it | No | Reword §1 to "no tracked modifications; this audit is the only new untracked file" |
| I1 | Info | AUDIT 76 §12 | "exactly match the prior replay" is by qid/margin/rank; `input_index` (19/7/0) is real-input detail not recorded by the prior replay | none (accurate) | No | Optionally note the comparison is by selected qid/margin/rank |
| I2 | Info | AUDIT 76 (all runtime values) | GPU/hash/artifact numbers are external/user-supplied; Linux cannot recompute them | expected limitation | No | none (already disclosed) |
| I3 | Info | AUDIT 76 §22 | "Phase 2 complete" is a strong phrase, bounded by §16–§18 | none (well-caveated) | No | Optionally add "(observational shadow-router stage)" inline in the verdict |

## 23. Required corrections before committing AUDIT 76

**None.** L1/I1/I3 are optional documentation-clarity refinements; the record is accurate, internally
consistent, honestly caveated, and code-compatible.

## 24. Remaining evidentiary limitations

The Windows GPU run, the SHA-256 values, and the artifact byte-sizes are external and not
independently reproducible in this Linux environment; they are accepted on the basis of internal
consistency and code-compatibility (all of which pass). Real accuracy/threshold calibration and
combined-mode forward-count remain out of scope for this evidence record.

## 25. Confirmation

No implementation fix, no Phase 3, no V12B/V13 execution or change, no selector change, no source/
test/config change, no prompt/parser/formula/model/Docker/dependency change, no external API/OpenRouter
call, no API key inspected/printed, no model download, no Git commit or push. AUDIT 71–76 were not
modified. Only this file (AUDIT 77) was created.

## 26. Current `git status --short`

```
?? docs/audits/76-windows-real-model-validation-phase2-shadow-router.md
?? docs/audits/77-independent-review-windows-phase2-evidence.md
```

## 27. Final verdict

**SAFE TO COMMIT WITH NON-BLOCKING DOCUMENTATION CAVEATS.**

AUDIT 76 accurately records the user-supplied Windows real-model shadow-router validation: provenance
is honestly external; the PowerShell count caveat is handled without overclaiming; hash/row/answer
invariance, candidate/selected counts, selected-record values, and artifact/privacy claims are
internally consistent and match the committed router; forward-count wording is appropriately limited;
"Phase 2 complete" is bounded to the observational shadow stage; and default promotion / Phase 3 remain
explicitly disallowed. The only findings are one Low wording nuance (§1 "clean") and informational
notes — none blocking. This verdict authorizes committing AUDIT 76 as the Phase 2 evidence record; it
does **not** authorize Phase 3 implementation or default promotion.

STOP — independent documentation review complete. AUDIT 76 not modified; nothing committed or pushed;
Phase 3 not implemented.
