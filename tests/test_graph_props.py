"""graph の性質試験（担当 D）：単調性・最小性・冪等・順序不変。乱数の構成で確かめる。

- 単調性：方針 monotone で、不明を足しても道は減らない（test_graph_paths にも。ここは関所の数も見る：
  不明を足すと関所は減らない……は**成り立たない**ことがあるので注意。道が増えても関所の最小数は増える
  とは限らない（同じ道具で断てる）。ここで確かめるのは「道の集合が減らない」だけ）
- 最小性：第一案の大きさは総当たりの最小と一致、代替案も全部の道を断つ
- 冪等：第一案を当てたら道は 0／当てた構成にもう一度当てても同じ／関所を 2 度求めても同じ
- 順序不変：道具の並びを入れ替えても、道の集合・関所の大きさ・手間は同じ
"""
from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import gen_raw_config  # noqa: E402
from test_contract_graph import brute_min  # noqa: E402
from test_graph_paths import with_unknown  # noqa: E402

from skopost import graph as G  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.graph.paths import path_set  # noqa: E402

N = int(os.environ.get("SKOPOST_GRAPH_PROP", "300"))


def configs(seed: int, n: int = N):
    rng = random.Random(seed)
    for i in range(n):
        yield i, M.parse(gen_raw_config(rng, n_tools=rng.randint(1, 12)))


class Monotone(unittest.TestCase):
    def test_paths_never_shrink(self):
        for i, cfg in configs(100):
            if not cfg.untrusted_in_context:
                continue
            before = path_set(G.harm_paths_policy(cfg, "observed", "monotone"))
            t = cfg.tools[i % len(cfg.tools)]
            for cap in M.ALL_CAPS:
                after = path_set(G.harm_paths_policy(with_unknown(cfg, t.id, cap), "observed", "monotone"))
                self.assertLessEqual(before, after, (i, t.id, cap))

    def test_v1_breaks_only_on_store_caps(self):
        """v1 方針では、単調性が破れるのは置き場の札だけ（真偽の札・acts では破れない）。"""
        broken = set()
        for i, cfg in configs(101):
            if not cfg.untrusted_in_context:
                continue
            before = path_set(G.harm_paths_policy(cfg, "observed", "v1"))
            t = cfg.tools[i % len(cfg.tools)]
            for cap in M.ALL_CAPS:
                after = path_set(G.harm_paths_policy(with_unknown(cfg, t.id, cap), "observed", "v1"))
                if not before <= after:
                    broken.add(cap)
        self.assertLessEqual(broken, set(M.STORE_LIST_CAPS), broken)


class Minimal(unittest.TestCase):
    def test_primary_is_minimum_and_alternatives_cut(self):
        for i, cfg in configs(200):
            paths = G.harm_paths(cfg, "observed")
            cp = G.min_checkpoints(cfg, paths)
            self.assertTrue(cp.exact, i)
            self.assertEqual(cp.size, brute_min(cfg, paths), i)
            self.assertTrue(cp.cuts(paths), i)
            for alt in cp.alternatives:
                self.assertTrue(cp.cuts(paths, alt), (i, alt))
                self.assertEqual(len(alt), cp.size)

    def test_every_checkpoint_is_needed(self):
        """最小なので、どの関所を外しても道が残る（大きさ 0 の場合を除く）。"""
        for i, cfg in configs(201):
            paths = G.harm_paths(cfg, "observed")
            cp = G.min_checkpoints(cfg, paths)
            for drop in cp.primary:
                rest = tuple(x for x in cp.primary if x != drop)
                self.assertFalse(cp.cuts(paths, rest), (i, drop))


