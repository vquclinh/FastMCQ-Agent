"""Generalized formula/concept bank (Phase 2L.19) — deterministic, qid-free.

A single entry point ``solve_formula_bank_sample`` that:
  1. delegates to the existing deterministic solvers (``calculation_solver`` for
     numeric formula families, ``concept_solver`` for qualitative concept rules),
  2. then tries a set of NEW generalized rules added here (electricity, waves,
     geometry, linear algebra, transforms, CS, and extra economics concepts).

Every rule inspects only the question text + option texts (and never a qid or any
public-test answer table or external sheet). A rule fires ONLY when the problem type
is clearly detected, the required facts are extractable, and exactly one option
matches — otherwise it declines. Numeric helpers are reused from
``calculation_solver`` so behavior matches the rest of the pipeline.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field

from src.calculation_solver import (_choice_values, _exact_label, _first, _nearest_label,
                                     _norm, _to_float)
from src.calculation_solver import solve_calculation_sample
from src.concept_solver import solve_concept_sample
from src.labels import labels_for

_NUM = r"[-+]?\d+(?:[.,]\d+)?"
_NUM_RE = re.compile(_NUM)


@dataclass
class FormulaBankResult:
    rule_id: str
    selected_answer: str | None
    confidence: float
    reason: str
    safe_to_override: bool
    matched_option_text: str = ""
    extracted_values: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _nums(text: str):
    return [float(m.group(0).replace(",", ".")) for m in _NUM_RE.finditer(text or "")]


# Standalone INTEGERS (comma/bracket are separators, not decimal points) — used for
# matrices/vectors where "1,2" means two entries, not the decimal 1.2.
_INT_RE = re.compile(r"(?<![\d.])[-+]?\d+(?![\d.])")


def _int_tokens(text: str):
    return [int(m.group(0)) for m in _INT_RE.finditer(text or "")]


def _has(text: str, kws) -> bool:
    return any(k in text for k in kws)


def _mk(rule_id, label, reason, choices, labels, *, conf=0.97, extracted=None):
    idx = labels.index(label)
    return FormulaBankResult(rule_id, label, conf, reason, True,
                             str(choices[idx]), extracted or {})


# --- Electricity --------------------------------------------------------------

def try_ohms_law(q, choices, labels):
    low = q.lower()
    if not _has(low, ("định luật ohm", "ohm", "v = i", "i = v", "hiệu điện thế",
                      "điện áp")):
        return None
    if not _has(low, ("điện trở", "dòng điện", "hiệu điện thế", "điện áp", "ohm", "ampe", "vôn")):
        return None
    V = _first(r"(?:hiệu điện thế|điện áp|u|v)\s*(?:là|=|:)?\s*(" + _NUM + r")\s*(?:v|vôn|volt)", q)
    R = _first(r"(?:điện trở|r)\s*(?:là|=|:)?\s*(" + _NUM + r")\s*(?:ω|ohm|Ω)", q)
    I = _first(r"(?:dòng điện|cường độ|i)\s*(?:là|=|:)?\s*(" + _NUM + r")\s*(?:a|ampe|ampere)", q)
    asks_I = _has(low, ("dòng điện", "cường độ")) and I is None
    asks_V = _has(low, ("hiệu điện thế", "điện áp")) and V is None
    asks_R = "điện trở" in low and R is None
    target = None
    if asks_I and V is not None and R:
        target, unit = V / R, "A"
    elif asks_V and I is not None and R is not None:
        target, unit = I * R, "V"
    elif asks_R and V is not None and I:
        target, unit = V / I, "Ω"
    else:
        return None
    lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
    if lbl:
        return _mk("ohms_law", lbl, f"Ohm's law -> {target:.4g}{unit}", choices, labels,
                   extracted={"V": V, "I": I, "R": R, "result": target})
    return None


def try_electric_power(q, choices, labels):
    low = q.lower()
    if "công suất" not in low and "power" not in low:
        return None
    V = _first(r"(?:hiệu điện thế|điện áp|u|v)\s*(?:là|=|:)?\s*(" + _NUM + r")\s*(?:v|vôn|volt)", q)
    I = _first(r"(?:dòng điện|cường độ|i)\s*(?:là|=|:)?\s*(" + _NUM + r")\s*(?:a|ampe|ampere)", q)
    R = _first(r"(?:điện trở|r)\s*(?:là|=|:)?\s*(" + _NUM + r")\s*(?:ω|ohm|Ω)", q)
    p = None
    if V is not None and I is not None:
        p = V * I
    elif I is not None and R is not None:
        p = I * I * R
    elif V is not None and R:
        p = V * V / R
    if p is None:
        return None
    lbl = _nearest_label(p, choices, labels, rel_tol=0.02)
    if lbl:
        return _mk("electric_power", lbl, f"P -> {p:.4g}W", choices, labels,
                   extracted={"V": V, "I": I, "R": R, "P": p})
    return None


def try_resistor_series_parallel(q, choices, labels):
    low = q.lower()
    if "điện trở" not in low:
        return None
    # Must explicitly ask for the EQUIVALENT resistance — not a power-matching, variable-
    # resistor, or current/voltage sub-question that merely mentions series/parallel.
    if not _has(low, ("tương đương", "equivalent", "tổng trở")):
        return None
    if _has(low, ("biến đổi", "biến trở", "công suất", "variable", "power")):
        return None
    vals = [v for v in (_to_float(x) for x in re.findall(r"(" + _NUM + r")\s*(?:ω|ohm|Ω)", q)) if v]
    if len(vals) < 2:
        return None
    if _has(low, ("nối tiếp", "mắc nối tiếp", "series")):
        target = sum(vals)
        kind = "series"
    elif _has(low, ("song song", "parallel")) and len(vals) == 2:
        target = vals[0] * vals[1] / (vals[0] + vals[1])
        kind = "parallel"
    else:
        return None
    lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
    if lbl:
        return _mk("resistor_series_parallel_basic", lbl,
                   f"{kind} R_eq={target:.4g}Ω", choices, labels,
                   extracted={"resistors": vals, "R_eq": target, "kind": kind})
    return None


# --- Waves / geometry ---------------------------------------------------------

def try_wave_speed(q, choices, labels):
    low = q.lower()
    if not _has(low, ("bước sóng", "tần số", "vận tốc sóng", "tốc độ sóng", "wavelength",
                      "frequency", "wave")):
        return None
    f = _first(r"tần số\D{0,12}(" + _NUM + r")", q) or _first(r"(" + _NUM + r")\s*hz", q)
    lam = (_first(r"bước sóng\D{0,12}(" + _NUM + r")", q)
           or _first(r"(" + _NUM + r")\s*(?:m\b|mét|met)", q))
    v = _first(r"(?:vận tốc|tốc độ)\D{0,12}(" + _NUM + r")", q)
    target = unit = None
    if "vận tốc" in low or "tốc độ" in low:
        if f and lam:
            target, unit = f * lam, "m/s"
    elif "tần số" in low and v and lam:
        target, unit = v / lam, "Hz"
    elif "bước sóng" in low and v and f:
        target, unit = v / f, "m"
    if target is None:
        return None
    lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
    if lbl:
        return _mk("wave_speed_frequency_wavelength", lbl, f"v=fλ -> {target:.4g}{unit}",
                   choices, labels, extracted={"f": f, "lambda": lam, "v": v})
    return None


def try_pythagorean_distance(q, choices, labels):
    low = q.lower()
    if not _has(low, ("vuông góc", "tam giác vuông", "khoảng cách", "pythagore",
                      "định lý pytago", "cạnh huyền", "perpendicular")):
        return None
    if not _has(low, ("khoảng cách", "cạnh huyền", "đường chéo", "độ dài")):
        return None
    nums = _nums(q)
    if len(nums) < 2:
        return None
    a, b = nums[0], nums[1]
    target = math.hypot(a, b)
    lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
    if lbl:
        return _mk("pythagorean_distance", lbl, f"√({a}²+{b}²)={target:.4g}",
                   choices, labels, extracted={"a": a, "b": b, "distance": target})
    return None


# --- Linear algebra -----------------------------------------------------------

def try_determinant_2x2(q, choices, labels):
    low = q.lower()
    if not _has(low, ("định thức", "determinant", "det")):
        return None
    nums = _int_tokens(q)
    # Use the last 4 integers (the matrix entries), tolerant of an order/index prefix.
    if len(nums) < 4:
        return None
    a, b, c, d = nums[-4:]
    target = a * d - b * c
    lbl = _exact_label(target, choices, labels) or _nearest_label(target, choices, labels, rel_tol=1e-6)
    if lbl:
        return _mk("determinant_2x2", lbl, f"det=ad-bc={target:g}", choices, labels,
                   conf=0.99, extracted={"matrix": [a, b, c, d], "det": target})
    return None


def try_matrix_vector_multiply(q, choices, labels):
    low = q.lower()
    if not _has(low, ("ma trận", "matrix")) or not _has(low, ("vector", "véc tơ", "vectơ")):
        return None
    nums = _int_tokens(q)
    if len(nums) < 6:                      # 4 matrix + 2 vector
        return None
    a, b, c, d, x, y = nums[-6:]
    r1, r2 = a * x + b * y, c * x + d * y
    # Options must be 2-component vectors; match the pair.
    hits = []
    for i, ch in enumerate(choices):
        cn = _int_tokens(str(ch))
        if len(cn) >= 2 and cn[0] == r1 and cn[1] == r2:
            hits.append(labels[i])
    if len(hits) == 1:
        return _mk("matrix_vector_multiply", hits[0], f"Av=({r1:g},{r2:g})", choices, labels,
                   extracted={"result": [r1, r2]})
    return None


# --- Transforms ---------------------------------------------------------------

def try_laplace_polynomial(q, choices, labels):
    low = q.lower()
    if "laplace" not in low:
        return None
    # Only the canonical single-power case L{t^n} = n!/s^(n+1) handled safely.
    m = re.search(r"t\s*\^\s*\{?\s*(\d+)", q) or re.search(r"t\s*\*\*\s*(\d+)", q)
    if not m:
        return None
    n = int(m.group(1))
    fact = math.factorial(n)
    want = f"{fact}/s^{n + 1}".replace(" ", "")
    hits = []
    for i, ch in enumerate(choices):
        cn = _norm(ch).replace("\\frac", "").replace("{", "").replace("}", "")
        cn = cn.replace("^", "^")
        if want.lower() in cn or f"{fact}/s^{n+1}".replace(" ", "") in cn:
            hits.append(labels[i])
    if len(hits) == 1:
        return _mk("laplace_polynomial", hits[0], f"L{{t^{n}}}={fact}/s^{n+1}",
                   choices, labels, conf=0.97, extracted={"n": n})
    return None


# --- Probability --------------------------------------------------------------

def try_expected_value(q, choices, labels):
    low = q.lower()
    if not _has(low, ("kỳ vọng", "giá trị kỳ vọng", "expected value", "expectation")):
        return None
    # Pair probabilities with values: "x với xác suất p" patterns.
    pairs = re.findall(r"(" + _NUM + r")\s*(?:với xác suất|xác suất|prob[^0-9]*)\s*(" + _NUM + r")", q,
                       re.IGNORECASE)
    if len(pairs) < 2:
        return None
    ev = 0.0
    psum = 0.0
    for x, p in pairs:
        xv, pv = _to_float(x), _to_float(p)
        if pv is not None and pv > 1:      # percent
            pv /= 100.0
        ev += (xv or 0) * (pv or 0)
        psum += pv or 0
    if abs(psum - 1.0) > 0.02:             # probabilities must sum to ~1
        return None
    lbl = _nearest_label(ev, choices, labels, rel_tol=0.02)
    if lbl:
        return _mk("basic_probability_expected_value", lbl, f"E[X]={ev:.4g}", choices, labels,
                   extracted={"ev": ev, "pairs": pairs})
    return None


# --- Economics concepts -------------------------------------------------------

def try_mc_vs_average_cost(q, choices, labels):
    """Generalized MC vs average cost (AVC or ATC). Distinguishes the target."""
    low = q.lower()
    is_atc = _has(low, ("chi phí trung bình", "tổng chi phí trung bình", "average total cost", "atc"))
    is_avc = _has(low, ("chi phí biến đổi trung bình", "average variable cost", "avc"))
    if not (_has(low, ("chi phí biên", "marginal cost", " mc")) and (is_atc or is_avc)):
        return None
    mc = (_first(r"chi phí biên\D{0,20}(" + _NUM + r")", q)
          or _first(r"marginal cost\D{0,20}(" + _NUM + r")", q))
    if is_atc and not is_avc:
        avg = (_first(r"chi phí trung bình\D{0,20}(" + _NUM + r")", q)
               or _first(r"tổng chi phí trung bình\D{0,20}(" + _NUM + r")", q)
               or _first(r"average total cost\D{0,20}(" + _NUM + r")", q))
        avg_word = "chi phí trung bình"
    else:
        avg = (_first(r"chi phí biến đổi trung bình\D{0,20}(" + _NUM + r")", q)
               or _first(r"average variable cost\D{0,20}(" + _NUM + r")", q))
        avg_word = "chi phí biến đổi trung bình"
    if mc is None or avg is None:
        return None
    if mc > avg:
        want, avoid = ("tăng", "increase", "rise"), ("giảm", "decrease")
        d = "increase"
    elif mc < avg:
        want, avoid = ("giảm", "decrease", "fall"), ("tăng", "increase")
        d = "decrease"
    else:
        want, avoid, d = ("không thay đổi", "không đổi", "unchanged"), (), "unchanged"
    hits = []
    for i, ch in enumerate(choices):
        cl = str(ch).lower()
        if d in ("increase", "decrease") and _has(cl, ("không", "cannot", "unable")):
            continue
        if _has(cl, want) and not _has(cl, avoid):
            hits.append(labels[i])
    if len(hits) == 1:
        return _mk("mc_vs_average_cost", hits[0],
                   f"MC={mc:g} vs {avg_word}={avg:g} -> {d}", choices, labels,
                   extracted={"mc": mc, "avg": avg, "direction": d})
    return None


def try_elasticity_revenue_direction(q, choices, labels):
    low = q.lower()
    if "co giãn" not in low or ("doanh thu" not in low and "revenue" not in low):
        return None
    elastic = _has(low, ("co giãn nhiều", "co giãn cao", "elastic")) and "không co giãn" not in low \
        and "ít co giãn" not in low
    inelastic = _has(low, ("không co giãn", "ít co giãn", "co giãn ít", "inelastic"))
    price_up = _has(low, ("tăng giá", "giá tăng", "price increase"))
    price_down = _has(low, ("giảm giá", "giá giảm", "price decrease"))
    if not (elastic ^ inelastic) or not (price_up ^ price_down):
        return None
    # elastic+up -> revenue down; elastic+down -> up; inelastic flips.
    rev_up = (inelastic and price_up) or (elastic and price_down)
    want = ("tăng", "increase", "rise") if rev_up else ("giảm", "decrease", "fall")
    avoid = ("giảm", "decrease") if rev_up else ("tăng", "increase")
    hits = []
    for i, ch in enumerate(choices):
        cl = str(ch).lower()
        if "doanh thu" not in cl and "revenue" not in cl:
            continue
        if _has(cl, want) and not _has(cl, avoid):
            hits.append(labels[i])
    if len(hits) == 1:
        return _mk("elasticity_revenue_direction", hits[0],
                   f"{'elastic' if elastic else 'inelastic'} + "
                   f"{'price_up' if price_up else 'price_down'} -> revenue "
                   f"{'up' if rev_up else 'down'}", choices, labels, conf=0.95)
    return None


def try_tax_supply_shift(q, choices, labels):
    low = q.lower()
    if "thuế" not in low or not _has(low, ("cung", "cân bằng", "supply")):
        return None
    if not _has(low, ("sản lượng", "lượng cân bằng", "giá", "quantity")):
        return None
    # A per-unit tax shifts supply up/left: equilibrium quantity falls, buyer price rises.
    asks_q = _has(low, ("sản lượng", "lượng cân bằng", "quantity"))
    want = ("giảm", "decrease", "fall") if asks_q else ("tăng", "increase", "rise")
    avoid = ("tăng", "increase") if asks_q else ("giảm", "decrease")
    hits = []
    for i, ch in enumerate(choices):
        cl = str(ch).lower()
        if _has(cl, ("không", "cannot")):
            continue
        if _has(cl, want) and not _has(cl, avoid):
            hits.append(labels[i])
    if len(hits) == 1:
        return _mk("tax_supply_shift_basic", hits[0],
                   "unit tax -> supply shifts up/left", choices, labels, conf=0.9)
    return None


# --- Computer science ---------------------------------------------------------

def try_cache_hit_rate(q, choices, labels):
    low = q.lower()
    if not _has(low, ("cache", "bộ nhớ đệm")):
        return None
    if _has(low, ("tỉ lệ trúng", "tỷ lệ trúng", "hit rate", "tỉ lệ hit")):
        hits_n = _first(r"(" + _NUM + r")\s*(?:lần\s*)?(?:trúng|hit)", q)
        acc = _first(r"(" + _NUM + r")\s*(?:lần\s*)?(?:truy cập|access)", q)
        if hits_n is not None and acc:
            hr = hits_n / acc
            for target in (hr, hr * 100):
                lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
                if lbl:
                    return _mk("cache_hit_rate", lbl, f"hit rate={hr:.4g}", choices, labels,
                               extracted={"hits": hits_n, "accesses": acc, "hit_rate": hr})
    return None


def try_time_complexity_nested_loops(q, choices, labels):
    low = q.lower()
    if not _has(low, ("độ phức tạp", "complexity", "big-o", "big o")):
        return None
    # Only the clean "two nested loops each running n times" canonical case.
    if _has(low, ("hai vòng lặp lồng", "lồng nhau", "nested")) and "n" in low:
        depth2 = low.count("lồng") >= 1
        want = "o(n^2)"
        hits = []
        for i, ch in enumerate(choices):
            cn = _norm(ch).replace(" ", "")
            if cn in ("o(n^2)", "o(n2)", "o(n²)", "θ(n^2)", "o(n^{2})"):
                hits.append(labels[i])
        if depth2 and len(hits) == 1:
            return _mk("time_complexity_nested_loops", hits[0], "two nested loops -> O(n^2)",
                       choices, labels, conf=0.9)
    return None


# --- Phase 2L.20 additions: more conservative generalized rules ---------------

def try_kinetic_energy(q, choices, labels):
    low = q.lower()
    if not _has(low, ("động năng", "kinetic energy")):
        return None
    m = _first(r"(?:khối lượng|mass|m)\D{0,12}(" + _NUM + r")\s*(?:kg)", q)
    v = _first(r"(?:vận tốc|tốc độ|velocity|speed|v)\D{0,12}(" + _NUM + r")\s*(?:m/s)", q)
    if m is None or v is None:
        return None
    ke = 0.5 * m * v * v
    lbl = _nearest_label(ke, choices, labels, rel_tol=0.02)
    return _mk("kinetic_energy", lbl, f"½mv²={ke:.4g}J", choices, labels,
               extracted={"m": m, "v": v, "KE": ke}) if lbl else None


def try_potential_energy(q, choices, labels):
    low = q.lower()
    if not _has(low, ("thế năng", "potential energy")):
        return None
    m = _first(r"(?:khối lượng|mass|m)\D{0,12}(" + _NUM + r")\s*(?:kg)", q)
    h = _first(r"(?:độ cao|chiều cao|height|h)\D{0,12}(" + _NUM + r")\s*(?:m\b|mét|met)", q)
    g = _first(r"g\s*=\s*(" + _NUM + r")", q) or 9.8
    if m is None or h is None:
        return None
    pe = m * g * h
    lbl = _nearest_label(pe, choices, labels, rel_tol=0.03)
    return _mk("potential_energy", lbl, f"mgh={pe:.4g}J (g={g:g})", choices, labels,
               extracted={"m": m, "g": g, "h": h, "PE": pe}) if lbl else None


def try_uniform_motion(q, choices, labels):
    low = q.lower()
    if not _has(low, ("chuyển động đều", "quãng đường", "uniform motion", "s = v")):
        return None
    if "quãng đường" not in low and "distance" not in low:
        return None
    v = _first(r"(?:vận tốc|tốc độ|speed|velocity)\D{0,12}(" + _NUM + r")\s*(?:m/s|km/h)", q)
    t = _first(r"(?:thời gian|time|trong)\D{0,12}(" + _NUM + r")\s*(?:s\b|giây|giờ|h\b)", q)
    if v is None or t is None:
        return None
    s = v * t
    lbl = _nearest_label(s, choices, labels, rel_tol=0.02)
    return _mk("uniform_motion", lbl, f"s=vt={s:.4g}", choices, labels,
               extracted={"v": v, "t": t, "s": s}) if lbl else None


def try_density(q, choices, labels):
    low = q.lower()
    if not _has(low, ("khối lượng riêng", "mật độ", "density")):
        return None
    m = _first(r"(?:khối lượng|mass)\D{0,12}(" + _NUM + r")\s*(?:kg|g\b)", q)
    vol = _first(r"(?:thể tích|volume)\D{0,12}(" + _NUM + r")\s*(?:m\^?3|m³|cm\^?3|cm³|l\b|lít)", q)
    if m is None or not vol:
        return None
    rho = m / vol
    lbl = _nearest_label(rho, choices, labels, rel_tol=0.02)
    return _mk("density", lbl, f"ρ=m/V={rho:.4g}", choices, labels,
               extracted={"m": m, "V": vol, "rho": rho}) if lbl else None


def try_pressure(q, choices, labels):
    low = q.lower()
    if "áp suất" not in low and "pressure" not in low:
        return None
    f = _first(r"(?:lực|force|f)\D{0,12}(" + _NUM + r")\s*(?:n\b|newton)", q)
    a = _first(r"(?:diện tích|area|a)\D{0,12}(" + _NUM + r")\s*(?:m\^?2|m²)", q)
    if f is None or not a:
        return None
    p = f / a
    lbl = _nearest_label(p, choices, labels, rel_tol=0.02)
    return _mk("pressure", lbl, f"P=F/A={p:.4g}Pa", choices, labels,
               extracted={"F": f, "A": a, "P": p}) if lbl else None


def try_frequency_period(q, choices, labels):
    low = q.lower()
    if not _has(low, ("tần số", "chu kỳ", "chu kì", "frequency", "period")):
        return None
    if "tần số" in low or "frequency" in low:
        T = _first(r"chu k[ỳì]\D{0,12}(" + _NUM + r")\s*(?:s\b|giây)", q)
        if not T:
            return None
        target, unit = 1.0 / T, "Hz"
    else:
        fr = _first(r"tần số\D{0,12}(" + _NUM + r")\s*hz", q)
        if not fr:
            return None
        target, unit = 1.0 / fr, "s"
    lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
    return _mk("frequency_period", lbl, f"f=1/T -> {target:.4g}{unit}", choices, labels) if lbl else None


def try_circle_area_circumference(q, choices, labels):
    low = q.lower()
    if "hình tròn" not in low and "đường tròn" not in low and "circle" not in low:
        return None
    r = _first(r"bán kính\D{0,12}(" + _NUM + r")", q) or _first(r"radius\D{0,12}(" + _NUM + r")", q)
    if not r:
        return None
    if _has(low, ("diện tích", "area")):
        target = math.pi * r * r
        rid = "circle_area"
    elif _has(low, ("chu vi", "circumference")):
        target = 2 * math.pi * r
        rid = "circle_circumference"
    else:
        return None
    lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
    return _mk(rid, lbl, f"{rid}={target:.4g}", choices, labels,
               extracted={"r": r, "result": target}) if lbl else None


def try_triangle_area(q, choices, labels):
    low = q.lower()
    if "tam giác" not in low and "triangle" not in low:
        return None
    if "diện tích" not in low and "area" not in low:
        return None
    base = _first(r"(?:đáy|cạnh đáy|base)\D{0,12}(" + _NUM + r")", q)
    height = _first(r"(?:chiều cao|đường cao|height)\D{0,12}(" + _NUM + r")", q)
    if base is None or height is None:
        return None
    area = 0.5 * base * height
    lbl = _nearest_label(area, choices, labels, rel_tol=0.02)
    return _mk("triangle_area", lbl, f"½·b·h={area:.4g}", choices, labels,
               extracted={"base": base, "height": height, "area": area}) if lbl else None


def try_profit(q, choices, labels):
    low = q.lower()
    if not _has(low, ("lợi nhuận", "profit")):
        return None
    rev = _first(r"(?:doanh thu|revenue)\D{0,12}(" + _NUM + r")", q)
    cost = _first(r"(?:chi phí|tổng chi phí|cost)\D{0,12}(" + _NUM + r")", q)
    if rev is None or cost is None:
        return None
    profit = rev - cost
    lbl = _nearest_label(profit, choices, labels, rel_tol=0.01)
    return _mk("profit", lbl, f"profit=rev-cost={profit:.4g}", choices, labels,
               extracted={"revenue": rev, "cost": cost, "profit": profit}) if lbl else None


def try_roi(q, choices, labels):
    low = q.lower()
    if "roi" not in low and "tỷ suất lợi nhuận" not in low and "return on investment" not in low:
        return None
    gain = _first(r"(?:lợi nhuận|gain|lãi)\D{0,12}(" + _NUM + r")", q)
    cost = _first(r"(?:đầu tư|vốn|investment|cost)\D{0,12}(" + _NUM + r")", q)
    if gain is None or not cost:
        return None
    roi = gain / cost * 100.0
    for target in (roi, roi / 100.0):
        lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
        if lbl:
            return _mk("roi", lbl, f"ROI={roi:.4g}%", choices, labels,
                       extracted={"gain": gain, "cost": cost, "roi_pct": roi})
    return None


def try_straight_line_depreciation(q, choices, labels):
    low = q.lower()
    if not _has(low, ("khấu hao", "depreciation")):
        return None
    cost = _first(r"(?:nguyên giá|giá trị|cost)\D{0,12}(" + _NUM + r")", q)
    salvage = _first(r"(?:giá trị thanh lý|thu hồi|salvage|residual)\D{0,12}(" + _NUM + r")", q) or 0.0
    life = _first(r"(?:tuổi thọ|thời gian sử dụng|life|năm)\D{0,12}(" + _NUM + r")", q)
    if cost is None or not life:
        return None
    dep = (cost - salvage) / life
    lbl = _nearest_label(dep, choices, labels, rel_tol=0.02)
    return _mk("straight_line_depreciation", lbl, f"(cost-salvage)/life={dep:.4g}",
               choices, labels, extracted={"cost": cost, "salvage": salvage, "life": life}) if lbl else None


def try_moles(q, choices, labels):
    low = q.lower()
    if "số mol" not in low and "mol" not in low and "mole" not in low:
        return None
    # Mass = a number before a mass unit that is NOT "g/mol" (molar mass).
    mass = _first(r"(" + _NUM + r")\s*(?:gam|gram|g)\b(?!\s*/?\s*mol)", q)
    molar = (_first(r"(" + _NUM + r")\s*g\s*/\s*mol", q)
             or _first(r"(?:khối lượng mol|phân tử khối|molar mass)\D{0,12}(" + _NUM + r")", q))
    if mass is None or not molar:
        return None
    n = mass / molar
    lbl = _nearest_label(n, choices, labels, rel_tol=0.02)
    return _mk("moles", lbl, f"n=m/M={n:.4g} mol", choices, labels,
               extracted={"mass": mass, "molar_mass": molar, "moles": n}) if lbl else None


def try_concentration(q, choices, labels):
    low = q.lower()
    if not _has(low, ("nồng độ mol", "molarity", "nồng độ (mol", "concentration")):
        return None
    n = (_first(r"(" + _NUM + r")\s*mol(?!\s*/)", q)        # "2 mol" (number before)
         or _first(r"số mol\D{0,12}(" + _NUM + r")", q))    # "số mol là 2"
    vol = _first(r"(?:thể tích|volume)\D{0,12}(" + _NUM + r")\s*(?:l\b|lít|liter)", q)
    if n is None or not vol:
        return None
    c = n / vol
    lbl = _nearest_label(c, choices, labels, rel_tol=0.02)
    return _mk("concentration", lbl, f"C=n/V={c:.4g} M", choices, labels,
               extracted={"moles": n, "volume": vol, "C": c}) if lbl else None


# --- Phase 2L.21 additions ----------------------------------------------------

def try_capacitor_series_parallel(q, choices, labels):
    low = q.lower()
    if not _has(low, ("tụ điện", "điện dung", "capacitor", "capacitance")):
        return None
    if not _has(low, ("tương đương", "equivalent")):     # must ask equivalent capacitance
        return None
    vals = [v for v in (_to_float(x) for x in
                        re.findall(r"(" + _NUM + r")\s*(?:µf|μf|uf|nf|pf|f\b|fara)", low)) if v]
    if len(vals) < 2:
        return None
    if _has(low, ("nối tiếp", "mắc nối tiếp", "series")) and all(v > 0 for v in vals):
        target = 1.0 / sum(1.0 / v for v in vals)
        kind = "series"
    elif _has(low, ("song song", "parallel")):
        target = sum(vals)
        kind = "parallel"
    else:
        return None
    lbl = _nearest_label(target, choices, labels, rel_tol=0.02)
    return _mk("capacitor_series_parallel", lbl, f"{kind} C_eq={target:.4g}", choices, labels,
               extracted={"caps": vals, "C_eq": target, "kind": kind}) if lbl else None


def try_mean_median_mode(q, choices, labels):
    low = q.lower()
    wants_mean = _has(low, ("trung bình cộng", "số trung bình", "giá trị trung bình", "mean"))
    wants_median = _has(low, ("trung vị", "median"))
    wants_mode = _has(low, ("yếu vị", "mốt", "mode"))
    if sum([wants_mean, wants_median, wants_mode]) != 1:   # exactly one statistic
        return None
    # Require an explicit data list after a marker, to avoid grabbing stray numbers.
    m = re.search(r"(?:dãy|tập|các giá trị|bộ số|dữ liệu|tập dữ liệu|dataset)[^0-9]{0,12}"
                  r"([-+0-9.,\s]+)", q, re.IGNORECASE)
    data = _nums(m.group(1)) if m else []
    if len(data) < 3:
        return None
    if wants_mean:
        target = sum(data) / len(data)
        rid = "mean"
    elif wants_median:
        s = sorted(data)
        n = len(s)
        target = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
        rid = "median"
    else:
        from collections import Counter as _C
        ct = _C(data)
        top = ct.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            return None                                   # no unique mode
        target = top[0][0]
        rid = "mode"
    lbl = _nearest_label(target, choices, labels, rel_tol=0.01)
    return _mk(rid, lbl, f"{rid}={target:.4g}", choices, labels,
               extracted={"data": data, rid: target}) if lbl else None


def try_break_even_quantity(q, choices, labels):
    low = q.lower()
    if not _has(low, ("hòa vốn", "điểm hòa vốn", "break-even", "break even", "breakeven")):
        return None
    fixed = _first(r"(?:chi phí cố định|định phí|fixed cost)\D{0,15}(" + _NUM + r")", q)
    price = _first(r"(?:giá bán|đơn giá|price)\D{0,15}(" + _NUM + r")", q)
    var = _first(r"(?:chi phí biến đổi(?: trên| mỗi)?|biến phí|variable cost)\D{0,15}(" + _NUM + r")", q)
    if fixed is None or price is None or var is None or price <= var:
        return None
    qbe = fixed / (price - var)
    lbl = _nearest_label(qbe, choices, labels, rel_tol=0.02)
    return _mk("break_even_quantity", lbl, f"Q*=FC/(P-VC)={qbe:.4g}", choices, labels,
               extracted={"fixed": fixed, "price": price, "var": var, "Q_be": qbe}) if lbl else None


def try_binary_decimal(q, choices, labels):
    low = q.lower()
    # decimal -> binary OR binary -> decimal, whichever is asked.
    if _has(low, ("sang nhị phân", "thành nhị phân", "to binary", "ra nhị phân")):
        m = re.search(r"(?:số|thập phân|decimal)\D{0,8}(\d+)", q) or re.search(r"\b(\d+)\b", q)
        if not m:
            return None
        target = bin(int(m.group(1)))[2:]
        hits = [labels[i] for i, c in enumerate(choices)
                if re.sub(r"\D", "", str(c)) == target]
        if len(hits) == 1:
            return _mk("binary_decimal", hits[0], f"dec->bin={target}", choices, labels)
    elif _has(low, ("sang thập phân", "thành thập phân", "to decimal", "ra thập phân")):
        m = re.search(r"(?:nhị phân|binary)\D{0,8}([01]{2,})", q) or re.search(r"\b([01]{2,})\b", q)
        if not m:
            return None
        target = float(int(m.group(1), 2))
        lbl = _exact_label(target, choices, labels)
        if lbl:
            return _mk("binary_decimal", lbl, f"bin->dec={int(target)}", choices, labels)
    return None


def try_cache_amat(q, choices, labels):
    low = q.lower()
    if not _has(low, ("cache", "bộ nhớ đệm")):
        return None
    if not _has(low, ("thời gian truy cập trung bình", "average access", "amat",
                      "thời gian truy cập bộ nhớ")):
        return None
    hit_time = _first(r"(?:thời gian (?:trúng|hit)|hit time)\D{0,12}(" + _NUM + r")", q)
    miss_rate = _first(r"(?:tỉ lệ trượt|tỷ lệ trượt|miss rate)\D{0,12}(" + _NUM + r")\s*%?", q)
    penalty = _first(r"(?:hình phạt trượt|miss penalty|thời gian trượt)\D{0,12}(" + _NUM + r")", q)
    if hit_time is None or miss_rate is None or penalty is None:
        return None
    mr = miss_rate / 100.0 if miss_rate > 1 else miss_rate
    amat = hit_time + mr * penalty
    lbl = _nearest_label(amat, choices, labels, rel_tol=0.02)
    return _mk("cache_amat", lbl, f"AMAT=hit+miss·penalty={amat:.4g}", choices, labels,
               extracted={"hit_time": hit_time, "miss_rate": mr, "penalty": penalty}) if lbl else None


_NEW_RULES = (
    try_determinant_2x2,
    try_ohms_law,
    try_electric_power,
    try_resistor_series_parallel,
    try_wave_speed,
    try_pythagorean_distance,
    try_matrix_vector_multiply,
    try_laplace_polynomial,
    try_expected_value,
    try_mc_vs_average_cost,
    try_elasticity_revenue_direction,
    try_tax_supply_shift,
    try_cache_hit_rate,
    try_time_complexity_nested_loops,
    # Phase 2L.20
    try_kinetic_energy,
    try_potential_energy,
    try_uniform_motion,
    try_density,
    try_pressure,
    try_frequency_period,
    try_circle_area_circumference,
    try_triangle_area,
    try_profit,
    try_roi,
    try_straight_line_depreciation,
    try_moles,
    try_concentration,
    # Phase 2L.21
    try_capacitor_series_parallel,
    try_mean_median_mode,
    try_break_even_quantity,
    try_binary_decimal,
    try_cache_amat,
)


def solve_formula_bank_sample(sample: dict):
    """Return a FormulaBankResult or None. Delegates to calc + concept, then new rules."""
    choices = sample.get("choices", []) or []
    if not choices:
        return None
    labels = labels_for(len(choices))

    # 1) Existing deterministic calculation families.
    calc = solve_calculation_sample(sample, labels)
    if calc.matched and calc.safe_to_override and calc.answer in labels:
        return FormulaBankResult(f"calc:{calc.method}", calc.answer, calc.confidence,
                                 calc.rationale, True, "", calc.extracted_values)
    # 2) Existing concept rules (paging, mc_vs_avc).
    con = solve_concept_sample(sample, labels)
    if con.matched and con.safe_to_override and con.answer in labels:
        return FormulaBankResult(f"concept:{con.rule_id}", con.answer, 0.97, con.reason,
                                 True, con.matched_option_text, {})
    # 3) New generalized formula/concept-bank rules.
    q = str(sample.get("question", "") or "")
    for rule in _NEW_RULES:
        try:
            res = rule(q, choices, labels)
        except Exception:
            res = None
        if res is not None and res.safe_to_override and res.selected_answer in labels:
            return res
    return None


# --- Formula HINT detection (log-only; never an answer) -----------------------
# Medium/high-risk families detectable by keyword but not safely auto-solvable.
# These produce a non-binding HINT for the prompt/log — NEVER a patched answer.
_HINT_FAMILIES = (
    ("capacitor_series_parallel", "high", ("tụ điện", "điện dung", "capacitor", "capacitance"),
     "Possible family: capacitor series/parallel. Series: 1/C=Σ1/Ci; parallel: C=ΣCi. "
     "Use only if the question clearly asks for equivalent capacitance."),
    ("inductor_series_parallel", "high", ("cuộn cảm", "độ tự cảm", "inductor", "inductance"),
     "Possible family: inductor series/parallel. Series: L=ΣLi; parallel: 1/L=Σ1/Li."),
    ("ideal_gas_law", "high", ("khí lý tưởng", "pv=nrt", "ideal gas"),
     "Possible family: ideal gas law PV=nRT. Use only if all values + units are explicit."),
    ("bayes_theorem", "high", ("bayes", "xác suất hậu nghiệm", "posterior"),
     "Possible family: Bayes' theorem. Use only if all priors/likelihoods are explicit."),
    ("quadratic_roots", "medium", ("phương trình bậc hai", "nghiệm của phương trình", "quadratic"),
     "Possible family: quadratic roots x=(-b±√(b²-4ac))/2a."),
    ("subnet_hosts", "medium", ("subnet", "mặt nạ mạng", "/24", "/26", "usable hosts", "địa chỉ host"),
     "Possible family: IPv4 subnet usable hosts = 2^(32-prefix) - 2."),
    ("gdp_expenditure", "medium", ("gdp", "tổng sản phẩm quốc nội", "c + i + g"),
     "Possible family: GDP expenditure identity Y = C + I + G + (X − M)."),
    ("normalization_forms", "medium", ("chuẩn hóa", "1nf", "2nf", "3nf", "dạng chuẩn"),
     "Possible family: DB normal forms (1NF atomic; 2NF no partial dep; 3NF no transitive dep)."),
    ("database_keys", "medium", ("khóa chính", "khóa ngoại", "khóa dự tuyển", "primary key",
                                 "foreign key", "candidate key"),
     "Possible family: DB key definitions (primary/candidate/foreign key)."),
)


def detect_formula_hints(sample: dict) -> list:
    """Return non-binding hint dicts for detected families (log/prompt only).

    Each hint: {detected_family, risk_level, hint, safe_to_override}. A SAFE
    deterministic match (from ``solve_formula_bank_sample``) is reported with
    ``safe_to_override=True``; keyword-only medium/high-risk detections are
    ``safe_to_override=False`` (hint only — never patches an answer).
    """
    q = str(sample.get("question", "") or "").lower()
    hints = []
    safe = solve_formula_bank_sample(sample)
    if safe is not None:
        hints.append({"detected_family": safe.rule_id, "risk_level": "low",
                      "hint": safe.reason, "safe_to_override": True})
    for fam, risk, kws, text in _HINT_FAMILIES:
        if _has(q, kws):
            hints.append({"detected_family": fam, "risk_level": risk,
                          "hint": text, "safe_to_override": False})
    return hints
