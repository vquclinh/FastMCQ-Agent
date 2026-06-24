"""Deterministic calculation helper (PAL-lite) — generic formula-family engine.

Closed-form matchers for common math/science/economics MCQ families. Designed to
**generalize to unseen (private-test) questions**: every matcher keys off generic
wording + numbers + formulas, never off a question id or a memorized answer. There
is **no qid logic, no public-test answer table, no `eval`/`exec`/code execution** —
only regex, numeric parsing, and fixed arithmetic.

Policy (correctness-first, conservative): a family fires only when its pattern is
unambiguous and the computed result maps to exactly one available label; on any
ambiguity it returns ``matched=False`` (no override) and the LLM path runs.
**Prefer no answer over a risky answer.**
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field


@dataclass
class CalculationResult:
    answer: str | None          # a label (e.g. "C"), never option text
    confidence: float
    method: str                 # which family matched (or "none")
    rationale: str              # short, human-readable (no hidden CoT)
    matched: bool
    safe_to_override: bool
    formula_family: str = ""     # category, e.g. "related_rates", "economics"
    extracted_values: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _no_match() -> CalculationResult:
    return CalculationResult(answer=None, confidence=0.0, method="none", rationale="",
                             matched=False, safe_to_override=False,
                             formula_family="", extracted_values={})


_CONF_EXACT = 0.99      # exact symbolic / exact numeric match
_CONF_NEAREST = 0.96    # nearest-numeric match with a clear margin
_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


# --- generic numeric / expression utilities ----------------------------------

def _to_float(token) -> float | None:
    """Parse a number, tolerating Vietnamese comma decimals ('2,5'->2.5) and signs."""
    if token is None:
        return None
    m = _NUM_RE.search(str(token))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def _all_numbers(text: str) -> list[float]:
    out = []
    for m in _NUM_RE.finditer(text or ""):
        v = _to_float(m.group(0))
        if v is not None:
            out.append(v)
    return out


def _choice_values(choices) -> list[float | None]:
    return [_to_float(c) for c in choices]


def _has_pi(choices) -> bool:
    return any(("π" in str(c)) or ("\\pi" in str(c)) or ("pi" in str(c).lower())
               for c in choices)


def _nearest_label(target: float, choices, labels, *, rel_tol: float = 0.06,
                   margin: float = 2.0):
    """Label of the choice nearest ``target`` if it is a clear and close winner.

    clear = nearest is >= ``margin``x closer than second-nearest; close = within
    ``rel_tol`` relative error. Else None (refuse borderline matches).
    """
    vals = _choice_values(choices)
    cand = sorted((abs(v - target), i) for i, v in enumerate(vals) if v is not None)
    if not cand:
        return None
    best_dist, best_i = cand[0]
    if best_dist / max(abs(target), 1e-9) > rel_tol:
        return None
    if len(cand) > 1 and cand[1][0] < margin * best_dist:
        return None
    return labels[best_i]


def _exact_label(target: float, choices, labels, *, tol: float = 1e-6):
    """Label of the unique choice numerically equal to ``target``, else None."""
    vals = _choice_values(choices)
    hits = [labels[i] for i, v in enumerate(vals) if v is not None and abs(v - target) <= tol]
    return hits[0] if len(hits) == 1 else None


def _norm(s: str) -> str:
    """Normalise LaTeX/whitespace for symbolic choice comparison."""
    s = str(s).lower()
    for ch in ("$", "\\left", "\\right", "{", "}", " ", "\\,", "\\cdot", "\\times",
               "\\text", "\\"):
        s = s.replace(ch, "")
    s = s.replace("frac", "frac")
    return s


def _first(pattern: str, text: str):
    m = re.search(pattern, text, re.IGNORECASE)
    return _to_float(m.group(1)) if m else None


def _first_int(pattern: str, text: str):
    """First capture group parsed as a plain non-negative integer, else None."""
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (ValueError, TypeError):
        return None


# --- formula families (each returns CalculationResult or _no_match()) ---------

def try_exponential(q: str, choices, labels) -> CalculationResult:
    """dX/dt = -kX -> X0 e^{-kt} (decay); dX/dt = kX -> X0 e^{kt} (growth)."""
    qn = q.replace(" ", "")
    is_ode = ("frac{d" in qn) or re.search(r"d[a-zA-Z]/dt", qn)
    if not is_ode:
        return _no_match()
    decay = bool(re.search(r"=-k[a-zA-Z]\b", qn) or "=-k" in qn)
    growth = bool(re.search(r"=\+?k[a-zA-Z]\b", qn) or re.search(r"=k[a-zA-Z]\b", qn)) and not decay
    if not (decay or growth):
        return _no_match()
    want = "e^-kt" if decay else "e^kt"
    avoid = "e^kt" if decay else "e^-kt"
    hits = []
    for i, c in enumerate(choices):
        cn = _norm(c).replace("e^{-kt", "e^-kt").replace("e^{kt", "e^kt")
        if want in cn and avoid not in cn:
            hits.append(labels[i])
    if len(hits) == 1:
        return CalculationResult(hits[0], _CONF_EXACT, "exponential_decay" if decay else "exponential_growth",
                                 ("dX/dt=-kX => X0·e^{-kt}" if decay else "dX/dt=kX => X0·e^{kt}"),
                                 True, True, "exponential_ode", {"mode": "decay" if decay else "growth"})
    return _no_match()


def try_hess_law(q: str, choices, labels) -> CalculationResult:
    """ΔH(total) = sum of the given sequential ΔH steps (2 or 3 given)."""
    if "hess" not in q.lower() and "delta h" not in q.lower().replace("\\", ""):
        return _no_match()
    steps = [_to_float(m.group(1)) for m in
             re.finditer(r"\\?Delta\s*H_?\d*\s*=\s*([-+]?\d+(?:[.,]\d+)?)", q, re.IGNORECASE)]
    steps = [s for s in steps if s is not None]
    if len(steps) < 2:
        return _no_match()
    total = sum(steps)
    label = _exact_label(total, choices, labels)
    if label is not None:
        return CalculationResult(label, _CONF_EXACT, "hess_law", f"ΣΔH={total:g}",
                                 True, True, "thermochemistry", {"steps": steps, "total": total})
    return _no_match()


def try_cylinder_rate(q: str, choices, labels) -> CalculationResult:
    """Cylinder fill: dh/dt = (dV/dt)/(π r²)."""
    low = q.lower()
    if "trụ" not in low or "bán kính" not in low:
        return _no_match()
    if not any(w in low for w in ("tốc độ", "thay đổi", "tăng")) or \
       not any(w in low for w in ("cao", "mực nước", "chiều cao")):
        return _no_match()
    dvdt = _first(r"([-+]?\d+(?:[.,]\d+)?)\s*(?:cm\^?3|cm³|centimet khối|cm khối)", q)
    r = _first(r"bán kính[^0-9]{0,20}([-+]?\d+(?:[.,]\d+)?)", q)
    if not dvdt or not r:
        return _no_match()
    dhdt = dvdt / (math.pi * r * r)
    label = _nearest_label(dhdt, choices, labels)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "cylinder_rate",
                                 f"dh/dt=(dV/dt)/(πr²)={dhdt:.4g}", True, True,
                                 "related_rates", {"dVdt": dvdt, "r": r, "dhdt": dhdt})
    return _no_match()


def try_sphere_rate(q: str, choices, labels) -> CalculationResult:
    """Sphere inflation: dV/dt = 4π r² dr/dt (choices often as multiples of π)."""
    low = q.lower()
    if "cầu" not in low or "bán kính" not in low:
        return _no_match()
    if "4" not in q or ("r^3" not in q.replace(" ", "") and "r³" not in q):
        return _no_match()  # require the V=4/3 π r^3 relation to be present
    # dr/dt = the rate after "tốc độ" (skip "tốc độ không đổi"); r = the radius in
    # the "khi (bán kính) ... N cm" clause. Extract them from distinct clauses.
    # dr/dt = first number close after "tốc độ" (skips "tốc độ không đổi"); the
    # unit may be LaTeX-wrapped ("0.1 \, \text{cm/s}"), so do not require it inline.
    drdt = _first(r"tốc độ\D{0,12}?([-+]?\d+(?:[.,]\d+)?)", q)
    r = _first(r"khi[^0-9]{0,30}?bán kính[^0-9]{0,12}?([-+]?\d+(?:[.,]\d+)?)", q) \
        or _first(r"bán kính là[^0-9]{0,8}?([-+]?\d+(?:[.,]\d+)?)", q)
    if not drdt or not r or drdt == r:
        return _no_match()
    coef = 4.0 * r * r * drdt           # dV/dt = (coef)·π
    if _has_pi(choices):
        # Choices expressed as N·π — match the π coefficient.
        label = _nearest_label(coef, choices, labels)
        rationale = f"dV/dt=4πr²·dr/dt={coef:.4g}π"
    else:
        label = _nearest_label(coef * math.pi, choices, labels)
        rationale = f"dV/dt=4πr²·dr/dt={coef*math.pi:.4g}"
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "sphere_rate", rationale,
                                 True, True, "related_rates", {"drdt": drdt, "r": r, "coef_pi": coef})
    return _no_match()


def try_gdp_inflation(q: str, choices, labels) -> CalculationResult:
    """GDP deflator + inflation: deflator = nominal/real·100; inflation vs prev."""
    low = q.lower()
    if "gdp" not in low or "lạm phát" not in low:
        return _no_match()
    nominal = _first(r"danh nghĩa[^0-9]{0,40}?([-+]?\d+(?:[.,]\d+)?)", q)
    real = _first(r"thực tế[^0-9]{0,40}?([-+]?\d+(?:[.,]\d+)?)", q)
    prev = _first(r"năm trước[^0-9]{0,30}?([-+]?\d+(?:[.,]\d+)?)", q)
    if not nominal or not real or not prev:
        return _no_match()
    deflator = nominal / real * 100.0
    inflation = (deflator - prev) / prev * 100.0
    label = _nearest_label(inflation, choices, labels, rel_tol=0.02)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "gdp_inflation",
                                 f"deflator={deflator:g}; inflation={inflation:g}%",
                                 True, True, "economics",
                                 {"nominal": nominal, "real": real, "prev": prev, "inflation": inflation})
    return _no_match()


def try_price_elasticity(q: str, choices, labels) -> CalculationResult:
    """Midpoint (arc) price elasticity from two (P,Q) points; signed or |E|."""
    low = q.lower()
    if "co giãn" not in low or "cầu" not in low:
        return _no_match()
    num = r"([-+]?\d+(?:[.,]\d+)?)"

    def _collect(patterns):
        found = []
        for pat in patterns:
            for m in re.finditer(pat, q, re.IGNORECASE):
                v = _to_float(m.group(1))
                if v is not None:
                    found.append((m.start(1), v))
        found.sort()
        seen, out = set(), []
        for _pos, v in found:
            if v not in seen:
                seen.add(v); out.append(v)
        return out

    prices = _collect([num + r"\s*(?:đô la|\$|usd)", r"(?:mức\s*)?giá\s*(?:là\s*)?" + num])
    qtys = _collect([num + r"\s*đơn vị", r"(?:lượng\s*cầu|cầu)\s*(?:là\s*)?" + num])
    if len(prices) != 2 or len(qtys) != 2:
        return _no_match()
    (p1, p2), (q1, q2) = prices, qtys
    dp = (p2 - p1) / ((p1 + p2) / 2)
    dq = (q2 - q1) / ((q1 + q2) / 2)
    if dp == 0:
        return _no_match()
    e_signed = dq / dp
    hit_labels, chosen = set(), None
    for target in (e_signed, abs(e_signed)):
        lbl = _nearest_label(target, choices, labels, rel_tol=0.06, margin=2.0)
        if lbl is not None:
            hit_labels.add(lbl); chosen = lbl
    if len(hit_labels) == 1 and chosen is not None:
        return CalculationResult(chosen, _CONF_NEAREST, "price_elasticity_midpoint",
                                 f"E(midpoint)={e_signed:.3g}", True, True, "economics",
                                 {"prices": prices, "qtys": qtys, "E": e_signed})
    return _no_match()


def try_expected_distinct(q: str, choices, labels) -> CalculationResult:
    """E[# distinct in n draws over {1..k}] = k(1-(1-1/k)^n)."""
    low = q.lower()
    if not (("khác nhau" in low or "phân biệt" in low) and ("kỳ vọng" in low or "expected" in low)):
        return _no_match()
    forms = ("k(1-(1-1/k)^", "k(1-(1-frac1k)^")
    hits = [labels[i] for i, c in enumerate(choices)
            if any(t in _norm(c) for t in forms)]
    if len(hits) == 1:
        return CalculationResult(hits[0], _CONF_EXACT, "expected_distinct",
                                 "E[Y]=k(1-(1-1/k)^n)", True, True, "probability", {})
    return _no_match()


def try_resistor(q: str, choices, labels) -> CalculationResult:
    """Resistor cut into two equal halves, then parallel: R/4 => I'=4I."""
    low = q.lower()
    if "điện trở" not in low:
        return _no_match()
    if not (("hai phần bằng nhau" in low or "hai phần" in low) and "song song" in low):
        return _no_match()
    hits = [labels[i] for i, c in enumerate(choices) if "=4i" in _norm(c)]
    if len(hits) == 1:
        return CalculationResult(hits[0], _CONF_EXACT, "resistor_cut_parallel",
                                 "halves R/2 ∥ R/2 = R/4 => I'=4I", True, True,
                                 "circuits", {})
    return _no_match()


# --- generic families added in Phase 2L.8 -------------------------------------

def try_kepler(q: str, choices, labels) -> CalculationResult:
    """Kepler III / power law: T ∝ r^(3/2). If radius scales by k, T scales by k^1.5.

    Two shapes: (a) old period T given -> T_new = T·k^(3/2); (b) only the factor is
    asked ("gấp bao nhiêu lần") -> ratio = k^(3/2).
    """
    low = q.lower()
    if "kepler" not in low and not (("chu kỳ" in low or "chu kì" in low)
                                    and ("quỹ đạo" in low or "hành tinh" in low or "vệ tinh" in low)):
        return _no_match()
    k = (_first(r"gấp\s*([-+]?\d+(?:[.,]\d+)?)\s*lần", q)
         or _first(r"bán kính[^0-9]{0,40}?([-+]?\d+(?:[.,]\d+)?)\s*lần", q))
    if k is None or k <= 0:
        return _no_match()
    t_old = _first(r"chu k[ỳì][^0-9]{0,30}?([-+]?\d+(?:[.,]\d+)?)\s*(?:năm|ngày|tháng|giờ|year|day)", q)
    ratio = k ** 1.5
    if t_old is not None:
        target, rationale = t_old * ratio, f"T'=T·k^(3/2)={t_old * ratio:.4g}"
        extracted = {"T_old": t_old, "k": k, "T_new": t_old * ratio}
    else:
        target, rationale = ratio, f"ratio=k^(3/2)={ratio:.4g}"
        extracted = {"k": k, "ratio": ratio}
    label = _nearest_label(target, choices, labels)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "kepler_third_law", rationale,
                                 True, True, "astronomy", extracted)
    return _no_match()


