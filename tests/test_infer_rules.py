"""infer の独自試験・性質試験（担当 C 所有）。標準ライブラリのみ。"""
from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import SEEDS, gen_raw_config  # noqa: E402

from skopost import infer as I  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402
from skopost.infer.rules import tokens  # noqa: E402
from skopost.model import Cap, Fact  # noqa: E402
from skopost.model.constants import ALL_CAPS, BOOL_CAPS  # noqa: E402

SAFE_VALUES = (False, frozenset())


def _all_facts(rng: random.Random, n: int = 400):
    words = ["run", "bash", "Shell", "fetch", "url", "sendEmail", "delete_file", "readOnly", "skill", "list", "get",
             "pay", "token", "slack", "deploy", "share", "削除します", "送信", "ウェブ", "note", "x"]
    keys = ["name", "description", "schema.properties", "openapi.method", "openapi.server_external",
            "mcp.annotation.destructiveHint", "mcp.annotation.openWorldHint", "mcp.annotation.readOnlyHint",
            "claude.tool", "claude.permission", "unknown.key"]
    for i in range(n):
        k = rng.choice(keys)
        if k == "schema.properties":
            v = tuple(rng.sample(["command", "url", "to", "amount", "path", "q", "apiKey", "limit"], rng.randint(0, 3)))
        elif k.startswith(("mcp.", "openapi.server")):
            v = rng.choice([True, False, None, "true"])
        elif k == "openapi.method":
            v = rng.choice(["GET", "post", "DELETE", "", 3])
        elif k == "claude.tool":
            v = rng.choice(["Bash", "Bash(npm test:*)", "WebFetch", "Read", "Edit"])
        else:
            v = " ".join(rng.sample(words, rng.randint(1, 4))) if rng.random() < 0.9 else rng.choice([None, 1, ()])
        yield Fact(f"t{i % 7}", k, v)


class DefaultRules(unittest.TestCase):
    def test_never_sure_never_safe(self):
        """F2：既定の規則は「確」を作らない。さらに安全側の値（false・空）も作らない（安全は人の観察だけ）。"""
        rng = random.Random(1)
        out = I.infer_caps(list(_all_facts(rng)), I.DEFAULT_RULES)
        self.assertTrue(out)
        for caps in out.values():
            for name, c in caps.items():
                self.assertIn(name, ALL_CAPS)
                self.assertNotEqual(c.confidence, "確")
                self.assertTrue(c.source.startswith("infer:R-"))
                self.assertNotIn(c.value, SAFE_VALUES, (name, c))

    def test_rule_ids_unique_and_capped(self):
        ids = [r.id for r in I.DEFAULT_RULES]
        self.assertEqual(len(ids), len(set(ids)))
        for r in I.DEFAULT_RULES:
            self.assertIn(r.max_confidence, ("論", "推"))

    def test_read_only_hint_infers_nothing(self):
        """作者の主張（readOnlyHint）からは安全側を推定しない。不明のまま＝危ない側。"""
        self.assertEqual(I.infer_caps([Fact("t", "mcp.annotation.readOnlyHint", True)], I.DEFAULT_RULES), {})

    def test_examples(self):
        out = I.infer_caps([Fact("a", "name", "run_shell_command"), Fact("b", "name", "sendEmail"),
                            Fact("c", "name", "skill_list"), Fact("d", "claude.tool", "Bash(npm test:*)"),
                            Fact("e", "openapi.method", "GET"), Fact("f", "schema.properties", ("url", "limit"))], I.DEFAULT_RULES)
        self.assertEqual(out["a"]["exec"].value, True)
        self.assertEqual(out["a"]["exec"].confidence, "推")
        self.assertEqual(out["b"]["acts"].value, frozenset({"send"}))
        self.assertNotIn("c", out)                       # skill ≠ kill・list は何も言わない
        self.assertEqual(out["d"]["exec"].confidence, "論")
        self.assertEqual(out["e"]["args_leave"].confidence, "論")
        self.assertEqual(out["e"]["reads_untrusted"].confidence, "推")
        self.assertNotIn("acts", out["e"])               # GET でも安全とは言わない（何も足さないだけ）
        self.assertEqual(out["f"]["net_out"].value, True)

    def test_description_japanese(self):
        out = I.infer_caps([Fact("t", "description", "ファイルを削除し、結果をメールで送信します")], I.DEFAULT_RULES)
        self.assertEqual(out["t"]["acts"].value, frozenset({"delete", "send"}))
        self.assertEqual(out["t"]["acts"].confidence, "推")

    def test_default_argument_is_default_rules(self):
        f = [Fact("t", "name", "bash")]
        self.assertEqual(I.infer_caps(f), I.infer_caps(f, I.DEFAULT_RULES))
        self.assertTrue(I.infer_caps(f)["t"]["exec"].value)
        self.assertEqual(I.infer_caps(f, ()), {})

    def test_tokens(self):
        self.assertEqual(tokens("runShell_command-v2.x"), ("run", "shell", "command", "v2", "x"))


