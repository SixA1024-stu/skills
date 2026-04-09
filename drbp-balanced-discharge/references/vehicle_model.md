---
# Vehicle Dynamics Model

This document describes the vehicle dynamics model used to calculate power requirements for the DRBP system.
---
## Overview

The vehicle model converts navigation information (speed, gradient, etc.) into electrical power requirements at the battery terminals. This is critical for selecting appropriate battery configurations that can meet the actual power demand.

## Fundamental Equations

### 1. Total Resistance Force

The total force resisting vehicle motion consists of four components:

```
F_total = F_aero + F_rolling + F_grade + F_accel
```

Where:
- `F_aero` = Aerodynamic drag force
- `F_rolling` = Rolling resistance force  
- `F_grade` = Hill climbing force
- `F_accel` = Acceleration force (assumed zero for constant speed)

### 2. Power at Wheels

```
P_wheels = F_total × v
```

Where `v` is vehicle speed in m/s.

### 3. Power at Battery

```
P_battery = P_wheels / η_drivetrain + P_auxiliary
```

Where:
- `η_drivetrain` = Overall drivetrain efficiency
- `P_auxiliary` = Power for auxiliary systems (lights, AC, etc.)

## Force Components

### 1. Aerodynamic Drag Force

```
F_aero = 0.5 × ρ × C_d × A × v²
```

| Parameter | Symbol | Typical Value | Units |
|-----------|--------|---------------|-------|
| Air density | ρ | 1.225 | kg/m³ |
| Drag coefficient | C_d | 0.28 | - |
| Frontal area | A | 2.4 | m² |
| Vehicle speed | v | Variable | m/s |

**Notes**:
- Air density decreases with altitude (1.225 kg/m³ at sea level, 15°C)
- Drag coefficient varies with vehicle shape and accessories
- Frontal area depends on vehicle size

### 2. Rolling Resistance Force

```
F_rolling = C_r × m × g × cos(θ)
```

| Parameter | Symbol | Typical Value | Units |
|-----------|--------|---------------|-------|
| Rolling coefficient | C_r | 0.012 | - |
| Vehicle mass | m | 1800 | kg |
| Gravity | g | 9.81 | m/s² |
| Road gradient | θ | Variable | radians |

**Notes**:
- Rolling coefficient depends on tire type and pressure
- Increases by ~20% on wet roads
- Increases with speed (minor effect)

### 3. Grade Force

```
F_grade = m × g × sin(θ)
```

Where `θ` is the road gradient angle.

**Gradient conversion**:
```
θ = arctan(grade_percent / 100)
```

Example: 5% grade = arctan(0.05) ≈ 2.86°

### 4. Acceleration Force (for completeness)

```
F_accel = m × a
```

Where `a` is acceleration in m/s².

For constant speed operation (our primary use case), `a = 0`.

## Drivetrain Efficiency

### Efficiency Chain

```
η_total = η_motor × η_inverter × η_gearbox × η_other
```

| Component | Efficiency | Notes |
|-----------|------------|-------|
| Electric motor | 92-96% | Best at medium torque/speed |
| Power inverter | 97-99% | IGBT/SiC switching losses |
| Gearbox/reducer | 95-98% | Single-speed typical |
| Bearings/couplings | 99% | Mechanical losses |
| **Total drivetrain** | **85-92%** | Typical range |

### Efficiency Mapping

Efficiency varies with operating point:

```
η_motor = f(Torque, Speed)
```

Simplified model for constant speed:
- Optimal: 94% at medium load (50-80% of max torque)
- Reduced: 90% at light load (<30%)
- Reduced: 92% at heavy load (>80%)

## Auxiliary Power Consumption

### Constant Loads

| System | Power | Notes |
|--------|-------|-------|
| Battery management | 100W | Always on |
| Vehicle computers | 200W | Always on |
| Instrumentation | 50W | Always on |
| **Subtotal** | **350W** | |

### Variable Loads

| System | Min Power | Max Power | Notes |
|--------|-----------|-----------|-------|
| Climate control | 500W | 6000W | Depends on settings |
| Lights | 100W | 500W | Time of day, conditions |
| Infotainment | 50W | 300W | User dependent |
| Power steering | 50W | 200W | Speed dependent |
| Brake system | 20W | 100W | Regenerative braking active |
| **Subtotal** | **720W** | **7100W** | |

