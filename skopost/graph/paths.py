"""危ない道の列挙（SPEC §7）と、方針ごとの差。

定義（どの方針でも同じ。違うのは caps.py の「不明」の倒し方だけ）：
- 前提：``untrusted_in_context`` が真。偽なら道は 0（外の文を一切読まない構成だけが使える設定）。
- 見るのは ``mode == "allow"`` の道具だけ（ask は「人が止める」）。
- 行動の道 ``[T]``：実効 exec が真 → kind "exec"。実効 acts が空でない → kind "act"（1 道具から両方出ることがある）。
- 持ち出しの道 ``[R, S]``：R の実効 secret が真、S の実効 net または args_leave が真。R と S は同じ道具でもよい。
  via は（R の secret の理由, S の送る側の理由）。送る側は net を優先（net と args_leave が両方真なら net）。
- 確度：道を作った札の確度の**弱い方**（不明 < 推 < 論 < 確）。declared 層は「宣言」。
- 順序：allow の道具の並びで、まず各道具の exec → act、次に読む側 × 送る側の二重の並び（v1 と同じ）。

「不明は危険」：observed 層で書かれていない・確度「不明」の札は能力があると仮定する。真偽は真、acts は全種、
置き場は方針による（v1：なし／monotone：全部）。仮定した項目は EffectiveCaps.assumed に載り、報告の
「不明として危ない側に倒した項目」になる。
"""
from __future__ import annotations

from collections.abc import Mapping

from ..model.constants import ACT_KINDS
from ..model.types import Config, EffectiveCaps, HarmPath, Layer, Store, weakest
from .caps import DEFAULT_POLICY, Policy, effective


def effective_all(cfg: Config, layer: Layer, policy: Policy = DEFAULT_POLICY) -> dict[str, EffectiveCaps]:
    """allow の道具ごとの実効の札（道具の並び順）。"""
    stores: Mapping[str, Store] = cfg.store_map()
    return {t.id: effective(t, stores, layer, policy) for t in cfg.allowed()}


def harm_paths_policy(cfg: Config, layer: Layer, policy: Policy = DEFAULT_POLICY) -> list[HarmPath]:
    if layer not in ("declared", "observed"):
        raise ValueError(f"layer は declared か observed：{layer!r}")
    if not cfg.untrusted_in_context:
        return []
    eff = effective_all(cfg, layer, policy)
    out: list[HarmPath] = []
    for tid, e in eff.items():
        if e["exec"].value:
            out.append(HarmPath("exec", (tid,), (e["exec"].why,), e["exec"].confidence))
        if e["acts"].value:
            # 不明 → 全種のときは ACT_KINDS の順（v1 と同じ文字列）。書かれた値は validate が辞書順に正規化している
            acts = ",".join(ACT_KINDS if "acts" in e.assumed else sorted(e["acts"].value))
            out.append(HarmPath("act", (tid,), ("acts:" + acts,), e["acts"].confidence))
    readers = [tid for tid, e in eff.items() if e["secret"].value]
    senders = [tid for tid, e in eff.items() if e["net"].value or e["args_leave"].value]
    for r in readers:
        er = eff[r]
        for s in senders:
            es = eff[s]
            send = es["net"] if es["net"].value else es["args_leave"]
            conf = _weakest_with_declared(er["secret"].confidence, send.confidence)
            out.append(HarmPath("exfil", (r, s), (er["secret"].why, send.why), conf))
    return out


def _weakest_with_declared(a: str, b: str) -> str:
    if a == "宣言" or b == "宣言":
        # declared 層：両方「宣言」。片方だけ「宣言」になることはない（層は道具ごとでなく全体で 1 つ）
        return "宣言"
    return weakest(a, b)  # type: ignore[arg-type]


def path_set(paths: list[HarmPath]) -> frozenset[tuple[str, str]]:
    """道の集合としての同一視（kind, key）。順序と via・確度は無視（基準線・単調性の比較用）。"""
    return frozenset((p.kind, p.key) for p in paths)


def policy_diff(cfg: Config, layer: Layer = "observed") -> dict[str, list[HarmPath]]:
    """v1 と monotone の差。``only_monotone``：不明を全置き場に倒したことで増えた道。``only_v1``：常に空のはず
    （monotone は v1 の上位集合。試験で確かめる）。"""
    a = harm_paths_policy(cfg, layer, "v1")
    b = harm_paths_policy(cfg, layer, "monotone")
    ka, kb = path_set(a), path_set(b)
    return {"only_monotone": [p for p in b if (p.kind, p.key) not in ka],
            "only_v1": [p for p in a if (p.kind, p.key) not in kb]}


__all__ = ["effective_all", "harm_paths_policy", "path_set", "policy_diff"]
