#!/usr/bin/env python3
"""
电池组全局状态摘要
输入：电芯状态 JSON 文件（必需），导航信息 JSON 文件（可选）
输出：包含 SOC、温度、电压、SOH、异常、模块摘要的统计信息
"""

import sys
import json
import argparse
import numpy as np
from typing import List, Dict, Any, Optional

# 阈值定义
VOLTAGE_LOW_THRESHOLD = 2.5  # V
TEMP_HIGH_THRESHOLD_K = 333.15  # 60°C
TEMP_LOW_THRESHOLD_K = 273.15 + 0  # 0°C（可根据需要调整）


def load_json(file_path: str) -> Any:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def compute_stats(values: List[float]) -> dict[str, None] | dict[str, float | Any]:
    """计算一组数值的基本统计量"""
    if not values:
        return {"min": None, "max": None, "mean": None, "std": None, "range": None}
    arr = np.array(values)
    return {
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "range": float(np.ptp(arr))
    }


def process_cell_states(cells: List[Dict]) -> Dict:
    """从电芯列表中提取全局统计"""
    # 提取字段
    socs = [c['soc'] for c in cells if not c.get('is_cut_off', False)]
    temps = [c['temperature_K'] for c in cells if not c.get('is_cut_off', False)]
    voltages = [c['voltage'] for c in cells if not c.get('is_cut_off', False)]
    internal_resistance = [c['R_eq'] for c in cells if not c.get('is_cut_off', False)]
    sohs = [c.get('soh', 1.0) for c in cells if not c.get('is_cut_off', False)]  # 若无SOH字段默认为1.0

    # 异常统计
    cut_off_count = sum(1 for c in cells if c.get('is_cut_off', False))
    low_voltage_count = sum(1 for c in cells if c.get('voltage', 0) < VOLTAGE_LOW_THRESHOLD)
    high_temp_count = sum(1 for c in cells if c.get('temperature_K', 0) > TEMP_HIGH_THRESHOLD_K)
    low_temp_count = sum(1 for c in cells if c.get('temperature_K', 0) < TEMP_LOW_THRESHOLD_K)

    # 模块级统计
    modules = {}
    for c in cells:
        mod = c['module_id']
        if mod not in modules:
            modules[mod] = {'socs': [], 'temps': [], 'cut_off_count': 0, 'total': 0}
        modules[mod]['total'] += 1
        if c.get('is_cut_off', False):
            modules[mod]['cut_off_count'] += 1
        else:
            modules[mod]['socs'].append(c['soc'])
            modules[mod]['temps'].append(c['temperature_K'])

    module_summary = {}
    for mod, data in modules.items():
        soc_stats = compute_stats(data['socs']) if data['socs'] else {}
        temp_stats = compute_stats(data['temps']) if data['temps'] else {}
        module_summary[mod] = {
            "total_cells": data['total'],
            "active_cells": data['total'] - data['cut_off_count'],
            "avg_soc": soc_stats.get('mean'),
            "soc_std": soc_stats.get('std'),
            "avg_temp_K": temp_stats.get('mean'),
            "temp_std": temp_stats.get('std')
        }

    return {
        "soc": compute_stats(socs),
        "temperature_K": compute_stats(temps),
        "voltage": compute_stats(voltages),
        "soh": compute_stats(sohs),
        "internal_resistance": compute_stats(internal_resistance),
        "abnormal": {
            "cut_off": cut_off_count,
            "low_voltage": low_voltage_count,
            "high_temperature": high_temp_count,
            "low_temperature": low_temp_count
        },
        "modules": module_summary
    }


def main():
    cell_file = "data/input_file.json"
    try:
        cells = load_json(cell_file)
    except Exception as e:
        print(f"错误：无法读取文件 {cell_file}: {e}", file=sys.stderr)
        sys.exit(1)

    cell_stats = process_cell_states(cells)

    output = {
        "timestamp": time.time(),  # 可增加时间戳
        "battery_summary": cell_stats,
    }
    print(output)


if __name__ == '__main__':
    import time

    sys.exit(main())
