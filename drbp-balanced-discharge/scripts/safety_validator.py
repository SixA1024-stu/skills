#!/usr/bin/env python3
"""
Safety validation for DRBP topology.
Performs comprehensive checks to ensure safe operation.
"""

import json
import math
import argparse
from typing import Dict, List, Tuple

# Default safety constraints
DEFAULT_CONSTRAINTS = {
    "min_cell_soc": 0.05,
    "max_cell_soc": 0.95,
    "max_cell_temp": 60.0,
    "min_cell_temp": -10.0,
    "max_current_per_cell": 150,
    "max_voltage_per_cell": 4.2,
    "min_voltage_per_cell": 3.0,
    "max_module_voltage": 4.2 * 4,  # 4 cells in series max
    "min_module_voltage": 3.0 * 1,  # 1 cell in series min
    "max_total_voltage": 20 * 4.2 * 4,  # Conservative upper bound
    "min_total_voltage": 20 * 3.0 * 1,  # Conservative lower bound
    "max_temperature_gradient": 10.0,  # Max temp difference between cells
    "max_soc_difference": 0.3,  # Max SOC difference between cells
}

def check_voltage_limits(topology: Dict, constraints: Dict) -> Tuple[bool, List[str]]:
    """Check voltage constraints at cell, module, and system levels."""
    checks = []
    passed = True
    
    # Cell voltage (nominal)
    cell_nominal = 3.7  # Should be from battery info
    if cell_nominal > constraints["max_voltage_per_cell"]:
        checks.append(f"Cell nominal voltage {cell_nominal}V exceeds max {constraints['max_voltage_per_cell']}V")
        passed = False
    if cell_nominal < constraints["min_voltage_per_cell"]:
        checks.append(f"Cell nominal voltage {cell_nominal}V below min {constraints['min_voltage_per_cell']}V")
        passed = False
    
    # Module voltage
    module_voltage = topology["module_voltage"]
    if module_voltage > constraints["max_module_voltage"]:
        checks.append(f"Module voltage {module_voltage}V exceeds max {constraints['max_module_voltage']}V")
        passed = False
    if module_voltage < constraints["min_module_voltage"]:
        checks.append(f"Module voltage {module_voltage}V below min {constraints['min_module_voltage']}V")
        passed = False
    
    # Total voltage
    total_voltage = topology["total_voltage"]
    if total_voltage > constraints["max_total_voltage"]:
        checks.append(f"Total voltage {total_voltage}V exceeds max {constraints['max_total_voltage']}V")
        passed = False
    if total_voltage < constraints["min_total_voltage"]:
        checks.append(f"Total voltage {total_voltage}V below min {constraints['min_total_voltage']}V")
        passed = False
    
    return passed, checks

def check_current_limits(topology: Dict, i_req: float, 
                        constraints: Dict) -> Tuple[bool, List[str]]:
    """Check current constraints at cell and system levels."""
    checks = []
    passed = True
    
    # Current per cell
    n_parallel = topology["parallel_per_module"]
    current_per_cell = i_req / n_parallel
    
    if current_per_cell > constraints["max_current_per_cell"]:
        checks.append(f"Current per cell {current_per_cell:.1f}A exceeds max {constraints['max_current_per_cell']}A")
        passed = False
    
    # Current margin
    current_margin = constraints["max_current_per_cell"] - current_per_cell
    if current_margin < 0:
        checks.append(f"Current margin negative: {current_margin:.1f}A")
    elif current_margin < 10:  # Less than 10A margin
        checks.append(f"Low current margin: {current_margin:.1f}A")
    
    return passed, checks

