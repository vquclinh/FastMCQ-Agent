#!/usr/bin/env python3
"""Scan runtime source/config/scripts for disallowed model references (no API).

PASS if only competition-allowed models are referenced in runtime code that can affect
model selection; FAIL (with file:line) if a disallowed vendor/model string appears.
Audit docs and unit tests are intentionally excluded — they legitimately mention
GPT/Claude/etc. as rejection examples. ``src/model_policy.py`` and this script are
also excluded (they define the banned list).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# A disallowed reference must look like a real MODEL ID being selected, not prose or a
# diagnostic column name: either a vendor namespace (``openai/…``) or a versioned model
# (``gpt-4``, ``claude-3``, ``gemini-1.5``, ``llama-3``). This avoids flagging external-
# sheet columns like ``gemini_answer`` or denylist words.
_VENDOR_SLASH_RE = re.compile(
    r"\b(?:openai|anthropic|deepseek|mistralai|meta-llama|cohere|google)/", re.IGNORECASE)
_VERSIONED_RE = re.compile(
    r"\b(?:gpt|claude|gemini|llama|deepseek|mistral|mixtral|grok|palm|bison)[-_]?\d",
    re.IGNORECASE)
# Qwen larger than 9B (e.g. qwen...-14b/32b/72b).
_BIG_QWEN_RE = re.compile(r"qwen[\w.\-/]*-(\d+)b", re.IGNORECASE)

# Runtime areas that affect model selection.
_SCAN_DIRS = ("src", "scripts", "configs")
# Files excluded from the scan: policy/guardrail definitions (they intentionally list
# banned names) and the external 3-LLM diagnostic tools (they reference sheet COLUMNS
# named gemini/gpt/claude, never a model to run).
_EXCLUDE = {
    "src/model_policy.py", "scripts/audit_model_policy.py",
    "configs/allowed_models.yaml",
    "scripts/audit_first100_consensus_risks.py",
    "scripts/compare_v7_programmatic_assist_pseudo.py",
    "scripts/export_risk_review_pack.py",
    "scripts/analyze_candidate_disagreements.py",
    "scripts/recommend_submission_candidate.py",
}


def _scan_file(path: Path):
    findings = []
    try:
        rel = str(path.relative_to(_ROOT))
    except ValueError:
        rel = path.name                      # path outside the repo (e.g. a temp file)
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return findings
    for i, line in enumerate(text.splitlines(), 1):
        low = line.strip().lower()
        if low.startswith("#") or low.startswith('"""') or low.startswith("*"):
            continue   # skip comments/docstring lines (reduce false positives)
        m = _VENDOR_SLASH_RE.search(line) or _VERSIONED_RE.search(line)
        if m:
            findings.append((rel, i, m.group(0), line.strip()[:100]))
        for bm in _BIG_QWEN_RE.finditer(line):
            if int(bm.group(1)) > 9:
                findings.append((rel, i, f"qwen-{bm.group(1)}B", line.strip()[:100]))
    return findings


def main(argv=None) -> int:
    findings = []
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in (".py", ".yaml", ".yml", ".json", ".sh"):
                continue
            rel = str(path.relative_to(_ROOT))
            if rel in _EXCLUDE or "/tests/" in f"/{rel}" or rel.startswith("docs/"):
                continue
            findings.extend(_scan_file(path))

    print("=" * 64)
    print("MODEL-POLICY REPO AUDIT (runtime src/scripts/configs)")
    print("=" * 64)
    if not findings:
        print("RESULT: PASS — only competition-allowed models referenced.")
        print("=" * 64)
        return 0
    print(f"RESULT: FAIL — {len(findings)} disallowed model reference(s):")
    for rel, line_no, tok, snippet in findings:
        print(f"  {rel}:{line_no}  [{tok}]  {snippet}")
    print("=" * 64)
    return 1


if __name__ == "__main__":
    sys.exit(main())
