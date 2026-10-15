"""v1 の解析エンジン（凍結した参照実装）。

単一ファイル `skopost.py`（v1.0.0）の解析・報告部分を**一字も変えずに**移したもの。現行の CLI はこれを使う。

位置づけ（ARCHITECTURE §1.10）：
- 段 2 の担当（infer・graph・report）は新しい実装を各自のパッケージに作り、契約試験（tests/test_contract_*.py）で
  この参照実装と同じ答えになることを確かめる。全部が一致したら cli の配線を新しい実装へ切り替え、このモジュールは
  「互換の確認用」として残す（消すのは 2.0.0 以降）。
- このモジュールを変えてよいのは担当 A だけ。挙動を変える変更は不可（互換が崩れる）。
- 依存は model だけ（試験 test_layering が守る）。
"""
from __future__ import annotations

import itertools
import json
import time
from typing import Any

from ..model.constants import ACT_KINDS, ALL_CAPS, BOOL_CAPS, CONF_ORDER, EXACT_LIMIT, MAX_ALTERNATIVES, SPEC_VERSION
from ..model.safe import safe


# ---------------------------------------------------------------- 実効の札
def _layer_value(tool: dict, cap: str, layer: str) -> tuple[Any, str, bool]:
    """(値, 確度, 不明を仮定したか)。declared 層：無い項目は false/[]・確度は「宣言」。
    observed 層：無い・不明の項目は危ない側（true／全種）に倒す。"""
    empty: Any = False if cap in BOOL_CAPS else []
    if layer == "declared":
        return tool["declared"].get(cap, empty), "宣言", False
    ob = tool["observed"].get(cap)
    if ob is None or ob["confidence"] == "不明":
        if cap in BOOL_CAPS:
            return True, "不明", True
        if cap == "acts":
            return list(ACT_KINDS), "不明", True
        return [], "不明", False  # 置き場は不明でも「全部」にはしない（置き場の性質で倒す方が過大警報にならない）
    return ob["value"], ob["confidence"], False


def effective(tool: dict, stores: dict, layer: str) -> dict:
    """置き場を畳み込んだ実効の札。各項目は {"v": 値, "c": 確度, "why": 理由}。"""
    eff: dict[str, dict] = {}
    assumed: list[str] = []
    get = lambda cap: _layer_value(tool, cap, layer)  # noqa: E731

    def mark(cap: str, v: Any, c: str, why: str) -> None:
        eff[cap] = {"v": v, "c": c, "why": why}

    for cap in ("reads_untrusted", "args_leave"):
        v, c, a = get(cap)
        mark(cap, v, c, cap)
        if a:
            assumed.append(cap)
    ws, _, _ = get("writes_stores")
    rs, _, _ = get("reads_stores")
    # exec
    v, c, a = get("exec")
    if a:
        assumed.append("exec")
    exec_stores = [s for s in ws if stores[s]["executes"]]
    if v:
        mark("exec", True, c, "exec")
    elif exec_stores:
        mark("exec", True, "論", f"writes_stores→{','.join(exec_stores)}（実行される置き場）")
    else:
        mark("exec", False, c, "")
    # net
    v, c, a = get("net_out")
    if a:
        assumed.append("net_out")
    ext_stores = [s for s in ws if stores[s]["external"]]
    if v:
        mark("net", True, c, "net_out")
    elif ext_stores:
        mark("net", True, "論", f"writes_stores→{','.join(ext_stores)}（外部の置き場）")
    else:
        mark("net", False, c, "")
    # secret
    v, c, a = get("reads_secret")
    if a:
        assumed.append("reads_secret")
    sec_stores = [s for s in rs if stores[s]["secret"]]
    if v:
        mark("secret", True, c, "reads_secret")
    elif sec_stores:
        mark("secret", True, "論", f"reads_stores→{','.join(sec_stores)}（秘密のある置き場）")
    else:
        mark("secret", False, c, "")
    # acts
    v, c, a = get("acts")
    if a:
        assumed.append("acts")
    mark("acts", list(v), c, "acts")
    eff["_assumed"] = assumed  # type: ignore[assignment]
    return eff


