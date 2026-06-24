"""Physics tool solver (Phase 2L.25).

Kinematics (s=vt), kinetic/potential energy, Ohm's law / power, wave speed, density,
pressure, pythagorean distance, capacitor/resistor equivalent (when explicit).
"""

from __future__ import annotations

from src.tool_solvers import _candidate_from_rule
from src.solvers.formula_bank_solver import (try_uniform_motion, try_kinetic_energy, try_potential_energy,
                                     try_ohms_law, try_electric_power, try_wave_speed,
                                     try_density, try_pressure, try_pythagorean_distance,
                                     try_frequency_period, try_capacitor_series_parallel,
                                     try_resistor_series_parallel)
from src.solvers.calculation_solver import (try_resistor, try_relativistic_momentum,
                                    try_relativistic_gamma, try_cylinder_rate, try_sphere_rate)


def solve(sample):
    return _candidate_from_rule(
        sample,
        (try_uniform_motion, try_kinetic_energy, try_potential_energy, try_ohms_law,
         try_electric_power, try_wave_speed, try_density, try_pressure,
         try_pythagorean_distance, try_frequency_period, try_capacitor_series_parallel,
         try_resistor_series_parallel, try_resistor, try_relativistic_momentum,
         try_relativistic_gamma, try_cylinder_rate, try_sphere_rate),
        "tool:physics")
