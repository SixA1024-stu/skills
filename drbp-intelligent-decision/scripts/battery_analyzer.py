#!/usr/bin/env python3
"""
电池状态分析器 - 为决策提供数据洞察
输出SOC分布、温度分析、健康状态等关键指标
"""

import json
import numpy as np
import argparse
import sys
from typing import Dict, List, Any

def analyze_battery_data(data: Any) -> Dict:
    """分析电池数据，返回关键指标"""
    
    cells = []
    
    # 处理不同格式
    if isinstance(data, list):
        # 扁平列表格式
        cells = data
        for i, cell in enumerate(cells):
            cell['cell_id'] = f"{cell.get('module_id', 0)}_{cell.get('id', i)}"
    elif isinstance(data, dict) and 'modules' in data:
        # 模组结构格式
        for module in data['modules']:
            mod_id = module['mod_id']
            for cell in module['cells']:
                cell_copy = cell.copy()
                cell_copy['module_id'] = mod_id
                cell_copy['cell_id'] = f"{mod_id}_{cell.get('id', 0)}"
                cells.append(cell_copy)
    else:
        raise ValueError("不支持的电池数据格式")
    
    if not cells:
        return {"error": "未找到电芯数据"}
    
    # 提取关键数据
    socs = [c.get('soc', 0.0) for c in cells]
    temps = [c.get('temperature_c', c.get('temperature_K', 298.15) - 273.15) for c in cells]
    sohs = [c.get('soh', 1.0) for c in cells]
    resistances = [c.get('internal_resistance', c.get('R_eq', 0.005)) for c in cells]
    cycles = [c.get('cycles', 0) for c in cells]
    
    # 按模组分组
    modules = {}
    for cell in cells:
        mod_id = cell.get('module_id', 0)
        if mod_id not in modules:
            modules[mod_id] = []
        modules[mod_id].append(cell)
    
    # 计算模组级统计
    module_stats = {}
    for mod_id, mod_cells in modules.items():
        mod_socs = [c.get('soc', 0.0) for c in mod_cells]
        mod_temps = [c.get('temperature_c', 25.0) for c in mod_cells]
        
        module_stats[mod_id] = {
            'cell_count': len(mod_cells),
            'soc_mean': float(np.mean(mod_socs)),
            'soc_std': float(np.std(mod_socs)),
            'soc_min': float(min(mod_socs)),
            'soc_max': float(max(mod_socs)),
            'soc_range': float(max(mod_socs) - min(mod_socs)),
            'temp_mean': float(np.mean(mod_temps)),
            'temp_std': float(np.std(mod_temps)),
            'temp_min': float(min(mod_temps)),
            'temp_max': float(max(mod_temps))
        }
    
    # 识别异常值
    soc_mean = np.mean(socs)
    soc_std = np.std(socs)
    temp_mean = np.mean(temps)
    temp_std = np.std(temps)
    
    high_soc_cells = [c for c in cells if c.get('soc', 0) > soc_mean + soc_std]
    low_soc_cells = [c for c in cells if c.get('soc', 0) < soc_mean - soc_std]
    high_temp_cells = [c for c in cells if c.get('temperature_c', 25) > temp_mean + temp_std]
    
    # 总体分析结果
    result = {
        'summary': {
            'total_cells': len(cells),
            'module_count': len(modules),
            'cells_per_module_avg': len(cells) / len(modules) if modules else 0
        },
        'soc_analysis': {
            'mean': float(soc_mean),
            'std': float(soc_std),
            'min': float(min(socs)),
            'max': float(max(socs)),
            'range': float(max(socs) - min(socs)),
            'cv': float(soc_std / soc_mean if soc_mean > 0 else 0),  # 变异系数
            'distribution': {
                'high_soc_count': len(high_soc_cells),
                'low_soc_count': len(low_soc_cells),
                'high_soc_examples': [{'cell_id': c['cell_id'], 'soc': c.get('soc', 0)} 
                                     for c in high_soc_cells[:3]],
                'low_soc_examples': [{'cell_id': c['cell_id'], 'soc': c.get('soc', 0)} 
                                    for c in low_soc_cells[:3]]
            }
        },
        'temperature_analysis': {
            'mean': float(temp_mean),
            'std': float(temp_std),
            'min': float(min(temps)),
            'max': float(max(temps)),
            'hot_spots': [{'cell_id': c['cell_id'], 'temp': c.get('temperature_c', 25)}
                         for c in high_temp_cells[:5]]
        },
        'health_analysis': {
            'soh_mean': float(np.mean(sohs)),
            'soh_min': float(min(sohs)),
            'soh_max': float(max(sohs)),
            'resistance_mean': float(np.mean(resistances)),
            'resistance_max': float(max(resistances)),
            'cycles_mean': float(np.mean(cycles)),
            'cycles_max': float(max(cycles))
        },
        'module_analysis': {
            'most_unbalanced_module': max(module_stats.items(), 
                                         key=lambda x: x[1]['soc_range'])[0] if module_stats else None,
            'hottest_module': max(module_stats.items(), 
                                 key=lambda x: x[1]['temp_mean'])[0] if module_stats else None,
            'module_details': module_stats
        },
        'recommendations': [
            f"SOC不均衡程度：{'高' if soc_std > 0.1 else '中' if soc_std > 0.05 else '低'}（标准差：{soc_std:.3f}）",
            f"温度差异：{'显著' if max(temps) - min(temps) > 10 else '一般' if max(temps) - min(temps) > 5 else '小'}",
            f"重点关注：{len(high_soc_cells)}个高SOC电芯，{len(high_temp_cells)}个高温电芯"
        ]
    }
    
    return result

def main():
    parser = argparse.ArgumentParser(description='电池状态分析器')
    parser.add_argument('--input', required=True, help='电池状态JSON文件')
    parser.add_argument('--output', help='输出JSON文件')
    parser.add_argument('--brief', action='store_true', help='简洁输出')
    
    args = parser.parse_args()
    
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        analysis = analyze_battery_data(data)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)
        
        # 控制台输出
        if args.brief:
            brief_result = {
                'total_cells': analysis['summary']['total_cells'],
                'soc_mean': analysis['soc_analysis']['mean'],
                'soc_std': analysis['soc_analysis']['std'],
                'soc_range': analysis['soc_analysis']['range'],
                'temp_mean': analysis['temperature_analysis']['mean'],
                'temp_range': analysis['temperature_analysis']['max'] - analysis['temperature_analysis']['min'],
                'recommendations': analysis['recommendations']
            }
            print(json.dumps(brief_result, ensure_ascii=False))
            return 0
        else:
            print(json.dumps(analysis, indent=2, ensure_ascii=False))
            return 0
            
    except Exception as e:
        error_result = {
            'success': False,
            'error': str(e),
            'message': '电池分析失败'
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)

if __name__ == '__main__':
    main()