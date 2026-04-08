#!/usr/bin/env python3
"""
Cell selection algorithm for DRBP with bucket effect protection.
Supports both legacy battery state format and new flat cell list format.
"""

import json
import math
import argparse
from typing import List, Dict, Tuple, Optional, Any
import sys

# Default safety constraints
DEFAULT_CONSTRAINTS = {
    "min_cell_soc": 0.05,  # Minimum SOC threshold
    "max_cell_temp": 60.0,  # Maximum temperature (°C)
    "max_current_per_cell": 150,  # Maximum continuous discharge current (A)
    "soc_margin": 0.05  # Additional SOC safety margin
}


def calculate_cell_score(cell: Dict, weights: Dict) -> float:
    """
    Calculate composite score for a cell based on strategy weights.
    Weights can be positive (higher is better) or negative (lower is better).
    """
    score = 0.0

    # SOC: higher is better
    if "soc" in weights:
        score += weights["soc"] * cell["soc"]

    # SOH (State of Health): higher is better (if available)
    if "soh" in weights:
        soh = cell.get("soh", 1.0)
        score += weights["soh"] * soh

    # Temperature: lower is better -> use negative weight
    if "temperature" in weights:
        temp_c = cell.get("temperature_c", 25.0)
        temp_norm = max(0.0, 1.0 - temp_c / 60.0)  # 0°C=1, 60°C=0
        score += weights["temperature"] * temp_norm

    # Internal resistance: lower is better -> negative weight
    if "internal_resistance" in weights:
        r = cell.get("internal_resistance_ohm", 0.005)
        r_norm = max(0.0, 1.0 - r / 0.01)  # 0 ohm=1, 0.01 ohm=0
        score += weights["internal_resistance"] * r_norm

    # Cycle count: lower is better -> negative weight
    if "cycles" in weights:
        cycles = cell.get("cycles", 0)
        cycles_norm = max(0.0, 1.0 - min(cycles / 1000, 1.0))
        score += weights["cycles"] * cycles_norm

    # Last used: alternation preference (1 if not used recently)
    if "last_used" in weights:
        score += weights["last_used"] * (1.0 if not cell.get("last_used", False) else 0.0)

    return score


def check_cell_safety(cell: Dict, discharge_ah: float, constraints: Dict) -> Tuple[bool, str]:
    """
    Check if a cell can safely discharge required Ah.
    Returns: (is_safe, reason)
    """
    capacity_ah = cell.get("capacity_ah", cell.get("rated capacity", 22.0))
    soc = cell["soc"]
    soc_after = soc - discharge_ah / capacity_ah
    min_allowed = constraints["min_cell_soc"] + constraints["soc_margin"]
    if soc_after < min_allowed:
        return False, f"SOC after discharge ({soc_after:.3f}) < {min_allowed:.3f}"

    temp_c = cell.get("temperature_c", 25.0)
    if temp_c > constraints["max_cell_temp"]:
        return False, f"Temperature ({temp_c:.1f}°C) exceeds {constraints['max_cell_temp']}°C"

    # Current check omitted here (handled by topology solver)
    return True, "OK"


def select_cells_for_module(module_cells: List[Dict], k: int, weights: Dict,
                            discharge_ah: float, constraints: Dict) -> Tuple[List[Dict], List[str]]:
    """
    Select top k cells from a module with bucket effect protection.
    Returns: (selected_cells, reasons)
    """
    # Calculate scores for all cells
    scored_cells = []
    for cell in module_cells:
        score = calculate_cell_score(cell, weights)
        scored_cells.append((score, cell))

    # Sort by score (descending)
    scored_cells.sort(key=lambda x: x[0], reverse=True)

    # Select cells with safety validation
    selected = []
    reasons = []
    skipped = 0

    for score, cell in scored_cells:
        if len(selected) >= k:
            break

        is_safe, reason = check_cell_safety(cell, discharge_ah, constraints)
        if is_safe:
            selected.append(cell)
            reasons.append(f"Cell {cell['cell_id']}: score={score:.3f}, {reason}")
        else:
            skipped += 1
            reasons.append(f"Skipped cell {cell['cell_id']}: {reason}")

    # If we couldn't select enough cells, try relaxing SOC margin
    if len(selected) < k and skipped > 0:
        relaxed_constraints = constraints.copy()
        relaxed_constraints["soc_margin"] = 0.0
        selected = []
        reasons.append("Retrying with relaxed SOC margin...")

        for score, cell in scored_cells:
            if len(selected) >= k:
                break
            is_safe, reason = check_cell_safety(cell, discharge_ah, relaxed_constraints)
            if is_safe:
                selected.append(cell)
                reasons.append(f"Cell {cell['cell_id']} (relaxed): {reason}")

    return selected, reasons


