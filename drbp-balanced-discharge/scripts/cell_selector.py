#!/usr/bin/env python3
"""
Cell selection algorithm for DRBP with bucket effect protection.
Selects cells within each module based on strategy weights and ensures
weakest cell can discharge safely for the required duration.
"""

import json
import math
import argparse
from typing import List, Dict, Tuple, Optional
import sys

# Default safety constraints
DEFAULT_CONSTRAINTS = {
    "min_cell_soc": 0.05,      # Minimum SOC threshold
    "max_cell_temp": 60.0,     # Maximum temperature (°C)
    "max_current_per_cell": 150,  # Maximum continuous discharge current (A)
    "soc_margin": 0.05         # Additional SOC safety margin
}

def calculate_cell_score(cell: Dict, weights: Dict) -> float:
    """
    Calculate composite score for a cell based on strategy weights.
    
    Weights should sum to approximately 1.0, but can be negative for
    parameters where lower values are better (e.g., temperature, resistance).
    """
    score = 0.0
    
    # SOC: higher is better
    if "soc" in weights:
        score += weights["soc"] * cell["soc"]
    
    # SOH (State of Health): higher is better
    if "soh" in weights:
        score += weights["soh"] * cell.get("soh", 1.0)
    
    # Temperature: lower is better (negative weight)
    if "temperature" in weights:
        # Normalize temperature: 0-60°C -> 1.0 to 0.0
        temp_norm = max(0, 1.0 - cell["temperature_c"] / 60.0)
        score += weights["temperature"] * temp_norm
    
    # Internal resistance: lower is better (negative weight)
    if "internal_resistance" in weights:
        # Normalize resistance: 0-0.01 ohm -> 1.0 to 0.0
        r_norm = max(0, 1.0 - cell["internal_resistance_ohm"] / 0.01)
        score += weights["internal_resistance"] * r_norm
    
    # Cycle count: lower is better (negative weight)
    if "cycles" in weights:
        cycles = cell.get("cycles", 0)
        cycles_norm = max(0, 1.0 - min(cycles / 1000, 1.0))
        score += weights["cycles"] * cycles_norm
    
    # Last used: alternation preference (negative if we want to rotate)
    if "last_used" in weights:
        score += weights["last_used"] * (1.0 if cell.get("last_used", False) else 0.0)
    
    return score

def check_cell_safety(cell: Dict, discharge_ah: float, 
                     cell_capacity_ah: float, constraints: Dict) -> Tuple[bool, str]:
    """
    Check if a cell can safely discharge required Ah.
    
    Returns: (is_safe, reason)
    """
    # 1. SOC check: will cell drop below minimum?
    soc_after = cell["soc"] - discharge_ah / cell_capacity_ah
    if soc_after < constraints["min_cell_soc"] + constraints["soc_margin"]:
        return False, f"SOC after discharge ({soc_after:.3f}) below safety threshold"
    
    # 2. Temperature check
    if cell["temperature_c"] > constraints["max_cell_temp"]:
        return False, f"Temperature ({cell['temperature_c']}°C) exceeds limit"
    
    # 3. Current check (needs to be validated with topology)
    # This is done separately in topology solver
    
    return True, "OK"

def select_cells_for_module(module_cells: List[Dict], k: int, weights: Dict,
                           discharge_ah: float, cell_capacity_ah: float,
                           constraints: Dict) -> Tuple[List[Dict], List[str]]:
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
        
        # Check if cell can safely discharge
        is_safe, reason = check_cell_safety(cell, discharge_ah, 
                                          cell_capacity_ah, constraints)
        
        if is_safe:
            selected.append(cell)
            reasons.append(f"Cell {cell['cell_id']}: score={score:.3f}, {reason}")
        else:
            skipped += 1
            reasons.append(f"Skipped cell {cell['cell_id']}: {reason}")
    
    # If we couldn't select enough cells, try relaxing constraints
    if len(selected) < k and skipped > 0:
        # Try selecting without SOC margin for the weakest cells
        temp_constraints = constraints.copy()
        temp_constraints["soc_margin"] = 0.0
        
        # Reset and try again
        selected = []
        reasons.append("Retrying with relaxed SOC margin...")
        
        for score, cell in scored_cells:
            if len(selected) >= k:
                break
            
            is_safe, reason = check_cell_safety(cell, discharge_ah,
                                              cell_capacity_ah, temp_constraints)
            if is_safe:
                selected.append(cell)
                reasons.append(f"Cell {cell['cell_id']} (relaxed): {reason}")
    
    return selected, reasons

