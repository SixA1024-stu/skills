#!/usr/bin/env python3
"""
LLM client for DRBP strategy selection.
Supports multiple LLM providers through a unified interface.
"""

import json
import os
import requests
from typing import Dict, Optional
import openai  # Optional, if using OpenAI official library

class LLMClient:
    """Unified LLM client for strategy selection."""
    
    def __init__(self, provider: str = "openai", api_key: str = None, 
                 endpoint: str = None, model: str = None):
        self.provider = provider
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.endpoint = endpoint
        self.model = model
        
        if provider == "openai" and not endpoint:
            self.endpoint = "https://api.openai.com/v1/chat/completions"
        elif provider == "anthropic" and not endpoint:
            self.endpoint = "https://api.anthropic.com/v1/messages"
        elif provider == "deepseek" and not endpoint:
            self.endpoint = "https://api.deepseek.com/v1/chat/completions"
    
    def select_strategy(self, battery_summary: Dict, navigation: Dict, 
                       available_strategies: Dict) -> Optional[Dict]:
        """
        Select optimal strategy using LLM.
        
        Returns: strategy dict or None if failed
        """
        prompt = self._build_prompt(battery_summary, navigation, available_strategies)
        
        try:
            if self.provider == "openai":
                return self._call_openai(prompt)
            elif self.provider == "anthropic":
                return self._call_anthropic(prompt)
            elif self.provider == "deepseek":
                return self._call_deepseek(prompt)
            elif self.provider == "mock":
                return self._mock_response()
            else:
                print(f"Unsupported provider: {self.provider}")
                return None
        except Exception as e:
            print(f"LLM API call failed: {e}")
            return None
    
    def _build_prompt(self, battery_summary: Dict, navigation: Dict,
                     available_strategies: Dict) -> str:
        """Build prompt for strategy selection."""
        
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
    "cells_per_module": 每个模组选择的电芯数(1-8),
    "priority_weights": {{"soc": 权重, "soh": 权重, "temperature": 权重, "internal_resistance": 权重}}
  }}
}}
```

请只输出JSON，不要有其他内容。"""
        
        return prompt
    
    def _call_openai(self, prompt: str) -> Dict:
        """Call OpenAI-compatible API."""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model or "gpt-4",
            "messages": [
                {"role": "system", "content": "你是一个专业的电池管理系统工程师。请严格按照要求的JSON格式输出。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(self.endpoint, headers=headers, 
                                json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        # Parse JSON from response
        try:
            strategy_result = json.loads(content)
            return strategy_result
        except json.JSONDecodeError:
            # Try to extract JSON if there's extra text
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise
    
    def _call_anthropic(self, prompt: str) -> Dict:
        """Call Anthropic Claude API."""
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model or "claude-3-opus-20240229",
            "max_tokens": 1000,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "system": "你是一个专业的电池管理系统工程师。请严格按照要求的JSON格式输出。"
        }
        
        response = requests.post(self.endpoint, headers=headers,
                                json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        content = result["content"][0]["text"]
        
        # Parse JSON from response
        try:
            strategy_result = json.loads(content)
            return strategy_result
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise
    
    def _call_deepseek(self, prompt: str) -> Dict:
        """Call DeepSeek API."""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model or "deepseek-chat",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(self.endpoint, headers=headers,
                                json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        try:
            strategy_result = json.loads(content)
            return strategy_result
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise
    
    def _mock_response(self) -> Dict:
        """Return mock response for testing."""
        
        return {
            "strategy": "equilibrium",
            "reason": "SOC标准差0.18，需要快速收敛以达成均衡放电目标",
            "parameters": {
                "cells_per_module": 4,
                "priority_weights": {
                    "soc": 0.9,
                    "soh": 0.1,
                    "temperature": -0.05,
                    "internal_resistance": -0.05
                }
            }
        }

# Command-line interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM client for DRBP strategy selection")
    parser.add_argument("--battery", required=True, help="Battery summary JSON file")
    parser.add_argument("--navigation", required=True, help="Navigation info JSON file")
    parser.add_argument("--strategies", required=True, help="Available strategies JSON file")
    parser.add_argument("--provider", default="mock", 
                       choices=["openai", "anthropic", "deepseek", "mock"],
                       help="LLM provider")
    parser.add_argument("--api_key", help="API key (or set LLM_API_KEY env var)")
    parser.add_argument("--endpoint", help="Custom API endpoint")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--output", help="Output JSON file")
    
    args = parser.parse_args()
    
    # Load input files
    with open(args.battery, 'r', encoding='utf-8') as f:
        battery_summary = json.load(f)
    
    with open(args.navigation, 'r', encoding='utf-8') as f:
        navigation = json.load(f)
    
    with open(args.strategies, 'r', encoding='utf-8') as f:
        available_strategies = json.load(f)
    
    # Initialize client
    client = LLMClient(
        provider=args.provider,
        api_key=args.api_key,
        endpoint=args.endpoint,
        model=args.model
    )
    
    # Select strategy
    result = client.select_strategy(battery_summary, navigation, available_strategies)
    
    if result:
        print("Strategy selection successful:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Saved to {args.output}")
    else:
        print("Strategy selection failed")
        sys.exit(1)