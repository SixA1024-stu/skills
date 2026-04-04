#!/usr/bin/env python3
"""
电芯挑选算法核心模块。

根据策略权重对每个模组内的电芯进行评分，选出 top‑k 个电芯。
支持多策略权重配置，可动态调整。

输入：电池状态 JSON + 策略代号 + k 参数
输出：每个模组选中电芯的 ID 列表
"""

import json
import argparse
import sys
from typing import Dict, List, Tuple, Any, Union
import numpy as np

# 策略权重预设（与 strategy_library.md 一致）
STRATEGY_WEIGHTS = {
    "HP": {"internal_resistance": 0.5, "temp": 0.3, "soc": 0.2},  # 高功率
    "HE": {"soc": 0.6, "health": 0.2, "temp": 0.2},  # 高能量
    "BL": {"soc": 0.8, "health": 0.2},  # 均衡
    "TM": {"temp": 0.7, "internal_resistance": 0.3},  # 热管理
    "FT": {"health": 1.0},  # 容错
    "RC": {"soc": 0.5, "internal_resistance": 0.3, "temp": 0.2},  # 充电优化
    "EC": {"cycle_count": 0.6, "health": 0.4},  # 经济性
    "SA": {"soc": 0.3, "temp": 0.3, "internal_resistance": 0.2, "health": 0.2}  # 安全保守
}

# 各指标归一化范围（基于电芯规格）
NORM_RANGES = {
    "soc": (0.2, 1.0),  # SOC 低于 20% 视为危险
    "temp": (15.0, 45.0),  # 15‑45°C 为工作范围，25°C 最佳
    "internal_resistance": (0.02, 0.05),  # 内阻越小越好（实际数据中 R_eq 约 0.006Ω，属极优）
    "health": (0.5, 1.0),  # 健康度低于 50% 视为失效
    "cycle_count": (0, 1000)  # 循环次数越少越好
}

# 缺失字段的默认值
DEFAULT_VALUES = {
    "health": 1.0,
    "cycle_count": 0
}


def normalize(value: float, key: str, reverse: bool = False) -> float:
    """
    将原始值归一化到 [0, 1] 区间。

    Args:
        value: 原始值
        key: 指标名称（soc/temp/internal_resistance/health/cycle_count）
        reverse: True 表示值越小越好（如内阻、循环次数）

    Returns:
        归一化后的分数（0‑1，越高越好）
    """
    if key not in NORM_RANGES:
        raise ValueError(f"未知的指标: {key}")

    min_val, max_val = NORM_RANGES[key]
    # 钳位到合理范围
    clipped = max(min(value, max_val), min_val)
    scaled = (clipped - min_val) / (max_val - min_val)

    # 对于 reverse=True 的指标（值越小越好），取反
    if reverse:
        return 1.0 - scaled
    return scaled


def score_cell(cell: Dict[str, Any], weights: Dict[str, float]) -> float:
    """
    计算单个电芯的加权得分。

    Args:
        cell: 电芯数据字典，应包含 soc, temp, internal_resistance, health, cycle_count 等字段
        weights: 策略权重字典，如 {"soc": 0.6, "temp": 0.2, ...}

    Returns:
        加权得分（越高表示越适合该策略）
    """
    total_score = 0.0
    total_weight = 0.0

    for key, weight in weights.items():
        if weight <= 0:
            continue

        if key not in cell:
            # 缺失字段时发出警告，并跳过该权重项（不报错）
            print(f"警告: 电芯 {cell.get('cell_id', 'unknown')} 缺少字段 '{key}'，已忽略该权重项", file=sys.stderr)
            continue

        # 确定是否需要反向（值越小越好）
        reverse = key in ["internal_resistance", "cycle_count"]

        # 归一化
        norm_score = normalize(cell[key], key, reverse=reverse)

        # 加权累加
        total_score += weight * norm_score
        total_weight += weight

    # 如果所有权重为0（或全部缺失），返回0分
    if total_weight == 0:
        return 0.0

    # 归一化到 [0, 1] 区间（保持加权和 ≤1）
    return total_score / total_weight


