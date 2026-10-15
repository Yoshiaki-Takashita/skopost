"""graph の実時間（G2 の実測・担当 D）。道具 64 個で実用時間かを測る。

既定は軽い回数（各 5 件）で、`SKOPOST_GRAPH_BENCH=1` を付けると docs/GRAPH.md の数字を出した回数（各 50 件）で回す。
失敗条件はゆるい上限（1 件 10 秒）だけ。数字は標準エラーに出す。

3 つの形：
- full   ：SPEC §7 の道を全部渡す（残りは完全二部＝自明に近い）。64 道具・観察の札を半分ほど不明に
- bip    ：任意の二部の辺（32×32、辺 500 本）＝最大流
- general：任意の辺（64 頂点、辺 500 本・非二部）＝分枝限定。**最悪の形**。時間切れなら貪欲に落ちる
"""
from __future__ import annotations

import os
import random
import statistics
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import gen_raw_config  # noqa: E402

from skopost import graph as G  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.graph import hitting as H  # noqa: E402

FULL = os.environ.get("SKOPOST_GRAPH_BENCH") == "1"
REPS = 50 if FULL else 5
LIMIT_S = 10.0


def _report(name: str, times: list[float], extra: str = "") -> None:
    times = sorted(times)
    p95 = times[min(len(times) - 1, int(len(times) * 0.95))]
    sys.stderr.write(f"\n[bench {name}] n={len(times)} mean={statistics.mean(times):.4f}s p95={p95:.4f}s max={times[-1]:.4f}s {extra}\n")


class Bench64(unittest.TestCase):
    def test_full_spec_paths_64_tools(self):
        rng = random.Random(64)
        times = []
        exact = 0
        for _ in range(REPS):
            raw = gen_raw_config(rng, n_tools=64, n_stores=3, p_unknown=0.5)
            for t in raw["tools"]:
                t["mode"] = "allow"
            cfg = M.parse(raw)
            t0 = time.perf_counter()
            res = G.analyze(cfg)
            dt = time.perf_counter() - t0
            times.append(dt)
            exact += res.checkpoints.exact
            self.assertLess(dt, LIMIT_S)
        _report("full-64", times, f"exact={exact}/{REPS} method={res.checkpoints.method} paths={res.summary.paths}")
        self.assertEqual(exact, REPS, "SPEC の道の全部なら 64 道具でも常に厳密")

    def test_bipartite_edges(self):
        rng = random.Random(65)
        times = []
        for _ in range(REPS):
            ids = [f"l{i}" for i in range(32)] + [f"r{i}" for i in range(32)]
            freq = [rng.randint(1, 9) for _ in ids]
            sets = {frozenset([f"l{rng.randrange(32)}", f"r{rng.randrange(32)}"]) for _ in range(500)}
            inst = H.make_instance(ids, freq, list(sets))
            t0 = time.perf_counter()
            cp, notes = H.solve(inst, exact_limit=20, time_budget_s=LIMIT_S)
            dt = time.perf_counter() - t0
            times.append(dt)
            self.assertTrue(cp.exact)
            self.assertEqual(cp.method, "bipartite-konig")
            self.assertLess(dt, LIMIT_S)
        _report("bipartite-32x32-500", times, f"enum_complete={notes['enum_complete']} size={cp.size}")

    def test_general_edges(self):
        rng = random.Random(66)
        times = []
        exact = 0
        methods = []
        for _ in range(REPS):
            ids = [f"t{i:02d}" for i in range(64)]
            freq = [rng.randint(1, 9) for _ in ids]
            sets = {frozenset(rng.sample(ids, 2)) for _ in range(500)}
            inst = H.make_instance(ids, freq, list(sets))
            t0 = time.perf_counter()
            cp, notes = H.solve(inst, exact_limit=20, time_budget_s=5.0)
            dt = time.perf_counter() - t0
            times.append(dt)
            exact += cp.exact
            methods.append(cp.method)
            self.assertLess(dt, LIMIT_S)
            self.assertLessEqual(cp.lower_bound, cp.size)
        _report("general-64-500", times, f"exact={exact}/{REPS} methods={sorted(set(methods))}")

    def test_general_sparse_edges(self):
        rng = random.Random(67)
        times = []
        exact = 0
        for _ in range(REPS):
            ids = [f"t{i:02d}" for i in range(64)]
            freq = [rng.randint(1, 9) for _ in ids]
            sets = {frozenset(rng.sample(ids, 2)) for _ in range(100)}
            inst = H.make_instance(ids, freq, list(sets))
            t0 = time.perf_counter()
            cp, notes = H.solve(inst, exact_limit=20, time_budget_s=5.0)
            dt = time.perf_counter() - t0
            times.append(dt)
            exact += cp.exact
            self.assertLess(dt, LIMIT_S)
        _report("general-64-100", times, f"exact={exact}/{REPS}")


if __name__ == "__main__":
    unittest.main()
