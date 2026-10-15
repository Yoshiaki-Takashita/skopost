#!/usr/bin/env python3
"""合成の評価：宣言だけ／拒否リスト／全部聞く／Skopost を、宣言の誤り率・道具の数・入り組み・不明率の格子で比べる。
全部合成・種固定・外部通信なし。結果は JSON（--out）。PREREG.md の格子と一致させる。

  python3 bench.py --quick            # 100 構成/格子点
  python3 bench.py --full --out results.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skopost as S  # noqa: E402

DEFAULT_SEED = 20261013
GRID = {"n": [6, 10, 16], "p": [0.0, 0.1, 0.2, 0.3], "e": [0.0, 0.3], "u": [0.0, 0.2]}
CAPS_BOOL = ["reads_secret", "net_out", "exec", "args_leave", "reads_untrusted"]
STORES = [{"id": "rc", "executes": True}, {"id": "env", "secret": True}, {"id": "pub", "external": True}]


def gen_config(r: random.Random, n: int, p: float, e: float, u: float) -> dict:
    """宣言の札は「読むだけが多く、ネット少数、実行まれ」。確率 p で宣言に無い能力を 1 つ実際に持つ。
    e で置き場（実行される rc・外部の pub・秘密の env）に繋がる。u で観察の項目が不明になる。"""
    tools = []
    for i in range(n):
        dec = {
            "reads_untrusted": r.random() < 0.5, "reads_secret": r.random() < 0.30, "net_out": r.random() < 0.20,
            "exec": r.random() < 0.08, "args_leave": r.random() < 0.05,
            "acts": sorted(r.sample(S.ACT_KINDS, 1)) if r.random() < 0.10 else [],
            "writes_stores": [], "reads_stores": [],
        }
        if r.random() < e:
            dec["writes_stores"] = [r.choice(["rc", "pub"])] if r.random() < 0.5 else []
            dec["reads_stores"] = ["env"] if r.random() < 0.5 else []
        obs = {k: (list(v) if isinstance(v, list) else v) for k, v in dec.items()}
        if r.random() < p:
            kind = r.choice(["args_leave", "net_out", "exec", "reads_secret", "acts", "writes_exec_store"])
            if kind == "acts":
                obs["acts"] = sorted(set(obs["acts"]) | {r.choice(S.ACT_KINDS)})
            elif kind == "writes_exec_store":
                obs["writes_stores"] = sorted(set(obs["writes_stores"]) | {"rc"})
            else:
                obs[kind] = True
        observed = {k: {"value": v, "confidence": "確", "evidence": "synthetic"} for k, v in obs.items()}
        for k in CAPS_BOOL:  # u に依らず同じ数だけ乱数を引く（真実の構成と乱数列を揃えるため）
            if r.random() < u:
                observed[k] = {"value": None, "confidence": "不明", "evidence": "synthetic"}
        tools.append({"id": f"t{i}", "mode": "ask" if r.random() < 0.3 else "allow", "declared": dec,
                      "observed": observed, "frequency": r.randint(1, 5)})
    return S.validate({"skopost": 1, "name": "synthetic", "stores": STORES, "tools": tools})




def make_pair(r: random.Random, n: int, p: float, e: float, u: float) -> tuple[dict, dict]:
    """(真実の構成, Skopost に渡す構成)。同じ乱数で u=0 の構成を作り、別の乱数で不明化する。"""
    state = r.getstate()
    truth = gen_config(r, n, p, e, 0.0)
    r.setstate(state)
    shown = gen_config(r, n, p, e, u)
    # shown は truth と同じ乱数列で作られる（u の判定は観察の後なので、truth の値と一致する）
    return truth, shown


def denylist_cut(cfg: dict) -> list[str]:
    out = []
    for t in cfg["tools"]:
        if t["mode"] != "allow":
            continue
        d = t["declared"]
        if d.get("exec") or d.get("net_out") or d.get("acts"):
            out.append(t["id"])
    return out


def run_cell(seed: int, configs: int, n: int, p: float, e: float, u: float) -> dict:
    r = random.Random(f"{seed}:{n}:{p}:{e}:{u}")
    methods = ["declared", "denylist", "askall", "skopost"]
    fails = {m: 0 for m in methods}
    burden = {m: 0 for m in methods}
    with_paths = 0
    truth_paths = missed = 0
    t_exact = 0.0
    for _ in range(configs):
        truth, shown = make_pair(r, n, p, e, u)
        tp = S.harm_paths(truth, "observed")
        truth_paths += len(tp)
        dkeys = {S.path_key(x) for x in S.harm_paths(truth, "declared")}
        missed += sum(1 for x in tp if S.path_key(x) not in dkeys)
        cuts = {
            "declared": S.min_checkpoints(shown, S.harm_paths(shown, "declared"))["primary"],
            "denylist": denylist_cut(shown),
            "askall": [t["id"] for t in shown["tools"] if t["mode"] == "allow"],
        }
        t0 = time.perf_counter()
        cuts["skopost"] = S.min_checkpoints(shown, S.harm_paths(shown, "observed"))["primary"]
        t_exact += time.perf_counter() - t0
        if tp:
            with_paths += 1
        for m in methods:
            burden[m] += len(cuts[m])
            if tp and S.harm_paths(S.apply_checkpoints(truth, cuts[m]), "observed"):
                fails[m] += 1
    return {
        "cell": f"n{n}_p{p:g}_e{e:g}_u{u:g}", "n": n, "p": p, "e": e, "u": u, "configs": configs,
        "configs_with_paths": with_paths, "mean_truth_paths": truth_paths / configs,
        "f": (missed / truth_paths) if truth_paths else 0.0,
        "g": {m: (fails[m] / with_paths if with_paths else 0.0) for m in methods},
        "burden": {m: burden[m] / configs for m in methods},
        "sec_per_config": t_exact / configs,
    }


def run(seed: int, configs: int) -> dict:
    cells = []
    for n in GRID["n"]:
        for p in GRID["p"]:
            for e in GRID["e"]:
                for u in GRID["u"]:
                    cells.append(run_cell(seed, configs, n, p, e, u))
    return {"seed": seed, "configs_per_cell": configs, "grid": GRID, "cells": cells}


def table(res: dict) -> str:
    L = ["| cell | 道/構成 | f | g declared | g denylist | g skopost | burden declared | denylist | askall | skopost | s/構成 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in res["cells"]:
        g, b = c["g"], c["burden"]
        L.append(f"| {c['cell']} | {c['mean_truth_paths']:.2f} | {c['f']:.1%} | {g['declared']:.1%} | {g['denylist']:.1%} | "
                 f"{g['skopost']:.1%} | {b['declared']:.2f} | {b['denylist']:.2f} | {b['askall']:.2f} | {b['skopost']:.2f} | {c['sec_per_config']:.4f} |")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--configs", type=int, default=None)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    configs = a.configs or (400 if a.full else 100)
    res = run(a.seed, configs)
    print(table(res))
    if a.out:
        if os.path.exists(a.out):
            print(f"{a.out} は既にあります。上書きしません", file=sys.stderr)
            return 1
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print(f"書きました：{a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
