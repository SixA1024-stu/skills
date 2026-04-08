#!/usr/bin/env python3
"""
Main agent for DRBP balanced discharge management.
Orchestrates the complete workflow: LLM strategy selection → cell selection →
topology determination → safety validation → structured output.
"""

import json
import os
import sys
import argparse
import subprocess
import tempfile
from typing import Dict, Optional
import datetime

# Default configuration
DEFAULT_CONFIG = {
    "llm_api_endpoint": "https://api.openai.com/v1/chat/completions",
    "llm_model": "gpt-4",
    "fallback_strategy": "highest_soc",
    "min_cells_per_module": 1,
    "max_cells_per_module": 8,
    "safety_margin_multiplier": 1.1,  # 10% safety margin on power
    "output_dir": "output",
    "log_dir": "logs"
}

def call_llm_api(prompt: str, api_key: str, config: Dict) -> Optional[Dict]:
    """
    Call LLM API for strategy selection.
    
    This is a placeholder implementation. Replace with actual API call
    based on the LLM provider being used.
    """
    # For development/testing, return a mock response
    print("Warning: Using mock LLM response (replace with actual API call)")
    
    # Mock response for equilibrium strategy
    mock_response = {
        "strategy": "equilibrium",
        "reason": "SOC标准差0.18，需要快速收敛以达成均衡放电目标",
        "parameters": {
            "cells_per_module": 4,
            "priority_weights": {"soc": 0.9, "soh": 0.1}
        }
    }
    
    # In production, implement actual API call:
    # import requests
    # headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    # payload = {
    #     "model": config["llm_model"],
    #     "messages": [{"role": "user", "content": prompt}],
    #     "temperature": 0.1
    # }
    # response = requests.post(config["llm_api_endpoint"], headers=headers, json=payload)
    # return response.json()
    
    return mock_response

def generate_llm_prompt(battery_summary: Dict, navigation: Dict, 
                       available_strategies: Dict) -> str:
    """Generate prompt for LLM strategy selection."""
    
    prompt = f"""你是一个电池管理系统专家，负责管理动态可重构电池组(DRBP)。
电池组架构：20个模组串联，每个模组16个电芯(4x4)，电芯容量一致。

## 当前电池状态
{json.dumps(battery_summary, indent=2, ensure_ascii=False)}

## 导航需求
{json.dumps(navigation, indent=2, ensure_ascii=False)}

## 可用策略
{json.dumps(available_strategies, indent=2, ensure_ascii=False)}

## 任务
选择最适合当前情况的策略，确保：
1. 所有电芯能够均衡放电（最终目标：放电结束时每个电芯SOC接近0）
2. 满足10分钟恒定功率需求
3. 考虑电芯健康状态和温度分布
4. 尽量少用电芯（只要满足需求即可）

## 输出格式
```json
{{
  "strategy": "策略名称",
  "reason": "选择理由（中文）",
  "parameters": {{
    "cells_per_module": 每个模组选择的电芯数,
    "priority_weights": {{"soc": 权重, "soh": 权重, "temperature": 权重}}
  }}
}}
```

请只输出JSON，不要有其他内容。"""
    
    return prompt

