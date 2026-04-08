# LLM Prompt Templates

This document contains prompt templates for Large Language Model (LLM) interactions in the DRBP system. These prompts are designed to elicit consistent, structured responses for battery management decisions.

## Prompt Design Principles

### 1. Structured Output
- Always specify exact JSON output format
- Include examples when helpful
- Request only JSON, no additional text

### 2. Context Provision
- Provide sufficient technical context
- Include relevant constraints and goals
- Share current state information

### 3. Clear Instructions
- State the decision to be made
- Specify evaluation criteria
- Define success metrics

## Core Prompt Templates

### Template 1: Strategy Selection

**Purpose**: Select optimal discharge strategy based on battery state and navigation requirements.

```text
You are a battery management system expert for a Dynamic Reconfigurable Battery Pack (DRBP).

## System Architecture
- 20 modules connected in series (fixed)
- Each module has 16 cells (4×4 matrix)
- Cells can be dynamically connected in series/parallel within each module
- Goal: Balanced discharge (all cells approach SOC=0 simultaneously)

## Current Battery State
{json_battery_summary}

## Navigation Requirements
{json_navigation}

## Available Strategies
{json_available_strategies}

## Task
Select the most appropriate strategy considering:
1. **Primary goal**: All cells should approach SOC=0 simultaneously
2. **Secondary goals**: Extend battery life, maintain safe temperatures
3. **Constraints**: Must meet {power_kw}kW for {duration_min} minutes
4. **Efficiency**: Use minimal cells necessary

## Output Format
Return ONLY valid JSON in this exact format:
```json
{
  "strategy": "strategy_name",
  "reason": "Selection reasoning in Chinese (100-200 characters)",
  "parameters": {
    "cells_per_module": integer_between_1_and_8,
    "priority_weights": {
      "soc": float_between_0_and_1,
      "soh": float_between_0_and_1,
      "temperature": float_between_minus_1_and_1,
      "internal_resistance": float_between_minus_1_and_1,
      "cycles": float_between_minus_1_and_1
    }
  }
}
```

## Guidelines
- Weights should sum to approximately 1.0
- Negative weights for parameters where lower values are better (temperature, resistance)
- `cells_per_module` must be sufficient to meet power demand
- Consider SOC distribution, temperature spread, and cell health

Return ONLY the JSON object.
```

### Template 2: Strategy Selection with Examples

**Purpose**: Same as Template 1 but with example responses for few-shot learning.

```text
You are a battery management system expert. Select the optimal discharge strategy.

## System Info
{system_info}

## Battery State
{battery_state}

## Navigation
{navigation}

## Available Strategies
{strategies}

## Examples

### Example 1 (High SOC dispersion)
Input: SOC std=0.18, Avg temp=28°C, Power=25kW, Duration=10min
Output:
```json
{
  "strategy": "equilibrium",
  "reason": "SOC标准差较大(0.18)，需要快速收敛以达成均衡放电目标",
  "parameters": {
    "cells_per_module": 5,
    "priority_weights": {
      "soc": 0.9,
      "soh": 0.05,
      "temperature": -0.05,
      "internal_resistance": -0.05,
      "cycles": -0.05
    }
  }
}
```

### Example 2 (High temperature)
Input: Max temp=48°C, SOC std=0.05, Power=20kW
Output:
```json
{
  "strategy": "thermal_management",
  "reason": "最高温度48°C接近安全限值，需要优先降温",
  "parameters": {
    "cells_per_module": 6,
    "priority_weights": {
      "soc": 0.2,
      "soh": 0.0,
      "temperature": 0.8,
      "internal_resistance": -0.1,
      "cycles": -0.1
    }
  }
}
```

### Example 3 (Low power demand)
Input: Power=10kW, SOC std=0.08, Avg SOH=0.92
Output:
```json
{
  "strategy": "minimum_cells",
  "reason": "功率需求较低，可最小化使用电芯数量，让其他电芯休息",
  "parameters": {
    "cells_per_module": 2,
    "priority_weights": {
      "soc": 0.5,
      "soh": 0.3,
      "temperature": -0.2,
      "internal_resistance": -0.3,
      "cycles": -0.3
    }
  }
}
```

## Current Situation
{current_situation}

## Your Task
Select strategy for current situation.

Output ONLY JSON in the specified format.
```