def _relativistic_beta(q: str):
    """Extract β = v/c from common relativity phrasings, or None."""
    m = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*c(?![a-zA-Z])", q)            # "0,6c"
    if m:
        return _to_float(m.group(1))
    m = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*%\s*(?:tốc độ|vận tốc)\s*ánh sáng", q, re.IGNORECASE)
    if m:
        return _to_float(m.group(1)) / 100.0
    m = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*lần\s*(?:tốc độ|vận tốc)\s*ánh sáng", q, re.IGNORECASE)
    if m:
        return _to_float(m.group(1))
    return None


def _asks_gamma(low: str) -> bool:
    """True only when the *asked quantity* is the Lorentz factor γ itself."""
    return any(w in low for w in ("hệ số lorentz", "lorentz factor", "hệ số giãn nở thời gian",
                                  "hệ số giãn nở", "hệ số tương đối tính", "thừa số lorentz"))


def try_relativistic_gamma(q: str, choices, labels) -> CalculationResult:
    """Lorentz factor γ = 1/√(1−β²). Fires ONLY when γ itself is the asked quantity.

    (Phase 2L.14B: previously over-matched generic relativity wording and answered γ
    for momentum/energy questions; now requires an explicit "Lorentz factor" ask.)
    """
    low = q.lower()
    # Must explicitly ask for γ, and must NOT be asking for a different quantity
    # (momentum/energy/length) that merely mentions relativity.
    if not _asks_gamma(low):
        return _no_match()
    if any(w in low for w in ("động lượng", "năng lượng", "động năng")):
        return _no_match()
    beta = None
    beta = _relativistic_beta(q)
    if beta is None or not (0.0 < beta < 1.0):
        return _no_match()
    gamma = 1.0 / math.sqrt(1.0 - beta * beta)
    label = _nearest_label(gamma, choices, labels, rel_tol=0.03)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "relativistic_gamma",
                                 f"γ=1/√(1−β²)={gamma:.4g} (β={beta:g})", True, True,
                                 "physics", {"beta": beta, "gamma": gamma})
    return _no_match()