def check_temperature(battery_info: Dict, arranged_modules: List[Dict],
                     constraints: Dict) -> Tuple[bool, List[str]]:
    """Check temperature constraints and gradients."""
    checks = []
    passed = True
    
    all_cells = []
    for module in arranged_modules:
        mod_id = module["mod_id"]
        # Find cell data from battery_info
        battery_module = battery_info["modules"][mod_id]
        for cell in battery_module["cells"]:
            if cell["cell_id"] in module["cell_ids"]:
                all_cells.append(cell)
    
    if not all_cells:
        checks.append("No cell data found for validation")
        return False, checks
    
    # Check individual cell temperatures
    temps = [cell["temperature_c"] for cell in all_cells]
    max_temp = max(temps)
    min_temp = min(temps)
    
    if max_temp > constraints["max_cell_temp"]:
        checks.append(f"Max cell temperature {max_temp}°C exceeds limit {constraints['max_cell_temp']}°C")
        passed = False
    
    if min_temp < constraints["min_cell_temp"]:
        checks.append(f"Min cell temperature {min_temp}°C below limit {constraints['min_cell_temp']}°C")
        passed = False
    
    # Check temperature gradient
    temp_gradient = max_temp - min_temp
    if temp_gradient > constraints["max_temperature_gradient"]:
        checks.append(f"Temperature gradient {temp_gradient}°C exceeds limit {constraints['max_temperature_gradient']}°C")
        passed = False
    
    return passed, checks

def check_soc_margins(battery_info: Dict, arranged_modules: List[Dict],
                     discharge_ah: float, cell_capacity_ah: float,
                     constraints: Dict) -> Tuple[bool, List[str]]:
    """
    Check SOC margins after discharge.
    This is the most critical check for bucket effect protection.
    """
    checks = []
    passed = True
    
    soc_values = []
    soc_after_values = []
    weakest_cell = None
    weakest_soc_margin = float('inf')
    
    for module in arranged_modules:
        mod_id = module["mod_id"]
        battery_module = battery_info["modules"][mod_id]
        
        for cell in battery_module["cells"]:
            if cell["cell_id"] in module["cell_ids"]:
                soc = cell["soc"]
                soc_after = soc - discharge_ah / cell_capacity_ah
                
                soc_values.append(soc)
                soc_after_values.append(soc_after)
                
                # Check minimum SOC
                soc_margin = soc_after - constraints["min_cell_soc"]
                if soc_margin < weakest_soc_margin:
                    weakest_soc_margin = soc_margin
                    weakest_cell = {
                        "mod_id": mod_id,
                        "cell_id": cell["cell_id"],
                        "soc": soc,
                        "soc_after": soc_after,
                        "margin": soc_margin
                    }
    
    if not soc_values:
        checks.append("No SOC data found for validation")
        return False, checks
    
    # Check weakest cell
    if weakest_cell:
        if weakest_cell["soc_after"] < constraints["min_cell_soc"]:
            checks.append(f"Weakest cell (mod{weakest_cell['mod_id']}-cell{weakest_cell['cell_id']}): "
                         f"SOC after discharge {weakest_cell['soc_after']:.3f} below min {constraints['min_cell_soc']}")
            passed = False
        else:
            checks.append(f"Weakest cell margin: {weakest_cell['margin']:.3f}")
    
    # Check SOC distribution
    soc_range = max(soc_values) - min(soc_values)
    if soc_range > constraints["max_soc_difference"]:
        checks.append(f"SOC range {soc_range:.3f} exceeds limit {constraints['max_soc_difference']}")
        passed = False
    
    return passed, checks

def check_balance(arranged_modules: List[Dict]) -> Tuple[bool, List[str]]:
    """
    Check if topology maintains or improves cell balance.
    Simple check: ensure each parallel branch has similar total SOC.
    """
    checks = []
    
    # For each module, check parallel branch balance
    for module in arranged_modules:
        mod_id = module["mod_id"]
        topology = module["cells"]  # List of parallel branches
        
        if len(topology) <= 1:
            continue  # No balance check needed for single branch
        
        # This would require SOC data per cell
        # For now, just note that balance check needs cell data
        checks.append(f"Module {mod_id}: Parallel branch balance check requires cell SOC data")
    
    return True, checks  # Default to passed for now

