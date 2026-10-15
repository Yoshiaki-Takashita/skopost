"""graph の詳細試験：危険経路の定義と「不明」の倒し方（担当 D）。

- 方針 v1 は compat.v1 と一致（契約試験でも見るが、ここでは実効の札そのものも比べる）
- 方針 monotone は**全項目**で単調（不明を足しても道は減らない）。置き場の札も含む（F1 の完全版）
- monotone の道は v1 の道の上位集合（過大警報の側にだけずれる）
- 段 1 で見つかった v1 の食い違い（置き場の札を不明にすると道が減る）が monotone では起きない
- infer（担当 C）が入ったら、v1 方針の実効の札・食い違い・仮定が infer と一致する（未実装なら飛ぶ）
"""
from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import SEEDS, call_or_skip, example_raws, gen_raw_config  # noqa: E402
from test_contract_graph import typed_paths  # noqa: E402

from skopost import graph as G  # noqa: E402
from skopost import infer as I  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402
from skopost.graph import analysis as GA  # noqa: E402
from skopost.graph import caps as GC  # noqa: E402
from skopost.graph.paths import path_set  # noqa: E402
from skopost.model import Cap, Config, Tool  # noqa: E402

N_PROP = int(os.environ.get("SKOPOST_GRAPH_PROP", "300"))


def corpus(n_tools=None):
    for name, raw in example_raws().items():
        yield name, raw
    for s in SEEDS:
        yield f"seed{s}", gen_raw_config(random.Random(s), n_tools=n_tools)


def with_unknown(cfg: Config, tid: str, cap: str) -> Config:
    t = cfg.tool(tid)
    obs = dict(t.observed)
    obs[cap] = Cap(None, "不明", "試験で不明にした")
    t2 = Tool(t.id, t.label, t.mode, t.frequency, t.declared, M.FrozenMap(obs), t.origin)
    return Config(cfg.name, cfg.untrusted_in_context, tuple(t2 if x.id == tid else x for x in cfg.tools),
                  cfg.stores, cfg.imports)


QUIRK_RAW = {"skopost": 1, "stores": [{"id": "ext", "external": True}], "tools": [
    {"id": "r", "observed": {c: {"value": c == "reads_secret", "confidence": "確"}
                             for c in ("reads_untrusted", "reads_secret", "net_out", "args_leave", "exec")}
     | {"acts": {"value": [], "confidence": "確"}, "writes_stores": {"value": [], "confidence": "確"},
        "reads_stores": {"value": [], "confidence": "確"}}},
    {"id": "w", "observed": {c: {"value": False, "confidence": "確"}
                             for c in ("reads_untrusted", "reads_secret", "net_out", "args_leave", "exec")}
     | {"acts": {"value": [], "confidence": "確"}, "writes_stores": {"value": ["ext"], "confidence": "確"},
        "reads_stores": {"value": [], "confidence": "確"}}}]}