# ---------------------------------------------------------------- 道と関所
def _min_conf(*cs: str) -> str:
    return min(cs, key=lambda c: CONF_ORDER.get(c, 1))


def harm_paths(cfg: dict, layer: str) -> list[dict]:
    """危ない道の列挙（SPEC §7）。"""
    if not cfg["untrusted_in_context"]:
        return []
    stores = cfg["stores"]
    allowed = [t for t in cfg["tools"] if t["mode"] == "allow"]
    eff = {t["id"]: effective(t, stores, layer) for t in allowed}
    out: list[dict] = []
    for t in allowed:
        e = eff[t["id"]]
        if e["exec"]["v"]:
            out.append({"kind": "exec", "tools": [t["id"]], "confidence": e["exec"]["c"], "via": [e["exec"]["why"]]})
        if e["acts"]["v"]:
            out.append({"kind": "act", "tools": [t["id"]], "confidence": e["acts"]["c"],
                        "via": ["acts:" + ",".join(e["acts"]["v"])]})
    readers = [t for t in allowed if eff[t["id"]]["secret"]["v"]]
    senders = [t for t in allowed if eff[t["id"]]["net"]["v"] or eff[t["id"]]["args_leave"]["v"]]
    for r in readers:
        er = eff[r["id"]]
        for s in senders:
            es = eff[s["id"]]
            send_cap = "net" if es["net"]["v"] else "args_leave"
            out.append({"kind": "exfil", "tools": [r["id"], s["id"]],
                        "confidence": _min_conf(er["secret"]["c"], es[send_cap]["c"]),
                        "via": [er["secret"]["why"], es[send_cap]["why"]]})
    return out


def path_key(p: dict) -> str:
    return ">".join(p["tools"])


def min_checkpoints(cfg: dict, paths: list[dict]) -> dict:
    """道を全部断つ allow→ask の最小集合。同じ大きさの案は frequency 合計の小さい順に最大 5 案。"""
    if not paths:
        return {"exact": True, "primary": [], "alternatives": [], "size": 0}
    ids = [t["id"] for t in cfg["tools"] if t["mode"] == "allow"]
    freq = {t["id"]: t["frequency"] for t in cfg["tools"]}
    idx = {tid: i for i, tid in enumerate(ids)}
    masks = sorted({sum(1 << idx[tid] for tid in set(p["tools"])) for p in paths})
    n = len(ids)
    if n <= EXACT_LIMIT:
        for size in range(1, n + 1):
            found: list[tuple[int, list[str]]] = []
            for comb in itertools.combinations(range(n), size):
                cm = 0
                for i in comb:
                    cm |= 1 << i
                if all(pm & cm for pm in masks):
                    chosen = [ids[i] for i in comb]
                    found.append((sum(freq[c] for c in chosen), chosen))
                    if len(found) >= 200:  # 同じ大きさの案が多すぎるときは打ち切る（結果の最小性は変わらない）
                        break
            if found:
                found.sort(key=lambda x: (x[0], x[1]))
                return {"exact": True, "primary": found[0][1],
                        "alternatives": [c for _, c in found[1:MAX_ALTERNATIVES + 1]], "size": size}
        return {"exact": True, "primary": ids, "alternatives": [], "size": n}
    # 貪欲法（道具 > 20）：残る道を最も多く断つ道具を順に取る
    remaining = list(masks)
    chosen_ids: list[str] = []
    while remaining:
        best = max(range(n), key=lambda i: (sum(1 for pm in remaining if pm & (1 << i)), -freq[ids[i]]))
        chosen_ids.append(ids[best])
        remaining = [pm for pm in remaining if not pm & (1 << best)]
    return {"exact": False, "primary": chosen_ids, "alternatives": [], "size": len(chosen_ids)}


