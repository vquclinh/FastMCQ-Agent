"""Calculation-first planning (Phase 2L.28B; deterministic, no API).

For calculation-route questions, decide a tool-first strategy and build a compact tool
context BEFORE any generic LLM prompt. The pilot showed generic long prompts on
calculation produce truncation, empty-evidence placeholders, and numeric mismatches; this
module pushes the deterministic solver and a structured numeric context to the front.

Nothing here calls a model or selects a final answer on its own — it classifies the
subtype, recommends a strategy, and assembles hints/option-numeric-maps/parsed numbers.
"""

from __future__ import annotations

import re

from src.solvers.formula_bank_solver import detect_formula_hints, solve_formula_bank_sample
from src.evidence.option_grounding import extract_option_features

CALC_SUBTYPES = ("arithmetic", "algebra", "probability", "geometry", "physics",
                 "finance_econ", "cs_numeric", "unknown")

# Keyword cues per subtype (Vietnamese + English). Order matters: earlier, more specific
# families win when several match.
_SUBTYPE_CUES = (
    ("probability", ("xác suất", "kỳ vọng", "phân phối", "biến ngẫu nhiên", "probability",
                     "expected value", "bernoulli", "binomial", "variance")),
    ("geometry", ("diện tích", "chu vi", "thể tích", "tam giác", "hình tròn", "bán kính",
                  "đường kính", "góc", "area", "perimeter", "volume", "radius", "triangle",
                  "circle", "hypotenuse", "pythagore")),
    ("physics", ("vận tốc", "gia tốc", "lực", "công suất", "điện trở", "dòng điện", "hiệu điện thế",
                 "nhiệt", "động năng", "velocity", "acceleration", "force", "voltage", "resistance",
                 "current", "kinetic", "newton", "joule", "ohm")),
    ("finance_econ", ("lãi suất", "lợi nhuận", "doanh thu", "chi phí", "cung", "cầu", "gdp",
                      "độc quyền", "cournot", "thị trường", "interest", "profit", "revenue",
                      "cost", "supply", "demand", "monopoly", "elasticity", "npv")),
    ("cs_numeric", ("nhị phân", "thập lục", "hex", "binary", "subnet", "địa chỉ ip", "bit",
                    "byte", "độ phức tạp", "big-o", "bộ nhớ", "throughput", "băng thông",
                    "bandwidth", "cache", "page", "trang nhớ")),
    ("algebra", ("phương trình", "nghiệm", "đa thức", "bất phương trình", "hệ phương trình",
                 "equation", "solve for", "polynomial", "quadratic", "ẩn số")),
    ("arithmetic", ("phần trăm", "trung bình", "tỉ lệ", "tỷ lệ", "tổng", "hiệu", "tích", "thương",
                    "percent", "average", "ratio", "proportion", "sum of", "đơn vị", "quy đổi",
                    "chuyển đổi", "convert")),
)

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def detect_calculation_subtype(sample) -> str:
    q = str(sample.get("question", "") or "").lower()
    choices = " ".join(str(c) for c in (sample.get("choices", []) or [])).lower()
    blob = q + " " + choices
    for subtype, cues in _SUBTYPE_CUES:
        if any(cue in blob for cue in cues):
            return subtype
    return "unknown"


def _parsed_numbers(question):
    out = []
    for m in _NUM_RE.findall(str(question or "")):
        try:
            out.append(float(m.replace(",", ".")))
        except ValueError:
            continue
    return out[:12]


def _option_numeric_map(choices):
    return {f.label: sorted(f.numeric) for f in extract_option_features(choices) if f.numeric}


def recommend_calculation_strategy(sample) -> dict:
    """Return {strategy, subtype, has_tool_answer, tool_answer, reason}.

    - tool_only   : a deterministic solver maps to a UNIQUE option (safe override).
    - tool_then_llm: subtype is known but the solver declined (give the LLM tool context).
    - compact_llm : subtype unknown (still use a compact calc agent, never a long prompt).
    """
    subtype = detect_calculation_subtype(sample)
    res = solve_formula_bank_sample(sample)
    if res is not None:
        return {"strategy": "tool_only", "subtype": subtype, "has_tool_answer": True,
                "tool_answer": res.selected_answer,
                "reason": f"deterministic solver {getattr(res, 'rule_id', '') or 'formula_bank'} "
                          "maps to a unique option"}
    if subtype != "unknown":
        return {"strategy": "tool_then_llm", "subtype": subtype, "has_tool_answer": False,
                "tool_answer": None,
                "reason": f"subtype {subtype} recognized but solver declined → LLM with tool context"}
    return {"strategy": "compact_llm", "subtype": subtype, "has_tool_answer": False,
            "tool_answer": None, "reason": "calculation subtype unknown → compact calc agent"}


def build_calculation_tool_context(sample) -> dict:
    """Compact, model-free context for a calculation agent (hints + numbers + decline reason)."""
    choices = sample.get("choices", []) or []
    hints = [h["hint"] for h in detect_formula_hints(sample)]
    strat = recommend_calculation_strategy(sample)
    return {
        "subtype": strat["subtype"],
        "strategy": strat["strategy"],
        "formula_hints": hints[:4],
        "option_numeric_map": _option_numeric_map(choices),
        "parsed_numbers": _parsed_numbers(sample.get("question", "")),
        "tool_answer": strat["tool_answer"],
        "decline_reason": None if strat["has_tool_answer"] else strat["reason"],
    }


def format_tool_context_for_prompt(ctx) -> str:
    """Render the tool context as a short prompt block (deterministic, compact)."""
    lines = [f"[BỐI CẢNH TÍNH TOÁN] subtype={ctx.get('subtype')}"]
    if ctx.get("parsed_numbers"):
        lines.append("Số đã trích: " + ", ".join(_fmt(n) for n in ctx["parsed_numbers"]))
    if ctx.get("option_numeric_map"):
        lines.append("Giá trị mỗi phương án: " + "; ".join(
            f"{lbl}={', '.join(_fmt(v) for v in vals)}" for lbl, vals in ctx["option_numeric_map"].items()))
    if ctx.get("formula_hints"):
        lines.append("Gợi ý công thức: " + " | ".join(ctx["formula_hints"]))
    if ctx.get("tool_answer"):
        lines.append(f"Ứng viên công cụ (tham khảo): {ctx['tool_answer']}")
    elif ctx.get("decline_reason"):
        lines.append("Công cụ chưa kết luận: " + ctx["decline_reason"])
    return "\n".join(lines)


def _fmt(n):
    return str(int(n)) if float(n).is_integer() else f"{n:g}"
