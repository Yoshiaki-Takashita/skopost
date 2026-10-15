"""危険経路の定義（担当 D・graph）：道具 1 個の「実効の札」を graph の方針（policy）で引く。

ここが根幹。SPEC §6 の畳み込みを、**不明の扱い**だけ切り替えられる形で持つ。

方針（Policy）
--------------
- ``"v1"``       ：compat.v1 と一字一句同じ答え。observed 層で ``writes_stores``・``reads_stores`` が不明のとき
                   「置き場なし（[]）」と読む（v1 の設計判断。過大警報を避ける）。**不明を足すと道が減ることがある**
                   （ARCHITECTURE「段 1 で見つけたこと」1・tests/test_contract_graph.V1StoreUnknownQuirk）。
- ``"monotone"`` ：約束「不明を足しても道は減らない」（ARCHITECTURE §1.3 F1）を全項目で守る定義。
                   置き場の札が不明なら「**全部の置き場**に書ける／読める」と倒す。真偽の札・acts は v1 と同じ
                   （不明 → 真／全種）。置き場の札を不明にしたぶんは ``assumed`` に ``writes_stores``／``reads_stores``
                   として載る（v1 は載せない）。

どちらも「確度は弱い方」「不明を仮定した項目は列挙」は同じ。公開 API の既定は ``"v1"``（契約試験＝v1 と同じ道・
同じ順序。報告のバイト一致）。``monotone`` は ``graph.harm_paths_policy`` から使える。既定を切り替えるのは
SPEC と契約試験の更新が要る（担当 A）。差の説明は docs/GRAPH.md。

統合（段 2 の後）：v1 方針の実効の札は infer.effective に寄せた（能力判定の重複を解消）。graph が自前で持つのは
monotone の倒し方だけ。自前の v1 計算 ``_effective_local`` は残し、infer と一致することを試験で確かめる
（tests/test_graph_paths.py CrossCheckWithInfer）。
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Optional, Union

from ..infer import api as _infer
from ..model.constants import ACT_KINDS, BOOL_CAPS
from ..model.frozen import FrozenMap
from ..model.types import Cap, EffCap, EffectiveCaps, Layer, Store, Tool

Policy = Literal["v1", "monotone"]
POLICIES: tuple[str, ...] = ("v1", "monotone")
DEFAULT_POLICY: Policy = "v1"

_DECLARED = "宣言"


def _check_policy(policy: str) -> None:
    if policy not in POLICIES:
        raise ValueError(f"policy は {POLICIES} のどれか：{policy!r}")


def layer_value(tool: Tool, cap: str, layer: Layer, stores: Mapping[str, Store], policy: Policy = DEFAULT_POLICY
                ) -> tuple[Union[bool, frozenset], str, bool]:
    """(値, 確度, 不明を仮定したか)。

    declared 層：無い項目は false／空・確度は「宣言」。
    observed 層：無い・不明の項目は危ない側。真偽 → True、acts → 全種、置き場 → policy による
    （v1：空＝仮定しない／monotone：全部の置き場＝仮定した）。
    """
    is_bool = cap in BOOL_CAPS
    if layer == "declared":
        c: Optional[Cap] = tool.declared.get(cap)
        if c is None:
            return (False if is_bool else frozenset()), _DECLARED, False
        return c.value, _DECLARED, False  # type: ignore[return-value]
    ob = tool.observed.get(cap)
    if ob is None or ob.unknown:
        if is_bool:
            return True, "不明", True
        if cap == "acts":
            return frozenset(ACT_KINDS), "不明", True
        if policy == "monotone":
            return frozenset(stores), "不明", True
        return frozenset(), "不明", False
    return ob.value, ob.confidence, False  # type: ignore[return-value]


def effective(tool: Tool, stores: Mapping[str, Store], layer: Layer, policy: Policy = DEFAULT_POLICY) -> EffectiveCaps:
    """置き場を畳み込んだ実効の札（SPEC §6）。policy="v1" は infer.effective に寄せる（統合・ユーザー決定）。
    monotone だけ graph の自前の計算を使う。自前の v1 計算（``_effective_local``）は一致試験のために残す。"""
    _check_policy(policy)
    if policy == "v1":
        return _infer.effective(tool, stores, layer)
    return _effective_local(tool, stores, layer, policy)


def _effective_local(tool: Tool, stores: Mapping[str, Store], layer: Layer, policy: Policy = DEFAULT_POLICY
                     ) -> EffectiveCaps:
    """graph の自前の畳み込み（monotone の本体・v1 は infer との一致試験用）。"""
    _check_policy(policy)
    caps: dict[str, EffCap] = {}
    assumed: list[str] = []

    def get(cap: str) -> tuple[Union[bool, frozenset], str, bool]:
        return layer_value(tool, cap, layer, stores, policy)

    for cap in ("reads_untrusted", "args_leave"):
        v, c, a = get(cap)
        caps[cap] = EffCap(bool(v), c, cap)  # type: ignore[arg-type]
        if a:
            assumed.append(cap)
    ws, _, ws_assumed = get("writes_stores")
    rs, _, rs_assumed = get("reads_stores")
    ws_tag = "writes_stores(不明→全置き場)" if ws_assumed else "writes_stores"
    rs_tag = "reads_stores(不明→全置き場)" if rs_assumed else "reads_stores"
    # 置き場の並びは id の辞書順（v1 の validate が sorted(set(v)) に正規化するので同じ並びになる）
    ws_sorted = sorted(ws)  # type: ignore[arg-type]
    rs_sorted = sorted(rs)  # type: ignore[arg-type]

    def fold(name: str, cap: str, lst: list[str], prop: str, why_store: str, tag: str) -> None:
        v, c, a = get(cap)
        if a:
            assumed.append(cap)
        hit = [s for s in lst if getattr(stores[s], prop)]
        if v:
            caps[name] = EffCap(True, c, cap)
        elif hit:
            # 置き場由来の確度：v1 は常に「論」。monotone で置き場の札が不明なら「不明」（仮定で導いた）
            via_c = "不明" if (tag.endswith("全置き場)") and layer == "observed") else "論"
            caps[name] = EffCap(True, via_c, f"{tag}→{','.join(hit)}（{why_store}）")
        else:
            caps[name] = EffCap(False, c, "")

    fold("exec", "exec", ws_sorted, "executes", "実行される置き場", ws_tag)
    fold("net", "net_out", ws_sorted, "external", "外部の置き場", ws_tag)
    fold("secret", "reads_secret", rs_sorted, "secret", "秘密のある置き場", rs_tag)
    v, c, a = get("acts")
    if a:
        assumed.append("acts")
    caps["acts"] = EffCap(frozenset(v), c, "acts")  # type: ignore[arg-type]
    if ws_assumed:
        assumed.append("writes_stores")
    if rs_assumed:
        assumed.append("reads_stores")
    return EffectiveCaps(tool.id, layer, FrozenMap(caps), frozenset(assumed))


def assumed_order(tool: Tool, stores: Mapping[str, Store], policy: Policy = DEFAULT_POLICY) -> list[str]:
    """observed 層で不明を仮定した項目を v1 の analyze と同じ順で（reads_untrusted, args_leave, exec, net_out,
    reads_secret, acts、monotone ではさらに writes_stores, reads_stores）。"""
    _check_policy(policy)
    out: list[str] = []
    for cap in ("reads_untrusted", "args_leave", "exec", "net_out", "reads_secret", "acts"):
        if layer_value(tool, cap, "observed", stores, policy)[2]:
            out.append(cap)
    if policy == "monotone":
        for cap in ("writes_stores", "reads_stores"):
            if layer_value(tool, cap, "observed", stores, policy)[2]:
                out.append(cap)
    return out


__all__ = ["Policy", "POLICIES", "DEFAULT_POLICY", "layer_value", "effective", "assumed_order"]
