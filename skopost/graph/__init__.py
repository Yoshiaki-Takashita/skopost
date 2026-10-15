"""graph：危険経路と最小関所（担当 D・段 2）。依存は model（と infer）だけ。

公開面（契約で固定）：analyze・apply_checkpoints・explain・harm_paths・min_checkpoints。
追加の公開（graph の裁量）：
- ``harm_paths_policy(cfg, layer, policy)``・``analyze_policy(cfg, policy)``：方針 "v1"／"monotone"（docs/GRAPH.md）
- ``policy_diff(cfg)``：v1 と monotone の道の差
- ``POLICIES``・``DEFAULT_POLICY``
"""
from __future__ import annotations

from .analysis import analyze as analyze_policy
from .api import analyze, apply_checkpoints, explain, harm_paths, min_checkpoints
from .caps import DEFAULT_POLICY, POLICIES, Policy
from .paths import harm_paths_policy, policy_diff

__all__ = ["analyze", "apply_checkpoints", "explain", "harm_paths", "min_checkpoints",
           "analyze_policy", "harm_paths_policy", "policy_diff", "POLICIES", "DEFAULT_POLICY", "Policy"]
