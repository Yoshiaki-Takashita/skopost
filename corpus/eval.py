#!/usr/bin/env python3
"""コーパス評価（段 3・担当 F）。docs/PREREG-CORPUS.md の予言 C1〜C6 を測り、prereg-corpus.json で判定する。

標準ライブラリのみ・外部通信なし・種固定。公開 API（skopost.ingest・skopost.pipeline・skopost.graph・skopost.model）
だけを使う。一時ファイルは tempfile（終了時に消す）。

  python3 corpus/eval.py                       # 全部（数十秒〜数分）
  python3 corpus/eval.py --out results-corpus.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import gen  # noqa: E402

from skopost import graph as G  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.ingest import detect, ingest  # noqa: E402
from skopost.model.errors import SkopostError  # noqa: E402
from skopost.pipeline import apply_inferred  # noqa: E402

UNREAD_KINDS = {"unread_key", "unsupported", "dropped"}


def _manifest() -> dict:
    with open(os.path.join(gen.REAL_DIR, "MANIFEST.json"), encoding="utf-8") as f:
        return json.load(f)


def _is_x_path_op(ptr: str) -> bool:
    parts = ptr.split("/")
    return ptr.startswith("/paths/") and parts[-1].startswith("x-")


# ------------------------------------------------------------ (1) 記録率
def eval_unread(man: dict) -> dict:
    per_fmt: dict = {}
    misses = []
    hit_non_x = tot_non_x = hit_x = tot_x = 0
    for rel, ent in sorted(man["files"].items()):
        res = ingest(os.path.join(gen.REAL_DIR, rel), adapter=ent["format"])
        got = {n.pointer for n in res.notes if n.kind in UNREAD_KINDS}
        f = per_fmt.setdefault(ent["format"], {"planted": 0, "recorded": 0})
        for p in ent["planted_unread"]:
            ok = p in got
            f["planted"] += 1
            f["recorded"] += ok
            if _is_x_path_op(p):
                tot_x += 1
                hit_x += ok
            else:
                tot_non_x += 1
                hit_non_x += ok
            if not ok:
                misses.append(f"{rel}#{p}")
    return {"per_format": per_fmt, "unread_recall_non_x": hit_non_x / tot_non_x if tot_non_x else None,
            "unread_recall_x_path_op": hit_x / tot_x if tot_x else None, "planted_non_x": tot_non_x,
            "planted_x_path_op": tot_x, "misses": misses}


# ------------------------------------------------------------ (2) 自動判別
def eval_detect(man: dict, renamed: bool) -> dict:
    items = []
    for rel, ent in sorted(man["files"].items()):
        with open(os.path.join(gen.REAL_DIR, rel), encoding="utf-8") as f:
            items.append((rel, ent["format"], json.load(f)))
    for name, raw in gen.synth_corpus(per_size=20):
        items.append((name, "native", raw))
    wrong, refused = [], []
    for rel, want, data in items:
        fn = "config.json" if renamed else os.path.basename(rel)
        try:
            got = detect(data, fn).name
        except SkopostError:
            refused.append(rel)
            continue
        if got != want:
            wrong.append(f"{rel}:{want}->{got}")
    n = len(items)
    return {"n": n, "wrong": wrong, "refused": refused, "error": (len(wrong) + len(refused)) / n}


# ------------------------------------------------------------ (3) 確度印の分布
def eval_infer(man: dict) -> dict:
    dist: Counter = Counter()
    by_fmt: dict = {}
    for rel, ent in sorted(man["files"].items()):
        res = ingest(os.path.join(gen.REAL_DIR, rel), adapter=ent["format"])
        cfg = apply_inferred(res.config, res.facts)
        c = by_fmt.setdefault(ent["format"], Counter())
        for t in cfg.tools:
            for _k, cap in t.observed.items():
                if str(cap.source).startswith("infer:"):
                    dist[cap.confidence] += 1
                    c[cap.confidence] += 1
    total = sum(dist.values())
    return {"distribution": dict(dist), "by_format": {k: dict(v) for k, v in by_fmt.items()}, "total": total,
            "inferred_kaku": dist.get("確", 0), "inferred_suisoku_share": dist.get("推", 0) / total if total else None}


# ------------------------------------------------------------ (4) 厳密解 vs 全探索・時間
def brute_min(paths) -> int:
    sets = [frozenset(p.tools) for p in paths]
    if not sets:
        return 0
    cand = sorted(set().union(*sets))
    for k in range(len(cand) + 1):
        for combo in itertools.combinations(cand, k):
            c = set(combo)
            if all(s & c for s in sets):
                return k
    raise AssertionError("被覆なし")


def eval_exact(seed: int, per_n: int = 200) -> dict:
    mismatch, nonexact, n_cfg, sizes = [], 0, 0, Counter()
    for n in range(10, 15):
        for i in range(per_n):
            cfg = M.parse(gen.synth(seed, n, i))
            res = G.analyze(cfg)
            n_cfg += 1
            cp = res.checkpoints
            if not cp.exact:
                nonexact += 1
            b = brute_min(res.paths)
            sizes[b] += 1
            covers = all(set(p.tools) & set(cp.primary) for p in res.paths)
            if len(cp.primary) != b or not covers:
                mismatch.append(f"n{n}-{i}: exact={len(cp.primary)} brute={b} covers={covers}")
    return {"configs": n_cfg, "exact_vs_brute_mismatch": len(mismatch) + nonexact, "mismatch": mismatch,
            "nonexact": nonexact, "brute_size_hist": dict(sorted(sizes.items()))}


def eval_time64(seed: int, reps: int = 50) -> dict:
    times, exact, methods, npaths = [], 0, Counter(), []
    for i in range(reps):
        cfg = M.parse(gen.synth(seed, 64, i))
        t0 = time.perf_counter()
        res = G.analyze(cfg)
        times.append(time.perf_counter() - t0)
        exact += res.checkpoints.exact
        methods[res.checkpoints.method] += 1
        npaths.append(len(res.paths))
    ts = sorted(times)
    return {"reps": reps, "p95_seconds_n64": ts[min(len(ts) - 1, int(len(ts) * 0.95))], "mean": statistics.mean(ts),
            "max": ts[-1], "exact": exact, "methods": dict(methods), "paths_mean": statistics.mean(npaths)}


# ------------------------------------------------------------ (5) monotone vs v1
def eval_monotone(seed: int) -> dict:
    sizes = (10, 16, 24, 32, 48, 64)
    per = {10: 167, 16: 167, 24: 167, 32: 167, 48: 166, 64: 166}
    shrink = grow = n_cfg = v1_total = mono_total = cut_grow = 0
    for n in sizes:
        for i in range(per[n]):
            cfg = M.parse(gen.synth(seed + 1, n, i))  # (4) と別の系列
            d = G.policy_diff(cfg)
            a = G.harm_paths_policy(cfg, "observed", "v1")
            b = G.harm_paths_policy(cfg, "observed", "monotone")
            n_cfg += 1
            v1_total += len(a)
            mono_total += len(b)
            shrink += bool(d["only_v1"])
            grow += bool(d["only_monotone"])
            if d["only_monotone"]:
                ra = G.analyze_policy(cfg, "v1").checkpoints
                rb = G.analyze_policy(cfg, "monotone").checkpoints
                cut_grow += len(rb.primary) > len(ra.primary)
    return {"configs": n_cfg, "monotone_shrink_configs": shrink, "monotone_grow_share": grow / n_cfg,
            "monotone_path_increase": mono_total / v1_total - 1 if v1_total else None, "v1_paths": v1_total,
            "monotone_paths": mono_total, "cut_grows": cut_grow}


# ------------------------------------------------------------ 判定
def judge(metrics: dict, pre: dict) -> list:
    out = []
    for pid, p in pre["predictions"].items():
        v = metrics.get(p["metric"])
        ok = v is not None
        if ok and "min" in p:
            ok = v >= p["min"]
        if ok and "max" in p:
            ok = ok and v <= p["max"]
        if ok and "max_exclusive" in p:
            ok = ok and v < p["max_exclusive"]
        out.append({"id": pid, "desc": p["desc"], "value": v, "hit": bool(ok)})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=gen.SEED)
    ns = ap.parse_args(argv)
    man = _manifest()
    with open(os.path.join(ROOT, "prereg-corpus.json"), encoding="utf-8") as f:
        pre = json.load(f)
    t0 = time.perf_counter()
    r = {"unread": eval_unread(man), "detect": eval_detect(man, False), "detect_renamed": eval_detect(man, True),
         "infer": eval_infer(man), "exact": eval_exact(ns.seed), "time64": eval_time64(ns.seed),
         "monotone": eval_monotone(ns.seed)}
    metrics = {}
    for k in ("unread", "infer", "exact", "time64", "monotone"):
        metrics.update({m: v for m, v in r[k].items() if not isinstance(v, (dict, list))})
    metrics["detect_error"] = r["detect"]["error"]
    metrics["detect_error_renamed"] = r["detect_renamed"]["error"]
    r["judgement"] = judge(metrics, pre)
    r["seconds"] = time.perf_counter() - t0
    for j in r["judgement"]:
        print(f"{'当たり' if j['hit'] else '外れ  '} {j['id']}: {j['desc']} → {j['value']}")
    hits = sum(j["hit"] for j in r["judgement"])
    print(f"\n予言 {len(r['judgement'])} 件中 当たり {hits}・外れ {len(r['judgement']) - hits}（{r['seconds']:.1f} 秒）")
    if ns.out:
        with open(ns.out, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1, default=str)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