class InferCapsMechanics(unittest.TestCase):
    def test_clamp_to_unknown_drops_value(self):
        r = I.Rule("R-U", lambda f: True, lambda f: {"exec": Cap(True, "推", "", "infer:R-U")}, "不明")
        c = I.infer_caps([Fact("t", "k", 1)], [r])["t"]["exec"]
        self.assertEqual((c.value, c.confidence), (None, "不明"))

    def test_source_rewritten(self):
        r = I.Rule("R-S", lambda f: True, lambda f: {"exec": Cap(True, "論", "", "manual")}, "論")
        self.assertEqual(I.infer_caps([Fact("t", "k", 1)], [r])["t"]["exec"].source, "infer:R-S")

    def test_unknown_cap_name_raises(self):
        r = I.Rule("R-B", lambda f: True, lambda f: {"nope": Cap(True, "推", "", "infer:R-B")})
        with self.assertRaises(ValueError):
            I.infer_caps([Fact("t", "k", 1)], [r])

    def test_two_rules_dangerous_side(self):
        r1 = I.Rule("R-A", lambda f: True, lambda f: {"acts": Cap(frozenset({"send"}), "論", "", "infer:R-A")}, "論")
        r2 = I.Rule("R-B", lambda f: True, lambda f: {"acts": Cap(frozenset({"pay"}), "推", "", "infer:R-B")}, "推")
        c = I.infer_caps([Fact("t", "k", 1)], [r1, r2])["t"]["acts"]
        self.assertEqual(c.value, frozenset({"send", "pay"}))
        self.assertEqual(c.confidence, "推")


class CombineProps(unittest.TestCase):
    def test_unknown_same_rank_stays_unknown(self):
        c = I.combine(Cap(None, "不明", "", "infer:R-A"), Cap(False, "論", "", "infer:R-B"))
        self.assertEqual((c.value, c.confidence), (None, "不明"))

    def test_ingest_beats_infer_manual_beats_ingest(self):
        a, b, m = Cap(True, "推", "", "infer:R-A"), Cap(False, "推", "", "ingest:mcp"), Cap(True, "論", "", "manual")
        self.assertIs(I.combine(a, b).value, False)
        self.assertIs(I.combine(b, m).value, True)

    def test_associative_and_never_sure_from_rules(self):
        rng = random.Random(3)
        for _ in range(300):
            cs = []
            for _ in range(3):
                conf = rng.choice(["論", "推", "不明"])
                cs.append(Cap(None if conf == "不明" else rng.random() < .5, conf, "", rng.choice(["infer:R-A", "infer:R-B"])))
            x = I.combine(I.combine(cs[0], cs[1]), cs[2])
            y = I.combine(cs[0], I.combine(cs[1], cs[2]))
            self.assertEqual((x.value, x.confidence), (y.value, y.confidence))
            self.assertNotEqual(x.confidence, "確")

    def test_mixed_layers_rejected(self):
        with self.assertRaises(ValueError):
            I.combine(Cap(True, None), Cap(True, "論"))


def _danger(eff) -> tuple:
    return tuple(eff[k].value for k in ("reads_untrusted", "args_leave", "exec", "net", "secret")) + (eff["acts"].value,)


def _ge(a: tuple, b: tuple) -> bool:
    return all((x >= y) for x, y in zip(a, b))   # bool も frozenset も「以上」で比べられる


class Monotonicity(unittest.TestCase):
    """F1（置き場以外）：観察の札を不明にしても実効の札は危なくならない側へは動かない（減らない）。"""

    def test_unknown_never_reduces_effective(self):
        for s in SEEDS:
            rng = random.Random(1000 + s)
            cfg = M.from_legacy(M.validate(gen_raw_config(rng)))
            stores = cfg.store_map()
            for t in cfg.tools:
                base = _danger(I.effective(t, stores, "observed"))
                for cap in ALL_CAPS:
                    if cap in ("writes_stores", "reads_stores"):
                        continue  # v1 互換の例外（ARCHITECTURE 段 1 の結果・1）
                    obs = dict(t.observed)
                    obs[cap] = Cap(None, "不明")
                    t2 = M.Tool(t.id, t.label, t.mode, t.frequency, t.declared, obs)
                    self.assertTrue(_ge(_danger(I.effective(t2, stores, "observed")), base), (s, t.id, cap))

    def test_inferred_caps_only_add_danger(self):
        """規則の札は安全側を出さないので、不明の項目を規則の札で埋めても危険は真偽で減らない（acts は具体化で減りうる）。"""
        rng = random.Random(9)
        out = I.infer_caps(list(_all_facts(rng, 200)), I.DEFAULT_RULES)
        for caps in out.values():
            for name, c in caps.items():
                if name in BOOL_CAPS and c.value is not None:
                    self.assertIs(c.value, True)


class AgreesWithV1Wider(unittest.TestCase):
    def test_more_seeds_effective_and_mismatches(self):
        for s in range(200, 260):
            raw = gen_raw_config(random.Random(s), p_unknown=0.4)
            legacy = M.validate(raw)
            cfg = M.from_legacy(legacy)
            self.assertEqual(len(I.mismatches(cfg)), len(V1.mismatches(legacy)))
            self.assertEqual([(a.tool, a.cap) for a in I.assumed_unknown(cfg)],
                             [(a["tool"], a["cap"]) for a in V1.analyze(legacy)["assumed"]])

    def test_bad_layer(self):
        cfg = M.parse({"skopost": 1, "tools": [{"id": "x"}]})
        with self.assertRaises(ValueError):
            I.effective(cfg.tools[0], cfg.store_map(), "nope")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
