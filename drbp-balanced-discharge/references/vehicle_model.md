---
# Vehicle Dynamics Model

This document describes the vehicle dynamics model used to calculate power requirements for the DRBP system.
---
## Overview

The vehicle model converts navigation information (speed, gradient, etc.) into electrical power requirements at the battery terminals. This is critical for selecting appropriate battery configurations that can meet the actual power demand.

Below is the **improved power calculation logic** in English, structured as a direct enhancement to your existing `vehicle_model.md`. You can replace or insert the corresponding sections.


## Improved Power Calculation Logic for DRBP

### 1. Complete Efficiency Chain (Drive & Regeneration)

Original `P_battery` only included `η_drivetrain` and a constant auxiliary load. For accurate battery‑terminal power, the full chain must be considered.

**Drive mode (P_wheels > 0)**:
```
P_battery_drive = (P_wheels / η_drivetrain + P_auxiliary) / (η_dcdc × η_battery_discharge)
```

Where:
- `η_drivetrain = η_motor × η_inverter × η_gearbox` (excluding DC‑DC and battery)
- `η_dcdc` = DC‑DC converter efficiency (0.97 – 0.99)
- `η_battery_discharge` = battery discharge efficiency (0.95 – 0.98)

**Regeneration mode (P_wheels < 0)**:
```
P_battery_regen = P_wheels × η_drivetrain_regen × η_dcdc × η_battery_charge
```

- `η_drivetrain_regen` = regeneration path efficiency (0.80 – 0.90)
- `η_battery_charge` = battery charge efficiency (0.90 – 0.95)

> Add a subsection: *“Efficiency Chain for Regeneration”*.


### 2. Segment‑wise Gradient & Energy Integration

Averaging gradient over a 10‑minute segment underestimates peaks and misses regen opportunities. Instead:

1. **Subdivide** the route into small segments (e.g., 100 m or 1 second).
2. For each sub‑segment, compute instantaneous wheel power using actual gradient, speed, and acceleration.
3. **Integrate energy** over the whole trip (positive = drive, negative = regen).
4. Convert to equivalent constant power: `P_avg = E_total / t_total`.

**Instantaneous wheel power** (including acceleration):
```
P_wheels(t) = [F_aero(t) + F_rolling(t) + F_grade(t) + m·a(t)] × v(t)
```

If navigation only provides average speed, assume constant speed but use real gradient profile:
```
E_wheels = Σ (F_total(v_const, θ_i) × v_const × Δt_i)
```

> Replace the original “Power Profile Generation” logic with this segment‑wise approach.


### 3. Regenerative Braking Model

When `P_wheels < 0` (deceleration or downhill), use regenerative braking first.

**Available regen power**:
```
P_regen_available = min( |P_wheels|, P_regen_max )
```
- `P_regen_max` = min(motor generation limit, battery charge limit, inverter reverse limit)
- Typical: `P_regen_max` ≈ 80‑90% of peak drive power.

**Recovered energy**:
```
E_regen = Σ (P_regen_available × η_regen_chain × Δt)
```
where `η_regen_chain = η_drivetrain_regen × η_dcdc × η_battery_charge`.

> Add a new subsection: *“Regenerative Braking Model”* with typical parameter values.


### 4. Dynamic Vehicle Mass

Fixed mass is unrealistic. Update mass based on load:
```
m = m_curb + m_cargo + m_passenger
```
- `m_curb` = curb weight (from database)
- `m_cargo` = cargo mass (user input or estimate)
- `m_passenger` = 75 kg per person × number of passengers

Both rolling resistance and grade force scale linearly with mass.


### 5. Dynamic Auxiliary Power

Replace constant `P_auxiliary` with a breakdown:
```
P_auxiliary = P_base + P_HVAC + P_lights + P_infotainment
```

- `P_base` = controllers, sensors (100 – 200 W)
- `P_HVAC`:
  - Heating: 2 – 5 kW at -10°C → `max(0, (T_set - T_amb) × 150 W/°C)`, clipped 0‑5 kW
  - Cooling: 1 – 3 kW at 35°C → `max(0, (T_amb - T_set) × 100 W/°C)`, clipped 0‑3 kW
- `P_lights`: low beam 120 W, high beam 200 W
- `P_infotainment`: 50 – 150 W

> Add subsection: *“Auxiliary Power Breakdown”*.


### 6. Motor Efficiency Map (Simplified)

Constant drivetrain efficiency is inaccurate at low loads. Use a simple load‑dependent correction:
```
η_motor = η_max - k × |(τ / τ_max) - 0.6|^2
```
- `η_max` = peak efficiency (e.g., 0.94)
- `τ` = current torque
- `τ_max` = maximum torque at current speed
- `k` = 0.1 – 0.2


