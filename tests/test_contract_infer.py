"""infer の契約試験（担当 A 所有・担当 C の受け入れ条件）。

空実装のあいだは「未実装」として飛ばす（helpers.call_or_skip）。実装が入った時点で自動的に効く。
参照実装は compat.v1（凍結）。F3：現行 effective と全合成例で一致。
"""
from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import SEEDS, call_or_skip, example_raws, gen_raw_config  # noqa: E402

from skopost import infer as I  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402
from skopost.model import Assumed, Cap, EffCap, EffectiveCaps, Fact, Mismatch  # noqa: E402

EFF = ("reads_untrusted", "args_leave", "exec", "net", "secret", "acts")


def corpus():
    for name, raw in example_raws().items():
        yield name, raw
    for s in SEEDS:
        yield f"seed{s}", gen_raw_config(random.Random(s))


def v1_effective_typed(tool_id: str, legacy_tool: dict, legacy_stores: dict, layer: str) -> EffectiveCaps:
    e = V1.effective(legacy_tool, legacy_stores, layer)
    caps = {k: EffCap(frozenset(e[k]["v"]) if k == "acts" else bool(e[k]["v"]), e[k]["c"], e[k]["why"]) for k in EFF}
    return EffectiveCaps(tool_id, layer, caps, frozenset(e["_assumed"]))  # type: ignore[arg-type]


class EffectiveMatchesV1(unittest.TestCase):
    impl = I   # 自己検査（test_contract_selfcheck）は参照実装に差し替える

    def test_effective(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            cfg = M.from_legacy(legacy)
            stores = cfg.store_map()
            for lt, t in zip(legacy["tools"], cfg.tools):
                for layer in ("declared", "observed"):
                    got = call_or_skip(self, self.impl.effective, t, stores, layer)
                    self.assertIsInstance(got, EffectiveCaps)
                    self.assertEqual(got, v1_effective_typed(t.id, lt, legacy["stores"], layer), (name, t.id, layer))

    def test_mismatches(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            want = [Mismatch(m["tool"], m["cap"], frozenset(m["declared"]) if isinstance(m["declared"], list) else m["declared"],
                             frozenset(m["observed"]) if isinstance(m["observed"], list) else m["observed"],
                             m["confidence"], m["evidence"], m["severity"]) for m in V1.mismatches(legacy)]
            self.assertEqual(call_or_skip(self, self.impl.mismatches, M.from_legacy(legacy)), want, name)

    def test_assumed_unknown(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            want = [Assumed(a["tool"], a["cap"]) for a in V1.analyze(legacy)["assumed"]]
            self.assertEqual(call_or_skip(self, self.impl.assumed_unknown, M.from_legacy(legacy)), want, name)

    def test_unknown_is_dangerous_side(self):
        """不明は危ない側：observed 層で札が 1 つも無い道具は、全項目が真・全操作。"""
        cfg = M.parse({"skopost": 1, "tools": [{"id": "x"}]})
        e = call_or_skip(self, self.impl.effective, cfg.tools[0], cfg.store_map(), "observed")
        for k in ("reads_untrusted", "args_leave", "exec", "net", "secret"):
            self.assertTrue(e[k].value, k)
        self.assertEqual(e["acts"].value, frozenset(M.ACT_KINDS))
        self.assertEqual(e.assumed, frozenset({"reads_untrusted", "args_leave", "exec", "net_out", "reads_secret", "acts"}))


class Combine(unittest.TestCase):
    impl = I   # 自己検査（test_contract_selfcheck）は参照実装に差し替える

    def test_manual_beats_rule(self):
        manual = Cap(False, "推", "人が読んだ", "manual")
        rule = Cap(True, "論", "", "infer:R-X")
        self.assertEqual(call_or_skip(self, self.impl.combine, manual, rule).value, False)
        self.assertEqual(call_or_skip(self, self.impl.combine, rule, manual).value, False)

    def test_same_source_dangerous_side_and_weaker_confidence(self):
        a, b = Cap(True, "推", "", "infer:R-A"), Cap(False, "論", "", "infer:R-B")
        for x, y in ((a, b), (b, a)):
            c = call_or_skip(self, self.impl.combine, x, y)
            self.assertIs(c.value, True)
            self.assertEqual(c.confidence, "推")
        s1, s2 = Cap(frozenset({"send"}), "論"), Cap(frozenset({"pay"}), "確")
        c = call_or_skip(self, self.impl.combine, s1, s2)
        self.assertEqual(c.value, frozenset({"send", "pay"}))
        self.assertEqual(c.confidence, "論")

    def test_commutative_on_value_and_confidence(self):
        rng = random.Random(7)
        srcs = ("manual", "infer:R-A", "ingest:mcp")
        for _ in range(200):
            def one():
                src = rng.choice(srcs)
                conf = rng.choice(["論", "推", "不明"] + (["確"] if src == "manual" else []))
                return Cap(None if conf == "不明" else rng.random() < 0.5, conf, "", src)
            a, b = one(), one()
            x, y = call_or_skip(self, self.impl.combine, a, b), call_or_skip(self, self.impl.combine, b, a)
            self.assertEqual((x.value, x.confidence), (y.value, y.confidence), (a, b))


class InferCaps(unittest.TestCase):
    impl = I   # 自己検査（test_contract_selfcheck）は参照実装に差し替える

    def _rule(self, conf="推", max_conf="推"):
        return I.Rule("R-TEST", applies=lambda f: f.key == "k",
                      infer=lambda f: {"exec": Cap(True, conf, "テスト", "infer:R-TEST")}, max_confidence=max_conf)

    def test_rule_type(self):
        with self.assertRaises(ValueError):
            I.Rule("bad id", applies=lambda f: True, infer=lambda f: {})
        with self.assertRaises(ValueError):
            I.Rule("R-X", applies=lambda f: True, infer=lambda f: {}, max_confidence="確")
        self.assertEqual(I.DEFAULT_RULES, I.DEFAULT_RULES)  # tuple（段 2 で C が埋める）
        for r in I.DEFAULT_RULES:
            self.assertIsInstance(r, I.Rule)

    def test_applies_and_source(self):
        out = call_or_skip(self, self.impl.infer_caps, [Fact("t", "k", 1), Fact("u", "other", 1)], [self._rule()])
        self.assertEqual(set(out), {"t"})
        self.assertEqual(out["t"]["exec"].source, "infer:R-TEST")
        self.assertEqual(out["t"]["exec"].value, True)

    def test_clamped_to_max_confidence(self):
        out = call_or_skip(self, self.impl.infer_caps, [Fact("t", "k", 1)], [self._rule(conf="論", max_conf="推")])
        self.assertEqual(out["t"]["exec"].confidence, "推")

    def test_no_facts_no_caps(self):
        self.assertEqual(call_or_skip(self, self.impl.infer_caps, [], [self._rule()]), {})

    def test_default_rules_never_sure(self):
        facts = [Fact("t", k, v) for k, v in (("openapi.method", "GET"), ("mcp.annotation.readOnlyHint", True),
                                                 ("claude.permission", "allow"))]
        out = call_or_skip(self, self.impl.infer_caps, facts)
        for caps in out.values():
            for c in caps.values():
                self.assertNotEqual(c.confidence, "確")
                self.assertTrue(c.source.startswith("infer:"))


if __name__ == "__main__":
    unittest.main()
