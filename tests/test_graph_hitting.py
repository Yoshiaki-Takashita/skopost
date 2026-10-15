"""graph の詳細試験：最小ヒッティングセット（担当 D）。

- 小さな例（道具 ≤ 10）で総当たりと一致：大きさ・frequency 合計・v1 の鍵（同点の順）まで厳密に
- 二部の最大流と分枝限定が一致（G3）・非二部（三角形など）でも総当たりと一致
- 代替案：列挙が完了したときは総当たりの上位と一致
- 同じ大きさの案が 200 件を超える構成：v1 は最小手間を逃すが、新実装は逃さない（段 1 の記録 3）
- 近似（貪欲）：下界 ≤ 真の最小 ≤ 案（G4）・exact=True と言うなら本当に最小
- 道に 3 個以上の道具・allow でない道具が混じれば ValueError（黙って落とさない）
"""
from __future__ import annotations

import itertools
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import example_raws  # noqa: E402

from skopost import graph as G  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402
from skopost.graph import hitting as H  # noqa: E402
from skopost.model import HarmPath  # noqa: E402

N_RAND = int(os.environ.get("SKOPOST_GRAPH_RAND", "400"))


def brute(inst: H.Instance) -> list[tuple[int, list[str], int]]:
    """全部の最小被覆を (frequency 合計, v1 の鍵, ビット集合) で並べて返す。"""
    n = inst.n
    masks = [sum(1 << i for i in s) for s in inst.sets]
    for k in range(0, n + 1):
        found = []
        for comb in itertools.combinations(range(n), k):
            cm = sum(1 << i for i in comb)
            if all(pm & cm for pm in masks):
                found.append((sum(inst.freq[i] for i in comb), [inst.ids[i] for i in comb], cm))
        if found:
            found.sort(key=lambda x: (x[0], x[1]))
            return found
    return []


def rand_instance(rng: random.Random, n: int, *, m: int | None = None, p_single: float = 0.15,
                  max_freq: int = 9, ids=None) -> H.Instance:
    ids = ids or [f"t{i}" for i in range(n)]
    freq = [rng.randint(1, max_freq) for _ in range(n)]
    m = rng.randint(1, n * 2) if m is None else m
    sets = []
    for _ in range(m):
        if n < 2 or rng.random() < p_single:
            sets.append(frozenset([ids[rng.randrange(n)]]))
        else:
            a, b = rng.sample(range(n), 2)
            sets.append(frozenset([ids[a], ids[b]]))
    return H.make_instance(ids, freq, sets)


def check_against_brute(tc: unittest.TestCase, inst: H.Instance, **kw) -> None:
    cp, notes = H.solve(inst, **kw)
    ranked = brute(inst)
    tc.assertTrue(cp.exact)
    tc.assertEqual(cp.lower_bound, len(ranked[0][1]) if ranked else 0)
    tc.assertEqual(list(cp.primary), ranked[0][1] if ranked else [])
    if notes["enum_complete"]:
        want_alts = [r[1] for r in ranked[1:1 + kw.get("max_alternatives", 5)]]
        tc.assertEqual([list(a) for a in cp.alternatives], want_alts)