def calculate_discharge_ah(power_w: float, duration_s: float,
                           nominal_voltage: float, efficiency: float,
                           num_selected_cells_total: int) -> float:
    """
    Calculate required discharge per cell in Ah.
    Assumes equal energy sharing among selected cells.
    """
    total_energy_ws = power_w * duration_s
    battery_energy_ws = total_energy_ws / efficiency
    battery_energy_wh = battery_energy_ws / 3600
    # Total Ah drawn from the whole pack at pack voltage
    pack_voltage = nominal_voltage * num_selected_cells_total  # approximate series count
    pack_ah = battery_energy_wh / pack_voltage if pack_voltage > 0 else 0
    # Divide by number of parallel strings (here we assume all cells in parallel? No.
    # Actually each module's selected cells will be arranged in some series/parallel.
    # We compute per-cell Ah assuming all selected cells share current equally.
    # This is a simplification; actual distribution depends on topology.
    per_cell_ah = pack_ah * (nominal_voltage / pack_voltage)  # detailed derivation omitted
    # Simpler: per-cell Ah = total_Ah / number_of_cells_in_parallel_equivalent
    # For safety we use: discharge_ah = (power_w * duration_s / 3600) / (nominal_voltage * efficiency * num_parallel_strings)
    # But we don't know parallel count yet. Use energy method:
    # Energy per cell = total energy / total cells selected
    # Ah per cell = (energy per cell) / nominal_voltage
    total_energy_wh = total_energy_ws / 3600
    energy_per_cell_wh = total_energy_wh / num_selected_cells_total
    per_cell_ah = energy_per_cell_wh / nominal_voltage
    return per_cell_ah