def apply_checkpoints(cfg: dict, cut: list[str]) -> dict:
    cs = set(cut)
    return {**cfg, "tools": [{**t, "mode": "ask"} if t["id"] in cs else t for t in cfg["tools"]]}


# ---------------------------------------------------------------- 食い違いと解析
def mismatches(cfg: dict) -> list[dict]:
    out: list[dict] = []
    for t in cfg["tools"]:
        for cap in ALL_CAPS:
            ob = t["observed"].get(cap)
            if ob is None or ob["confidence"] == "不明":
                continue
            dv = t["declared"].get(cap, False if cap in BOOL_CAPS else [])
            ov = ob["value"]
            if dv == ov:
                continue
            if cap in BOOL_CAPS:
                sev = "under" if ov and not dv else "over"
            else:
                sev = "under" if set(ov) - set(dv) else "over"
            out.append({"tool": t["id"], "cap": cap, "declared": dv, "observed": ov,
                        "confidence": ob["confidence"], "evidence": ob["evidence"], "severity": sev})
    return out


def analyze(cfg: dict) -> dict:
    t0 = time.perf_counter()
    actual = harm_paths(cfg, "observed")
    declared = harm_paths(cfg, "declared")
    cps = min_checkpoints(cfg, actual)
    reasons: dict[str, list[str]] = {}
    for tid in cps["primary"]:
        reasons[tid] = [f"{p['kind']}: {path_key(p)}" for p in actual if tid in p["tools"]]
    d_cut = min_checkpoints(cfg, declared)
    surviving = harm_paths(apply_checkpoints(cfg, d_cut["primary"]), "observed")
    assumed = []
    for t in cfg["tools"]:
        if t["mode"] != "allow":
            continue
        for cap in effective(t, cfg["stores"], "observed")["_assumed"]:
            assumed.append({"tool": t["id"], "cap": cap})
    mm = mismatches(cfg)
    dkeys = {path_key(p) for p in declared}
    missed = [p for p in actual if path_key(p) not in dkeys]
    not_checked = [
        "人の確認の素通し（ask にした道具を人が実際に止めるか）は測っていない",
        "文脈の中の値の流れは追っていない（文脈は 1 つの汚れうる場所として丸めた）",
        "札の正しさは確かめていない（札は入力。確度と根拠を見て判断すること）",
    ]
    if not cfg["untrusted_in_context"]:
        not_checked.append("untrusted_in_context=false のため道を数えていない（外の文を一切読まない構成だけが使える設定）")
    if not cps["exact"]:
        not_checked.append(f"道具が {EXACT_LIMIT} 個を超えるため関所は近似（貪欲法）。最小でない可能性がある")
    return {
        "skopost": SPEC_VERSION, "name": cfg["name"],
        "exit_code": 2 if actual else 0,
        "summary": {"tools": len(cfg["tools"]), "allowed": sum(t["mode"] == "allow" for t in cfg["tools"]),
                    "paths": len(actual), "paths_declared_only": len(declared), "missed_by_declared": len(missed),
                    "mismatches": len(mm), "assumed_unknown": len(assumed),
                    "seconds": round(time.perf_counter() - t0, 4)},
        "paths": actual, "mismatches": mm, "assumed": assumed,
        "checkpoints": {**cps, "reasons": reasons},
        "declared_only": {"cut": d_cut["primary"], "holds": not surviving, "surviving_paths": len(surviving),
                          "surviving": [path_key(p) for p in surviving]},
        "not_checked": not_checked,
    }


# ---------------------------------------------------------------- 報告（Markdown）
KIND_JA = {"exec": "実行", "act": "取り返しのつかない操作", "exfil": "持ち出し"}