### Template 3: Topology Validation

**Purpose**: Validate or suggest improvements to a proposed topology.

```text
You are a battery topology expert. Analyze the proposed battery configuration.

## Proposed Configuration
{json_proposed_topology}

## Battery State
{json_battery_state}

## Requirements
- Voltage: {v_req}V ±5%
- Current: {i_req}A
- Duration: {duration_min} minutes
- Power: {power_kw}kW

## Safety Constraints
{json_safety_constraints}

## Task
Analyze the proposed configuration and suggest improvements if needed.

Consider:
1. Voltage matching (is total voltage appropriate?)
2. Current sharing (will parallel branches balance?)
3. Thermal considerations (any hotspots likely?)
4. Cell stress (are weak cells over-stressed?)
5. Efficiency (could fewer cells be used?)

## Output Format
```json
{
  "validation_result": "approve" | "modify" | "reject",
  "confidence": float_between_0_and_1,
  "issues": [
    {
      "issue": "description",
      "severity": "low" | "medium" | "high",
      "suggestion": "how to address"
    }
  ],
  "suggested_modifications": {
    "cells_per_module": integer,
    "series_per_module": integer,
    "parallel_per_module": integer
  },
  "reason": "Detailed explanation in Chinese"
}
```

Return ONLY the JSON object.
```

### Template 4: Fault Diagnosis

**Purpose**: Diagnose issues based on sensor data and symptoms.

```text
You are a battery fault diagnosis expert.

## System State
{json_system_state}

## Symptoms
{symptoms_list}

## Recent Events
{recent_events}

## Available Diagnostics
{available_diagnostics}

## Task
Diagnose the most likely issue and recommend actions.

## Output Format
```json
{
  "diagnosis": "primary_issue",
  "confidence": float_between_0_and_1,
  "alternative_possibilities": [
    {"issue": "name", "probability": float}
  ],
  "immediate_actions": [
    {"action": "description", "priority": "high" | "medium" | "low"}
  ],
  "investigation_steps": [
    {"step": "description", "expected_result": "what to look for"}
  ],
  "safety_impact": "none" | "minor" | "major" | "critical",
  "reason": "Diagnostic reasoning in Chinese"
}
```

Return ONLY the JSON object.
```

### Template 5: Performance Optimization

**Purpose**: Suggest optimizations based on historical performance data.

```text
You are a battery performance optimization expert.

## Historical Performance Data
{json_performance_history}

## Current Configuration
{json_current_config}

## Goals
1. Improve SOC convergence rate
2. Reduce temperature gradients
3. Extend battery life
4. Maintain or improve efficiency

## Constraints
{safety_and_operational_constraints}

## Task
Analyze historical data and suggest parameter adjustments.

## Output Format
```json
{
  "analysis_summary": "Key findings from historical data",
  "recommended_adjustments": [
    {
      "parameter": "parameter_name",
      "current_value": "value",
      "recommended_value": "value",
      "expected_improvement": "description",
      "confidence": float
    }
  ],
  "strategy_adjustments": {
    "weights_adjustment": {
      "soc": {"change": "+0.1" | "-0.05" | "no_change"},
      "temperature": {"change": "...", "reason": "..."}
    },
    "topology_preferences": {
      "prefer_more_parallel": boolean,
      "prefer_higher_voltage": boolean
    }
  },
  "monitoring_recommendations": [
    {"metric": "metric_to_watch", "threshold": "value"}
  ],
  "reason": "Optimization reasoning in Chinese"
}
```

Return ONLY the JSON object.
```

## Battery State Summary Format

The `{json_battery_summary}` placeholder should contain:

```json
{
  "summary_timestamp": "2026-04-08T10:30:00+08:00",
  "total_modules": 20,
  "modules_sampled": 3,
  "soc_statistics": {
    "mean": 0.65,
    "std": 0.12,
    "min": 0.42,
    "max": 0.89,
    "distribution": "skewed_high"  // or "uniform", "skewed_low"
  },
  "temperature_statistics": {
    "mean": 28.5,
    "max": 35.2,
    "min": 22.1,
    "gradient": 13.1
  },
  "soh_statistics": {
    "mean": 0.88,
    "min": 0.72,
    "max": 0.95
  },
  "recent_trends": {
    "soc_convergence": "improving",  // or "stable", "diverging"
    "temperature_trend": "stable",
    "aging_rate": "normal"
  },
  "notable_issues": [
    {"module": 3, "issue": "high_temp", "severity": "medium"},
    {"module": 12, "issue": "low_soh", "severity": "low"}
  ]
}
```

## Navigation Information Format

The `{json_navigation}` placeholder should contain:

```json
{
  "segment_id": "nav_001",
  "duration_min": 10,
  "required_power_kw": 25.5,
  "power_source": "constant_power",
  "environment": {
    "ambient_temp_c": 25.0,
    "road_gradient_percent": 2.5,
    "road_condition": "dry",
    "elevation_m": 120
  },
  "vehicle_state": {
    "mass_kg": 1850,
    "cargo_kg": 150,
    "driving_mode": "normal"  // or "eco", "sport"
  },
  "historical_context": {
    "previous_power_kw": 22.1,
    "previous_duration_min": 10,
    "previous_strategy": "high_energy"
  }
}
```

## Available Strategies Format

The `{json_available_strategies}` placeholder should contain:

```json
{
  "strategies": {
    "high_energy": {
      "description": "Maximize energy output. Prioritize high-SOC cells.",
      "typical_cells_per_module": [3, 6],
      "best_for": ["high_soc", "flat_terrain", "moderate_temp"],
      "avoid_when": ["high_temp", "low_soh", "steep_grades"]
    },
    "equilibrium": {
      "description": "Fast SOC convergence. Prioritize highest-SOC cells.",
      "typical_cells_per_module": [4, 8],
      "best_for": ["uneven_soc", "preparing_for_long_discharge"],
      "avoid_when": ["low_power_demand", "thermal_issues"]
    },
    "thermal_management": {
      "description": "Control temperature distribution. Prioritize high-temperature cells.",
      "typical_cells_per_module": [5, 8],
      "best_for": ["high_temp", "hot_environment", "cooling_needed"],
      "avoid_when": ["low_temp", "min_cells_needed"]
    },
    "lifetime_optimization": {
      "description": "Extend battery life. Prioritize low-SOH cells.",
      "typical_cells_per_module": [3, 6],
      "best_for": ["aging_battery", "mixed_soh", "mission_critical"],
      "avoid_when": ["high_power_demand", "thermal_issues"]
    },
    "minimum_cells": {
      "description": "Use minimum cells necessary. Balance rest and usage.",
      "typical_cells_per_module": [1, 4],
      "best_for": ["low_power", "cell_rest", "efficiency"],
      "avoid_when": ["high_power", "thermal_issues", "soc_imbalance"]
    }
  },
  "selection_guidelines": {
    "primary_factor": "soc_std > 0.15 → equilibrium",
    "secondary_factor": "max_temp > 40 → thermal_management",
    "tertiary_factor": "avg_soh < 0.85 → lifetime_optimization"
  }
}
```

## Prompt Optimization Tips

### 1. Temperature Control
- Use `temperature: 0.1` for deterministic outputs
- Lower for creative solutions, higher for consistency

### 2. Few-Shot Learning
- Provide 2-3 high-quality examples
- Ensure examples cover different scenarios
- Include both successful and edge cases

### 3. Output Constraints
- Use `response_format: {"type": "json_object"}` if supported
- Specify exact key names and types
- Include validation rules in the prompt

### 4. Context Management
- Keep prompts under 4000 tokens when possible
- Summarize rather than include raw data
- Use statistical summaries instead of full datasets

### 5. Error Handling
- Instruct LLM to return error if insufficient information
- Include fallback options in the prompt
- Specify what to do when uncertain

## Integration with DRBP System

### Prompt Generation Function

