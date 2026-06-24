"""Programmatic solver layer (Phase 2L.35A) — V13 shadow stack.

For numeric/formula MCQs the model should emit a STRUCTURED calculation spec (operation +
operands), never a final label. This module safely evaluates the spec with a whitelisted set
of operations, computes the numeric result, and maps it to the original option label. It makes
no API calls and executes no arbitrary model code.

Whitelisted domains: arithmetic, percentage/ratio, probability basics, distance/geometry
basics, explicit-formula economics (Cournot/monopoly/elasticity/marginal), and base/bitwise
(binary/hex/subnet) operations. Anything else, or an ambiguous/no option match, is rejected.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass, field

from src.utils.labels import labels_for
from src.evidence.option_grounding import map_claim_to_option

_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

# Whitelisted arithmetic AST node handlers for safe expression evaluation.
_BIN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
            ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
            ast.FloorDiv: operator.floordiv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max,
          "log": math.log, "exp": math.exp, "pow": pow}

_ALLOWED_OPERATIONS = {
    "arithmetic", "percentage", "ratio", "probability", "distance", "geometry",
    "cournot", "monopoly", "elasticity", "marginal", "binary", "hex", "subnet", "expression",
}

_ECON_HINTS = ("cournot", "monopoly", "elasticity", "marginal", "demand", "cost", "revenue",
               "giá", "cầu", "chi phí", "doanh thu", "độc quyền")
_NET_HINTS = ("binary", "hex", "subnet", "netmask", "ip", "nhị phân", "thập lục", "mạng con")
_GEO_HINTS = ("distance", "area", "perimeter", "diện tích", "chu vi", "khoảng cách", "tam giác")


@dataclass
class CalculationSpec:
    operation: str
    expression: str | None = None
    operands: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    parse_status: str = "ok"


@dataclass
class ProgrammaticMatchResult:
    ok: bool
    value: float | None
    mapped_label: str | None
    failure_reason: str = ""
    detail: dict = field(default_factory=dict)


def extract_numeric_values(text) -> list:
    if text is None:
        return []
    return [float(m) for m in _NUM.findall(str(text))]


def classify_programmatic_domain(sample: dict) -> str:
    q = (sample.get("question") or "").lower()
    if any(h in q for h in _NET_HINTS):
        return "binary"
    if any(h in q for h in _ECON_HINTS):
        return "economics"
    if any(h in q for h in _GEO_HINTS):
        return "geometry"
    if extract_numeric_values(q):
        return "arithmetic"
    return "none"


def build_programmatic_prompt(sample: dict, domain: str) -> str:
    choices = sample.get("choices") or []
    labels = labels_for(len(choices))
    opts = "\n".join(f"{lab}. {txt}" for lab, txt in zip(labels, choices))
    return (
        "You are a calculation engine. Do NOT pick an option letter. Instead return a SINGLE "
        "JSON object describing the computation. Required keys: "
        '"operation" (one of: arithmetic, percentage, ratio, probability, distance, geometry, '
        'cournot, monopoly, elasticity, marginal, binary, hex, subnet), '
        '"expression" (a pure arithmetic expression using + - * / ** % and sqrt/abs/log, '
        'NO variables, NO function defs, NO names), '
        '"operands" (object of the numbers used), "result_hint" (the numeric result), '
        '"evidence" (one line). '
        f"Domain hint: {domain}.\n\nQuestion:\n{sample.get('question','')}\n\n"
        f"Options (for context only — do not select one):\n{opts}\n\nReturn JSON now."
    )


def parse_calculation_spec(model_json: dict) -> CalculationSpec:
    if not isinstance(model_json, dict):
        return CalculationSpec(operation="none", parse_status="parse_error")
    op = str(model_json.get("operation") or "").strip().lower()
    expr = model_json.get("expression")
    operands = model_json.get("operands") if isinstance(model_json.get("operands"), dict) else {}
    status = "ok" if op in _ALLOWED_OPERATIONS or expr else "unsupported_operation"
    return CalculationSpec(operation=op or "expression", expression=expr,
                           operands=operands, raw=model_json, parse_status=status)


def _safe_eval(node):
    """Evaluate a whitelisted arithmetic AST; raise ValueError on anything unsafe."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("non-numeric constant")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise ValueError("kwargs not allowed")
        return _FUNCS[node.func.id](*[_safe_eval(a) for a in node.args])
    raise ValueError(f"disallowed expression node: {type(node).__name__}")


def safe_execute_calculation(spec: CalculationSpec) -> ProgrammaticMatchResult:
    if spec.parse_status != "ok":
        return ProgrammaticMatchResult(False, None, None, spec.parse_status)
    expr = spec.expression
    if not expr or not isinstance(expr, str):
        # Fall back to a result hint number if present (operands-only specs).
        nums = extract_numeric_values(str(spec.raw.get("result_hint", "")))
        if len(nums) == 1:
            return ProgrammaticMatchResult(True, nums[0], None, "", {"source": "result_hint"})
        return ProgrammaticMatchResult(False, None, None, "no_expression")
    # Reject obviously unsafe content fast.
    if any(tok in expr for tok in ("__", "import", "lambda", "=", ";", "exec", "eval", "open")):
        return ProgrammaticMatchResult(False, None, None, "unsafe_expression")
    try:
        tree = ast.parse(expr, mode="eval")
        value = _safe_eval(tree)
    except Exception as exc:
        return ProgrammaticMatchResult(False, None, None, f"unsafe_expression:{type(exc).__name__}")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ProgrammaticMatchResult(False, None, None, "non_numeric_result")
    return ProgrammaticMatchResult(True, float(value), None, "", {"expression": expr})


def match_result_to_options(result, sample: dict) -> ProgrammaticMatchResult:
    """Map a numeric result to a unique option label, else reject (ambiguous/no match)."""
    if isinstance(result, ProgrammaticMatchResult):
        if not result.ok or result.value is None:
            return result
        value = result.value
        base = result
    else:
        value = result
        base = ProgrammaticMatchResult(True, value, None, "")
    choices = sample.get("choices") or []
    mapped = map_claim_to_option(value, choices)
    if mapped is None:
        return ProgrammaticMatchResult(False, value, None, "ambiguous_or_no_option_match",
                                       base.detail)
    return ProgrammaticMatchResult(True, value, mapped, "", base.detail)


def validate_programmatic_candidate(candidate: dict):
    """(valid, reason) for a stored programmatic candidate record."""
    if (candidate.get("parse_status") or "") != "ok":
        return False, f"parse_status={candidate.get('parse_status')}"
    if not candidate.get("valid", False):
        return False, candidate.get("rejection_reason") or "not_valid"
    if not candidate.get("proposed_label"):
        return False, "no_label"
    return True, "ok"