def report_md(res: dict, cfg: dict, explain: bool = False) -> str:
    L: list[str] = []
    labels = {t["id"]: safe(t["label"], 40) for t in cfg["tools"]}
    s = res["summary"]
    L.append(f"# Skopost 報告：{safe(res['name'], 60) or '（名前なし）'}")
    L.append("")
    verdict = "危ない道はありません（この札の範囲で）" if res["exit_code"] == 0 else f"危ない道 {s['paths']} 本。関所 {res['checkpoints']['size']} か所で全部断てます"
    L.append(f"**結論**：{verdict}。")
    L.append("")
    L.append(f"- 道具 {s['tools']}（確認なし {s['allowed']}）／宣言だけの地図では道 {s['paths_declared_only']} 本"
             f"（見落とし {s['missed_by_declared']} 本）／宣言と観察の食い違い {s['mismatches']}／不明として危ない側に倒した項目 {s['assumed_unknown']}")
    L.append("")
    cps = res["checkpoints"]
    L.append("## 関所（ここに人の確認を置く）")
    L.append("")
    if not cps["primary"]:
        L.append("なし。")
    else:
        for tid in cps["primary"]:
            L.append(f"- **{tid}**（{labels.get(tid, tid)}）→ `mode: ask`")
            if explain:
                for r in cps["reasons"].get(tid, []):
                    L.append(f"  - 断つ道：{r}")
        if not cps["exact"]:
            L.append("")
            L.append(f"（道具が {EXACT_LIMIT} 個を超えるため近似。最小でない可能性があります）")
        if cps["alternatives"]:
            L.append("")
            L.append("代替案（同じ個数・手間の少ない順）：")
            for alt in cps["alternatives"]:
                L.append(f"- {', '.join(alt)}")
    L.append("")
    d = res["declared_only"]
    L.append("## 宣言だけで決めたらどうなるか")
    L.append("")
    if not d["cut"] and s["paths"] == 0:
        L.append("宣言でも観察でも道はありません。")
    elif d["holds"]:
        L.append(f"宣言だけの関所 {d['cut'] or '（なし）'} でも、観察の層の道は全部断てます。")
    else:
        L.append(f"宣言だけの関所 {d['cut'] or '（なし）'} では、観察の層で **{d['surviving_paths']} 本**の道が残ります："
                 + "、".join(f"`{x}`" for x in d["surviving"]))
        L.append("")
        L.append("これが「一覧で管理すると安全の錯覚になる」の具体です。")
    L.append("")
    L.append("## 危ない道")
    L.append("")
    if res["paths"]:
        L.append("| 種類 | 道 | 確度 | 経路 |")
        L.append("|---|---|---|---|")
        for p in res["paths"]:
            L.append(f"| {KIND_JA[p['kind']]} | {path_key(p)} | {p['confidence']} | {safe(' → '.join(p['via']), 80)} |")
    else:
        L.append("なし。")
    L.append("")
    L.append("## 宣言と観察の食い違い")
    L.append("")
    if res["mismatches"]:
        L.append("| 道具 | 項目 | 宣言 | 観察 | 確度 | 向き | 根拠 |")
        L.append("|---|---|---|---|---|---|---|")
        for m in res["mismatches"]:
            sev = "**申告より危ない**" if m["severity"] == "under" else "申告より安全"
            L.append(f"| {m['tool']} | {m['cap']} | {json.dumps(m['declared'], ensure_ascii=False)} | "
                     f"{json.dumps(m['observed'], ensure_ascii=False)} | {m['confidence']} | {sev} | {safe(m['evidence'], 60)} |")
    else:
        L.append("なし。")
    L.append("")
    L.append("## 不明として危ない側に倒した項目")
    L.append("")
    if res["assumed"]:
        L.append("観察の札を書けば、関所が減る可能性があります。")
        for a in res["assumed"]:
            L.append(f"- {a['tool']}.{a['cap']}")
    else:
        L.append("なし。")
    L.append("")
    L.append("## 走らせなかった検査・限界")
    L.append("")
    for x in res["not_checked"]:
        L.append(f"- {x}")
    L.append("")
    L.append(f"_Skopost v{SPEC_VERSION}・計算 {s['seconds']} 秒・外部通信なし・入力は変更していません_")
    return "\n".join(L) + "\n"
