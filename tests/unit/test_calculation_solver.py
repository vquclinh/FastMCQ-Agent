"""Tests for the deterministic calculation helper (no network, no LLM).

Runnable with pytest, or standalone: ``python tests/test_calculation_solver.py``.
Synthetic samples only — no qid-specific logic is tested or relied upon.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
    src = Path(__file__).resolve().parents[2].joinpath("src/calculation_solver.py").read_text()
    # No code that READS a qid (prose in comments mentioning "qid" is fine).
    for pat in (r'\[\s*["\']qid', r'\.get\(\s*["\']qid', r'qid\s*==', r'==\s*qid'):
        assert not _re.search(pat, src), f"qid usage found: {pat}"
    # No unsafe dynamic execution.
    assert "eval(" not in src and "exec(" not in src and "__import__" not in src


def test_extracted_values_recorded():
    q = "Một bể hình trụ đổ nước 50 cm³/s, bán kính 5 cm. Tốc độ tăng độ cao?"
    r, _ = _solve(q, ["0.2", "0.4", "0.6", "0.8"])
    assert r.matched and "dhdt" in r.extracted_values and r.formula_family == "related_rates"


# --- Phase 2L.8 generic families --------------------------------------------

def test_kepler_period_ratio():
    q = ("Theo định luật Kepler III, một hành tinh có bán kính quỹ đạo gấp 4 lần "
         "Trái Đất thì chu kỳ quỹ đạo gấp bao nhiêu lần?")
    r, _ = _solve(q, ["2 lần", "4 lần", "8 lần", "16 lần"])  # 4^1.5 = 8
    assert r.matched and r.answer == "C" and r.method == "kepler_third_law"
    assert r.formula_family == "astronomy" and r.safe_to_override


def test_kepler_absolute_period():
    q = ("Một vệ tinh có chu kỳ quỹ đạo là 2 năm. Nếu bán kính quỹ đạo tăng gấp 4 "
         "lần thì chu kỳ quỹ đạo mới là bao nhiêu? (định luật Kepler)")
    r, _ = _solve(q, ["8 năm", "16 năm", "4 năm", "32 năm"])  # 2 * 8 = 16
    assert r.matched and r.answer == "B" and r.extracted_values["T_old"] == 2.0


def test_kepler_declines_without_factor():
    q = "Hành tinh có chu kỳ quỹ đạo là 2 năm. Chu kỳ này bằng bao nhiêu ngày?"
    r, _ = _solve(q, ["730 ngày", "365 ngày", "100 ngày", "50 ngày"])
    assert not r.matched and not r.safe_to_override


def test_gamma_fraction_of_c():
    q = ("Theo thuyết tương đối, một vật chuyển động với vận tốc 0,6c. Hệ số giãn "
         "nở thời gian gamma là bao nhiêu?")
    r, _ = _solve(q, ["1,25", "1,33", "1,5", "2,0"])  # 1/sqrt(1-0.36)=1.25
    assert r.matched and r.answer == "A" and r.method == "relativistic_gamma"
    assert r.formula_family == "physics"


def test_gamma_percent_of_c():
    q = ("Trong thuyết tương đối, một hạt chuyển động bằng 80% tốc độ ánh sáng. Hệ "
         "số Lorentz gamma của hạt là bao nhiêu?")
    r, _ = _solve(q, ["1,67", "1,25", "2,0", "1,33"])  # 1/sqrt(1-0.64)=1.667
    assert r.matched and r.answer == "A"


def test_gamma_declines_without_speed():
    r, _ = _solve("Thuyết tương đối hẹp của Einstein nói về điều gì?",
                  ["Không gian", "Thời gian", "Cả hai", "Khác"])
    assert not r.matched


def test_money_multiplier_percent():
    q = "Nếu tỷ lệ dự trữ bắt buộc là 10%, số nhân tiền tối đa là bao nhiêu?"
    r, _ = _solve(q, ["5", "10", "20", "100"])  # 1/0.10 = 10
    assert r.matched and r.answer == "B" and r.method == "money_multiplier"


def test_money_multiplier_other_ratio():
    q = "Với tỷ lệ dự trữ bắt buộc 25%, số nhân tiền là bao nhiêu?"
    r, _ = _solve(q, ["2", "3", "4", "5"])  # 1/0.25 = 4
    assert r.matched and r.answer == "C"


def test_money_multiplier_declines_no_ratio():
    r, _ = _solve("Số nhân tiền phụ thuộc vào yếu tố nào?",
                  ["Lãi suất", "Tỷ lệ dự trữ", "Lạm phát", "Tỷ giá"])
    assert not r.matched


def test_t_statistic_basic():
    q = ("Một mẫu có trung bình mẫu là 52, độ lệch chuẩn là 5, cỡ mẫu là 25. Kiểm "
         "định giả thuyết trung bình tổng thể là 50. Giá trị thống kê t là bao nhiêu?")
    r, _ = _solve(q, ["1,0", "2,0", "2,5", "4,0"])  # (52-50)/(5/5)=2
    assert r.matched and r.answer == "B" and r.method == "t_statistic"
    assert r.formula_family == "statistics"


def test_t_statistic_negative():
    q = ("Trung bình mẫu là 48, độ lệch chuẩn là 4, cỡ mẫu là 16. Kiểm định giả "
         "thuyết trung bình tổng thể là 50. Tính giá trị thống kê t.")
    r, _ = _solve(q, ["-2,0", "-1,0", "2,0", "1,0"])  # (48-50)/(4/4)=-2
    assert r.matched and r.answer == "A"


def test_t_statistic_declines_missing_value():
    q = "Kiểm định giả thuyết với trung bình mẫu là 52 và cỡ mẫu là 25. Giá trị t?"
    r, _ = _solve(q, ["1,0", "2,0", "2,5", "4,0"])  # no s -> decline
    assert not r.matched


def test_acid_base_volume():
    q = "Cần bao nhiêu mL dung dịch NaOH 0,1 M để trung hòa 50 mL dung dịch HCl 0,2 M?"
    r, _ = _solve(q, ["50 mL", "100 mL", "150 mL", "25 mL"])  # 0.2*50/0.1 = 100
    assert r.matched and r.answer == "B" and r.method == "acid_base_neutralization"
    assert r.formula_family == "chemistry"


def test_acid_base_volume_other():
    q = "Thể tích NaOH 0,5 M cần để trung hòa 100 mL HCl 0,25 M là bao nhiêu?"
    r, _ = _solve(q, ["25 mL", "50 mL", "100 mL", "200 mL"])  # 0.25*100/0.5 = 50
    assert r.matched and r.answer == "B"


def test_acid_base_declines_non_neutralization():
    r, _ = _solve("HCl là một axit mạnh hay yếu?", ["Mạnh", "Yếu", "Trung tính", "Bazơ"])
    assert not r.matched


def test_supply_demand_shortage():
    q = ("Cho hàm cầu Qd = 100 - 2P và hàm cung Qs = 20 + 3P. Nếu chính phủ áp giá "
         "trần là 10, mức thiếu hụt trên thị trường là bao nhiêu?")
    r, _ = _solve(q, ["10", "20", "30", "40"])  # Qd=80 Qs=50 shortage=30
    assert r.matched and r.answer == "C" and r.method == "supply_demand_gap"


def test_supply_demand_surplus():
    q = ("Hàm cầu Qd = 120 - 4P, hàm cung Qs = 30 + 2P. Với giá sàn 20, mức dư thừa "
         "trên thị trường là bao nhiêu?")
    r, _ = _solve(q, ["10", "30", "40", "70"])  # Qd=40 Qs=70 surplus=30
    assert r.matched and r.answer == "B"


def test_supply_demand_declines_no_equations():
    q = "Khi giá trần thấp hơn giá cân bằng, thị trường sẽ thiếu hụt. Điều này đúng không?"
    r, _ = _solve(q, ["Đúng", "Sai"])
    assert not r.matched


def test_cobb_douglas_isoquant():
    q = ("Hàm sản xuất Q = 2\\sqrt{KL}. Để đạt sản lượng 12 trên đường đẳng lượng, "
         "tổ hợp đầu vào nào sau đây phù hợp?")
    r, _ = _solve(q, ["K=2, L=4", "K=4, L=9", "K=3, L=3", "K=5, L=5"])  # 2*sqrt(36)=12
    assert r.matched and r.answer == "B" and r.method == "cobb_douglas_isoquant"


def test_cobb_douglas_pair_tuple_form():
    q = "Với hàm sản xuất Q = √(KL), sản lượng 6 đạt được tại tổ hợp nào? (đẳng lượng)"
    r, _ = _solve(q, ["(2, 8)", "(3, 10)", "(4, 9)", "(1, 5)"])  # sqrt(36)=6 -> (4,9)
    assert r.matched and r.answer == "C"


def test_cobb_douglas_declines_ambiguous():
    # Two pairs satisfy Q -> ambiguous -> decline.
    q = "Hàm sản xuất Q = 2\\sqrt{KL}, sản lượng 12 đạt tại tổ hợp nào? (đẳng lượng)"
    r, _ = _solve(q, ["K=4, L=9", "K=9, L=4", "K=1, L=1", "K=2, L=2"])  # both first two -> 12
    assert not r.matched


def test_modular_power():
    r, _ = _solve("Tìm số dư khi chia 2^10 cho 7.", ["1", "2", "3", "4"])  # 1024%7=2
    assert r.matched and r.answer == "B" and r.method == "modular_arithmetic"
    assert r.formula_family == "number_theory"


def test_modular_power_mod_keyword():
    r, _ = _solve("Giá trị của 7^100 mod 5 là bao nhiêu?", ["0", "1", "2", "3"])  # =1
    assert r.matched and r.answer == "B"


def test_modular_declines_without_modulus():
    r, _ = _solve("Lũy thừa 2^10 bằng bao nhiêu?", ["512", "1024", "2048", "256"])
    assert not r.matched


def test_new_families_no_qid_effect():
    q = "Nếu tỷ lệ dự trữ bắt buộc là 10%, số nhân tiền tối đa là bao nhiêu?"
    ch = ["5", "10", "20", "100"]
    L = labels_for(len(ch))
    r1 = solve_calculation_sample({"qid": "test_0055", "question": q, "choices": ch}, L)
    r2 = solve_calculation_sample({"qid": "private_zzz", "question": q, "choices": ch}, L)
    r3 = solve_calculation_sample({"question": q, "choices": ch}, L)
    assert r1.answer == r2.answer == r3.answer == "B"


# --- Phase 2L.14B: relativity fix + new generic families ---------------------

def test_gamma_still_fires_when_gamma_asked():
    q = "Một hạt chuyển động với tốc độ 0,6c. Hệ số Lorentz của hạt là bao nhiêu?"
    r, _ = _solve(q, ["1,25", "1,33", "1,5", "2,0"])
    assert r.matched and r.answer == "A" and r.method == "relativistic_gamma"


def test_gamma_does_not_fire_for_momentum():
    # The 2L.13 bug: gamma over-matched a momentum question. Must NOT answer γ now.
    q = ("Một hạt đang chuyển động với tốc độ 0,6c. Động lượng tương đối p của hạt "
         "là bao nhiêu nếu khối lượng nghỉ của nó là m₀?")
    r, _ = _solve(q, ["0,6 m₀c", "0,75 m₀c", "1,25 m₀c", "1,0 m₀c"])
    assert r.method != "relativistic_gamma"


def test_relativistic_momentum_075_m0c():
    q = ("Một hạt chuyển động với tốc độ 0,6c, khối lượng nghỉ m₀. Động lượng tương "
         "đối p của hạt là bao nhiêu?")
    r, _ = _solve(q, ["0,6 m₀c", "0,75 m₀c", "1,25 m₀c", "1,0 m₀c"])  # γβ=1.25*0.6=0.75
    assert r.matched and r.answer == "B" and r.method == "relativistic_momentum"


def test_cobb_douglas_scaling_half_output():
    q = ("Hàm sản xuất Q = 2K^0.5L^0.5. Tại điểm K=4, L=9, nếu sản lượng giảm một "
         "nửa thì tổ hợp đầu vào nào sau đây phù hợp?")  # Q0=12, half=6 -> 2√(KL)=6 -> (1,9)
    r, _ = _solve(q, ["K=1, L=9", "K=4, L=9", "K=5, L=5", "K=2, L=2"])
    assert r.matched and r.answer == "A" and r.method == "cobb_douglas_isoquant_scaling"


def test_t_statistic_one_sample_interval():
    q = ("Kiểm định giả thuyết trung bình tổng thể là 50. Trung bình mẫu là 52, độ "
         "lệch chuẩn 5, cỡ mẫu 25. Giá trị thống kê t nằm trong khoảng nào?")  # t=2.0
    r, _ = _solve(q, ["nhỏ hơn 1,0", "1,0 đến 1,5", "2,0 đến 2,5", "lớn hơn 2,5"])
    assert r.matched and r.answer == "C" and r.method == "t_statistic_one_sample"


def test_z_score_one_sample_numeric():
    q = ("Kiểm định z: độ lệch chuẩn của quần thể là 10. Trung bình mẫu là 105, "
         "trung bình tổng thể giả thuyết là 100, cỡ mẫu 4. Giá trị thống kê z?")  # z=1.0
    r, _ = _solve(q, ["0,5", "1,0", "2,0", "2,5"])
    assert r.matched and r.answer == "B" and r.method == "z_score_one_sample"


def test_supply_demand_price_control_shortage():
    q = ("Hàm cầu Qd = 100 - 2P, hàm cung Qs = 30P - 50. Chính phủ áp giá trần 4. "
         "Mức thiếu hụt là bao nhiêu?")  # Qd=92, Qs=70 -> shortage 22
    r, _ = _solve(q, ["10", "22", "30", "40"])
    assert r.matched and r.answer == "B" and r.method == "supply_demand_price_control"


def test_henderson_hasselbalch_buffer_decimal_comma():
    q = ("Một dung dịch đệm có pKa = 4,74. Nồng độ bazơ liên hợp là 0,1 M và nồng độ "
         "axit là 0,1 M. Tính pH của dung dịch đệm.")  # pH = 4,74
    r, _ = _solve(q, ["3,74", "4,74", "5,74", "6,74"])
    assert r.matched and r.answer == "B" and r.method == "henderson_hasselbalch_buffer"


def test_linear_total_equation_y_zero():
    q = ("E1 = 3000 + 100y, E2 = 4000 + 150y, E3 = 5000 + 200y, E4 = 6000 + 250y. "
         "Tổng của bốn phương trình bằng 18000. Tìm y.")  # y = 0
    r, _ = _solve(q, ["0", "2", "5", "10"])
    assert r.matched and r.answer == "A" and r.method == "linear_total_equation"


def test_nuclear_binding_energy_release():
    q = ("Một hạt nhân có số khối 200 bị phân hạch. Năng lượng liên kết trên mỗi "
         "nucleon trước là 7,5 MeV và sau là 8,5 MeV. Năng lượng giải phóng là?")  # 200*1=200
    r, _ = _solve(q, ["100 MeV", "150 MeV", "200 MeV", "250 MeV"])
    assert r.matched and r.answer == "C" and r.method == "nuclear_binding_energy_release"


def test_accrued_simple_interest_july_to_dec():
    q = ("Một trái phiếu có mệnh giá 1.000.000 đồng, lãi suất 12%/năm. Tính lãi tích "
         "lũy từ ngày 1 tháng 7 đến ngày 31 tháng 12.")  # 1e6*0.12*6/12 = 60000
    r, _ = _solve(q, ["30.000 đồng", "60.000 đồng", "90.000 đồng", "120.000 đồng"])
    assert r.matched and r.answer == "B" and r.method == "accrued_simple_interest"


def test_operating_margin_asset_turnover_combined():
    q = ("Doanh nghiệp có lợi nhuận gộp 500, chi phí hoạt động 300, doanh thu 1000, "
         "tổng tài sản 500. Biên lợi nhuận hoạt động và vòng quay tài sản là bao nhiêu?")
    r, _ = _solve(q, ["Biên 10%, vòng quay 1,0", "Biên 20%, vòng quay 2,0",
                      "Biên 30%, vòng quay 2,0", "Biên 20%, vòng quay 1,0"])  # 20%, 2.0
    assert r.matched and r.answer == "B" and r.method == "operating_margin_asset_turnover"


def test_legal_admin_count_not_formula_overridden():
    # Legal/admin count is NOT a deterministic formula -> must defer to LLM (no match).
    q = "Theo Luật Bảo vệ môi trường 2020, có bao nhiêu nguyên tắc bảo vệ môi trường?"
    r, _ = _solve(q, ["5", "6", "7", "8"])
    assert not r.matched and not r.safe_to_override


def test_new_families_no_qid_effect():
    q = ("Một hạt chuyển động với tốc độ 0,6c, khối lượng nghỉ m₀. Động lượng tương "
         "đối p của hạt là bao nhiêu?")
    ch = ["0,6 m₀c", "0,75 m₀c", "1,25 m₀c", "1,0 m₀c"]
    L = labels_for(len(ch))
    r1 = solve_calculation_sample({"qid": "test_0085", "question": q, "choices": ch}, L)
    r2 = solve_calculation_sample({"qid": "private_x", "question": q, "choices": ch}, L)
    r3 = solve_calculation_sample({"question": q, "choices": ch}, L)
    assert r1.answer == r2.answer == r3.answer == "B"


def test_source_has_no_network_imports():
    src = Path(__file__).resolve().parents[2].joinpath("src/calculation_solver.py").read_text()
    for bad in ("import requests", "import urllib", "import httpx", "import socket",
                "open(", "eval(", "exec(", "__import__"):
        assert bad not in src, f"unexpected '{bad}' in calculation_solver.py"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
