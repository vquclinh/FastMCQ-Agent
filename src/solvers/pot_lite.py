"""PoT-lite: a SAFE arithmetic evaluator foundation (Phase 2L.23).

A Program-of-Thoughts-style numeric layer that NEVER executes model-generated code.
It parses an arithmetic string with Python's ``ast`` and evaluates ONLY a strict
whitelist (numbers, + - * / **, unary ±, parentheses, and the functions
``sqrt``/``log10`` plus the constant ``pi``). Any name, call, attribute, subscript,
comprehension, import, etc. is rejected. This is a foundation module — it is NOT wired
into production overrides in this phase.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass

_ALLOWED_FUNCS = {"sqrt": math.sqrt, "log10": math.log10}
_ALLOWED_CONSTS = {"pi": math.pi}
_MAX_POW = 1e6   # guard against giant exponentiation


@dataclass
class EvalResult:
    ok: bool
    value: float | None = None
    error: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "value": self.value, "error": self.error}


class _SafeEvaluator(ast.NodeVisitor):
    """Evaluate only the whitelisted AST node types; raise ValueError otherwise."""

    def visit(self, node):
        method = getattr(self, "visit_" + type(node).__name__, None)
        if method is None:
            raise ValueError(f"disallowed syntax: {type(node).__name__}")
        return method(node)

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("only numeric constants allowed")
        return float(node.value)

    def visit_BinOp(self, node):
        left, right = self.visit(node.left), self.visit(node.right)
        op = type(node.op).__name__
        if op == "Add":
            return left + right
        if op == "Sub":
            return left - right
        if op == "Mult":
            return left * right
        if op == "Div":
            if right == 0:
                raise ValueError("division by zero")
            return left / right
        if op == "Pow":
            if abs(right) > 100 or abs(left) > _MAX_POW:
                raise ValueError("exponent/base too large")
            return left ** right
        raise ValueError(f"disallowed operator: {op}")

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        op = type(node.op).__name__
        if op == "UAdd":
            return +operand
        if op == "USub":
            return -operand
        raise ValueError(f"disallowed unary op: {op}")

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValueError("only sqrt()/log10() calls allowed")
        if node.keywords or len(node.args) != 1:
            raise ValueError("function takes exactly one positional arg")
        return _ALLOWED_FUNCS[node.func.id](self.visit(node.args[0]))

    def visit_Name(self, node):
        if node.id not in _ALLOWED_CONSTS:
            raise ValueError(f"disallowed name: {node.id}")
        return _ALLOWED_CONSTS[node.id]


def safe_eval_arithmetic(expr: str) -> EvalResult:
    """Safely evaluate a whitelisted arithmetic expression string."""
    if not isinstance(expr, str) or not expr.strip():
        return EvalResult(False, error="empty expression")
    # Normalize common math notation to Python.
    e = expr.strip().replace("^", "**").replace("√", "sqrt")
    try:
        tree = ast.parse(e, mode="eval")
        value = _SafeEvaluator().visit(tree)
        return EvalResult(True, value=float(value))
    except ValueError as exc:
        return EvalResult(False, error=str(exc))
    except Exception as exc:   # syntax errors, recursion, etc.
        return EvalResult(False, error=f"{type(exc).__name__}: {exc}")


def map_to_option(value, choices, labels, *, rel_tol: float = 0.02, margin: float = 2.0):
    """Return the unique label whose numeric value matches ``value``, else None.

    Requires the nearest option to be within ``rel_tol`` AND clearly closer than the
    runner-up (>= ``margin``x). Declines on ambiguity. No qid logic.
    """
    import re
    num = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

    def _to_float(s):
        m = num.search(str(s))
        return float(m.group(0).replace(",", ".")) if m else None

    cands = sorted(((abs((_to_float(c) if _to_float(c) is not None else 1e18) - value), i)
                    for i, c in enumerate(choices) if _to_float(c) is not None))
    if not cands:
        return None
    best_dist, best_i = cands[0]
    if best_dist / max(abs(value), 1e-9) > rel_tol:
        return None
    if len(cands) > 1 and cands[1][0] < margin * best_dist:
        return None
    return labels[best_i]
