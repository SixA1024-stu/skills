#!/usr/bin/env python3
"""
Calculate power requirements for DRBP based on navigation information.
Input: Battery state + navigation parameters
Output: Required voltage (v_req) and current (i_req)
"""

import json
import math
import argparse
from typing import Dict, Tuple

# Vehicle parameters (default values, can be overridden)
DEFAULT_VEHICLE = {
    "mass_kg": 1800,
    "frontal_area_m2": 2.4,
    "drag_coefficient": 0.28,
    "rolling_resistance": 0.012,
    "efficiency": 0.92,  # Drivetrain efficiency
    "auxiliary_power_w": 500  # Lights, AC, etc.
}

# Physical constants
AIR_DENSITY = 1.225  # kg/m³ at sea level
GRAVITY = 9.81  # m/s²

def calculate_road_load_power(speed_mps: float, gradient_percent: float, 
                             vehicle: Dict) -> float:
    """
    Calculate required power to overcome road load forces.
    Based on vehicle dynamics model.
    """
    # Gradient angle in radians
    gradient_rad = math.atan(gradient_percent / 100)
    
    # Aerodynamic drag force
    drag_force = 0.5 * AIR_DENSITY * vehicle["drag_coefficient"] * \
                 vehicle["frontal_area_m2"] * speed_mps ** 2
    
    # Rolling resistance force
    rolling_force = vehicle["rolling_resistance"] * vehicle["mass_kg"] * GRAVITY * \
                    math.cos(gradient_rad)
    
    # Hill climbing force
    hill_force = vehicle["mass_kg"] * GRAVITY * math.sin(gradient_rad)
    
    # Total force
    total_force = drag_force + rolling_force + hill_force
    
    # Power at wheels
    wheel_power_w = total_force * speed_mps
    
    # Motor power (accounting for efficiency)
    motor_power_w = wheel_power_w / vehicle["efficiency"]
    
    # Total power including auxiliary
    total_power_w = motor_power_w + vehicle["auxiliary_power_w"]
    
    return total_power_w

def calculate_battery_requirements(power_kw: float, duration_min: int,
                                  battery_info: Dict) -> Tuple[float, float]:
    """
    Calculate voltage and current requirements for battery pack.
    
    Strategy:
    1. Use nominal battery voltage as base (20 modules * cell_nominal_voltage)
    2. Adjust based on available voltage range
    3. Calculate current based on power and selected voltage
    """
    # Base voltage: 20 modules in series
    cell_nominal_voltage = battery_info["cell_nominal_voltage"]
    base_voltage = 20 * cell_nominal_voltage
    
    # Convert power to watts
    power_w = power_kw * 1000
    
    # Calculate current at base voltage
    current_a = power_w / base_voltage
    
    # Check if current exceeds cell limits
    cell_max_current = battery_info["cell_max_current_a"]
    
    # If current too high, we need to increase voltage (more series)
    # or increase parallel branches (more current capability)
    # For initial calculation, we'll use base voltage and validate later
    v_req = base_voltage
    i_req = current_a
    
    # Simple adjustment: ensure current per cell is reasonable
    # Assuming at least 1 parallel branch per module
    min_parallel = 1
    max_current_per_cell = i_req / min_parallel
    
    if max_current_per_cell > cell_max_current:
        # Need more parallel branches or different voltage
        # For now, just warn - topology solver will handle this
        print(f"Warning: Current per cell ({max_current_per_cell:.1f}A) "
              f"exceeds max ({cell_max_current}A)")
    
    return v_req, i_req

def main():
    parser = argparse.ArgumentParser(description="Calculate DRBP power requirements")
    parser.add_argument("--battery", required=True, help="Battery state JSON file")
    parser.add_argument("--power", type=float, required=True, help="Required power in kW")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    parser.add_argument("--speed", type=float, default=60, help="Speed in km/h")
    parser.add_argument("--gradient", type=float, default=0, help="Road gradient percent")
    parser.add_argument("--output", help="Output JSON file (optional)")
    
    args = parser.parse_args()
    
    # Load battery state
    with open(args.battery, 'r', encoding='utf-8') as f:
        battery_info = json.load(f)
    
    # Calculate actual power demand (including road load)
    speed_mps = args.speed * 1000 / 3600  # km/h to m/s
    actual_power_w = calculate_road_load_power(
        speed_mps, args.gradient, DEFAULT_VEHICLE
    )
    actual_power_kw = actual_power_w / 1000
    
    # Use the larger of required power or calculated power
    power_kw = max(args.power, actual_power_kw)
    
    # Calculate battery requirements
    v_req, i_req = calculate_battery_requirements(
        power_kw, args.duration, battery_info
    )
    
    # Prepare output
    result = {
        "status": True,
        "v_req": round(v_req, 2),
        "i_req": round(i_req, 2),
        "power_kw": round(power_kw, 2),
        "actual_power_kw": round(actual_power_kw, 2),
        "calculations": {
            "base_voltage_v": round(20 * battery_info["cell_nominal_voltage"], 2),
            "required_power_w": round(power_kw * 1000, 2),
            "duration_s": args.duration * 60,
            "energy_wh": round(power_kw * args.duration / 60 * 1000, 2)
        }
    }
    
    # Output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {args.output}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result

if __name__ == "__main__":
    main()