class Idempotent(unittest.TestCase):
    def test_apply_primary_kills_all_paths(self):
        for i, cfg in configs(300):
            paths = G.harm_paths(cfg, "observed")
            cp = G.min_checkpoints(cfg, paths)
            cfg2 = G.apply_checkpoints(cfg, cp.primary)
            self.assertEqual(G.harm_paths(cfg2, "observed"), [], i)
            self.assertEqual(G.min_checkpoints(cfg2, []).primary, ())
            self.assertEqual(G.apply_checkpoints(cfg2, cp.primary), cfg2, "もう一度当てても同じ")
            self.assertEqual(G.apply_checkpoints(cfg2, []), cfg2)
            for alt in cp.alternatives:
                self.assertEqual(G.harm_paths(G.apply_checkpoints(cfg, alt), "observed"), [], (i, alt))

    def test_deterministic(self):
        for i, cfg in configs(301, 60):
            a = G.analyze(cfg)
            b = G.analyze(cfg)
            self.assertEqual((a.paths, a.checkpoints, a.reasons, a.declared_only, a.assumed, a.mismatches),
                             (b.paths, b.checkpoints, b.reasons, b.declared_only, b.assumed, b.mismatches), i)

    def test_apply_never_loosens(self):
        for i, cfg in configs(302, 60):
            out = G.apply_checkpoints(cfg, [t.id for t in cfg.tools])
            self.assertTrue(all(t.mode == "ask" for t in out.tools))
            self.assertEqual(G.apply_checkpoints(out, []), out)
            # ask → allow には戻らない（API に緩める操作が無い）
            self.assertFalse(any(t.mode == "allow" for t in G.apply_checkpoints(out, ["anything"]).tools))


class OrderInvariant(unittest.TestCase):
    def _shuffled(self, cfg: M.Config, rng: random.Random) -> M.Config:
        tools = list(cfg.tools)
        rng.shuffle(tools)
        stores = list(cfg.stores)
        rng.shuffle(stores)
        return M.Config(cfg.name, cfg.untrusted_in_context, tuple(tools), tuple(stores), cfg.imports)

    def test_paths_and_cut_size_invariant(self):
        rng = random.Random(400)
        for i, cfg in configs(401):
            cfg2 = self._shuffled(cfg, rng)
            for layer in ("declared", "observed"):
                self.assertEqual(path_set(G.harm_paths(cfg, layer)), path_set(G.harm_paths(cfg2, layer)), (i, layer))
                self.assertEqual(path_set(G.harm_paths_policy(cfg, layer, "monotone")),
                                 path_set(G.harm_paths_policy(cfg2, layer, "monotone")), (i, layer))
            p1 = G.harm_paths(cfg, "observed")
            p2 = G.harm_paths(cfg2, "observed")
            c1 = G.min_checkpoints(cfg, p1)
            c2 = G.min_checkpoints(cfg2, p2)
            freq = {t.id: t.frequency for t in cfg.tools}
            self.assertEqual(c1.size, c2.size, i)
            self.assertEqual(sum(freq[x] for x in c1.primary), sum(freq[x] for x in c2.primary), i)
            # 案の集合（並びを除く）も同じ：列挙が完了する大きさなので
            s1 = {frozenset(c) for c in (c1.primary,) + c1.alternatives}
            s2 = {frozenset(c) for c in (c2.primary,) + c2.alternatives}
            self.assertEqual(s1, s2, i)

    def test_path_order_is_tool_order(self):
        """道の順序は allow の道具の並び（v1 と同じ約束）。並びを変えれば道の順序も変わるが集合は同じ。"""
        rng = random.Random(402)
        for i, cfg in configs(403, 60):
            cfg2 = self._shuffled(cfg, rng)
            order = {t.id: k for k, t in enumerate(cfg2.allowed())}
            paths = G.harm_paths(cfg2, "observed")
            singles = [order[p.tools[0]] for p in paths if p.kind != "exfil"]
            self.assertEqual(singles, sorted(singles), i)
            pairs = [(order[p.tools[0]], order[p.tools[1]]) for p in paths if p.kind == "exfil"]
            self.assertEqual(pairs, sorted(pairs), i)


if __name__ == "__main__":
    unittest.main()
