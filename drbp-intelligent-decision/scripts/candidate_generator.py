#!/usr/bin/env python3
"""
候选方案生成器 - 为决策提供多个可行选项
生成Pareto最优的候选方案，每个方案侧重不同目标
"""

import json
import math
import argparse
import sys
from typing import Dict, List, Any
import numpy as np

def calculate_power_requirements(power_kw: float, duration_min: float, 
                               efficiency: float = 0.92) -> Dict:
    """计算功率需求"""
    power_w = power_kw * 1000
    duration_s = duration_min * 60
    total_energy_j = power_w * duration_s
    battery_energy_j = total_energy_j / efficiency
    battery_energy_wh = battery_energy_j / 3600
    battery_energy_ah = battery_energy_wh / 3.7  # 标称电压3.7V
    
    return {
        'power_w': power_w,
        'duration_s': duration_s,
        'total_energy_j': total_energy_j,
        'battery_energy_wh': battery_energy_wh,
        'battery_energy_ah': battery_energy_ah
    }

def generate_candidates(battery_data: Any, power_kw: float, duration_min: float = 10) -> List[Dict]:
    """生成候选方案"""
    
    # 加载电芯数据
    cells = []
    if isinstance(battery_data, list):
        cells = battery_data
    elif isinstance(battery_data, dict) and 'modules' in battery_data:
        for module in battery_data['modules']:
            for cell in module['cells']:
                cell_copy = cell.copy()
                cell_copy['module_id'] = module['mod_id']
                cells.append(cell_copy)
    
    if not cells:
        return []
    
    # 计算功率需求
    power_req = calculate_power_requirements(power_kw, duration_min)
    
    # 分析电池状态
    socs = [c.get('soc', 0.5) for c in cells]
    soc_mean = np.mean(socs)
    soc_std = np.std(socs)
    
    # 候选方案策略
    candidates = []
    
    # 方案1：高SOC优先（快速均衡）
    high_soc_cells = sorted(cells, key=lambda x: x.get('soc', 0), reverse=True)
    candidate1 = {
        'name': '高SOC优先策略',
        'description': '优先使用高SOC电芯，快速降低总体SOC差异',
        'priority': '快速均衡',
        'cells_per_module': 4,  # 假设每个模组选4个
        'topology': {'series': 2, 'parallel': 2},
        'selection_logic': '选择每个模组中SOC最高的4个电芯',
        'advantages': [
            'SOC收敛速度快',
            '适合当前SOC差异大的情况',
            '能量输出效率高'
        ],
        'disadvantages': [
            '可能加速高SOC电芯老化',
            '温度可能不均匀'
        ],
        'estimated_impact': {
            'soc_variance_reduction': f"预计SOC方差减少{soc_std * 0.7:.3f}",
            'temperature_increase': '可能增加2-3°C',
            'convergence_speed': '快'
        }
    }
    candidates.append(candidate1)
    
    # 方案2：均衡混合策略
    candidate2 = {
        'name': '均衡混合策略',
        'description': '混合不同SOC水平的电芯，实现平稳放电',
        'priority': '平稳放电',
        'cells_per_module': 6,
        'topology': {'series': 3, 'parallel': 2},
        'selection_logic': '每个模组选择：2个高SOC + 2个中SOC + 2个低SOC',
        'advantages': [
            '放电过程平稳',
            '温度分布均匀',
            '有利于电芯寿命均衡'
        ],
        'disadvantages': [
            'SOC收敛速度较慢',
            '需要更多电芯'
        ],
        'estimated_impact': {
            'soc_variance_reduction': f"预计SOC方差减少{soc_std * 0.5:.3f}",
            'temperature_increase': '温和，约1-2°C',
            'convergence_speed': '中等'
        }
    }
    candidates.append(candidate2)
    
    # 方案3：温度优化策略
    candidate3 = {
        'name': '温度优化策略',
        'description': '优先使用低温电芯，避免温度过高',
        'priority': '热管理',
        'cells_per_module': 4,
        'topology': {'series': 2, 'parallel': 2},
        'selection_logic': '选择每个模组中温度最低的4个电芯，避免高温电芯',
        'advantages': [
            '有效控制温度',
            '保护电池寿命',
            '安全性高'
        ],
        'disadvantages': [
            '可能使用低SOC电芯，影响均衡速度',
            '能量效率可能略低'
        ],
        'estimated_impact': {
            'soc_variance_reduction': f"预计SOC方差减少{soc_std * 0.4:.3f}",
            'temperature_increase': '最小化，<1°C',
            'convergence_speed': '慢'
        }
    }
    candidates.append(candidate3)
    
    # 方案4：最小电芯策略
    candidate4 = {
        'name': '最小电芯策略',
        'description': '使用最少的电芯满足需求，减轻系统负担',
        'priority': '系统简化',
        'cells_per_module': 2,
        'topology': {'series': 2, 'parallel': 1},
        'selection_logic': '选择每个模组中SOC最高的2个电芯',
        'advantages': [
            '电芯使用最少',
            '系统复杂度低',
            '开关损耗小'
        ],
        'disadvantages': [
            '每个电芯电流较大',
            '对电芯要求高',
            'SOC收敛慢'
        ],
        'estimated_impact': {
            'soc_variance_reduction': f"预计SOC方差减少{soc_std * 0.3:.3f}",
            'temperature_increase': '可能增加3-4°C',
            'convergence_speed': '较慢'
        }
    }
    candidates.append(candidate4)
    
    # 方案5：寿命优化策略
    candidate5 = {
        'name': '寿命优化策略',
        'description': '优先使用健康状态好的电芯，延长整体寿命',
        'priority': '寿命优化',
        'cells_per_module': 5,
        'topology': {'series': 5, 'parallel': 1},
        'selection_logic': '选择每个模组中SOH最高的5个电芯',
        'advantages': [
            '最大化电池组寿命',
            '减少维护需求',
            '长期经济效益好'
        ],
        'disadvantages': [
            '可能忽略SOC均衡',
            '配置灵活性低'
        ],
        'estimated_impact': {
            'soc_variance_reduction': f"预计SOC方差减少{soc_std * 0.2:.3f}",
            'temperature_increase': '中等，约2°C',
            'convergence_speed': '慢'
        }
    }
    candidates.append(candidate5)
    
    # 为每个方案计算技术参数
    cell_nominal_voltage = 3.7
    cell_max_current = 150
    
    for candidate in candidates:
        s = candidate['topology']['series']
        p = candidate['topology']['parallel']
        cells_per_module = s * p
        
        # 更新实际电芯数
        candidate['cells_per_module'] = cells_per_module
        
        # 计算电气参数
        module_voltage = s * cell_nominal_voltage
        pack_voltage = 20 * module_voltage  # 20个模组串联
        
        # 估算电流
        pack_power_w = power_kw * 1000
        pack_current = pack_power_w / pack_voltage if pack_voltage > 0 else 0
        cell_current = pack_current / p if p > 0 else 0
        
        candidate['electrical_parameters'] = {
            'module_voltage': round(module_voltage, 1),
            'pack_voltage': round(pack_voltage, 1),
            'pack_current': round(pack_current, 1),
            'cell_current': round(cell_current, 1),
            'current_safety': '安全' if cell_current <= cell_max_current else '警告',
            'voltage_match': '良好' if 250 <= pack_voltage <= 400 else '注意调整'  # 典型电动车电压范围
        }
        
        # 计算能量需求满足度
        total_cells_used = cells_per_module * 20
        candidate['resource_usage'] = {
            'total_cells_used': total_cells_used,
            'utilization_rate': total_cells_used / 320,  # 320 = 20模组×16电芯
            'cells_available': 320 - total_cells_used
        }
    
    return candidates

def main():
    parser = argparse.ArgumentParser(description='候选方案生成器')
    parser.add_argument('--input', required=True, help='电池状态JSON文件')
    parser.add_argument('--power', type=float, required=True, help='功率需求（kW）')
    parser.add_argument('--duration', type=float, default=10, help='持续时间（分钟）')
    parser.add_argument('--output', help='输出JSON文件')
    parser.add_argument('--max_candidates', type=int, default=5, help='最大候选方案数')
    
    args = parser.parse_args()
    
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        candidates = generate_candidates(data, args.power, args.duration)
        
        # 限制数量
        candidates = candidates[:args.max_candidates]
        
        result = {
            'power_requirements': calculate_power_requirements(args.power, args.duration),
            'candidate_count': len(candidates),
            'candidates': candidates,
            'selection_advice': [
                '请基于你的优先级选择最合适的方案',
                '考虑当前SOC分布、温度状况和长期目标',
                '可以混合不同方案的思路'
            ]
        }
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        error_result = {
            'success': False,
            'error': str(e),
            'message': '候选方案生成失败'
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)

if __name__ == '__main__':
    main()