class BruteForceAgreement(unittest.TestCase):
    def test_random_small(self):
        rng = random.Random(1)
        methods = set()
        for i in range(N_RAND):
            inst = rand_instance(rng, rng.randint(1, 10))
            cp, _ = H.solve(inst)
            methods.add(cp.method)
            check_against_brute(self, inst)
        self.assertEqual(methods, {"trivial", "bipartite-konig", "branch-and-bound"}, "3 つの経路を全部通った")

    def test_many_ties_equal_freq(self):
        """frequency が全部同じ＝同点だらけ。鍵（id の並び順の列の辞書順）まで一致。"""
        rng = random.Random(2)
        for i in range(N_RAND // 2):
            inst = rand_instance(rng, rng.randint(2, 10), max_freq=1)
            check_against_brute(self, inst)

    def test_ids_not_alphabetical(self):
        """id が並び順と辞書順で食い違う（v1 の鍵は文字列の比較）。"""
        rng = random.Random(3)
        for i in range(N_RAND // 2):
            n = rng.randint(2, 9)
            ids = rng.sample(["b", "a", "z", "c10", "c2", "y", "x", "d", "e", "f"], n)
            inst = rand_instance(rng, n, max_freq=2, ids=ids)
            check_against_brute(self, inst)

    def test_triangles_and_dense(self):
        """非二部（奇数の閉路）と密なグラフ。"""
        rng = random.Random(4)
        for i in range(N_RAND // 4):
            n = rng.randint(3, 10)
            ids = [f"t{i}" for i in range(n)]
            freq = [rng.randint(1, 5) for _ in range(n)]
            sets = [frozenset([ids[a], ids[b]]) for a in range(n) for b in range(a + 1, n) if rng.random() < 0.7]
            if not sets:
                continue
            inst = H.make_instance(ids, freq, sets)
            cp, _ = H.solve(inst)
            check_against_brute(self, inst)

    def test_matches_v1_on_corpus_paths(self):
        for name, raw in example_raws().items():
            legacy = M.validate(raw)
            cfg = M.from_legacy(legacy)
            paths = [HarmPath(p["kind"], tuple(p["tools"]), tuple(p["via"]), p["confidence"])
                     for p in V1.harm_paths(legacy, "observed")]
            cp = G.min_checkpoints(cfg, paths)
            want = V1.min_checkpoints(legacy, V1.harm_paths(legacy, "observed"))
            self.assertEqual((list(cp.primary), [list(a) for a in cp.alternatives]), (want["primary"], want["alternatives"]), name)


class KonigVsBranchAndBound(unittest.TestCase):
    """G3：二部のとき、最大流の答えと分枝限定の答えが同じ（重み＝大きさ・手間）。"""

    def test_agree(self):
        rng = random.Random(5)
        for i in range(N_RAND // 2):
            L = rng.randint(1, 8)
            R = rng.randint(1, 8)
            ids = [f"l{i}" for i in range(L)] + [f"r{i}" for i in range(R)]
            freq = [rng.randint(1, 9) for _ in ids]
            sets = [frozenset([f"l{a}", f"r{b}"]) for a in range(L) for b in range(R) if rng.random() < 0.5]
            if not sets:
                continue
            inst = H.make_instance(ids, freq, sets)
            w = [sum(freq) + 1 + f for f in freq]
            res = H._reduce(inst)
            bip = H._is_bipartite(res.alive, res.adj)
            self.assertIsNotNone(bip)
            cost_k, cover_k = H._bipartite_cover(res, bip[0], bip[1], w)
            bb = H._BB(res.adj, w, None)
            bb.run(res.alive, 0, 0)
            self.assertEqual(cost_k, bb.best_cost, i)
            self.assertEqual(sum(w[v] for v in H._bits(cover_k)), cost_k)


class TiesBeyondV1Cap(unittest.TestCase):
    """段 1 の記録 3：v1 は同じ大きさの案を 200 件で打ち切るので、第一案が frequency 最小でないことがある。"""

    def _instance(self):
        # 9 本の互いに素な辺 (2i, 2i+1)。偶数側は手間 2、奇数側は手間 1。最小は奇数側を全部（手間 9）。
        # v1 は組み合わせの順で最初の 200 件（偶数側が多い案）しか見ないので、奇数側だけの案に届かない。
        n = 18
        ids = [f"t{i:02d}" for i in range(n)]
        freq = [2 if i % 2 == 0 else 1 for i in range(n)]
        sets = [frozenset([ids[2 * i], ids[2 * i + 1]]) for i in range(9)]
        return ids, freq, sets

    def test_new_finds_min_effort(self):
        ids, freq, sets = self._instance()
        inst = H.make_instance(ids, freq, sets)
        cp, notes = H.solve(inst)
        self.assertTrue(cp.exact)
        self.assertEqual(cp.size, 9)
        self.assertEqual(list(cp.primary), [ids[2 * i + 1] for i in range(9)])
        self.assertTrue(notes["enum_complete"], "512 件の案は列挙できる")
        self.assertEqual(len(cp.alternatives), 5)
        costs = [sum(freq[ids.index(x)] for x in a) for a in cp.alternatives]
        self.assertEqual(costs, [10] * 5, "代替案は手間 10（奇数側 8 個＋偶数側 1 個）が 5 件")

    def test_v1_misses_it(self):
        ids, freq, sets = self._instance()
        raw = {"skopost": 1, "stores": [],
               "tools": [{"id": t, "frequency": f, "observed": {c: {"value": False, "confidence": "確"} for c in M.BOOL_CAPS}
                          | {"acts": {"value": [], "confidence": "確"}}} for t, f in zip(ids, freq)]}
        legacy = M.validate(raw)
        paths = [{"kind": "exfil", "tools": sorted(s), "via": ["x", "y"], "confidence": "確"} for s in sets]
        v1 = V1.min_checkpoints(legacy, paths)
        self.assertTrue(v1["exact"])
        self.assertEqual(len(v1["primary"]), 9)
        v1_cost = sum(freq[ids.index(x)] for x in v1["primary"])
        self.assertGreater(v1_cost, 9, "v1 の第一案は手間が最小でない（記録どおり）")

    def test_oracle_tiebreak_when_enumeration_cut(self):
        """列挙を打ち切っても（上限を小さくして再現）、第一案は鍵の最小を厳密に出す。"""
        ids, freq, sets = self._instance()
        inst = H.make_instance(ids, freq, sets)
        old = H.ENUM_COVER_CAP
        try:
            H.ENUM_COVER_CAP = 10
            cp, notes = H.solve(inst)
        finally:
            H.ENUM_COVER_CAP = old
        self.assertFalse(notes["enum_complete"])
        self.assertEqual(notes["tiebreak"], "oracle")
        self.assertEqual(list(cp.primary), [ids[2 * i + 1] for i in range(9)])
        self.assertTrue(cp.exact)
        # 同点の鍵まで一致（手間が全部同じ）
        rng = random.Random(8)
        for i in range(40):
            inst = rand_instance(rng, rng.randint(4, 10), max_freq=1)
            want = brute(inst)[0][1]
            try:
                H.ENUM_COVER_CAP = 0
                H.ENUM_NODE_CAP = 1
                cp, notes = H.solve(inst)
            finally:
                H.ENUM_COVER_CAP = old
                H.ENUM_NODE_CAP = 200_000
            self.assertEqual(list(cp.primary), want, i)


class GreedyFallback(unittest.TestCase):
    def test_bounds_hold(self):
        rng = random.Random(9)
        certified = 0
        for i in range(N_RAND // 2):
            inst = rand_instance(rng, rng.randint(1, 10))
            cp, notes = H.solve(inst, exact_limit=0, time_budget_s=0.0)
            self.assertEqual(cp.method, "greedy")
            ranked = brute(inst)
            true_min = len(ranked[0][1]) if ranked else 0
            self.assertLessEqual(cp.lower_bound, true_min)
            self.assertLessEqual(true_min, cp.size)
            if cp.exact:
                self.assertEqual(cp.size, true_min)
                certified += 1
            masks = [sum(1 << j for j in s) for s in inst.sets]
            cm = sum(1 << inst.ids.index(t) for t in cp.primary)
            self.assertTrue(all(pm & cm for pm in masks))
        self.assertGreater(certified, 0, "下界と一致して大きさを証明できる例がある")

    def test_greedy_matches_v1_greedy(self):
        """貪欲法は v1 と同じ選び方（同じ案）。"""
        rng = random.Random(10)
        for i in range(60):
            n = rng.randint(21, 30)
            ids = [f"t{j:02d}" for j in range(n)]
            freq = [rng.randint(1, 9) for _ in range(n)]
            sets = [frozenset(rng.sample(ids, rng.choice((1, 2)))) for _ in range(rng.randint(1, 40))]
            inst = H.make_instance(ids, freq, sets)
            cp, _ = H.solve(inst, exact_limit=20, time_budget_s=0.0)
            raw = {"skopost": 1, "stores": [],
                   "tools": [{"id": t, "frequency": f} for t, f in zip(ids, freq)]}
            legacy = M.validate(raw)
            paths = [{"kind": "exfil" if len(s) == 2 else "exec", "tools": sorted(s), "via": ["x"] * len(s), "confidence": "確"} for s in sets]
            self.assertEqual(list(cp.primary), V1.min_checkpoints(legacy, paths)["primary"], i)

    def test_timeout_returns_honest_answer(self):
        """時間切れ（予算 0 秒に近い）でも、返す案は全部の道を断ち、exact=True なら下界と一致。"""
        rng = random.Random(12)
        for i in range(20):
            n = 40
            ids = [f"t{j:02d}" for j in range(n)]
            freq = [rng.randint(1, 9) for _ in range(n)]
            sets = [frozenset(rng.sample(ids, 2)) for _ in range(300)]
            inst = H.make_instance(ids, freq, sets)
            cp, notes = H.solve(inst, exact_limit=20, time_budget_s=1e-9)
            masks = [sum(1 << j for j in s) for s in inst.sets]
            cm = sum(1 << inst.ids.index(t) for t in cp.primary)
            self.assertTrue(all(pm & cm for pm in masks))
            self.assertLessEqual(cp.lower_bound, cp.size)
            if cp.exact:
                self.assertEqual(cp.lower_bound, cp.size)


class Validation(unittest.TestCase):
    def test_rejects_bad_paths(self):
        cfg = M.parse(example_raws()["example"])
        allowed = [t.id for t in cfg.allowed()]
        asks = [t.id for t in cfg.tools if t.mode == "ask"]
        if asks:
            with self.assertRaises(ValueError):
                G.min_checkpoints(cfg, [HarmPath("exec", (asks[0],), ("x",), "確")])
        with self.assertRaises(ValueError):
            H.make_instance(["a", "b", "c"], [1, 1, 1], [frozenset(["a", "b", "c"])])
        with self.assertRaises(ValueError):
            H.make_instance(["a", "b"], [1, 1], [frozenset()])
        with self.assertRaises(ValueError):
            H.make_instance(["a", "a"], [1, 1], [frozenset(["a"])])
        with self.assertRaises(ValueError):
            G.min_checkpoints(cfg, [HarmPath("exec", ("no_such",), ("x",), "確")])

    def test_self_loop_is_forced(self):
        """R と S が同じ道具（[t, t]）は単独の道と同じ＝強制。"""
        inst = H.make_instance(["a", "b"], [1, 1], [frozenset(["a"]), frozenset(["a", "b"])])
        cp, _ = H.solve(inst)
        self.assertEqual((cp.primary, cp.method, cp.exact), (("a",), "trivial", True))


if __name__ == "__main__":
    unittest.main()
