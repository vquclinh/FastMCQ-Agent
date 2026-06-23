"""Finance/economics tool solver (Phase 2L.25).

ROI, profit, operating margin / asset turnover, break-even, elasticity & total
revenue, GDP-related, depreciation, MC vs average cost. Delegates to tested rules.
"""

from __future__ import annotations

from src.tool_solvers import _candidate_from_rule
from src.formula_bank_solver import (try_roi, try_profit, try_break_even_quantity,
                                     try_straight_line_depreciation,
                                     try_elasticity_revenue_direction, try_tax_supply_shift,
                                     try_mc_vs_average_cost, try_cournot_duopoly,
                                     try_monopoly_linear)
from src.calculation_solver import (try_operating_margin_asset_turnover, try_gdp_inflation,
                                    try_price_elasticity, try_money_multiplier)


def solve(sample):
    return _candidate_from_rule(
        sample,
        (try_cournot_duopoly, try_monopoly_linear, try_roi, try_profit, try_break_even_quantity,
         try_straight_line_depreciation, try_elasticity_revenue_direction,
         try_tax_supply_shift, try_mc_vs_average_cost, try_operating_margin_asset_turnover,
         try_gdp_inflation, try_price_elasticity, try_money_multiplier),
        "tool:finance_econ")