def calculate_discharge_ah(power_w: float, duration_s: float,
                          cell_nominal_voltage: float, efficiency: float) -> float:
    """
    Calculate required discharge per cell in Ah.
    
    Assumes energy is distributed equally among selected cells.
    Actual distribution depends on topology.
    """
    # Total energy in watt-seconds (joules)
    total_energy_ws = power_w * duration_s
    
    # Account for efficiency losses
    battery_energy_ws = total_energy_ws / efficiency
    
    # Convert to watt-hours
    battery_energy_wh = battery_energy_ws / 3600
    
    # Convert to Ah at nominal cell voltage
    battery_energy_ah = battery_energy_wh / cell_nominal_voltage
    
    return battery_energy_ah

def main():
    parser = argparse.ArgumentParser(description="DRBP cell selector with bucket effect protection")
    parser.add_argument("--battery", required=True, help="Battery state JSON file")
    parser.add_argument("--strategy", required=True, 
                       help="Strategy name or 'custom' for custom weights")
    parser.add_argument("--cells_per_module", type=int, required=True,
                       help="Number of cells to select per module (k)")
    parser.add_argument("--weights", help="Custom weights as JSON string")
    parser.add_argument("--power", type=float, required=True, help="Power in kW")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    parser.add_argument("--efficiency", type=float, default=0.92, help="System efficiency")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    
    args = parser.parse_args()
    
    # Load battery state
    with open(args.battery, 'r', encoding='utf-8') as f:
        battery_info = json.load(f)
    
    # Define strategy weights
    strategy_weights = {
        "high_energy": {"soc": 0.7, "soh": 0.2, "temperature": -0.1},
        "equilibrium": {"soc": 0.9, "internal_resistance": -0.1},
        "thermal_management": {"temperature": 0.8, "soc": 0.2},
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
    
    # Calculate discharge per cell
    power_w = args.power * 1000
    duration_s = args.duration * 60
    cell_nominal_voltage = battery_info["cell_nominal_voltage"]
    
    discharge_ah = calculate_discharge_ah(power_w, duration_s,
                                        cell_nominal_voltage, args.efficiency)
    
    if args.verbose:
        print(f"Power: {args.power} kW")
        print(f"Duration: {args.duration} min")
        print(f"Discharge per cell: {discharge_ah:.3f} Ah")
        print(f"Strategy weights: {weights}")
    
    # Select cells for each module
    all_selected = []
    all_reasons = []
    cell_capacity_ah = battery_info["cell_capacity_ah"]
    
    for module in battery_info["modules"]:
        mod_id = module["mod_id"]
        selected_cells, reasons = select_cells_for_module(
            module["cells"], args.cells_per_module, weights,
            discharge_ah, cell_capacity_ah, DEFAULT_CONSTRAINTS
        )
        
        # Extract cell IDs for output
        cell_ids = [cell["cell_id"] for cell in selected_cells]
        
        all_selected.append({
            "mod_id": mod_id,
            "selected_cell_ids": cell_ids,
            "selected_cells": selected_cells  # Include full data for validation
        })
        
        all_reasons.append({
            "mod_id": mod_id,
            "reasons": reasons,
            "selected_count": len(selected_cells)
        })
    
    # Check if any module failed to select enough cells
    success = all(len(item["selected_cell_ids"]) >= args.cells_per_module 
                  for item in all_selected)
    
    # Prepare output
    result = {
        "status": success,
        "strategy": args.strategy,
        "cells_per_module_target": args.cells_per_module,
        "cells_per_module_actual": [len(item["selected_cell_ids"]) for item in all_selected],
        "discharge_ah_per_cell": round(discharge_ah, 4),
        "selected_modules": all_selected,
        "reasons": all_reasons
    }
    
    if not success:
        result["error"] = "Some modules could not select enough safe cells"
    
    # Output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        if args.verbose:
            print(f"Results saved to {args.output}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result

if __name__ == "__main__":
    main()