class EffectiveV1(unittest.TestCase):
    def test_effective_matches_v1(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            cfg = M.from_legacy(legacy)
            stores = cfg.store_map()
            for lt, t in zip(legacy["tools"], cfg.tools):
                for layer in ("declared", "observed"):
                    e = V1.effective(lt, legacy["stores"], layer)
                    got = GC.effective(t, stores, layer, "v1")
                    for k in M.EFF_NAMES:
                        v = frozenset(e[k]["v"]) if k == "acts" else bool(e[k]["v"])
                        self.assertEqual((got[k].value, got[k].confidence, got[k].why), (v, e[k]["c"], e[k]["why"]), (name, t.id, layer, k))
                    self.assertEqual(got.assumed, frozenset(e["_assumed"]), (name, t.id, layer))

    def test_mismatches_and_assumed_match_v1(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            cfg = M.from_legacy(legacy)
            want = V1.analyze(legacy)
            self.assertEqual([(a.tool, a.cap) for a in GA.assumed_unknown(cfg)],
                             [(a["tool"], a["cap"]) for a in want["assumed"]], name)
            got = [(m.tool, m.cap, m.severity, m.confidence) for m in GA.mismatches(cfg)]
            self.assertEqual(got, [(m["tool"], m["cap"], m["severity"], m["confidence"]) for m in want["mismatches"]], name)

    def test_bad_policy_rejected(self):
        cfg = M.parse(example_raws()["example"])
        with self.assertRaises(ValueError):
            G.harm_paths_policy(cfg, "observed", "strict")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            G.harm_paths_policy(cfg, "both", "v1")  # type: ignore[arg-type]


class CrossCheckWithInfer(unittest.TestCase):
    """infer（担当 C）が入ったら、graph の自前の計算（方針 v1）と一致すること。未実装なら飛ぶ。"""

    def test_effective(self):
        for name, raw in corpus():
            cfg = M.parse(raw)
            stores = cfg.store_map()
            for t in cfg.tools:
                for layer in ("declared", "observed"):
                    got = call_or_skip(self, I.effective, t, stores, layer)
                    # graph の公開は infer に寄せたので、自前の計算（_effective_local）と照合する
                    self.assertEqual(got, GC._effective_local(t, stores, layer, "v1"), (name, t.id, layer))
                    self.assertEqual(got, GC.effective(t, stores, layer, "v1"), (name, t.id, layer))

    def test_mismatches_and_assumed(self):
        for name, raw in corpus():
            cfg = M.parse(raw)
            self.assertEqual(call_or_skip(self, I.mismatches, cfg), GA._mismatches_local(cfg), name)
            self.assertEqual(call_or_skip(self, I.assumed_unknown, cfg), GA._assumed_unknown_local(cfg, "v1"), name)


class MonotonePolicy(unittest.TestCase):
    def test_quirk_fixed(self):
        """段 1 の食い違い：v1 では置き場の札を不明にすると道が減る。monotone では減らない。"""
        before = M.parse(QUIRK_RAW)
        after = with_unknown(before, "w", "writes_stores")
        v1_b = path_set(G.harm_paths_policy(before, "observed", "v1"))
        v1_a = path_set(G.harm_paths_policy(after, "observed", "v1"))
        self.assertEqual(v1_b, {("exfil", "r>w")})
        self.assertEqual(v1_a, set(), "v1 の挙動（記録どおり道が消える）")
        self.assertEqual(typed_paths(V1.harm_paths(M.to_legacy(after), "observed")), [], "凍結の参照実装も同じ")
        mo_b = path_set(G.harm_paths_policy(before, "observed", "monotone"))
        mo_a = G.harm_paths_policy(after, "observed", "monotone")
        self.assertEqual(mo_b, {("exfil", "r>w")})
        self.assertEqual(path_set(mo_a), {("exfil", "r>w")})
        self.assertEqual(mo_a[0].confidence, "不明", "仮定で導いた道の確度は不明")
        self.assertIn("writes_stores(不明→全置き場)", mo_a[0].via[1])
        d = G.policy_diff(after)
        self.assertEqual([p.key for p in d["only_monotone"]], ["r>w"])
        self.assertEqual(d["only_v1"], [])

    def test_monotone_all_caps(self):
        """F1 の完全版：どの札（置き場の札も）を不明にしても、monotone の道は減らない。"""
        rng = random.Random(7)
        n = 0
        for name, raw in corpus():
            cfg = M.parse(raw)
            if not cfg.untrusted_in_context:
                continue
            before = path_set(G.harm_paths_policy(cfg, "observed", "monotone"))
            for _ in range(3):
                t = rng.choice(cfg.tools)
                if not t.observed:
                    continue
                cap = rng.choice(list(t.observed))
                after = path_set(G.harm_paths_policy(with_unknown(cfg, t.id, cap), "observed", "monotone"))
                self.assertLessEqual(before, after, (name, t.id, cap))
                n += 1
        self.assertGreater(n, 50)

    def test_monotone_random_many(self):
        """乱数の構成を N_PROP 件、観察の札を 1〜3 個ずつ不明にして単調性を確かめる。"""
        rng = random.Random(2026)
        for i in range(N_PROP):
            cfg = M.parse(gen_raw_config(rng, p_unknown=0.1))
            before = path_set(G.harm_paths_policy(cfg, "observed", "monotone"))
            cur = cfg
            for _ in range(rng.randint(1, 3)):
                t = rng.choice(cur.tools)
                if not t.observed:
                    continue
                cur = with_unknown(cur, t.id, rng.choice(list(t.observed)))
            after = path_set(G.harm_paths_policy(cur, "observed", "monotone"))
            self.assertLessEqual(before, after, i)

    def test_monotone_is_superset_of_v1(self):
        rng = random.Random(11)
        for i in range(N_PROP):
            cfg = M.parse(gen_raw_config(rng, p_unknown=0.3))
            v1 = G.harm_paths_policy(cfg, "observed", "v1")
            mo = G.harm_paths_policy(cfg, "observed", "monotone")
            self.assertLessEqual(path_set(v1), path_set(mo), i)
            self.assertEqual(G.policy_diff(cfg)["only_v1"], [], i)
            # declared 層は不明が無いので方針に依らず同じ
            self.assertEqual(G.harm_paths_policy(cfg, "declared", "v1"), G.harm_paths_policy(cfg, "declared", "monotone"), i)

    def test_monotone_assumed_lists_store_caps(self):
        cfg = with_unknown(M.parse(QUIRK_RAW), "w", "writes_stores")
        self.assertEqual([(a.tool, a.cap) for a in GA.assumed_unknown(cfg, "monotone")], [("w", "writes_stores")])
        self.assertEqual(GA.assumed_unknown(cfg, "v1"), [])

    def test_analyze_policy_monotone(self):
        cfg = with_unknown(M.parse(QUIRK_RAW), "w", "writes_stores")
        res = G.analyze_policy(cfg, "monotone")
        self.assertEqual(res.exit_code, 2)
        self.assertEqual(res.summary.paths, 1)
        self.assertEqual(res.summary.assumed_unknown, 1)
        self.assertTrue(any("方針 monotone" in x for x in res.not_checked))
        self.assertEqual(G.analyze(cfg).exit_code, 0, "既定（v1）は道なし")

    def test_difference_rate_recorded(self):
        """差の大きさの目安（docs/GRAPH.md の数字の出どころ）。失敗条件ではなく、0 件でないことだけ見る。"""
        rng = random.Random(5)
        differ = 0
        total = 500
        for _ in range(total):
            cfg = M.parse(gen_raw_config(rng))
            if G.policy_diff(cfg)["only_monotone"]:
                differ += 1
        self.assertGreater(differ, 0)


if __name__ == "__main__":
    unittest.main()
