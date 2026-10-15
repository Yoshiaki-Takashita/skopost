"""model の型の不変条件（担当 A）。型は全担当の契約なので、破れたら生成時に ValueError になること。"""
from __future__ import annotations

import dataclasses
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401

from skopost import model as M  # noqa: E402
from skopost.model import (AnalysisResult, Assumed, Baseline, BaselineDiff, Cap, Checkpoints, Config,  # noqa: E402
                           DeclaredOnly, EffCap, EffectiveCaps, Fact, FrozenMap, HarmPath, ImportRecord, IngestNote,
                           IngestResult, Mismatch, Origin, Store, Summary, Tool)


def eff_caps(**over):
    base = {"reads_untrusted": EffCap(False, "確"), "args_leave": EffCap(False, "確"), "exec": EffCap(False, "確"),
            "net": EffCap(False, "確"), "secret": EffCap(False, "確"), "acts": EffCap(frozenset(), "確")}
    base.update(over)
    return base


class FrozenMapTest(unittest.TestCase):
    def test_immutable_hashable_equal(self):
        a = FrozenMap({"x": 1, "y": 2})
        b = FrozenMap({"y": 2, "x": 1})
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(a, {"x": 1, "y": 2})
        self.assertEqual(list(a), ["x", "y"])
        with self.assertRaises(TypeError):
            a["z"] = 3  # type: ignore[index]
        with self.assertRaises(AttributeError):
            a._d = {}  # type: ignore[attr-defined]
        self.assertEqual(a.to_dict(), {"x": 1, "y": 2})
        self.assertNotEqual(a, 3)

    def test_source_dict_copied(self):
        src = {"x": 1}
        a = FrozenMap(src)
        src["x"] = 2
        self.assertEqual(a["x"], 1)


class CapTest(unittest.TestCase):
    def test_declared_and_observed(self):
        self.assertTrue(Cap(True, None).is_declared)
        self.assertTrue(Cap(None, "不明").unknown)
        with self.assertRaises(ValueError):
            Cap(None, None)                    # 宣言は値が要る
        with self.assertRaises(ValueError):
            Cap(True, "不明")                  # 不明なら値は None
        with self.assertRaises(ValueError):
            Cap(None, "確")
        with self.assertRaises(ValueError):
            Cap(True, "maybe")                 # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Cap(["a"], "確")                   # list は不可（frozenset）

    def test_rules_and_ingest_never_sure(self):
        for src in ("infer:R-X", "ingest:mcp"):
            with self.assertRaises(ValueError):
                Cap(True, "確", source=src)
            Cap(True, "論", source=src)
        Cap(True, "確", source="manual")
        with self.assertRaises(ValueError):
            Cap(True, "論", source="llm")

    def test_frozen(self):
        c = Cap(True, "確")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            c.value = False  # type: ignore[misc]


