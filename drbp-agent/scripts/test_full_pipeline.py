#!/usr/bin/env python3
"""
完整流程测试脚本。

演示从导航信息和电池状态开始，经过策略选择、电芯挑选、拓扑生成的完整流程。
"""

import json
import sys
import os
import tempfile
from pathlib import Path

# 添加当前目录到路径，以便导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from strategy_selector import select_strategy
    from cell_selector import select_cells_global
    from topology_generator import generate_topology
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保所有模块文件都在 scripts/ 目录下")
    sys.exit(1)


def test_full_pipeline():
    """运行完整流程测试"""
    print("=" * 60)
    print("动态可重构电池组 - 完整流程测试")
    print("=" * 60)
    
    # 1. 加载测试数据
    test_dir = Path(__file__).parent / "test_data"
    nav_file = test_dir / "navigation_example.json"
    battery_file = test_dir / "battery_example.json"
    
    if not nav_file.exists() or not battery_file.exists():
        print(f"错误: 测试数据文件不存在")
        print(f"导航文件: {nav_file} - {'存在' if nav_file.exists() else '缺失'}")
        print(f"电池文件: {battery_file} - {'存在' if battery_file.exists() else '缺失'}")
        return False
    
    with open(nav_file, 'r', encoding='utf-8') as f:
        navigation_data = json.load(f)
    
    with open(battery_file, 'r', encoding='utf-8') as f:
        battery_data = json.load(f)
    
    print(f"\n1. 加载测试数据完成")
    print(f"   导航信息: {navigation_data.get('road', '未知')}路段, "
          f"距离{navigation_data.get('dist_km', 0)}km, "
          f"爬升{navigation_data.get('gain_m', 0)}m")
    print(f"   电池状态: {len(battery_data.get('modules', []))}个模组, "
          f"每个模组{len(battery_data.get('modules', [{}])[0].get('cells', []))}个电芯")
    
    # 2. 策略选择
    print(f"\n2. 策略选择")
    strategy_result = select_strategy(navigation_data, battery_data)
    
    strategy = strategy_result["strategy"]
    strategy_name = strategy_result["strategy_name"]
    reasons = strategy_result["decision_reasons"]
    
    print(f"   选择策略: {strategy} ({strategy_name})")
    print(f"   优先级: {strategy_result['priority']}")
    print(f"   决策依据:")
    for i, reason in enumerate(reasons, 1):
        print(f"     {i}. {reason}")
    
    if strategy_result["faults_detected"]:
        print(f"   检测到故障: {strategy_result['faults_detected'][:3]}")
    
    # 3. 电芯挑选
    print(f"\n3. 电芯挑选")
    
    # 确定 k 值（根据策略）
    k_by_strategy = {
        "HP": 3,   # 高功率：选3个电芯并联
        "HE": 4,   # 高能量：选4个电芯串联
        "BL": 2,   # 均衡：选2个最高SOC电芯放电
        "TM": 3,   # 热管理：选3个温度最低的电芯
        "FT": 3,   # 容错：选3个健康度最高的电芯
        "RC": 4,   # 充电优化：选4个最低SOC电芯
        "EC": 3,   # 经济性：选3个最年轻电芯
        "SA": 16   # 安全保守：全选（实际会全串联）
    }
    
    k = k_by_strategy.get(strategy, 3)
    
    try:
        selected_cells = select_cells_global(
            battery_data,
            strategy,
            k=k,
            module_adjust=True
        )
        
        # 统计选中的电芯
        total_selected = sum(len(ids) for ids in selected_cells.values())
        total_cells = sum(len(m.get("cells", [])) for m in battery_data.get("modules", []))
        
        print(f"   策略: {strategy}, k={k}")
        print(f"   选中电芯: {total_selected}/{total_cells} ({total_selected/total_cells*100:.1f}%)")
        
        # 显示每个模组的选中情况
        for module_id, cell_ids in selected_cells.items():
            if cell_ids:
                print(f"     模组 {module_id}: 选中 {len(cell_ids)} 个电芯 (ID: {cell_ids})")
        
    except Exception as e:
        print(f"   电芯挑选失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 4. 拓扑生成
    print(f"\n4. 拓扑生成")
    
    try:
        topology_result = generate_topology(strategy, selected_cells, battery_data)
        
        topology_type = topology_result["topology_type"]
        expected_voltage = topology_result["expected_voltage"]
        expected_current = topology_result["expected_current"]
        num_instructions = len(topology_result["switch_matrix"])
        
        print(f"   拓扑类型: {topology_type}")
        print(f"   期望电压: {expected_voltage} V")
        print(f"   期望电流: {expected_current} A")
        print(f"   开关指令数: {num_instructions}")
        
        if topology_result.get("notes"):
            print(f"   注意:")
            for note in topology_result["notes"]:
                print(f"     - {note}")
        
        # 显示前几条指令作为示例
        print(f"   示例指令 (前3条):")
        for i, instr in enumerate(topology_result["switch_matrix"][:3]):
            print(f"     {i+1}. 模组{instr['module']} 电芯{instr['cell']}: "
                  f"{instr['action']} -> {instr.get('connect_to', 'N/A')}")
        
    except Exception as e:
        print(f"   拓扑生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. 保存中间结果（可选）
    print(f"\n5. 保存结果")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 保存策略选择结果
        strategy_file = Path(tmpdir) / "strategy_result.json"
        with open(strategy_file, 'w', encoding='utf-8') as f:
            json.dump(strategy_result, f, indent=2, ensure_ascii=False)
        
        # 保存电芯挑选结果
        selected_file = Path(tmpdir) / "selected_cells.json"
        selected_data = {
            "strategy": strategy,
            "k": k,
            "selected_cells": selected_cells
        }
        with open(selected_file, 'w', encoding='utf-8') as f:
            json.dump(selected_data, f, indent=2, ensure_ascii=False)
        
        # 保存拓扑生成结果
        topology_file = Path(tmpdir) / "topology_instructions.json"
        with open(topology_file, 'w', encoding='utf-8') as f:
            json.dump(topology_result, f, indent=2, ensure_ascii=False)
        
        print(f"   中间结果已保存到临时目录:")
        print(f"     - 策略选择: {strategy_file}")
        print(f"     - 电芯挑选: {selected_file}")
        print(f"     - 拓扑生成: {topology_file}")
    
    print(f"\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    return True


def test_individual_modules():
    """单独测试每个模块"""
    print("\n" + "=" * 60)
    print("模块单独测试")
    print("=" * 60)
    
    test_dir = Path(__file__).parent / "test_data"
    nav_file = test_dir / "navigation_example.json"
    battery_file = test_dir / "battery_example.json"
    
    with open(nav_file, 'r', encoding='utf-8') as f:
        nav_data = json.load(f)
    
    with open(battery_file, 'r', encoding='utf-8') as f:
        bat_data = json.load(f)
    
    # 测试策略选择器
    print("\n1. 测试策略选择器:")
    from strategy_selector import extract_navigation_features, extract_battery_features
    nav_features = extract_navigation_features(nav_data)
    bat_features = extract_battery_features(bat_data)
    print(f"   导航特征: {len(nav_features)} 个")
    print(f"   电池特征: {len(bat_features)} 个")
    
    # 测试电芯挑选器
    print("\n2. 测试电芯挑选器:")
    from cell_selector import select_cells_global
    selected = select_cells_global(bat_data, "HP", k=3)
    print(f"   HP策略选中: {sum(len(ids) for ids in selected.values())} 个电芯")
    
    # 测试拓扑生成器
    print("\n3. 测试拓扑生成器:")
    from topology_generator import generate_topology
    topology = generate_topology("HP", selected, bat_data)
    print(f"   生成指令: {len(topology['switch_matrix'])} 条")
    
    print("\n模块测试完成！")


if __name__ == "__main__":
    # 运行完整流程测试
    success = test_full_pipeline()
    
    if success:
        # 询问是否运行模块单独测试
        print("\n是否运行模块单独测试? (y/n)", end=" ")
        # 在脚本中默认运行
        test_individual_modules()
    
    sys.exit(0 if success else 1)