def run_command(cmd: str, description: str) -> Dict:
    """Run a shell command and parse JSON output."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        output = json.loads(result.stdout)
        print(f"Success: {description}")
        return output
    except subprocess.CalledProcessError as e:
        print(f"Error running {description}:")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        raise
    except json.JSONDecodeError as e:
        print(f"JSON decode error in {description}:")
        print(f"Output: {result.stdout if 'result' in locals() else 'N/A'}")
        raise

def create_battery_summary(battery_info: Dict) -> Dict:
    """Create summary statistics for LLM prompt."""
    summary = {
        "total_modules": len(battery_info["modules"]),
        "modules": []
    }
    
    for module in battery_info["modules"][:3]:  # Sample first 3 modules
        cells = module["cells"]
        soc_values = [c["soc"] for c in cells]
        temp_values = [c["temperature_c"] for c in cells]
        soh_values = [c.get("soh", 1.0) for c in cells]
        
        summary["modules"].append({
            "mod_id": module["mod_id"],
            "soc_stats": {
                "avg": sum(soc_values) / len(soc_values),
                "min": min(soc_values),
                "max": max(soc_values),
                "std": (sum((s - sum(soc_values)/len(soc_values))**2 for s in soc_values) / len(soc_values))**0.5
            },
            "temperature_stats": {
                "avg": sum(temp_values) / len(temp_values),
                "max": max(temp_values)
            },
            "soh_stats": {
                "avg": sum(soh_values) / len(soh_values),
                "min": min(soh_values)
            }
        })
    
    return summary

def fallback_highest_soc(battery_info: Dict, power_kw: float) -> Dict:
    """Fallback strategy: select cells with highest SOC."""
    print("Using fallback strategy: highest SOC cells")
    
    # Simple heuristic: select enough cells to share current
    cell_max_current = battery_info["cell_max_current_a"]
    required_current = (power_kw * 1000) / (20 * battery_info["cell_nominal_voltage"])
    min_parallel = max(1, int(required_current / cell_max_current) + 1)
    
    # Each module needs at least min_parallel cells
    cells_per_module = min_parallel * 2  # Double for safety
    
    return {
        "strategy": "highest_soc_fallback",
        "reason": "LLM决策失败，使用最高SOC电芯作为后备策略",
        "parameters": {
            "cells_per_module": cells_per_module,
            "priority_weights": {"soc": 1.0}
        }
    }

def main():
    parser = argparse.ArgumentParser(description="DRBP Main Agent")
    parser.add_argument("--battery", required=True, help="Battery state JSON file")
    parser.add_argument("--power", type=float, required=True, help="Required power in kW")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    parser.add_argument("--strategy", choices=["llm", "deterministic"], default="llm",
                       help="Strategy selection method")
    parser.add_argument("--llm_api_key", help="LLM API key (required for llm strategy)")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    parser.add_argument("--keep_temp", action="store_true", help="Keep temporary files")
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(DEFAULT_CONFIG["output_dir"], exist_ok=True)
    os.makedirs(DEFAULT_CONFIG["log_dir"], exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Load battery state
    with open(args.battery, 'r', encoding='utf-8') as f:
        battery_info = json.load(f)
    
    # Create navigation info
    navigation = {
        "required_power_kw": args.power,
        "duration_min": args.duration,
        "timestamp": timestamp
    }
    
    # Step 1: Strategy Selection
    strategy_result = None
    if args.strategy == "llm":
        if not args.llm_api_key:
            print("Error: LLM strategy requires --llm_api_key")
            sys.exit(1)
        
        # Prepare LLM prompt
        battery_summary = create_battery_summary(battery_info)
        
        available_strategies = {
            "high_energy": "高能量策略：优先使用SOC高的电芯，最大化能量输出",
            "equilibrium": "均衡策略：优先使用SOC最高的电芯，快速收敛SOC分布",
            "thermal_management": "热管理策略：优先使用高温电芯，改善温度分布",
            "lifetime_optimization": "寿命优化策略：优先使用健康度低的电芯，均衡老化"
        }
        
        prompt = generate_llm_prompt(battery_summary, navigation, available_strategies)
        
        if args.verbose:
            print("LLM Prompt:")
            print(prompt)
        
        # Call LLM
        try:
            llm_response = call_llm_api(prompt, args.llm_api_key, DEFAULT_CONFIG)
            strategy_result = llm_response
            print(f"LLM selected strategy: {strategy_result['strategy']}")
        except Exception as e:
            print(f"LLM API call failed: {e}")
            print("Falling back to deterministic strategy...")
            strategy_result = fallback_highest_soc(battery_info, args.power)
    
    else:  # deterministic
        # Use simple deterministic strategy
        strategy_result = {
            "strategy": "equilibrium",
            "reason": "确定性策略：默认均衡放电",
            "parameters": {
                "cells_per_module": 4,
                "priority_weights": {"soc": 0.9, "soh": 0.1}
            }
        }
    
    # Step 2: Calculate Requirements
    req_output = f"temp_requirements_{timestamp}.json"
    cmd = f'python scripts/calculate_requirements.py --battery "{args.battery}" --power {args.power} --duration {args.duration} --output "{req_output}"'
    requirements = run_command(cmd, "Power Requirement Calculation")
    
    # Step 3: Cell Selection
    cells_per_module = strategy_result["parameters"]["cells_per_module"]
    weights_json = json.dumps(strategy_result["parameters"]["priority_weights"])
    
    cells_output = f"temp_selected_cells_{timestamp}.json"
    cmd = f'python scripts/cell_selector.py --battery "{args.battery}" --strategy custom --weights \'{weights_json}\' --cells_per_module {cells_per_module} --power {args.power} --duration {args.duration} --output "{cells_output}"'
    selected_cells = run_command(cmd, "Cell Selection")
    
    if not selected_cells["status"]:
        print("Cell selection failed. Using fallback...")
        # Fallback: use highest SOC cells
        strategy_result = fallback_highest_soc(battery_info, args.power)
        cells_per_module = strategy_result["parameters"]["cells_per_module"]
        weights_json = json.dumps(strategy_result["parameters"]["priority_weights"])
        
        cmd = f'python scripts/cell_selector.py --battery "{args.battery}" --strategy custom --weights \'{weights_json}\' --cells_per_module {cells_per_module} --power {args.power} --duration {args.duration} --output "{cells_output}"'
        selected_cells = run_command(cmd, "Fallback Cell Selection")
    
    # Step 4: Topology Determination
    topology_output = f"temp_topology_{timestamp}.json"
    cmd = f'python scripts/topology_solver.py --selected_cells "{cells_output}" --v_req {requirements["v_req"]} --i_req {requirements["i_req"]} --cell_nominal_voltage {battery_info["cell_nominal_voltage"]} --cell_max_current {battery_info["cell_max_current_a"]} --output "{topology_output}"'
    topology = run_command(cmd, "Topology Determination")
    
    if not topology["status"]:
        print("Error: No valid topology found")
        # Try with more cells
        cells_per_module += 2
        print(f"Retrying with {cells_per_module} cells per module...")
        
        cmd = f'python scripts/cell_selector.py --battery "{args.battery}" --strategy custom --weights \'{weights_json}\' --cells_per_module {cells_per_module} --power {args.power} --duration {args.duration} --output "{cells_output}"'
        selected_cells = run_command(cmd, "Retry Cell Selection")
        
        cmd = f'python scripts/topology_solver.py --selected_cells "{cells_output}" --v_req {requirements["v_req"]} --i_req {requirements["i_req"]} --cell_nominal_voltage {battery_info["cell_nominal_voltage"]} --cell_max_current {battery_info["cell_max_current_a"]} --output "{topology_output}"'
        topology = run_command(cmd, "Retry Topology Determination")
    
    # Step 5: Safety Validation
    safety_output = f"temp_safety_{timestamp}.json"
    cmd = f'python scripts/safety_validator.py --topology "{topology_output}" --battery "{args.battery}" --requirements "{req_output}" --output "{safety_output}"'
    safety = run_command(cmd, "Safety Validation")
    
    # Step 6: Generate Final Output
    final_output = {
        "status": safety["all_checks_passed"],
        "v_req": requirements["v_req"],
        "i_req": requirements["i_req"],
        "selected_cells": topology["arranged_modules"],
        "strategy_used": strategy_result,
        "topology": topology["topology"],
        "safety_check": safety["summary"],
        "reason": f"{strategy_result['reason']}。{safety['checks'][3]['checks'][0] if len(safety['checks']) > 3 else '安全校验通过。'}"
    }
    
    # Add detailed safety check results if verbose
    if args.verbose:
        final_output["detailed_safety"] = safety
    
    # Save final output
    if args.output:
        output_file = args.output
    else:
        output_file = os.path.join(DEFAULT_CONFIG["output_dir"], f"drbp_result_{timestamp}.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"Final output saved to: {output_file}")
    print(f"Status: {'SUCCESS' if final_output['status'] else 'FAILED'}")
    print(f"Strategy: {strategy_result['strategy']}")
    print(f"Topology: {topology['summary']['configuration']}")
    print(f"Cells used: {topology['summary']['total_cells_used']} / {20*16}")
    print(f"Safety: {safety['summary']}")
    
    # Clean up temporary files
    if not args.keep_temp:
        for temp_file in [req_output, cells_output, topology_output, safety_output]:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                if args.verbose:
                    print(f"Removed temp file: {temp_file}")
    
    return final_output

if __name__ == "__main__":
    main()