class ToolStoreConfigTest(unittest.TestCase):
    def test_tool_validation(self):
        Tool("a")
        for bad in (dict(id="a b"), dict(id="a", mode="deny"), dict(id="a", frequency=0), dict(id="a", frequency=True),
                    dict(id="a", declared={"exec": Cap(True, "確")}),            # 宣言に確度
                    dict(id="a", observed={"exec": Cap(True, None)}),           # 観察に確度なし
                    dict(id="a", observed={"exec": Cap(frozenset(), "確")}),    # 型違い
                    dict(id="a", observed={"acts": Cap(frozenset({"launch"}), "確")}),
                    dict(id="a", declared={"bogus": Cap(True, None)})):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Tool(**bad)  # type: ignore[arg-type]

    def test_tool_mapping_coerced_to_frozenmap(self):
        t = Tool("a", declared={"exec": Cap(True, None)})
        self.assertIsInstance(t.declared, FrozenMap)
        hash(t)

    def test_config_validation(self):
        s = Store("env", secret=True)
        t = Tool("a", observed={"reads_stores": Cap(frozenset({"env"}), "確")})
        cfg = Config(tools=[t], stores=[s])   # list も tuple に直る
        self.assertIsInstance(cfg.tools, tuple)
        self.assertEqual(cfg.tool("a"), t)
        self.assertEqual(cfg.allowed(), (t,))
        self.assertEqual(cfg.store_map()["env"], s)
        with self.assertRaises(KeyError):
            cfg.tool("zz")
        with self.assertRaises(ValueError):
            Config(tools=(t,))                # 置き場が無い
        with self.assertRaises(ValueError):
            Config(tools=(Tool("a"), Tool("a")))
        with self.assertRaises(ValueError):
            Config(stores=(Store("s"), Store("s")))
        hash(cfg)

    def test_origin_import(self):
        Origin("f", "/a/b", 1)
        for bad in (dict(file=""), dict(file="f", pointer="a"), dict(file="f", line=0), dict(file="f", line=True)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Origin(**bad)  # type: ignore[arg-type]
        ImportRecord("f", "0" * 64)
        with self.assertRaises(ValueError):
            ImportRecord("f", "0" * 63)
        with self.assertRaises(ValueError):
            ImportRecord("f", "0" * 64, adapter="Bad")


class IngestTypesTest(unittest.TestCase):
    def test_fact_values_must_be_frozen_json(self):
        Fact("t", "openapi.method", "GET")
        Fact("t", "k", ("a", 1, None, (True,)))
        for bad in ([1], {"a": 1}, object()):
            with self.assertRaises(ValueError):
                Fact("t", "k", bad)

    def test_ingest_result(self):
        r = IngestResult(Config(tools=(Tool("a"),)), notes=[IngestNote("dropped", "/x", "捨てた")], dropped=["/x"])
        self.assertIsInstance(r.notes, tuple)
        with self.assertRaises(ValueError):
            IngestNote("other", "/x", "")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            IngestResult(Config(), dropped=("no-slash",))


class EffectiveTest(unittest.TestCase):
    def test_effective_caps_shape(self):
        e = EffectiveCaps("a", "observed", eff_caps(exec=EffCap(True, "不明", "exec")), frozenset({"exec"}))
        self.assertTrue(e["exec"].value)
        with self.assertRaises(ValueError):
            EffectiveCaps("a", "observed", {k: v for k, v in eff_caps().items() if k != "net"})
        with self.assertRaises(ValueError):
            EffectiveCaps("a", "declared", eff_caps(), frozenset({"exec"}))   # declared は仮定しない
        with self.assertRaises(ValueError):
            EffectiveCaps("a", "observed", eff_caps(acts=EffCap(False, "確")))
        EffectiveCaps("a", "declared", eff_caps(exec=EffCap(False, "宣言")))


class PathsAndCheckpoints(unittest.TestCase):
    def test_harm_path_shapes(self):
        self.assertEqual(HarmPath("exfil", ["r", "s"], ["a", "b"], "論").key, "r>s")
        HarmPath("exfil", ("r", "r"), ("a", "b"), "確")         # 同じ道具でもよい（SPEC §7）
        for bad in (("exec", ("a", "b"), ("x",)), ("exfil", ("a",), ("x",)), ("exec", ("a",), ()),
                    ("loop", ("a",), ("x",))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                HarmPath(bad[0], bad[1], bad[2], "確")  # type: ignore[arg-type]

    def test_checkpoints_invariants(self):
        cp = Checkpoints(True, ("a", "b"), (("a", "c"),), "exhaustive", 2)
        self.assertEqual(cp.size, 2)
        p = (HarmPath("exec", ("a",), ("exec",), "確"), HarmPath("exfil", ("b", "c"), ("x", "y"), "確"))
        self.assertTrue(cp.cuts(p))
        self.assertFalse(cp.cuts(p, ("c",)))
        for bad in (dict(exact=True, primary=("a",), lower_bound=0),
                    dict(exact=False, primary=("a",), lower_bound=2),
                    dict(exact=False, primary=("a", "a")),
                    dict(exact=False, primary=("a",), alternatives=(("b", "c"),)),
                    dict(exact=False, primary=("a",), alternatives=(("a",),)),
                    dict(exact=False, primary=("a",), method="magic")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Checkpoints(**bad)  # type: ignore[arg-type]

    def test_result_invariants(self):
        p = HarmPath("exec", ("a",), ("exec",), "確")
        cp = Checkpoints(True, ("a",), lower_bound=1)
        s = Summary(1, 1, 1, 0, 1, 0, 0, 0.0)
        r = AnalysisResult("n", s, (p,), (), (), cp, {"a": ["exec: a"]}, DeclaredOnly((), ("a",)), ("x",))
        self.assertEqual(r.exit_code, 2)
        self.assertFalse(r.declared_only.holds)
        self.assertEqual(r.declared_only.surviving_paths, 1)
        with self.assertRaises(ValueError):
            AnalysisResult("n", s, (), (), (), cp, {}, DeclaredOnly((), ()), ("x",))      # 本数が違う
        with self.assertRaises(ValueError):
            AnalysisResult("n", s, (p,), (), (), cp, {}, DeclaredOnly((), ()), ())         # not_checked 空
        with self.assertRaises(ValueError):
            AnalysisResult("n", s, (p,), (), (), cp, {"zz": ()}, DeclaredOnly((), ()), ("x",))
        with self.assertRaises(ValueError):
            Summary(1, 2, 0, 0, 0, 0, 0, 0.0)

    def test_mismatch_and_assumed(self):
        Mismatch("a", "exec", False, True, "確", "", "under")
        with self.assertRaises(ValueError):
            Mismatch("a", "exec", True, True, "確", "", "under")
        with self.assertRaises(ValueError):
            Mismatch("a", "exec", False, True, "不明", "", "under")
        Assumed("a", "exec")
        with self.assertRaises(ValueError):
            Assumed("a", "net")   # 実効の名前ではなく元の項目名

    def test_baseline(self):
        b = Baseline([("exec", "a"), ("exfil", "r>s")])
        self.assertIsInstance(b.entries, frozenset)
        with self.assertRaises(ValueError):
            Baseline([("loop", "a")])
        self.assertTrue(BaselineDiff((("exec", "a"),), (), ()).regressed)
        self.assertFalse(BaselineDiff((), (("exec", "a"),), ()).regressed)

    def test_weakest(self):
        self.assertEqual(M.weakest("確", "推", "論"), "推")
        self.assertEqual(M.weakest(), "不明")


if __name__ == "__main__":
    unittest.main()
