"""Formula cards — metadata describing deterministic formula families.

Cards are *metadata* (triggers, required variables, disambiguation intents, the
name of the executor, and whether it is implemented). The actual numeric executors
live in ``src/calculation_solver.py``; Phase 2L.15B will bind them to cards. A card
being present does NOT mean an answer is overridden — overrides are gated by the
orchestrator and are disabled in trace-only mode.

CRITICAL disambiguation (Phase 2L.13 bug): ``relativistic_gamma`` must only be
eligible when γ / the Lorentz factor is the *asked* quantity, and
``relativistic_momentum`` only when momentum (động lượng / p) is asked.
"""

from __future__ import annotations

from src.layers.adaptive_types import FormulaCard

CARDS: tuple = (
    FormulaCard(
        formula_id="relativistic_gamma", domain="physics",
        trigger_keywords=("tốc độ ánh sáng", "0,6c", "0.6c", "lorentz", "tương đối"),
        required_variables=("beta",),
        do_not_use_when=("động lượng", "năng lượng", "động năng"),
        target_intents=("gamma", "lorentz", "hệ số lorentz", "hệ số giãn nở thời gian", "γ"),
        output_type="numeric", option_match_policy="nearest_margin",
        executor="try_relativistic_gamma", implemented=True,
        notes="γ=1/√(1−β²); fire ONLY when the Lorentz factor itself is asked."),
    FormulaCard(
        formula_id="relativistic_momentum", domain="physics",
        trigger_keywords=("động lượng", "tương đối", "ánh sáng"),
        required_variables=("beta", "m0"),
        do_not_use_when=(),
        target_intents=("động lượng", "momentum", "p"),
        output_type="multiple_of", option_match_policy="nearest_margin",
        executor="try_relativistic_momentum", implemented=True,
        notes="p=γβ·m₀c; options as multiples of m₀c."),
    FormulaCard(
        formula_id="henderson_hasselbalch_buffer", domain="chemistry",
        trigger_keywords=("đệm", "buffer", "pka", "henderson"),
        required_variables=("pKa", "base", "acid"),
        target_intents=("ph",),
        output_type="numeric", option_match_policy="nearest_margin",
        executor="try_henderson_hasselbalch_buffer", implemented=True,
        notes="pH=pKa+log10([base]/[acid])."),
    FormulaCard(
        formula_id="z_score_one_sample", domain="statistics",
        trigger_keywords=("thống kê z", "giá trị z", "z-score", "kiểm định"),
        required_variables=("xbar", "mu0", "sigma_pop", "n"),
        target_intents=("z",),
        output_type="numeric", option_match_policy="nearest_margin",
        executor="try_z_score_one_sample", implemented=True,
        notes="Requires POPULATION σ to distinguish from t."),
    FormulaCard(
        formula_id="t_statistic_one_sample", domain="statistics",
        trigger_keywords=("thống kê t", "giá trị t", "kiểm định", "t-test"),
        required_variables=("xbar", "mu0", "s", "n"),
        target_intents=("t",),
        output_type="interval", option_match_policy="interval_membership",
        executor="try_t_statistic_one_sample", implemented=True,
        notes="Interval options; numeric options handled by try_t_statistic."),
    FormulaCard(
        formula_id="supply_demand_price_control", domain="economics",
        trigger_keywords=("thiếu hụt", "dư thừa", "giá trần", "giá sàn", "qd", "qs"),
        required_variables=("Qd", "Qs", "P"),
        target_intents=("shortage", "surplus", "thiếu hụt", "dư thừa"),
        output_type="numeric", option_match_policy="nearest_margin",
        executor="try_supply_demand_price_control", implemented=True),
    FormulaCard(
        formula_id="cobb_douglas_isoquant_scaling", domain="economics",
        trigger_keywords=("sản lượng", "đẳng lượng", "sản xuất", "k^", "√"),
        required_variables=("A", "K0", "L0", "fraction"),
        target_intents=("k", "l", "tổ hợp"),
        output_type="pair", option_match_policy="exact",
        executor="try_cobb_douglas_isoquant_scaling", implemented=True),
    FormulaCard(
        formula_id="accrued_simple_interest", domain="finance",
        trigger_keywords=("lãi", "trái phiếu", "mệnh giá", "lãi suất"),
        required_variables=("principal", "rate", "months"),
        target_intents=("lãi", "interest"),
        output_type="numeric", option_match_policy="nearest_margin",
        executor="try_accrued_simple_interest", implemented=True),
    FormulaCard(
        formula_id="operating_margin_asset_turnover", domain="finance",
        trigger_keywords=("lợi nhuận gộp", "chi phí hoạt động", "doanh thu", "tài sản"),
        required_variables=("gross", "opex", "sales", "assets"),
        target_intents=("biên", "vòng quay", "margin", "turnover"),
        output_type="combined", option_match_policy="combined",
        executor="try_operating_margin_asset_turnover", implemented=True),
    FormulaCard(
        formula_id="nuclear_binding_energy_release", domain="physics",
        trigger_keywords=("năng lượng liên kết", "phân hạch", "phân rã"),
        required_variables=("A", "be_before", "be_after"),
        target_intents=("năng lượng", "mev"),
        output_type="numeric", option_match_policy="nearest_margin",
        executor="try_nuclear_binding_energy_release", implemented=True),
    FormulaCard(
        formula_id="linear_total_equation", domain="algebra",
        trigger_keywords=("tổng", "phương trình"),
        required_variables=("equations", "total"),
        target_intents=("y", "x", "ẩn"),
        output_type="numeric", option_match_policy="abs_nearest",
        executor="try_linear_total_equation", implemented=True),
)