def preprocess_battery_data(raw_data: Union[List, Dict]) -> Dict[int, List[Dict]]:
    """
    将原始输入数据统一转换为标准格式：{module_id: [cell_dict, ...]}

    支持两种输入格式：
    1. 新格式：列表，每个元素包含 module_id, id, soc, temperature_K, R_eq 等
    2. 旧格式：字典，包含 'modules' 列表，每个模块含 'cells' 列表

    Args:
        raw_data: 原始 JSON 解析后的数据

    Returns:
        字典，键为 module_id，值为该模块下的电芯列表（已标准化字段）
    """
    # 情况1：已经是旧格式（包含 modules 字段）
    if isinstance(raw_data, dict) and "modules" in raw_data:
        modules_dict = {}
        for module in raw_data["modules"]:
            module_id = module.get("module_id")
            if module_id is None:
                raise ValueError("模块数据缺少 module_id 字段")
            cells = []
            for cell in module.get("cells", []):
                # 转换温度单位
                temp_c = cell.get("temperature_K", 298.15) - 273.15
                # 构建标准化电芯字典
                std_cell = {
                    "cell_id": cell.get("cell_id") or cell.get("id"),
                    "soc": cell.get("soc", 0.5),
                    "temp": temp_c,
                    "internal_resistance": cell.get("internal_resistance") or cell.get("R_eq", 0.03),
                    "health": cell.get("health", DEFAULT_VALUES["health"]),
                    "cycle_count": cell.get("cycle_count", DEFAULT_VALUES["cycle_count"])
                }
                if std_cell["cell_id"] is None:
                    raise ValueError("电芯数据缺少 cell_id 或 id 字段")
                cells.append(std_cell)
            modules_dict[module_id] = cells
        return modules_dict

    # 情况2：新格式（列表）
    if isinstance(raw_data, list):
        modules_dict = {}
        for item in raw_data:
            module_id = item.get("module_id")
            if module_id is None:
                raise ValueError("电芯数据缺少 module_id 字段")
            cell_id = item.get("id")
            if cell_id is None:
                raise ValueError("电芯数据缺少 id 字段")

            # 转换温度
            temp_k = item.get("temperature_K", 298.15)
            temp_c = temp_k - 273.15

            std_cell = {
                "cell_id": cell_id,
                "soc": item.get("soc", 0.5),
                "temp": temp_c,
                "internal_resistance": item.get("R_eq", 0.03),
                "health": item.get("health", DEFAULT_VALUES["health"]),
                "cycle_count": item.get("cycle_count", DEFAULT_VALUES["cycle_count"])
            }
            modules_dict.setdefault(module_id, []).append(std_cell)
        return modules_dict

    raise ValueError("不支持的输入数据格式，应为包含 'modules' 的字典或电芯列表")


def select_cells_in_module(
        module_cells: List[Dict[str, Any]],
        strategy: str,
        k: int = 3
) -> List[int]:
    """
    在一个模组内挑选 top‑k 个电芯。

    Args:
        module_cells: 模组内所有电芯的数据列表（每个元素是标准化电芯字典）
        strategy: 策略代号（HP/HE/BL/TM/FT/RC/EC/SA）
        k: 要挑选的电芯数量（默认3）

    Returns:
        选中电芯的 ID 列表（按得分降序）
    """
    if strategy not in STRATEGY_WEIGHTS:
        raise ValueError(f"未知的策略: {strategy}")

    weights = STRATEGY_WEIGHTS[strategy]

    # 计算每个电芯的得分
    scored_cells = []
    for cell in module_cells:
        cell_id = cell.get("cell_id")
        if cell_id is None:
            raise ValueError("电芯数据缺少 cell_id 字段")

        try:
            s = score_cell(cell, weights)
            scored_cells.append((cell_id, s))
        except Exception as e:
            print(f"警告: 电芯 {cell_id} 评分失败: {e}", file=sys.stderr)
            scored_cells.append((cell_id, 0.0))

    # 按得分降序排序
    scored_cells.sort(key=lambda x: x[1], reverse=True)

    # 选取前 k 个
    selected_ids = [cell_id for cell_id, score in scored_cells[:k]]

    return selected_ids


