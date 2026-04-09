#!/usr/bin/env python3
"""
安全验证器 - 检查方案是否符合安全约束
验证SOC、电流、温度等关键安全指标
"""

import json
import argparse
import sys
from typing import Dict, List, Any

def load_battery_data(file_path: str) -> List[Dict]:
    """加载电池数据"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    cells = []
    if isinstance(data, list):
        cells = data
    elif isinstance(data, dict) and 'modules' in data:
        for module in data['modules']:
            for cell in module['cells']:
                cell_copy = cell.copy()
                cell_copy['module_id'] = module['mod_id']
                cells.append(cell_copy)
    
    return cells

def check_safety(plan: Dict, battery_data: List[Dict], power_kw: float, duration_min: float = 10) -> Dict:
    """检查方案安全性"""
    
    # 默认安全约束
    constraints = {
        'min_soc': 0.05,
        'max_cell_current': 150,
        'max_cell_temp': 60.0,
        'min_cell_voltage': 3.0,
        'max_cell_voltage': 4.2
    }
    
    # 获取方案参数
    cells_per_module = plan.get('cells_per_module', 4)
    topology = plan.get('topology', {})
    series = topology.get('series', 2)
    parallel = topology.get('parallel', 2)
    
    # 计算电气参数
    cell_nominal_voltage = 3.7
    module_voltage = series * cell_nominal_voltage
    pack_voltage = 20 * module_voltage
    
    power_w = power_kw * 1000
    pack_current = power_w / pack_voltage if pack_voltage > 0 else 0
    cell_current = pack_current / parallel if parallel > 0 else 0
    
    # 计算能量需求
    duration_s = duration_min * 60
    total_energy_j = power_w * duration_s
    battery_energy_j = total_energy_j / 0.92  # 效率92%
    battery_energy_wh = battery_energy_j / 3600
    
    # 每个电芯的能量
    total_cells_used = cells_per_module * 20
    energy_per_cell_wh = battery_energy_wh / total_cells_used if total_cells_used > 0 else 0
    capacity_wh_per_cell = 50 * cell_nominal_voltage  # 50Ah * 3.7V
    soc_drop_per_cell = energy_per_cell_wh / capacity_wh_per_cell
    
    # 安全检查结果
    checks = []
    
    # 1. 电流检查
    current_safe = cell_current <= constraints['max_cell_current']
    checks.append({
        'check': '电芯电流',
        'value': round(cell_current, 1),
        'limit': constraints['max_cell_current'],
        'safe': current_safe,
        'message': f"电芯电流{cell_current:.1f}A，限制{constraints['max_cell_current']}A"
    })
    
    # 2. 电压检查
    # 估算放电结束时的电压
    voltage_drop = cell_current * 0.005  # 假设内阻5mΩ
    cell_voltage_end = cell_nominal_voltage - voltage_drop
    voltage_safe = constraints['min_cell_voltage'] <= cell_voltage_end <= constraints['max_cell_voltage']
    checks.append({
        'check': '电芯电压',
        'value': round(cell_voltage_end, 2),
        'limit': f"{constraints['min_cell_voltage']}-{constraints['max_cell_voltage']}V",
        'safe': voltage_safe,
        'message': f"放电结束时电压约{cell_voltage_end:.2f}V"
    })
    
    # 3. 拓扑合理性检查
    topology_valid = (series <= 4 and parallel <= 4 and series * parallel <= 16)
    checks.append({
        'check': '拓扑配置',
        'value': f"{series}串{parallel}并",
        'limit': '符合4×4矩阵',
        'safe': topology_valid,
        'message': f"配置{series}×{parallel}={series*parallel}电芯，每个模组最多16电芯"
    })
    
    # 4. 模组一致性检查
    modules_consistent = (cells_per_module % 1 == 0 and cells_per_module >= 1 and cells_per_module <= 16)
    checks.append({
        'check': '模组一致性',
        'value': cells_per_module,
        'limit': '1-16个电芯，且20个模组相同',
        'safe': modules_consistent,
        'message': f"每个模组{cells_per_module}个电芯，20个模组配置相同"
    })
    
    # 5. 木桶效应分析（基于电池数据）
    if battery_data:
        # 假设选择最高SOC的电芯（最坏情况分析）
        socs = [c.get('soc', 0.5) for c in battery_data]
        min_soc = min(socs)
        soc_after = min_soc - soc_drop_per_cell
        
        bucket_safe = soc_after >= constraints['min_soc']
        checks.append({
            'check': '木桶效应',
            'value': round(soc_after, 3),
            'limit': f">={constraints['min_soc']}",
            'safe': bucket_safe,
            'message': f"最弱电芯SOC从{min_soc:.3f}降至{soc_after:.3f}"
        })
        
        # 温度分析
        temps = [c.get('temperature_c', 25.0) for c in battery_data]
        max_temp = max(temps)
        # 简单估算温度上升
        temp_increase = cell_current ** 2 * 0.005 * 0.1  # 简化模型
        temp_after = max_temp + temp_increase
        temp_safe = temp_after <= constraints['max_cell_temp']
        checks.append({
            'check': '温度安全',
            'value': round(temp_after, 1),
            'limit': f"<={constraints['max_cell_temp']}°C",
            'safe': temp_safe,
            'message': f"最高温度从{max_temp:.1f}°C升至{temp_after:.1f}°C"
        })
    
    # 汇总结果
    all_safe = all(check['safe'] for check in checks)
    safe_count = sum(1 for check in checks if check['safe'])
    total_checks = len(checks)
    
    result = {
        'overall_safe': all_safe,
        'safety_score': safe_count / total_checks if total_checks > 0 else 0,
        'checks': checks,
        'electrical_summary': {
            'pack_voltage': round(pack_voltage, 1),
            'pack_current': round(pack_current, 1),
            'cell_current': round(cell_current, 1),
            'power_delivered': round(pack_voltage * pack_current / 1000, 1),  # kW
            'required_power': power_kw
        },
        'energy_summary': {
            'soc_drop_per_cell': round(soc_drop_per_cell, 3),
            'energy_per_cell_wh': round(energy_per_cell_wh, 1),
            'total_energy_wh': round(battery_energy_wh, 1)
        },
        'recommendations': []
    }
    
    # 生成建议
    if not all_safe:
        failed_checks = [check for check in checks if not check['safe']]
        for check in failed_checks:
            if check['check'] == '电芯电流' and cell_current > constraints['max_cell_current']:
                result['recommendations'].append(
                    f"电芯电流过高：建议增加并联数或减少功率"
                )
            elif check['check'] == '木桶效应' and soc_after < constraints['min_soc']:
                result['recommendations'].append(
                    f"最弱电芯SOC可能过低：建议选择SOC较高的电芯或减少放电时间"
                )
            elif check['check'] == '温度安全' and temp_after > constraints['max_cell_temp']:
                result['recommendations'].append(
                    f"温度可能过高：建议选择低温电芯或改善散热"
                )
    else:
        result['recommendations'].append("所有安全检查通过，方案安全可行")
    
    return result

def main():
    parser = argparse.ArgumentParser(description='安全验证器')
    parser.add_argument('--plan', required=True, help='方案配置JSON文件')
    parser.add_argument('--battery', required=True, help='电池状态JSON文件')
    parser.add_argument('--power', type=float, required=True, help='功率需求（kW）')
    parser.add_argument('--duration', type=float, default=10, help='持续时间（分钟）')
    parser.add_argument('--output', help='输出JSON文件')
    
    args = parser.parse_args()
    
    try:
        # 加载方案
        with open(args.plan, 'r', encoding='utf-8') as f:
            plan = json.load(f)
        
        # 加载电池数据
        battery_data = load_battery_data(args.battery)
        
        # 安全检查
        result = check_safety(plan, battery_data, args.power, args.duration)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        error_result = {
            'success': False,
            'error': str(e),
            'message': '安全检查失败'
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)

if __name__ == '__main__':
    main()