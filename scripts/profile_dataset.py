#!/usr/bin/env python3
"""Profile an MCQ dataset and (optionally) a sample submission.

Produces a human-readable Markdown report and a machine-readable JSON dump:

    python scripts/profile_dataset.py \
        --input public-test_1780368312.json \
        --sample-submission submission_1780332147.csv

Stdlib-only by design. Category and "long context" detection use simple keyword
heuristics — they are deliberately rough, meant to guide solver design rather
than to be ground truth.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

# Allow running the script directly without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_io import load_dataset, read_predictions  # noqa: E402

# Keywords that signal a long context passage is embedded in the question.
CONTEXT_KEYWORDS = ["Đoạn thông tin", "Nội dung:", "Tiêu đề:", "-- Đoạn văn"]

# Below this character count a question is treated as a short standalone question.
SHORT_QUESTION_CHARS = 200

# Category heuristics. Each sample is assigned to the FIRST category (in this
# order) whose keywords match; "reading comprehension" and the sciences are
# checked before broader buckets so the more specific signal wins. Matching is
# case-insensitive over question text + choices.
CATEGORY_RULES = [
    ("reading_comprehension", CONTEXT_KEYWORDS),
    ("math_calculation", ["đạo hàm", "tích phân", "phương trình", "xác suất",
                          "hàm số", "tính giá trị", "đồ thị", "ma trận", "logarit"]),
    ("physics", ["vận tốc", "gia tốc", "lực ", "điện trường", "năng lượng",
                 "vật lý", "quãng đường", "động năng", "nhiệt độ"]),
    ("chemistry", ["phản ứng hóa", "hóa học", "nồng độ", "phân tử", "nguyên tử",
                   "dung dịch", " mol", "hợp chất"]),
    ("biology", ["tế bào", "gen ", "sinh học", "enzyme", "protein", "vi khuẩn",
                 "di truyền", "nhiễm sắc thể"]),
    ("economics", ["độ co giãn", "lượng cầu", "lượng cung", "kinh tế", "lạm phát",
                   "thị trường", "gdp", "lợi nhuận", "chi phí biên"]),
    ("law_admin", ["pháp luật", "luật ", "hành chính", "nghị định", "hiến pháp",
                   "công vụ", "điều khoản", "quy phạm"]),
    ("history_geo_culture", ["lịch sử", "triều đại", "chiến tranh", "thủ đô",
                             "địa lý", "thế kỷ", "vương quốc", "văn hóa", "nhà vua"]),
    ("safety_ethics", ["đạo đức", "an toàn", "không nên", "từ chối", "nguy hiểm",
                       "vi phạm đạo đức", "hành vi sai"]),
]
# Anything matching none of the above falls here.
FALLBACK_CATEGORY = "general_knowledge"

# A question with LaTeX math or mostly-numeric choices but no category keyword is
# still very likely a calculation question.
_LATEX_RE = re.compile(r"\$.+?\$|\\frac|\\sqrt|\\times")
_DIGIT_RE = re.compile(r"\d")


def approx_words(text: str) -> int:
    """Rough word count (whitespace split). Vietnamese is space-separated."""
    return len(text.split())


def has_long_context(question: str) -> bool:
    return any(kw in question for kw in CONTEXT_KEYWORDS)


def choices_mostly_numeric(choices: list[str]) -> bool:
    if not choices:
        return False
    numeric = sum(1 for c in choices if _DIGIT_RE.search(c))
    return numeric / len(choices) > 0.6


def categorize(sample: dict) -> str:
    """Assign a single rough category to a sample via priority-ordered keywords."""
    haystack = (sample["question"] + " " + " ".join(sample["choices"])).lower()
    for name, keywords in CATEGORY_RULES:
        if any(kw.lower() in haystack for kw in keywords):
            return name
    # Calculation fallback before "general": LaTeX or numeric-answer questions.
    if _LATEX_RE.search(sample["question"]) or choices_mostly_numeric(sample["choices"]):
        return "math_calculation"
    return FALLBACK_CATEGORY


def normalize_for_template(question: str) -> str:
    """Normalise a question so near-template variants collapse to one signature.

    Lowercase, drop digits and LaTeX/punctuation, collapse whitespace, then take
    a prefix. Cheap and good enough to surface templated question families (e.g.
    the same physics problem with different numbers).
    """
    text = question.lower()
    text = re.sub(r"\$.*?\$", " ", text)        # strip inline LaTeX
    text = re.sub(r"[\d.,;:!?$\\{}()\[\]/%-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80]


def truncate(text: str, length: int = 100) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1] + "…"


def profile_dataset(samples: list[dict]) -> dict:
    """Compute the full profile dict for a dataset."""
    n = len(samples)
    q_chars = [len(s["question"]) for s in samples]
    q_words = [approx_words(s["question"]) for s in samples]
    n_choices = [len(s["choices"]) for s in samples]

    long_context = [s for s in samples if has_long_context(s["question"])]
    short_q = [s for s in samples if len(s["question"]) < SHORT_QUESTION_CHARS
               and not has_long_context(s["question"])]

    # Category assignment + examples.
    categories: dict[str, list[dict]] = {}
    for s in samples:
        categories.setdefault(categorize(s), []).append(s)
    category_summary = {}
    for name, members in sorted(categories.items(), key=lambda kv: -len(kv[1])):
        category_summary[name] = {
            "count": len(members),
            "pct": round(100 * len(members) / n, 1),
            "examples": [
                {"qid": m["qid"], "question": truncate(m["question"], 120),
                 "num_choices": len(m["choices"])}
                for m in members[:3]
            ],
        }

    # Choice-count buckets of interest.
    more_than_4 = [s for s in samples if len(s["choices"]) > 4]
    two_or_three = [s for s in samples if len(s["choices"]) in (2, 3)]

    # Near-duplicate / template groups.
    sig_groups: dict[str, list[str]] = {}
    for s in samples:
        sig_groups.setdefault(normalize_for_template(s["question"]), []).append(s["qid"])
    template_groups = sorted(
        ([{"signature": sig, "qids": qids, "size": len(qids)}
          for sig, qids in sig_groups.items() if len(qids) > 1]),
        key=lambda g: -g["size"],
    )

    # Edge cases worth a human glance.
    edge_cases = []
    for s in samples:
        reasons = []
        if not s["question"].strip():
            reasons.append("empty question")
        if len(s["choices"]) < 2:
            reasons.append(f"<2 choices ({len(s['choices'])})")
        if len(set(c.strip() for c in s["choices"])) != len(s["choices"]):
            reasons.append("duplicate choices")
        # Long context passages are expected; only flag genuinely extreme outliers
        # (the bulk of >5k-char items are normal reading-comprehension passages).
        if len(s["question"]) > 8000:
            reasons.append(f"very long question ({len(s['question'])} chars)")
        if reasons:
            edge_cases.append({"qid": s["qid"], "reasons": reasons})

    return {
        "total_samples": n,
        "qid_examples": [s["qid"] for s in samples[:5]],
        "qid_pattern": sorted({re.sub(r"\d", "#", s["qid"]) for s in samples}),
        "question_length_chars": _stats(q_chars),
        "question_length_words_approx": _stats(q_words),
        "num_choices": _stats(n_choices),
        "num_choices_distribution": dict(sorted(Counter(n_choices).items())),
        "long_context": {
            "count": len(long_context),
            "pct": round(100 * len(long_context) / n, 1),
        },
        "short_standalone": {
            "count": len(short_q),
            "pct": round(100 * len(short_q) / n, 1),
        },
        "categories": category_summary,
        "choices_gt_4": {
            "count": len(more_than_4),
            "pct": round(100 * len(more_than_4) / n, 1),
            "qids": [s["qid"] for s in more_than_4[:10]],
        },
        "choices_2_or_3": {
            "count": len(two_or_three),
            "qids": [s["qid"] for s in two_or_three],
        },
        "template_groups": {
            "count": len(template_groups),
            "top": template_groups[:10],
        },
        "edge_cases": edge_cases,
    }


def _stats(values: list[int]) -> dict:
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0}
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(statistics.mean(values), 1),
        "median": round(statistics.median(values), 1),
    }


def profile_submission(sub_path: Path, sample_qids: set[str]) -> dict:
    """Inspect a sample submission CSV."""
    rows = read_predictions(sub_path)
    columns = list(rows[0].keys()) if rows else []
    answers = [r.get("answer", "").strip() for r in rows]
    sub_qids = {r.get("qid", "") for r in rows}
    unique_labels = sorted(set(a for a in answers if a))

    # Does it use labels beyond A-D?
    beyond_abcd = sorted(l for l in unique_labels
                         if l not in {"A", "B", "C", "D"})

    return {
        "columns": columns,
        "row_count": len(rows),
        "unique_answer_labels": unique_labels,
        "supports_beyond_ABCD": bool(beyond_abcd),
        "labels_beyond_ABCD": beyond_abcd,
        "qids_in_submission": len(sub_qids),
        "qids_in_dataset": len(sample_qids),
        "qids_only_in_submission": sorted(sub_qids - sample_qids)[:10],
        "qids_missing_from_submission": sorted(sample_qids - sub_qids)[:10],
        "covers_full_dataset": sub_qids >= sample_qids,
    }


def render_markdown(profile: dict, submission: dict | None, input_name: str) -> str:
    p = profile
    lines = [
        "# Dataset Profile",
        "",
        f"_Auto-generated by `scripts/profile_dataset.py` from `{input_name}`._",
        "",
        "## Overview",
        "",
        f"- **Total samples:** {p['total_samples']}",
        f"- **QID pattern(s):** {', '.join('`' + s + '`' for s in p['qid_pattern'])} "
        f"(e.g. {', '.join(p['qid_examples'][:3])})",
        f"- **Question length (chars):** min {p['question_length_chars']['min']}, "
        f"median {p['question_length_chars']['median']}, "
        f"mean {p['question_length_chars']['mean']}, "
        f"max {p['question_length_chars']['max']}",
        f"- **Question length (~words):** min {p['question_length_words_approx']['min']}, "
        f"median {p['question_length_words_approx']['median']}, "
        f"max {p['question_length_words_approx']['max']}",
        f"- **Choices per question:** min {p['num_choices']['min']}, "
        f"max {p['num_choices']['max']}, mean {p['num_choices']['mean']}, "
        f"median {p['num_choices']['median']}",
        "",
        "### Distribution of choice counts",
        "",
        "| # choices | samples |",
        "|---:|---:|",
    ]
    for k, v in p["num_choices_distribution"].items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "### Context vs. standalone",
        "",
        f"- **Long-context (passage-based) questions:** {p['long_context']['count']} "
        f"({p['long_context']['pct']}%) — detected via keywords "
        f"{', '.join('`' + k + '`' for k in CONTEXT_KEYWORDS)}.",
        f"- **Short standalone questions (<{SHORT_QUESTION_CHARS} chars):** "
        f"{p['short_standalone']['count']} ({p['short_standalone']['pct']}%).",
        "",
        "## Rough category breakdown",
        "",
        "_Heuristic, single-label, priority-ordered keyword matching — indicative only._",
        "",
        "| Category | Count | % | Example qids |",
        "|---|---:|---:|---|",
    ]
    for name, info in p["categories"].items():
        ex = ", ".join(e["qid"] for e in info["examples"])
        lines.append(f"| {name} | {info['count']} | {info['pct']} | {ex} |")

    lines += ["", "### Category examples", ""]
    for name, info in p["categories"].items():
        lines.append(f"**{name}** ({info['count']}, {info['pct']}%)")
        for e in info["examples"]:
            lines.append(f"- `{e['qid']}` ({e['num_choices']} choices): {e['question']}")
        lines.append("")

    lines += [
        "## Choice-count edge buckets",
        "",
        f"- **More than 4 choices:** {p['choices_gt_4']['count']} "
        f"({p['choices_gt_4']['pct']}%). Sample qids: "
        f"{', '.join(p['choices_gt_4']['qids'])}.",
        f"- **Only 2 or 3 choices:** {p['choices_2_or_3']['count']}. "
        f"qids: {', '.join(p['choices_2_or_3']['qids'])}.",
        "",
        "## Possible template / near-duplicate groups",
        "",
        f"Found **{p['template_groups']['count']}** normalized-text groups with >1 member "
        "(cheap prefix heuristic, not embeddings).",
        "",
    ]
    if p["template_groups"]["top"]:
        lines += ["| Size | Example qids | Signature (truncated) |", "|---:|---|---|"]
        for g in p["template_groups"]["top"]:
            lines.append(
                f"| {g['size']} | {', '.join(g['qids'][:5])} | {truncate(g['signature'], 50)} |"
            )
        lines.append("")

    lines += ["## Edge cases", ""]
    if p["edge_cases"]:
        for e in p["edge_cases"]:
            lines.append(f"- `{e['qid']}`: {', '.join(e['reasons'])}")
    else:
        lines.append("_None detected._")
    lines.append("")

    if submission is not None:
        s = submission
        lines += [
            "## Sample submission",
            "",
            f"- **Columns:** {', '.join('`' + c + '`' for c in s['columns'])}",
            f"- **Rows:** {s['row_count']}",
            f"- **Unique answer labels:** {', '.join(s['unique_answer_labels']) or '(none)'}",
            f"- **Uses labels beyond A–D:** {'yes — ' + ', '.join(s['labels_beyond_ABCD']) if s['supports_beyond_ABCD'] else 'no'}",
            f"- **QIDs in submission / dataset:** {s['qids_in_submission']} / {s['qids_in_dataset']}",
            f"- **Covers full dataset:** {'yes' if s['covers_full_dataset'] else 'no'}",
        ]
        if s["qids_missing_from_submission"]:
            lines.append(
                f"- **Missing from submission (sample):** {', '.join(s['qids_missing_from_submission'])}"
            )
        lines.append("")

    # Static analytical sections (not data-derived) to guide modeling.
    lines += [
        "## Key observations",
        "",
        "- The dataset is **Vietnamese**, mixing short standalone questions with long",
        "  passage-based reading-comprehension items.",
        "- Choice counts are **not fixed at 4** — there is a large bucket of 10-choice",
        "  questions plus a few with 2, 3, 5, and 11 choices. Solvers and validators",
        "  must handle dynamic labels (A, B, C, ...).",
        "- A substantial share of questions are **calculation/STEM** items, often with",
        "  LaTeX math and numeric answer options.",
        "",
        "## Risk points for modeling",
        "",
        "- **Variable option counts** break any A–D assumption; always size labels to",
        "  the actual choice list.",
        "- **Long contexts** may exceed small prompt budgets; truncation strategy matters.",
        "- **LaTeX / math** answers require care when formatting prompts and parsing output.",
        "- **Vietnamese** content — tokenization and model language coverage matter.",
        "- **Template families** mean leakage between very similar items is unlikely to",
        "  help, but they are useful for sanity-checking solver consistency.",
        "",
        "## Implications for solver design",
        "",
        "- Keep the `BaseSolver` contract returning a single dynamic label.",
        "- Format prompts with the question + explicitly enumerated, index-aligned choices.",
        "- Preserve a robust fallback (already in `postprocess.py`).",
        "",
        "## Recommended Phase 2B strategy",
        "",
        "1. Start with a zero-shot LLM solver that emits a single label.",
        "2. Add choice-aware prompting and output parsing with the existing fallback.",
        "3. Special-case calculation questions only if accuracy data justifies it.",
        "4. Log every experiment in `experiments/leaderboard_log.csv`.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile an MCQ dataset")
    parser.add_argument("--input", required=True, help="dataset JSON/CSV")
    parser.add_argument("--sample-submission", default=None, help="optional sample submission CSV")
    parser.add_argument("--output-md", default="docs/DATASET_PROFILE.md")
    parser.add_argument("--output-json", default="output/dataset_profile.json")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    samples = load_dataset(input_path)
    profile = profile_dataset(samples)

    submission = None
    if args.sample_submission:
        sample_qids = {s["qid"] for s in samples}
        submission = profile_submission(Path(args.sample_submission), sample_qids)

    # Write JSON.
    json_path = Path(args.output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"dataset": profile}
    if submission is not None:
        payload["sample_submission"] = submission
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write Markdown.
    md_path = Path(args.output_md)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(profile, submission, input_path.name), encoding="utf-8")

    # Console summary.
    print(f"profiled {profile['total_samples']} samples from {input_path}")
    print(f"  choice counts: {profile['num_choices_distribution']}")
    print(f"  long-context : {profile['long_context']['count']} ({profile['long_context']['pct']}%)")
    print(f"  categories   : " + ", ".join(f"{k}={v['count']}" for k, v in profile["categories"].items()))
    print(f"  >4 choices   : {profile['choices_gt_4']['count']}")
    if submission is not None:
        print(f"  submission   : {submission['row_count']} rows, labels={submission['unique_answer_labels']}, "
              f"beyond A-D={submission['supports_beyond_ABCD']}, covers_full={submission['covers_full_dataset']}")
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