def select_cells_global(
        modules_dict: Dict[int, List[Dict]],
        strategy: str,
        k: int = 3,
        module_adjust: bool = False
) -> Dict[int, List[int]]:
    """
    全局电芯挑选，处理所有模组。

    Args:
        modules_dict: 预处理后的模块字典 {module_id: [cells]}
        strategy: 策略代号
        k: 每个模组默认挑选数量
        module_adjust: 是否启用模组间均衡调整（让 SOC 高的模组多放电）

    Returns:
        字典：{module_id: [selected_cell_ids]}
    """
    # 如果启用模组间均衡，计算全局平均 SOC
    if module_adjust and strategy in ["BL", "HE", "HP"]:
        all_socs = []
        for cells in modules_dict.values():
            for cell in cells:
                all_socs.append(cell.get("soc", 0.5))

        if all_socs:
            global_avg_soc = np.mean(all_socs)
        else:
            global_avg_soc = 0.5
    else:
        global_avg_soc = 0.5

    result = {}

    for module_id, cells in modules_dict.items():
        if len(cells) == 0:
            print(f"警告: 模组 {module_id} 无电芯数据", file=sys.stderr)
            result[module_id] = []
            continue

        # 调整 k 值（模组间均衡）
        adjusted_k = k
        if module_adjust and strategy in ["BL", "HE", "HP"]:
            module_socs = [cell.get("soc", 0.5) for cell in cells]
            module_avg_soc = np.mean(module_socs)
            # SOC 高的模组多选电芯（多放电），SOC 低的模组少选
            # 调整因子：1.0 ± 0.5 × (模组SOC - 全局SOC)
            adjust_factor = 1.0 + 0.5 * (module_avg_soc - global_avg_soc)
            adjusted_k = max(1, int(k * adjust_factor))
            adjusted_k = min(adjusted_k, len(cells))  # 不超过电芯总数

        # 模组内挑选
        selected = select_cells_in_module(cells, strategy, adjusted_k)
        result[module_id] = selected

    return result


def main():
    parser = argparse.ArgumentParser(description="动态可重构电池组电芯挑选算法")
    parser.add_argument("--strategy", "-s", required=True,
                        choices=list(STRATEGY_WEIGHTS.keys()),
                        help="策略代号 (HP/HE/BL/TM/FT/RC/EC/SA)")
    parser.add_argument("--k", type=int, default=3,
                        help="每个模组挑选的电芯数量（默认 3）")
    parser.add_argument("--input", "-i", default='data/input_file.json',
                        help="输入 JSON 文件路径（默认 data/input_file.json）")
    parser.add_argument("--output", "-o", default='data/output.json',
                        help="输出 JSON 文件路径（默认 data/output.json）")
    parser.add_argument("--no-module-adjust", action="store_true",
                        help="禁用模组间均衡调整")

    args = parser.parse_args()

    try:
        # 读取输入文件
        with open(args.input, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        # 预处理数据
        modules_dict = preprocess_battery_data(raw_data)

        # 执行挑选
        result = select_cells_global(
            modules_dict,
            args.strategy,
            k=args.k
        )

        # 准备输出数据
        output_data = {
            "strategy": args.strategy,
            "k": args.k,
            "module_adjust": not args.no_module_adjust,
            "selected_cells": result,
            "timestamp": np.datetime64('now').astype(str)
        }

        print(output_data)

        return 0

    except FileNotFoundError:
        print(f"错误: 输入文件不存在: {args.input}", file=sys.stderr)
        return 1
    except json.JSONDecodeError:
        print(f"错误: 输入文件不是有效的 JSON: {args.input}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"未知错误: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())