def try_money_multiplier(q: str, choices, labels) -> CalculationResult:
    """Simple money multiplier = 1 / reserve_ratio."""
    low = q.lower()
    if not any(w in low for w in ("dự trữ bắt buộc", "tỷ lệ dự trữ", "reserve ratio",
                                  "số nhân tiền", "money multiplier")):
        return _no_match()
    rr = _first(r"(?:dự trữ bắt buộc|tỷ lệ dự trữ|reserve ratio)[^0-9%]{0,30}?"
                r"([-+]?\d+(?:[.,]\d+)?)\s*%", q)
    ratio = rr / 100.0 if rr is not None else None
    if ratio is None:
        rr = _first(r"(?:dự trữ bắt buộc|tỷ lệ dự trữ)[^0-9]{0,30}?(0?[.,]\d+)", q)
        ratio = rr if rr is not None else None
    if ratio is None or not (0.0 < ratio <= 1.0):
        return _no_match()
    mult = 1.0 / ratio
    label = _nearest_label(mult, choices, labels, rel_tol=0.03)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "money_multiplier",
                                 f"m=1/rr={mult:.4g}", True, True, "economics",
                                 {"reserve_ratio": ratio, "multiplier": mult})
    return _no_match()


def try_t_statistic(q: str, choices, labels) -> CalculationResult:
    """One-sample t/z statistic: t = (x̄ − μ₀) / (s / √n)."""
    low = q.lower()
    if not any(w in low for w in ("kiểm định", "thống kê t", "t-statistic", "giá trị t",
                                  "thống kê z", "z-statistic", "giá trị z")):
        return _no_match()
    xbar = _first(r"trung bình mẫu[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
    mu0 = (_first(r"giả thuyết[^0-9]{0,40}?([-+]?\d+(?:[.,]\d+)?)", q)
           or _first(r"trung bình[^0-9]{0,8}?(?:tổng thể|lý thuyết|kỳ vọng)[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
           or _first(r"[μµ]_?0?\s*=\s*([-+]?\d+(?:[.,]\d+)?)", q))
    s = _first(r"độ lệch chuẩn[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
    n = (_first(r"(?:cỡ mẫu|kích thước mẫu)[^0-9]{0,12}?([-+]?\d+(?:[.,]\d+)?)", q)
         or _first(r"\bn\s*=\s*([-+]?\d+(?:[.,]\d+)?)", q))
    if None in (xbar, mu0, s, n) or s == 0 or n <= 0:
        return _no_match()
    t = (xbar - mu0) / (s / math.sqrt(n))
    label = _nearest_label(t, choices, labels, rel_tol=0.05)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "t_statistic",
                                 f"t=(x̄−μ₀)/(s/√n)={t:.4g}", True, True, "statistics",
                                 {"xbar": xbar, "mu0": mu0, "s": s, "n": n, "t": t})
    return _no_match()


def try_acid_base_volume(q: str, choices, labels) -> CalculationResult:
    """1:1 strong acid/base neutralization volume: V_b = (M_a·V_a)/M_b (same unit)."""
    low = q.lower()
    is_ab = ("hcl" in low and "naoh" in low) or \
            ("trung hòa" in low and any(w in low for w in ("axit", "axít", "bazơ", "bazo", "kiềm")))
    if not is_ab or "trung hòa" not in low:
        return _no_match()
    # Acid (M, V) — accept either "V mL ... HCl ... M" or "HCl ... M ... V mL".
    acid = re.search(r"(\d+(?:[.,]\d+)?)\s*ml[^?.]{0,30}?hcl[^?.]{0,30}?(\d+(?:[.,]\d+)?)\s*m\b", low)
    if acid:
        v_a, m_a = _to_float(acid.group(1)), _to_float(acid.group(2))
    else:
        acid = re.search(r"hcl[^?.]{0,30}?(\d+(?:[.,]\d+)?)\s*m\b[^?.]{0,30}?(\d+(?:[.,]\d+)?)\s*ml", low)
        if not acid:
            return _no_match()
        m_a, v_a = _to_float(acid.group(1)), _to_float(acid.group(2))
    m_b = _first(r"naoh[^?.]{0,30}?(\d+(?:[.,]\d+)?)\s*m\b", low)
    if None in (v_a, m_a, m_b) or not m_b:
        return _no_match()
    v_b = (m_a * v_a) / m_b
    label = _nearest_label(v_b, choices, labels, rel_tol=0.03)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "acid_base_neutralization",
                                 f"V_b=(M_a·V_a)/M_b={v_b:.4g} mL", True, True, "chemistry",
                                 {"M_acid": m_a, "V_acid": v_a, "M_base": m_b, "V_base": v_b})
    return _no_match()


def try_supply_demand(q: str, choices, labels) -> CalculationResult:
    """Linear Qd/Qs at a controlled price -> shortage (Qd−Qs) or surplus (Qs−Qd)."""
    low = q.lower()
    if not any(w in low for w in ("thiếu hụt", "dư thừa", "dư cung", "thặng dư", "shortage", "surplus")):
        return _no_match()
    eq = r"=\s*([-+]?\d+(?:[.,]\d+)?)\s*([-+])\s*(\d+(?:[.,]\d+)?)\s*p"
    qd = re.search(r"q[_]?d\s*" + eq, low) or re.search(r"(?:lượng cầu|cầu)[^=]{0,12}?" + eq, low)
    qs = re.search(r"q[_]?s\s*" + eq, low) or re.search(r"(?:lượng cung|cung)[^=]{0,12}?" + eq, low)
    p0 = (_first(r"giá (?:trần|sàn)[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
          or _first(r"(?:quy định|kiểm soát|ấn định)[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q))
    if not qd or not qs or p0 is None:
        return _no_match()

    def _val(m):
        a, sign, b = _to_float(m.group(1)), m.group(2), _to_float(m.group(3))
        return a + (b if sign == "+" else -b) * p0

    q_d, q_s = _val(qd), _val(qs)
    wants_shortage = any(w in low for w in ("thiếu hụt", "shortage"))
    diff = (q_d - q_s) if wants_shortage else (q_s - q_d)
    if diff <= 0:
        return _no_match()  # requested condition not actually present -> defer
    label = _nearest_label(diff, choices, labels, rel_tol=0.02)
    if label is not None:
        kind = "shortage" if wants_shortage else "surplus"
        return CalculationResult(label, _CONF_NEAREST, "supply_demand_gap",
                                 f"{kind}={diff:.4g} at P={p0:g}", True, True, "economics",
                                 {"Qd": q_d, "Qs": q_s, "P": p0, kind: diff})
    return _no_match()


def try_cobb_douglas_isoquant(q: str, choices, labels) -> CalculationResult:
    """Isoquant: pick the (K,L) choice that yields the target output for Q=A√(KL)."""
    low = q.lower()
    qn = q.replace(" ", "")
    is_sqrt = bool(re.search(r"=\s*(\d+(?:[.,]\d+)?)?\\?sqrt\{?kl", qn, re.IGNORECASE)) or \
              ("√" in q and "kl" in low)
    if not is_sqrt or not any(w in low for w in ("đẳng lượng", "isoquant", "sản lượng", "sản xuất")):
        return _no_match()
    a = _first(r"(\d+(?:[.,]\d+)?)\s*\\?sqrt", qn) or _first(r"(\d+(?:[.,]\d+)?)\s*√", q) or 1.0
    target = (_first(r"sản lượng[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
              or _first(r"q\s*=\s*([-+]?\d+(?:[.,]\d+)?)\D", low))
    if target is None:
        return _no_match()
    hits = []
    for i, c in enumerate(choices):
        pair = re.search(r"k\s*=\s*(\d+(?:[.,]\d+)?)\D{0,10}?l\s*=\s*(\d+(?:[.,]\d+)?)", str(c), re.IGNORECASE) \
            or re.search(r"\(\s*(\d+(?:[.,]\d+)?)\s*[,;]\s*(\d+(?:[.,]\d+)?)\s*\)", str(c))
        if not pair:
            continue
        kk, ll = _to_float(pair.group(1)), _to_float(pair.group(2))
        if kk is None or ll is None or kk < 0 or ll < 0:
            continue
        q_pred = a * math.sqrt(kk * ll)
        if abs(q_pred - target) <= 1e-6 + 1e-3 * abs(target):
            hits.append(labels[i])
    if len(hits) == 1:
        return CalculationResult(hits[0], _CONF_EXACT, "cobb_douglas_isoquant",
                                 f"Q={a:g}√(KL)={target:g}", True, True, "economics",
                                 {"A": a, "target_Q": target})
    return _no_match()


def try_modular_arithmetic(q: str, choices, labels) -> CalculationResult:
    """Modular results computed with integer arithmetic only (no eval/exec).

    Handles ``base^exp mod n`` via ``pow(base, exp, n)`` and simple ``a mod n``.
    """
    low = q.lower()
    if not any(w in low for w in ("mod", "chia", "đồng dư", "số dư", "dư")):
        return _no_match()
    n = _first_int(r"(?:mod(?:ulo)?|chia[^?.\n]{0,15}?cho)\s*(\d+)", q)
    if n is None or n <= 0:
        return _no_match()
    pe = re.search(r"(\d+)\s*(?:\^|mũ)\s*\{?\s*(\d+)", q)
    if pe:
        base, exp = int(pe.group(1)), int(pe.group(2))
        result = pow(base, exp, n)
        rationale = f"{base}^{exp} mod {n} = {result}"
    else:
        a = _first_int(r"(\d{2,})\s*(?:chia|mod)", q)  # only a clear standalone integer
        if a is None:
            return _no_match()
        result = a % n
        rationale = f"{a} mod {n} = {result}"
    label = _exact_label(float(result), choices, labels)
    if label is not None:
        return CalculationResult(label, _CONF_EXACT, "modular_arithmetic", rationale,
                                 True, True, "number_theory", {"mod": n, "result": result})
    return _no_match()


# --- Phase 2L.14B helpers -----------------------------------------------------

def _to_amount(token):
    """Parse a currency/amount tolerating VN thousands grouping ('1.000.000'->1e6).

    Decimal sep = a trailing '.'/',' followed by exactly 1-2 digits; all other
    '.'/',' are treated as thousands separators and stripped.
    """
    if token is None:
        return None
    s = re.sub(r"[^\d.,]", "", str(token))
    if not s:
        return None
    m = re.search(r"[.,](\d{1,2})$", s)
    try:
        if m:
            intpart = re.sub(r"[.,]", "", s[: m.start()])
            return float(f"{intpart or 0}.{m.group(1)}")
        return float(re.sub(r"[.,]", "", s))
    except ValueError:
        return None


def _first_amount(pattern: str, text: str):
    m = re.search(pattern, text, re.IGNORECASE)
    return _to_amount(m.group(1)) if m else None


def _parse_interval(text):
    """Parse an option like '< 1.0', 'lớn hơn 2.5', '1.0 đến 1.5' -> (lo, hi) or None."""
    s = str(text).lower().strip()
    nums = _all_numbers(s)
    if (s.startswith("<") or any(w in s for w in ("nhỏ hơn", "dưới", "ít hơn", "bé hơn"))) and nums:
        return (float("-inf"), nums[0])
    if (s.startswith(">") or any(w in s for w in ("lớn hơn", "trên", "nhiều hơn", "vượt"))) and nums:
        return (nums[0], float("inf"))
    if (("đến" in s or "tới" in s or "–" in s or re.search(r"\d\s*-\s*\d", s)) and len(nums) >= 2):
        return (min(nums[0], nums[1]), max(nums[0], nums[1]))
    return None


def _parse_linear_in_P(s):
    """Parse a linear-in-P RHS ('100-2P', '30P-50', '2.5P') -> (intercept, slope)."""
    s = str(s).replace(" ", "").lower()
    intercept = slope = 0.0
    found = False
    for m in re.finditer(r"([+-]?\d+(?:[.,]\d+)?)(p?)", s):
        val = _to_float(m.group(1))
        if val is None:
            continue
        found = True
        if m.group(2) == "p":
            slope += val
        else:
            intercept += val
    return (intercept, slope) if found else None


def _m0c_coeff(choice):
    """Coefficient k in an option of the form 'k·m₀c' (m_0 c / m0c / mc), else None."""
    s = str(choice).replace("₀", "0").replace("·", "").replace("\\", "").replace("{", "").replace("}", "")
    m = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*m\s*_?\s*0?\s*c", s, re.IGNORECASE)
    return _to_float(m.group(1)) if m else None


def _abs_nearest_label(target, choices, labels, *, tol, margin=2.0):
    """Nearest choice within absolute ``tol`` and a clear margin (handles target≈0)."""
    vals = _choice_values(choices)
    cand = sorted((abs(v - target), i) for i, v in enumerate(vals) if v is not None)
    if not cand or cand[0][0] > tol:
        return None
    if len(cand) > 1 and cand[1][0] < margin * cand[0][0] + 1e-9:
        return None
    return labels[cand[0][1]]


def _extract_mean_test(q):
    """Shared (x̄, μ₀, n) extraction for the one-sample mean tests."""
    xbar = _first(r"trung bình mẫu[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
    mu0 = (_first(r"giả thuyết[^0-9]{0,40}?([-+]?\d+(?:[.,]\d+)?)", q)
           or _first(r"trung bình[^0-9]{0,8}?(?:tổng thể|lý thuyết|kỳ vọng)[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
           or _first(r"[μµ]_?0?\s*=\s*([-+]?\d+(?:[.,]\d+)?)", q))
    n = (_first(r"(?:cỡ mẫu|kích thước mẫu)[^0-9]{0,12}?([-+]?\d+(?:[.,]\d+)?)", q)
         or _first(r"\bn\s*=\s*([-+]?\d+(?:[.,]\d+)?)", q))
    return xbar, mu0, n


# --- Phase 2L.14B formula families --------------------------------------------

def try_relativistic_momentum(q: str, choices, labels) -> CalculationResult:
    """Relativistic momentum p = γβ·m₀c (options expressed as multiples of m₀c)."""
    low = q.lower()
    if "động lượng" not in low:
        return _no_match()
    if not any(w in low for w in ("tương đối", "ánh sáng", "lorentz")) and \
       not re.search(r"\d\s*c(?![a-zA-Z])", q):
        return _no_match()
    beta = _relativistic_beta(q)
    if beta is None or not (0.0 < beta < 1.0):
        return _no_match()
    gamma = 1.0 / math.sqrt(1.0 - beta * beta)
    target = gamma * beta                       # p in units of m₀c
    coeffs = [_m0c_coeff(c) for c in choices]
    cand = sorted((abs(v - target), i) for i, v in enumerate(coeffs) if v is not None)
    if not cand or cand[0][0] / max(abs(target), 1e-9) > 0.03:
        return _no_match()
    if len(cand) > 1 and cand[1][0] < 2.0 * cand[0][0]:
        return _no_match()
    return CalculationResult(labels[cand[0][1]], _CONF_NEAREST, "relativistic_momentum",
                             f"p=γβ·m₀c={target:.4g}·m₀c (β={beta:g}, γ={gamma:.4g})",
                             True, True, "physics",
                             {"beta": beta, "gamma": gamma, "p_over_m0c": target})


def try_cobb_douglas_isoquant_scaling(q: str, choices, labels) -> CalculationResult:
    """Q=A·K^a·L^b at (K0,L0), scaled by a fraction -> pick the (K,L) option hitting Q1."""
    low = q.lower()
    qn = q.replace(" ", "")
    mfun = re.search(r"q=(\d+(?:[.,]\d+)?)?k\^?\{?(\d+(?:[.,]\d+)?)\}?l\^?\{?(\d+(?:[.,]\d+)?)\}?", qn, re.IGNORECASE)
    sqrt = re.search(r"q=(\d+(?:[.,]\d+)?)?\\?sqrt\{?kl", qn, re.IGNORECASE) or ("√" in q and "kl" in low)
    if not mfun and not sqrt:
        return _no_match()
    if mfun:
        A = _to_float(mfun.group(1)) if mfun.group(1) else 1.0
        a, b = _to_float(mfun.group(2)), _to_float(mfun.group(3))
    else:
        A = _first(r"(\d+(?:[.,]\d+)?)\s*\\?sqrt", qn) or _first(r"(\d+(?:[.,]\d+)?)\s*√", q) or 1.0
        a = b = 0.5
    k0 = _first(r"k\s*_?0?\s*=\s*(\d+(?:[.,]\d+)?)", q) or _first(r"k\s*=\s*(\d+(?:[.,]\d+)?)", q)
    l0 = _first(r"l\s*_?0?\s*=\s*(\d+(?:[.,]\d+)?)", q) or _first(r"l\s*=\s*(\d+(?:[.,]\d+)?)", q)
    if None in (A, a, b, k0, l0):
        return _no_match()
    frac = None
    if any(w in low for w in ("một nửa", "1/2", "phân nửa", "giảm một nửa", "halve", "half")):
        frac = 0.5
    elif any(w in low for w in ("gấp đôi", "tăng gấp đôi", "double")):
        frac = 2.0
    else:
        f = _first(r"(\d+(?:[.,]\d+)?)\s*lần", q)
        frac = f if f else None
    if frac is None:
        return _no_match()
    q1 = frac * (A * (k0 ** a) * (l0 ** b))
    hits = []
    for i, c in enumerate(choices):
        pair = re.search(r"k\s*=\s*(\d+(?:[.,]\d+)?)\D{0,10}?l\s*=\s*(\d+(?:[.,]\d+)?)", str(c), re.IGNORECASE) \
            or re.search(r"\(\s*(\d+(?:[.,]\d+)?)\s*[,;]\s*(\d+(?:[.,]\d+)?)\s*\)", str(c))
        if not pair:
            continue
        kk, ll = _to_float(pair.group(1)), _to_float(pair.group(2))
        if kk is None or ll is None or kk < 0 or ll < 0:
            continue
        if abs(A * (kk ** a) * (ll ** b) - q1) <= 1e-6 + 1e-3 * abs(q1):
            hits.append(labels[i])
    if len(hits) == 1:
        return CalculationResult(hits[0], _CONF_EXACT, "cobb_douglas_isoquant_scaling",
                                 f"Q1={frac:g}·Q0={q1:g}", True, True, "economics",
                                 {"A": A, "a": a, "b": b, "K0": k0, "L0": l0, "fraction": frac, "Q1": q1})
    return _no_match()


def try_t_statistic_one_sample(q: str, choices, labels) -> CalculationResult:
    """One-sample t-statistic with INTERVAL options ('< 1.0', '1.0 đến 1.5', ...)."""
    low = q.lower()
    if not any(w in low for w in ("kiểm định", "thống kê t", "giá trị t", "t-statistic", "t-test")):
        return _no_match()
    intervals = [_parse_interval(c) for c in choices]
    if sum(1 for iv in intervals if iv) < 2:     # require interval-style options
        return _no_match()
    xbar, mu0, n = _extract_mean_test(q)
    s = _first(r"độ lệch chuẩn(?:\s*mẫu)?[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
    if None in (xbar, mu0, s, n) or s == 0 or n <= 0:
        return _no_match()
    t = (xbar - mu0) / (s / math.sqrt(n))
    hits = [labels[i] for i, iv in enumerate(intervals) if iv and iv[0] <= t <= iv[1]]
    if len(hits) == 1:
        return CalculationResult(hits[0], _CONF_NEAREST, "t_statistic_one_sample",
                                 f"t=(x̄−μ₀)/(s/√n)={t:.4g}", True, True, "statistics",
                                 {"xbar": xbar, "mu0": mu0, "s": s, "n": n, "t": t})
    return _no_match()


def try_z_score_one_sample(q: str, choices, labels) -> CalculationResult:
    """One-sample z-statistic z=(x̄−μ₀)/(σ/√n); requires POPULATION std to fire."""
    low = q.lower()
    if not any(w in low for w in ("kiểm định", "thống kê z", "giá trị z", "z-score",
                                  "z-statistic", "điểm z")):
        return _no_match()
    sigma = (_first(r"độ lệch chuẩn[^0-9]{0,8}?(?:của\s*)?(?:quần thể|tổng thể|dân số)[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
             or _first(r"(?:quần thể|tổng thể)[^0-9]{0,20}?độ lệch chuẩn[^0-9]{0,12}?([-+]?\d+(?:[.,]\d+)?)", q)
             or _first(r"[σ]\s*=\s*([-+]?\d+(?:[.,]\d+)?)", q))
    if sigma is None:                            # population std distinguishes z from t
        return _no_match()
    xbar, mu0, n = _extract_mean_test(q)
    if None in (xbar, mu0, n) or sigma == 0 or n <= 0:
        return _no_match()
    z = (xbar - mu0) / (sigma / math.sqrt(n))
    label = _nearest_label(z, choices, labels, rel_tol=0.05)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "z_score_one_sample",
                                 f"z=(x̄−μ₀)/(σ/√n)={z:.4g}", True, True, "statistics",
                                 {"xbar": xbar, "mu0": mu0, "sigma": sigma, "n": n, "z": z})
    return _no_match()


def try_supply_demand_price_control(q: str, choices, labels) -> CalculationResult:
    """Shortage/surplus at a controlled price for general linear Qd/Qs (incl. P-first)."""
    low = q.lower()
    if not any(w in low for w in ("thiếu hụt", "dư thừa", "dư cung", "thặng dư", "shortage", "surplus")):
        return _no_match()

    def _rhs(tags):
        for t in tags:
            m = re.search(t + r"\s*=\s*([0-9pP+\-.,\s]+)", low)
            if m:
                lin = _parse_linear_in_P(m.group(1))
                if lin and (lin[1] != 0.0):
                    return lin
        return None

    qd = _rhs([r"q\s*_?d", r"qd", r"lượng cầu", r"cầu"])
    qs = _rhs([r"q\s*_?s", r"qs", r"lượng cung", r"cung"])
    p0 = (_first(r"giá (?:trần|sàn)[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q)
          or _first(r"(?:quy định|kiểm soát|ấn định|áp đặt|áp giá)[^0-9]{0,20}?([-+]?\d+(?:[.,]\d+)?)", q))
    if not qd or not qs or p0 is None:
        return _no_match()
    q_d = qd[0] + qd[1] * p0
    q_s = qs[0] + qs[1] * p0
    wants_shortage = any(w in low for w in ("thiếu hụt", "shortage"))
    diff = (q_d - q_s) if wants_shortage else (q_s - q_d)
    if diff <= 0:
        return _no_match()
    label = _nearest_label(diff, choices, labels, rel_tol=0.02)
    if label is not None:
        kind = "shortage" if wants_shortage else "surplus"
        return CalculationResult(label, _CONF_NEAREST, "supply_demand_price_control",
                                 f"{kind}={diff:.4g} at P={p0:g}", True, True, "economics",
                                 {"Qd": q_d, "Qs": q_s, "P": p0, kind: diff})
    return _no_match()


def try_henderson_hasselbalch_buffer(q: str, choices, labels) -> CalculationResult:
    """Buffer pH = pKa + log10([base]/[acid])."""
    low = q.lower()
    if not any(w in low for w in ("đệm", "buffer", "henderson", "pka")):
        return _no_match()
    pka = _first(r"pka[^0-9\-]{0,8}?([-+]?\d+(?:[.,]\d+)?)", q)
    base = _first(r"(?:bazơ|bazo|base|muối|liên hợp|gốc bazơ)[^0-9]{0,24}?([-+]?\d+(?:[.,]\d+)?)\s*m", low)
    acid = _first(r"(?:axit|axít|acid|ha\b)[^0-9]{0,24}?([-+]?\d+(?:[.,]\d+)?)\s*m", low)
    if None in (pka, base, acid) or acid <= 0 or base <= 0:
        return _no_match()
    ph = pka + math.log10(base / acid)
    label = _nearest_label(ph, choices, labels, rel_tol=0.03)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "henderson_hasselbalch_buffer",
                                 f"pH=pKa+log10([base]/[acid])={ph:.4g}", True, True, "chemistry",
                                 {"pKa": pka, "base": base, "acid": acid, "pH": ph})
    return _no_match()


def try_linear_total_equation(q: str, choices, labels) -> CalculationResult:
    """Sum of linear equations 'const ± coef·y' equal to a total -> solve y."""
    low = q.lower()
    eqs = re.findall(r"(\d+(?:[.,]\d+)?)\s*([+-])\s*(\d+(?:[.,]\d+)?)\s*[a-zA-Z]", q)
    if len(eqs) < 2:
        return _no_match()
    total = _first(r"tổng[^0-9]{0,30}?(?:là|bằng|=|đạt)\s*([-+]?\d+(?:[.,]\d+)?)", q)
    if total is None:
        return _no_match()
    c_sum = sum(_to_float(c) for c, _s, _k in eqs)
    k_sum = sum((_to_float(k) if s == "+" else -_to_float(k)) for _c, s, k in eqs)
    if k_sum == 0:
        return _no_match()
    y = (total - c_sum) / k_sum
    label = _abs_nearest_label(y, choices, labels, tol=0.5)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "linear_total_equation",
                                 f"y=(T−ΣC)/ΣK={y:.4g}", True, True, "algebra",
                                 {"sum_const": c_sum, "sum_coef": k_sum, "total": total, "y": y})
    return _no_match()


def try_nuclear_binding_energy_release(q: str, choices, labels) -> CalculationResult:
    """Fission energy release ΔE = A·(BE/nucleon_after − BE/nucleon_before) [MeV]."""
    low = q.lower()
    if "năng lượng liên kết" not in low:
        return _no_match()
    if not any(w in low for w in ("phân hạch", "phân rã", "vỡ", "tách", "fission")):
        return _no_match()
    a = (_first(r"(?:số khối|số nucleon|số nuclôn)[^0-9]{0,12}?(\d+(?:[.,]\d+)?)", q)
         or _first(r"\bA\s*=\s*(\d+)", q))
    be_before = _first(r"(?:trước|ban đầu|hạt nhân mẹ|mẹ)[^0-9]{0,30}?([-+]?\d+(?:[.,]\d+)?)\s*mev", low)
    be_after = _first(r"(?:sau|sản phẩm|mảnh|con)[^0-9]{0,30}?([-+]?\d+(?:[.,]\d+)?)\s*mev", low)
    if None in (a, be_before, be_after):
        return _no_match()
    de = a * (be_after - be_before)
    label = _nearest_label(de, choices, labels, rel_tol=0.03)
    if label is not None:
        return CalculationResult(label, _CONF_NEAREST, "nuclear_binding_energy_release",
                                 f"ΔE=A·Δ(BE/nucleon)={de:.4g} MeV", True, True, "physics",
                                 {"A": a, "be_before": be_before, "be_after": be_after, "dE": de})
    return _no_match()


def try_accrued_simple_interest(q: str, choices, labels) -> CalculationResult:
    """Simple accrued interest I = P·r·(elapsed_months/12) between two dates."""
    low = q.lower()
    if "lãi" not in low and "interest" not in low:
        return _no_match()
    if not any(w in low for w in ("trái phiếu", "mệnh giá", "tiền gốc", "principal", "khoản vay")):
        return _no_match()
    principal = _first_amount(r"(?:mệnh giá|tiền gốc|principal|số tiền|khoản vay)[^0-9]{0,20}?([0-9.,]+)", q)
    rate = _first(r"(?:lãi suất|interest rate|rate|lãi)[^0-9%]{0,20}?([-+]?\d+(?:[.,]\d+)?)\s*%", q)
    dates = re.findall(r"(\d{1,2})\s*tháng\s*(\d{1,2})", low)
    if principal is None or rate is None or len(dates) < 2:
        return _no_match()
    (d1, m1), (d2, m2) = (int(dates[0][0]), int(dates[0][1])), (int(dates[1][0]), int(dates[1][1]))
    months = (m2 - m1) + (d2 - d1) / 30.0
    if months <= 0:
        return _no_match()
    interest = principal * (rate / 100.0) * (months / 12.0)
    vals = [_to_amount(c) for c in choices]
    cand = sorted((abs(v - interest), i) for i, v in enumerate(vals) if v is not None)
    if not cand or cand[0][0] / max(abs(interest), 1e-9) > 0.02:
        return _no_match()
    if len(cand) > 1 and cand[1][0] < 2.0 * cand[0][0]:
        return _no_match()
    return CalculationResult(labels[cand[0][1]], _CONF_NEAREST, "accrued_simple_interest",
                             f"I=P·r·t={interest:.6g} ({months:.1f} months)", True, True, "finance",
                             {"principal": principal, "rate": rate, "months": months, "interest": interest})


def try_operating_margin_asset_turnover(q: str, choices, labels) -> CalculationResult:
    """Operating margin = (gross−opex)/sales; asset turnover = sales/assets (combined option)."""
    low = q.lower()
    gross = _first_amount(r"(?:lợi nhuận gộp|gross profit)[^0-9]{0,20}?([0-9.,]+)", q)
    opex = _first_amount(r"(?:chi phí hoạt động|operating expense[s]?)[^0-9]{0,20}?([0-9.,]+)", q)
    sales = _first_amount(r"(?:doanh số|doanh thu|sales|net sales)[^0-9]{0,20}?([0-9.,]+)", q)
    assets = _first_amount(r"(?:tổng tài sản|tài sản|total assets)[^0-9]{0,20}?([0-9.,]+)", q)
    if None in (gross, opex, sales, assets) or sales == 0 or assets == 0:
        return _no_match()
    margin = (gross - opex) / sales            # fraction
    turnover = sales / assets
    hits = []
    for i, c in enumerate(choices):
        cl = str(c).lower()
        mp = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*%", cl)
        rest = _all_numbers(re.sub(r"[-+]?\d+(?:[.,]\d+)?\s*%", "", cl))
        if not mp or not rest:
            continue
        m_opt = _to_float(mp.group(1)) / 100.0
        t_opt = rest[0]
        if abs(m_opt - margin) <= 0.01 and abs(t_opt - turnover) <= 0.05:
            hits.append(labels[i])
    if len(hits) == 1:
        return CalculationResult(hits[0], _CONF_NEAREST, "operating_margin_asset_turnover",
                                 f"margin={margin*100:.3g}%, turnover={turnover:.3g}", True, True, "finance",
                                 {"margin": margin, "turnover": turnover})
    return _no_match()


# Conservative order: exact-result families first, then nearest-numeric families.
_FAMILIES = (
    try_exponential,
    try_hess_law,
    try_expected_distinct,
    try_resistor,
    try_modular_arithmetic,
    try_cobb_douglas_isoquant_scaling,
    try_cobb_douglas_isoquant,
    try_linear_total_equation,
    try_supply_demand,
    try_supply_demand_price_control,
    try_gdp_inflation,
    try_cylinder_rate,
    try_sphere_rate,
    try_price_elasticity,
    try_kepler,
    try_relativistic_momentum,
    try_relativistic_gamma,
    try_money_multiplier,
    try_z_score_one_sample,
    try_t_statistic_one_sample,
    try_t_statistic,
    try_henderson_hasselbalch_buffer,
    try_nuclear_binding_energy_release,
    try_accrued_simple_interest,
    try_operating_margin_asset_turnover,
    try_acid_base_volume,
)


def solve_calculation_sample(sample: dict, labels: list[str],
                             *, min_confidence: float = 0.95) -> CalculationResult:
    """Try each high-confidence family; return the first confident, valid match.

    Never returns a label outside ``labels``. ``safe_to_override`` is True only
    when a family matched with confidence >= ``min_confidence``. No qid is used.
    """
    q = str(sample.get("question", "") or "")
    choices = sample.get("choices", []) or []
    if not labels or not choices:
        return _no_match()

    for family in _FAMILIES:
        try:
            res = family(q, choices, labels)
        except Exception:
            res = _no_match()  # a matcher bug must never crash the run
        if res.matched and res.answer in labels:
            res.safe_to_override = res.confidence >= min_confidence
            return res
    return _no_match()