### Typical Scenarios

| Scenario | Total Auxiliary Power | Notes |
|----------|----------------------|-------|
| Night driving, mild weather | 800-1200W | Lights + basic systems |
| Daytime, AC on | 1500-3000W | Moderate cooling |
| Extreme weather | 4000-7000W | Max heating/cooling |

## Vehicle Parameters Database

### Passenger Vehicle (Typical)

```json
{
  "category": "passenger_sedan",
  "mass_kg": 1800,
  "frontal_area_m2": 2.4,
  "drag_coefficient": 0.28,
  "rolling_coefficient": 0.012,
  "drivetrain_efficiency": 0.92,
  "auxiliary_baseline_w": 350,
  "wheel_radius_m": 0.33
}
```

### SUV/Large Vehicle

```json
{
  "category": "suv",
  "mass_kg": 2200,
  "frontal_area_m2": 2.8,
  "drag_coefficient": 0.32,
  "rolling_coefficient": 0.013,
  "drivetrain_efficiency": 0.90,
  "auxiliary_baseline_w": 400,
  "wheel_radius_m": 0.35
}
```

### Delivery Van

```json
{
  "category": "delivery_van",
  "mass_kg": 3000,
  "frontal_area_m2": 3.2,
  "drag_coefficient": 0.35,
  "rolling_coefficient": 0.014,
  "drivetrain_efficiency": 0.88,
  "auxiliary_baseline_w": 500,
  "wheel_radius_m": 0.38
}
```

## Environmental Factors

### Air Density Correction

```
ρ = ρ_0 × (P / P_0) × (T_0 / T)
```

Where:
- `ρ_0` = 1.225 kg/m³ (standard)
- `P_0` = 101.325 kPa (sea level)
- `T_0` = 288.15 K (15°C)
- `P` = Actual pressure
- `T` = Actual temperature (K)

Simplified for altitude:
```
ρ ≈ 1.225 × e^(-altitude/8500)
```

### Temperature Effects

1. **Battery efficiency**: Decreases at low temperatures
2. **Rolling resistance**: Increases at low temperatures (tire stiffness)
3. **Auxiliary loads**: Heating increases at low temperatures

### Road Surface Effects

| Surface | Rolling Coefficient Multiplier |
|---------|-------------------------------|
| Dry asphalt | 1.0 |
| Wet asphalt | 1.2 |
| Gravel | 1.5 |
| Snow | 2.0 |


### Typical Validation Results

| Condition | Predicted Power | Measured Power | Error |
|-----------|----------------|----------------|-------|
| 60 km/h, flat | 15.2 kW | 15.8 kW | +4% |
| 80 km/h, flat | 23.1 kW | 22.7 kW | -2% |
| 60 km/h, 5% grade | 32.4 kW | 33.1 kW | +2% |
| 40 km/h, flat | 8.7 kW | 9.1 kW | +5% |

**Target accuracy**: ±10% for DRBP purposes

## Integration with Navigation System

### Required Navigation Data

```json
{
  "segment_id": "seg_001",
  "distance_m": 10000,
  "duration_s": 600,
  "average_speed_kmh": 60,
  "max_speed_kmh": 70,
  "gradient_profile": [
    {"distance_m": 0, "gradient_percent": 0},
    {"distance_m": 3000, "gradient_percent": 3},
    {"distance_m": 7000, "gradient_percent": -2}
  ],
  "road_condition": "dry",
  "ambient_temperature_c": 25
}
```

### Power Profile Generation

```
For each 10-minute segment:
1. Calculate average gradient
2. Calculate required power using vehicle model
3. Add safety margin (10%)
4. Output: constant_power_kw for the segment
```

### Battery Requirement Calculation

From constant power P (kW) and duration t (hours):

```
Energy_required = P × t  (kWh)
Battery_energy = Energy_required / η_battery

Where η_battery includes:
- Drivetrain efficiency (already in P)
- Battery discharge efficiency (95-98%)
- DC-DC converter efficiency (97-99%)
```
