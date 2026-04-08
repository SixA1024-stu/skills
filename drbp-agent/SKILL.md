---
name: drbp-agent
description: 本技能用于电动汽车动态可重构电池组的连接规划。根据导航任务（行驶里程、速度、坡度等）和当前各电芯的实时状态（SOC、温度、电压、内阻），为20个固定串联的模组（每个模组4×4电芯）设计内部串并联连接方案，选择最合适的电芯组合，使电池组能够安全、高效地完成任务，并尽可能均衡所有电芯的剩余容量。
---

# DRBP Agent Skill

该技能为动态可重构电池组（Dynamically Reconfigurable Battery Pack, DRBP）提供智能连接规划能力。


根据实时导航信息和电池组状态，选择最优策略并执行电芯挑选，生成标准化输出。

## 快速开始

### 输入数据格式

1. **导航信息**（JSON，10分钟片段）：
   ```json
   {
     "id": 1,
     "duration_min": 10,
     "dist_km": 9.0,
     "speed": 54,
     "gain_m": 120.0,
     "loss_m": 10.0,
     "road": "山路",
     "traffic": "通畅",
     "temp": 20
   }
   ```

2. **电池组状态**：使用 `run_script` 工具执行 `scripts/battery_monitor.py`，它会输出电池状态的 JSON 统计信息。
例如：调用 `run_script("scripts/battery_monitor.py")`。

### 核心工作流程

1. **电池状态获取**：执行 `battery_monitor.py` 获取实时电池组统计数据
2. **需求分析**：根据导航信息和车辆参数，计算满足导航任务所需的电压、电流
3. **能力评估**：计算电池组能提供的最大电压、电流
4. **策略选择**：根据导航信息 + 电池统计特征，选择预定义策略（参见 [策略库](references/strategy_library.md)）
5. **电芯挑选**：执行 `cell_selector` 根据选择的预定义策略挑选电芯
6. **电芯分配**：为挑选的电芯选择串并联方式
7. **状态判断**：判断电池组是否能满足需求
8. **结果输出**：生成标准化输出


## 技能资源

### 脚本 (`scripts/`)

- **[battery_monitor.py](scripts/battery_monitor.py)**：电池状态获取脚本
- **[cell_selector.py](scripts/cell_selector.py)**：电芯挑选核心算法，支持多策略权重评分


### 参考文档 (`references/`)

- **[strategy_library.md](references/strategy_library.md)**：完整策略库，包含触发条件、权重配置、拓扑映射
- **[architecture_overview.md](references/architecture_overview.md)**：系统架构说明（20×固定串联模组，每模组 4×4 可重构电芯）
- **[evaluation_metrics.md](references/evaluation_metrics.md)**：评估指标定义（均衡度、容量利用率、热安全等）



### 模块化使用

如需自定义流程，可单独调用各模块：

**电芯挑选**：
   ```bash
   python scripts/cell_selector.py --strategy HP --k 3 --input data/input_file.json
   ```


### 3. 安全约束

始终遵守以下安全边界：

- **电压限制**：总电压不得超出逆变器范围（如 300‑450V）
- **电流限制**：单个电芯电流 ≤ 3C（倍率）
- **温度保护**：任何电芯温度 > 50°C 立即旁路
- **通信超时**：若 agent 决策超时（>2秒），自动切换到安全保守策略 (SA)
- **需求匹配**：电池组能提供的电压/电流必须 ≥ 导航任务需求并且确保每个电芯都能够放电任务所需时间。

### 输出格式说明
```json
{
  "status": boolean,        // True 表示电池组可继续运行，False 表示无法满足需求
  "v_req": float,           // 需求电压（V）
  "i_req": float,           // 需求电流（A）
  "selected_cells": [       // 选中的电芯，按模组组织
    {
      "mod_id": int,        // 模组ID
      "cells": [[1,2,3,4],[5,6,7,8]]  // 二维列表，每个子列表为一个并联支路，比如这是4串2并
    },
    ...
  ],
  "reason": string         // 选择理由，包括计算过程和选择依据
}
```

- **status**: True 表示电池组可继续运行，False 表示无法满足需求
- **i_req**: 满足当前导航任务的需求电流（A），基于车辆模型计算
- **v_req**: 满足当前导航任务的需求电压（V），基于功率需求和电压计算
- **selected_cells**: 选中的电芯，按模组组织，每个模组内的 `cells` 为二维列表，每个子列表为一个并联支路，例如，`[[1,2,3,4],[5,6,7,8]]`是一个4串2并的电路
- **reason**: 详细的选择理由，包括计算过程和决策依据




