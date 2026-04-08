#!/usr/bin/env python3
"""
Determine series/parallel topology for selected DRBP cells.
Constraints: 20 modules in series, each module must have identical topology.
"""

import json
import math
import argparse
from typing import List, Dict, Optional, Tuple
import sys

def find_possible_topologies(selected_cells_per_module: int, 
                            v_req: float, i_req: float,
                            cell_nominal_voltage: float,
                            cell_max_current: float) -> List[Dict]:
    """
    Find all possible series/parallel topologies given constraints.
    
    Constraints:
    1. n_series * n_parallel = selected_cells_per_module (must use all selected cells)
    2. total_voltage = 20 * n_series * cell_nominal_voltage ≥ v_req
    3. module_current = n_parallel * cell_max_current ≥ i_req
    
    Returns list of valid topologies sorted by preference (fewest cells, then voltage match)
    """
    valid_topologies = []
    
    # Find all factor pairs of selected_cells_per_module
    for n_series in range(1, selected_cells_per_module + 1):
        if selected_cells_per_module % n_series != 0:
            continue
        
        n_parallel = selected_cells_per_module // n_series
        
        # Calculate voltage and current capabilities
        module_voltage = n_series * cell_nominal_voltage
        total_voltage = 20 * module_voltage
        module_current = n_parallel * cell_max_current
        
        # Check constraints
        voltage_ok = total_voltage >= v_req * 0.95  # Allow 5% tolerance
        current_ok = module_current >= i_req
        
        if voltage_ok and current_ok:
            # Calculate metrics for sorting
            voltage_match = abs(total_voltage - v_req) / v_req
            current_margin = (module_current - i_req) / i_req if i_req > 0 else 0
            
            valid_topologies.append({
                "series_per_module": n_series,
                "parallel_per_module": n_parallel,
                "module_voltage": module_voltage,
                "total_voltage": total_voltage,
                "module_current": module_current,
                "voltage_match_ratio": voltage_match,
                "current_margin_ratio": current_margin,
                "cells_used": selected_cells_per_module
            })
    
    # Sort by: 1. Fewest parallel branches (conservative), 2. Best voltage match
    valid_topologies.sort(key=lambda x: (x["parallel_per_module"], x["voltage_match_ratio"]))
    
    return valid_topologies

def arrange_cells_into_topology(selected_cell_ids: List[int], 
                               n_series: int, n_parallel: int) -> List[List[int]]:
    """
    Arrange selected cell IDs into topology structure.
    
    Returns: List of parallel branches, each branch is a list of series cell IDs
    Example: [[1,2,3,4], [5,6,7,8]] for 4 series, 2 parallel
    """
    # Sort cell IDs (could be by SOC or other criteria, but simple sort for now)
    sorted_ids = sorted(selected_cell_ids)
    
    # Distribute cells to parallel branches
    topology = []
    cells_per_branch = n_series
    
    for p in range(n_parallel):
        start_idx = p * cells_per_branch
        end_idx = start_idx + cells_per_branch
        branch = sorted_ids[start_idx:end_idx]
        if len(branch) == cells_per_branch:
            topology.append(branch)
    
    return topology

def main():
    parser = argparse.ArgumentParser(description="DRBP topology solver")
    parser.add_argument("--selected_cells", required=True, 
                       help="JSON file with selected cells (output from cell_selector.py)")
    parser.add_argument("--v_req", type=float, required=True, help="Required voltage (V)")
    parser.add_argument("--i_req", type=float, required=True, help="Required current (A)")
    parser.add_argument("--cell_nominal_voltage", type=float, default=3.7,
                       help="Nominal cell voltage (default: 3.7V)")
    parser.add_argument("--cell_max_current", type=float, default=150,
                       help="Maximum cell current (default: 150A)")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    
    args = parser.parse_args()
    
    # Load selected cells
    with open(args.selected_cells, 'r', encoding='utf-8') as f:
        selected_data = json.load(f)
    
    # Extract selected cell IDs per module
    modules_selected = selected_data["selected_modules"]
    
    # Check all modules have same number of selected cells
    cells_per_module_list = [len(module["selected_cell_ids"]) for module in modules_selected]
    if len(set(cells_per_module_list)) > 1:
        print("Error: Modules have different numbers of selected cells")
        print(f"Cells per module: {cells_per_module_list}")
        sys.exit(1)
    
    selected_cells_per_module = cells_per_module_list[0]
    
    if args.verbose:
        print(f"Selected cells per module: {selected_cells_per_module}")
        print(f"Required voltage: {args.v_req}V")
        print(f"Required current: {args.i_req}A")
    
    # Find possible topologies
    topologies = find_possible_topologies(
        selected_cells_per_module, args.v_req, args.i_req,
        args.cell_nominal_voltage, args.cell_max_current
    )
    
    if not topologies:
        result = {
            "status": False,
            "error": "No valid topology found",
            "constraints": {
                "selected_cells_per_module": selected_cells_per_module,
                "v_req": args.v_req,
                "i_req": args.i_req,
                "cell_nominal_voltage": args.cell_nominal_voltage,
                "cell_max_current": args.cell_max_current
            },
            "suggestions": [
                "Increase cells per module",
                "Reduce power requirement",
                "Check cell current limits"
            ]
        }
    else:
        # Choose best topology (first in sorted list)
        best = topologies[0]
        
        # Arrange cells into topology for each module
        arranged_modules = []
        for module in modules_selected:
            mod_id = module["mod_id"]
            cell_ids = module["selected_cell_ids"]
            
            topology = arrange_cells_into_topology(
                cell_ids, best["series_per_module"], best["parallel_per_module"]
            )
            
            arranged_modules.append({
                "mod_id": mod_id,
                "cells": topology,
                "cell_ids": cell_ids
            })
        
        result = {
            "status": True,
            "topology": best,
            "arranged_modules": arranged_modules,
            "alternative_topologies": topologies[1:5] if len(topologies) > 1 else [],
            "summary": {
                "total_modules": 20,
                "cells_per_module": selected_cells_per_module,
                "total_cells_used": 20 * selected_cells_per_module,
                "configuration": f"{best['series_per_module']}S{best['parallel_per_module']}P per module",
                "total_configuration": f"{20 * best['series_per_module']}S{best['parallel_per_module']}P"
            }
        }
    
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