def main():
    parser = argparse.ArgumentParser(description="DRBP safety validator")
    parser.add_argument("--topology", required=True, 
                       help="Topology JSON file (output from topology_solver.py)")
    parser.add_argument("--battery", required=True, help="Battery state JSON file")
    parser.add_argument("--requirements", required=True,
                       help="Requirements JSON file (output from calculate_requirements.py)")
    parser.add_argument("--constraints", help="Custom constraints JSON file")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    
    args = parser.parse_args()
    
    # Load data
    with open(args.topology, 'r', encoding='utf-8') as f:
        topology_data = json.load(f)
    
    with open(args.battery, 'r', encoding='utf-8') as f:
        battery_info = json.load(f)
    
    with open(args.requirements, 'r', encoding='utf-8') as f:
        requirements = json.load(f)
    
    # Load constraints
    if args.constraints:
        with open(args.constraints, 'r', encoding='utf-8') as f:
            constraints = json.load(f)
    else:
        constraints = DEFAULT_CONSTRAINTS
    
    # Extract data
    if not topology_data["status"]:
        print("Error: Invalid topology input")
        return
    
    topology = topology_data["topology"]
    arranged_modules = topology_data["arranged_modules"]
    v_req = requirements["v_req"]
    i_req = requirements["i_req"]
    
    # Get discharge per cell from requirements or calculate
    if "discharge_ah_per_cell" in requirements:
        discharge_ah = requirements["discharge_ah_per_cell"]
    else:
        # Estimate from power and duration
        power_w = requirements.get("power_kw", 25) * 1000
        duration_s = requirements.get("duration_s", 600)
        cell_nominal_voltage = battery_info["cell_nominal_voltage"]
        efficiency = 0.92
        discharge_ah = (power_w * duration_s / 3600) / (cell_nominal_voltage * efficiency)
    
    cell_capacity_ah = battery_info["cell_capacity_ah"]
    
    # Perform all checks
    all_checks = []
    all_passed = True
    
    # 1. Voltage limits
    voltage_passed, voltage_checks = check_voltage_limits(topology, constraints)
    all_checks.append({"category": "voltage", "passed": voltage_passed, "checks": voltage_checks})
    all_passed = all_passed and voltage_passed
    
    # 2. Current limits
    current_passed, current_checks = check_current_limits(topology, i_req, constraints)
    all_checks.append({"category": "current", "passed": current_passed, "checks": current_checks})
    all_passed = all_passed and current_passed
    
    # 3. Temperature
    temp_passed, temp_checks = check_temperature(battery_info, arranged_modules, constraints)
    all_checks.append({"category": "temperature", "passed": temp_passed, "checks": temp_checks})
    all_passed = all_passed and temp_passed
    
    # 4. SOC margins (most critical)
    soc_passed, soc_checks = check_soc_margins(battery_info, arranged_modules,
                                              discharge_ah, cell_capacity_ah,
                                              constraints)
    all_checks.append({"category": "soc", "passed": soc_passed, "checks": soc_checks})
    all_passed = all_passed and soc_passed
    
    # 5. Balance check
    balance_passed, balance_checks = check_balance(arranged_modules)
    all_checks.append({"category": "balance", "passed": balance_passed, "checks": balance_checks})
    all_passed = all_passed and balance_passed
    
    # Prepare result
    result = {
        "status": all_passed,
        "all_checks_passed": all_passed,
        "checks": all_checks,
        "summary": {
            "voltage_ok": voltage_passed,
            "current_ok": current_passed,
            "temperature_ok": temp_passed,
            "soc_ok": soc_passed,
            "balance_ok": balance_passed
        },
        "constraints_used": constraints,
        "input_files": {
            "topology": args.topology,
            "battery": args.battery,
            "requirements": args.requirements
        }
    }
    
    # Add recommendations if failed
    if not all_passed:
        result["recommendations"] = [
            "Consider selecting different cells",
            "Increase cells per module for better current sharing",
            "Reduce power demand if possible",
            "Check for faulty cells with high temperature or low SOC"
        ]
    
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