```python
def generate_strategy_prompt(battery_summary, navigation, strategies):
    """Generate LLM prompt for strategy selection."""
    
    template = """You are a battery management system expert for a Dynamic Reconfigurable Battery Pack (DRBP).

## System Architecture
- 20 modules connected in series (fixed)
- Each module has 16 cells (4×4 matrix)
- Cells can be dynamically connected in series/parallel within each module
- Goal: Balanced discharge (all cells approach SOC=0 simultaneously)

## Current Battery State
{battery_summary}

## Navigation Requirements
{navigation}

## Available Strategies
{strategies}

## Task
Select the most appropriate strategy considering:
1. **Primary goal**: All cells should approach SOC=0 simultaneously
2. **Secondary goals**: Extend battery life, maintain safe temperatures
3. **Constraints**: Must meet {power_kw}kW for {duration_min} minutes
4. **Efficiency**: Use minimal cells necessary

## Output Format
Return ONLY valid JSON in this exact format:
```json
{{
  "strategy": "strategy_name",
  "reason": "Selection reasoning in Chinese (100-200 characters)",
  "parameters": {{
    "cells_per_module": integer_between_1_and_8,
    "priority_weights": {{
      "soc": float_between_0_and_1,
      "soh": float_between_0_and_1,
      "temperature": float_between_minus_1_and_1,
      "internal_resistance": float_between_minus_1_and_1,
      "cycles": float_between_minus_1_and_1
    }}
  }}
}}
```

Return ONLY the JSON object."""
    
    # Fill in the template
    power_kw = navigation.get("required_power_kw", 25)
    duration_min = navigation.get("duration_min", 10)
    
    prompt = template.format(
        battery_summary=json.dumps(battery_summary, indent=2, ensure_ascii=False),
        navigation=json.dumps(navigation, indent=2, ensure_ascii=False),
        strategies=json.dumps(strategies, indent=2, ensure_ascii=False),
        power_kw=power_kw,
        duration_min=duration_min
    )
    
    return prompt
```

### Response Parsing Function

```python
def parse_llm_response(response_text):
    """Parse LLM response and extract strategy."""
    
    try:
        # Try to parse as JSON
        result = json.loads(response_text)
        
        # Validate required fields
        required = ["strategy", "reason", "parameters"]
        for field in required:
            if field not in result:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate parameters
        params = result["parameters"]
        if "cells_per_module" not in params:
            raise ValueError("Missing cells_per_module")
        if "priority_weights" not in params:
            raise ValueError("Missing priority_weights")
        
        # Ensure cells_per_module is within bounds
        cells = params["cells_per_module"]
        if not 1 <= cells <= 8:
            raise ValueError(f"cells_per_module out of range: {cells}")
        
        return result
        
    except json.JSONDecodeError:
        # Try to extract JSON if wrapped in text
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return parse_llm_response(json_match.group())
        else:
            raise ValueError("Could not parse LLM response as JSON")
```

## Testing Prompts

### Test Cases

```python
test_cases = [
    {
        "name": "High SOC dispersion",
        "battery_summary": {
            "soc_statistics": {"mean": 0.75, "std": 0.18, "min": 0.45, "max": 0.95},
            "temperature_statistics": {"mean": 28.0, "max": 32.0, "gradient": 8.0}
        },
        "navigation": {"required_power_kw": 25, "duration_min": 10},
        "expected_strategy": "equilibrium"
    },
    {
        "name": "High temperature",
        "battery_summary": {
            "soc_statistics": {"mean": 0.65, "std": 0.05, "min": 0.60, "max": 0.70},
            "temperature_statistics": {"mean": 42.0, "max": 48.0, "gradient": 12.0}
        },
        "navigation": {"required_power_kw": 20, "duration_min": 10},
        "expected_strategy": "thermal_management"
    }
]
```

## Performance Monitoring

### Metrics to Track

1. **Response quality**: Percentage of valid JSON responses
2. **Strategy appropriateness**: How often selected strategy matches expert judgment
3. **Response time**: Average time to generate response
4. **Token usage**: Average tokens per prompt/response
5. **Error rate**: Percentage of failed parses or invalid outputs

### Continuous Improvement

- Collect real decision outcomes
- Use for fine-tuning or prompt optimization
- A/B test different prompt variations
- Update examples based on operational experience