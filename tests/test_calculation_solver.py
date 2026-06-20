"""Tests for the deterministic calculation helper (no network, no LLM).

Runnable with pytest, or standalone: ``python tests/test_calculation_solver.py``.
Synthetic samples only — no qid-specific logic is tested or relied upon.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.calculation_solver import solve_calculation_sample  # noqa: E402
from src.labels import labels_for  # noqa: E402


def _solve(question, choices):
    labels = labels_for(len(choices))
    return solve_calculation_sample({"qid": "x", "question": question, "choices": choices}, labels), labels


def test_exponential_decay():
    q = r"nồng độ giảm theo $ \frac{dB}{dt} = -k B $, ban đầu $ B_0 $, nồng độ tại t?"
    choices = [r"$ B(t) = B_0 e^{-kt} $", r"$ B(t) = B_0 e^{kt} $",
               r"$ B(t) = B_0 (1 - kt) $", r"$ B(t) = \frac{B_0}{1 + kt} $"]
    r, _ = _solve(q, choices)
    assert r.matched and r.answer == "A" and r.method == "exponential_decay"


def test_hess_law_sum():
    q = (r"Xét: X -> Y với $ \Delta H_1 = -80 $ kJ/mol; Y -> Z với "
         r"$ \Delta H_2 = -30 $ kJ/mol. Theo định luật Hess, $ \Delta H_3 $?")
    choices = ["-110 kJ/mol", "-80 kJ/mol", "-30 kJ/mol", "0 kJ/mol"]
    r, _ = _solve(q, choices)
    assert r.matched and r.answer == "A"  # -80 + -30 = -110


def test_cylinder_fill_rate_nearest():
    q = ("Một bể chứa hình trụ được đổ đầy nước với tốc độ 50 cm³/s. Bán kính của "
         "bể là 5 cm. Tốc độ tăng của độ cao mực nước là bao nhiêu?")
    choices = ["0.2 cm/s", "0.4 cm/s", "0.6 cm/s", "0.8 cm/s"]
    r, _ = _solve(q, choices)
    # dh/dt = 50/(pi*25) = 0.6366 -> nearest 0.6 (label C)
    assert r.matched and r.answer == "C" and r.method == "cylinder_rate"


def test_price_elasticity_positive_choices_uses_abs():
    q = ("Tại mức giá 5 đô la, lượng cầu là 150 đơn vị; tại mức giá 3 đô la, lượng "
         "cầu là 250 đơn vị. Độ co giãn của cầu theo giá giữa hai điểm là bao nhiêu?")
    choices = ["0.5", "1.0", "2.0", "2.5"]
    r, _ = _solve(q, choices)
    assert r.matched and r.answer == "B"  # |E_midpoint| = 1.0


def test_price_elasticity_signed_choices():
    q = ("Cửa hàng tăng giá từ 2,00 đô la lên 2,50 đô la, và lượng cầu giảm từ 100 "
         "đơn vị xuống 80 đơn vị. Sử dụng công thức trung điểm, độ co giãn của cầu?")
    choices = ["-0,5", "-1,0", "-1,5", "-2,0"]
    r, _ = _solve(q, choices)
    assert r.matched and r.answer == "B"  # E_midpoint = -1.0


def test_expected_distinct_symbolic():
    q = ("Mỗi $X_i$ phân bố đều trên {1..k}, Y là số giá trị khác nhau trong n lần "
         "rút. Giá trị kỳ vọng của Y là bao nhiêu?")
    choices = ["k(1 - (1 - 1/k)^n)", "k", "n", "k/n", "n/k"]
    r, _ = _solve(q, choices)
    assert r.matched and r.answer == "A" and r.method == "expected_distinct"


def test_resistor_cut_parallel_4I():
    q = ("Một điện trở R nối với nguồn V, dòng điện I. Điện trở được cắt thành hai "
         "phần bằng nhau và nối song song với nguồn V. Dòng điện I' là bao nhiêu?")
    choices = [r"$ I' = \frac{I}{2} $", r"$ I' = \frac{I}{4} $", r"$ I' = I $",
               r"$ I' = 2I $", r"$ I' = 4I $"]
    r, _ = _solve(q, choices)
    assert r.matched and r.answer == "E" and r.method == "resistor_cut_parallel"


def test_ambiguous_returns_no_match():
    r, _ = _solve("Thủ đô của Pháp là gì?", ["Paris", "Lyon", "Nice", "Hue"])
    assert not r.matched and r.answer is None and not r.safe_to_override


def test_never_returns_label_outside_choices():
    # Cylinder result not near any choice -> no match (no invalid label).
    q = ("Một bể hình trụ đổ nước 50 cm³/s, bán kính 5 cm. Tốc độ tăng độ cao mực "
         "nước là bao nhiêu?")
    choices = ["100 cm/s", "200 cm/s"]   # 0.6366 not near either
    r, labels = _solve(q, choices)
    assert (r.answer is None) or (r.answer in labels)
    assert not r.matched


def test_no_match_returns_valid_or_none_for_all_families():
    # A clearly non-calculation prompt must never fabricate a label.
    for choices in (["a", "b"], ["x", "y", "z", "w"]):
        r, labels = _solve("Một câu hỏi không phải tính toán.", choices)
        assert not r.matched and (r.answer is None or r.answer in labels)


def test_decay_ambiguous_two_matches_no_override():
    # Two choices both contain e^{-kt} -> ambiguous -> no match (conservative).
    q = r"$ \frac{dN}{dt} = -k N $, ban đầu $ N_0 $?"
    choices = [r"$ N_0 e^{-kt} $", r"$ N_0 e^{-kt} $", "other", "other2"]
    r, _ = _solve(q, choices)
    assert not r.matched


def test_gdp_deflator_inflation():
    q = ("Trong một năm, GDP danh nghĩa của một quốc gia là 500 tỷ USD và GDP thực "
         "tế là 400 tỷ USD. Nếu chỉ số giá GDP của năm trước là 100, thì tỷ lệ lạm "
         "phát cho năm hiện tại là bao nhiêu?")
    r, _ = _solve(q, ["20%", "25%", "30%", "15%"])
    assert r.matched and r.answer == "B" and r.method == "gdp_inflation"  # 25%


def test_sphere_inflation_rate_pi_choices():
    q = ("Một quả bóng hình cầu được bơm khí, thể tích $V = \\frac{4}{3}\\pi r^3$. "
         "Bán kính tăng với tốc độ 2 cm/s. Tốc độ thay đổi của thể tích khi bán "
         "kính là 3 cm là bao nhiêu?")
    choices = [r"$ 72\pi $", r"$ 36\pi $", r"$ 18\pi $", r"$ 9\pi $"]
    r, _ = _solve(q, choices)  # dV/dt = 4π·9·2 = 72π
    assert r.matched and r.answer == "A" and r.method == "sphere_rate"


def test_exponential_growth():
    q = r"Quần thể tăng theo $ \frac{dN}{dt} = k N $, ban đầu $ N_0 $. N tại t?"
    choices = [r"$ N_0 e^{kt} $", r"$ N_0 e^{-kt} $", r"$ N_0 (1+kt) $", "khác"]
    r, _ = _solve(q, choices)
    assert r.matched and r.answer == "A" and r.method == "exponential_growth"


def test_hess_three_steps_sum():
    q = (r"X->Y $\Delta H_1 = -50$; Y->Z $\Delta H_2 = -30$; Z->W $\Delta H_3 = -20$. "
         r"Theo Hess, ΔH cho X->W?")
    r, _ = _solve(q, ["-100 kJ/mol", "-80 kJ/mol", "-50 kJ/mol", "0 kJ/mol"])
    assert r.matched and r.answer == "A"  # -50 + -30 + -20 = -100


def test_comma_decimal_and_percent_parsing():
    from src.calculation_solver import _to_float
    assert _to_float("2,5") == 2.5
    assert _to_float("-1,0") == -1.0
    assert _to_float("20%") == 20.0
    assert _to_float("$ 0.25 $ cm/s") == 0.25


def test_no_qid_in_solver_logic_or_output():
    # Same content under different qids (incl. a public-looking one) => same result.
    q = ("Một bể chứa hình trụ đổ nước 50 cm³/s, bán kính 5 cm. Tốc độ tăng độ cao?")
    ch = ["0.2 cm/s", "0.4 cm/s", "0.6 cm/s", "0.8 cm/s"]
    labels = labels_for(len(ch))
    r1 = solve_calculation_sample({"qid": "test_0009", "question": q, "choices": ch}, labels)
    r2 = solve_calculation_sample({"qid": "zzz_99999", "question": q, "choices": ch}, labels)
    r3 = solve_calculation_sample({"question": q, "choices": ch}, labels)  # no qid
    assert r1.answer == r2.answer == r3.answer == "C"


def test_source_has_no_qid_usage_or_unsafe_eval():
    import re as _re
    src = Path(__file__).resolve().parent.parent.joinpath("src/calculation_solver.py").read_text()
    # No code that READS a qid (prose in comments mentioning "qid" is fine).
    for pat in (r'\[\s*["\']qid', r'\.get\(\s*["\']qid', r'qid\s*==', r'==\s*qid'):
        assert not _re.search(pat, src), f"qid usage found: {pat}"
    # No unsafe dynamic execution.
    assert "eval(" not in src and "exec(" not in src and "__import__" not in src


def test_extracted_values_recorded():
    q = "Một bể hình trụ đổ nước 50 cm³/s, bán kính 5 cm. Tốc độ tăng độ cao?"
    r, _ = _solve(q, ["0.2", "0.4", "0.6", "0.8"])
    assert r.matched and "dhdt" in r.extracted_values and r.formula_family == "related_rates"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