def load_battery_data(file_path: str, nominal_voltage: float = None) -> Tuple[Any, float, float]:
    """
    Load battery state from JSON file.
    Supports two formats:
    1) Legacy: {"cell_nominal_voltage":..., "cell_capacity_ah":..., "modules": [...]}
    2) Flat list: [{"module_id":0, "id":0, "soc":..., "temperature_K":..., "rated capacity":..., "R_eq":...}, ...]

    Returns: (battery_info_dict, nominal_voltage, cell_capacity_ah)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Check if legacy format
    if isinstance(data, dict) and "modules" in data:
        # Legacy format
        nominal_voltage = data.get("cell_nominal_voltage", nominal_voltage or 3.7)
        cell_capacity_ah = data.get("cell_capacity_ah", 22.0)
        modules = data["modules"]
        # Ensure each cell has necessary fields
        for mod in modules:
            for cell in mod["cells"]:
                if "temperature_c" not in cell and "temperature_K" in cell:
                    cell["temperature_c"] = cell["temperature_K"] - 273.15
                if "internal_resistance_ohm" not in cell and "R_eq" in cell:
                    cell["internal_resistance_ohm"] = cell["R_eq"]
                if "capacity_ah" not in cell:
                    cell["capacity_ah"] = cell_capacity_ah
                cell["cell_id"] = f"{mod['mod_id']}_{cell.get('id', 0)}"
        return data, nominal_voltage, cell_capacity_ah

    # Assume flat list format
    if not isinstance(data, list):
        raise ValueError("Input JSON must be either a dict with 'modules' or a list of cells")

    # Group by module_id
    modules_dict = {}
    for cell in data:
        mod_id = cell["module_id"]
        if mod_id not in modules_dict:
            modules_dict[mod_id] = []
        # Convert temperature to Celsius if needed
        if "temperature_c" not in cell and "temperature_K" in cell:
            cell["temperature_c"] = cell["temperature_K"] - 273.15
        # Map internal resistance
        if "internal_resistance_ohm" not in cell and "R_eq" in cell:
            cell["internal_resistance_ohm"] = cell["R_eq"]
        # Capacity
        if "capacity_ah" not in cell and "rated capacity" in cell:
            cell["capacity_ah"] = cell["rated capacity"]
        # Create a unique cell id
        cell["cell_id"] = f"{mod_id}_{cell.get('id', 0)}"
        modules_dict[mod_id].append(cell)

    # Build modules list
    modules = []
    for mod_id, cells in modules_dict.items():
        modules.append({
            "mod_id": mod_id,
            "cells": cells
        })

    # Determine nominal voltage (use provided or try to infer from voltage field)
    if nominal_voltage is None:
        # Try to get average voltage from data
        voltages = [c.get("voltage", 3.7) for c in data if "voltage" in c]
        if voltages:
            nominal_voltage = sum(voltages) / len(voltages)
        else:
            nominal_voltage = 3.7  # default Li-ion
    # Determine cell capacity (use first cell's rated capacity)
    cell_capacity_ah = data[0].get("capacity_ah", 22.0) if data else 22.0

    battery_info = {
        "cell_nominal_voltage": nominal_voltage,
        "cell_capacity_ah": cell_capacity_ah,
        "modules": modules
    }
    return battery_info, nominal_voltage, cell_capacity_ah


def main():
    parser = argparse.ArgumentParser(description="DRBP cell selector with bucket effect protection")
    parser.add_argument("--battery", required=True, help="Battery state JSON file")
    parser.add_argument("--strategy", required=True,
                        help="Strategy name: high_energy, equilibrium, thermal_management, lifetime_optimization, or custom")
    parser.add_argument("--cells_per_module", type=int, required=True,
                        help="Number of cells to select per module (k)")
    parser.add_argument("--weights", help="Custom weights as JSON string (e.g., '{\"soc\":0.7,\"temperature\":-0.3}')")
    parser.add_argument("--power", type=float, required=True, help="Power in kW")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    parser.add_argument("--efficiency", type=float, default=0.92, help="System efficiency (0-1)")
    parser.add_argument("--nominal_voltage", type=float, default=None,
                        help="Nominal cell voltage (V). Auto-detected if not given")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")

    args = parser.parse_args()

    # Load battery data (auto-detects format)
    battery_info, nominal_voltage, cell_capacity_ah = load_battery_data(args.battery, args.nominal_voltage)
    modules = battery_info["modules"]

    # Define strategy weights
    strategy_weights = {
        "high_energy": {"soc": 0.7, "soh": 0.2, "temperature": -0.1},
        "equilibrium": {"soc": 0.9, "internal_resistance": -0.1},
        "thermal_management": {"temperature": -0.8, "soc": 0.2},
        "lifetime_optimization": {"soh": 0.6, "cycles": -0.3, "soc": 0.1}
    }

    if args.strategy == "custom":
        if not args.weights:
            print("Error: Custom strategy requires --weights parameter")
            sys.exit(1)
        weights = json.loads(args.weights)
    else:
        if args.strategy not in strategy_weights:
            print(f"Error: Unknown strategy '{args.strategy}'. Available: {list(strategy_weights.keys())}")
            sys.exit(1)
        weights = strategy_weights[args.strategy]

    # Total number of modules
    num_modules = len(modules)
    total_cells_to_select = num_modules * args.cells_per_module

    # Calculate discharge per cell (Ah)
    power_w = args.power * 1000
    duration_s = args.duration * 60
    discharge_ah_per_cell = calculate_discharge_ah(
        power_w, duration_s, nominal_voltage, args.efficiency, total_cells_to_select
    )

    if args.verbose:
        print(f"Power: {args.power} kW, Duration: {args.duration} min")
        print(f"Nominal voltage: {nominal_voltage} V, Cell capacity: {cell_capacity_ah} Ah")
        print(f"Total cells to select: {total_cells_to_select}")
        print(f"Discharge per cell: {discharge_ah_per_cell:.4f} Ah")
        print(f"Strategy: {args.strategy}, Weights: {weights}")

    # Select cells for each module
    all_selected = []
    all_reasons = []
    constraints = DEFAULT_CONSTRAINTS.copy()

    for module in modules:
        mod_id = module["mod_id"]
        selected_cells, reasons = select_cells_for_module(
            module["cells"], args.cells_per_module, weights,
            discharge_ah_per_cell, constraints
        )

        # Extract cell IDs, removing the module ID prefix (keep only the original cell id)
        cell_ids = [cell["cell_id"].split('_', 1)[-1] for cell in selected_cells]

        all_selected.append({
            "mod_id": mod_id,
            "selected_cell_ids": cell_ids
        })

        all_reasons.append({
            "mod_id": mod_id,
            "reasons": reasons,
            "selected_count": len(selected_cells)
        })

    # Check success
    success = all(len(item["selected_cell_ids"]) >= args.cells_per_module for item in all_selected)

    # Prepare output
    result = {
        "status": success,
        "strategy": args.strategy,
        "cells_per_module_target": args.cells_per_module,
        "cells_per_module_actual": [len(item["selected_cell_ids"]) for item in all_selected],
        "discharge_ah_per_cell": round(discharge_ah_per_cell, 4),
        "selected_modules": all_selected,
        "nominal_voltage": nominal_voltage,
        "cell_capacity_ah": cell_capacity_ah
    }

    if not success:
        result["error"] = "Some modules could not select enough safe cells"

    # Output
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())