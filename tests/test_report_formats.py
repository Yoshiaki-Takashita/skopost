"""report の詳細試験（担当 E）。text・SARIF の仕様の必須項目・ゴールデン出力。

SARIF の公式スキーマ（sarif-schema-2.1.0.json）は手元に無いため、スキーマでの検証は未実施（不明）。
代わりに OASIS SARIF 2.1.0 の本文が「必須」とする項目を個別に確かめる（§3.13 sarifLog・§3.14 run・
§3.18 toolComponent・§3.27 result・§3.11 message・§3.30 region・§3.20 invocation）。
ゴールデンの更新：SKOPOST_UPDATE_GOLDEN=1 で書き直す（計算秒数は伏せる）。
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import example_raws, gen_raw_config, mask_seconds  # noqa: E402

from skopost import model as M  # noqa: E402
from skopost import report as R  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_report_golden")


def typed(raw):
    legacy = M.validate(raw)
    return M.result_from_legacy(V1.analyze(legacy)), M.from_legacy(legacy)


def all_cases(n=200):
    out = [(k,) + typed(v) for k, v in example_raws().items()]
    out += [(f"seed{s}",) + typed(gen_raw_config(random.Random(1000 + s))) for s in range(n)]
    return out


def mask(text: str) -> str:
    return re.sub(r'"(version|semanticVersion)": "[^"]+"', r'"\1": "X"', mask_seconds(text))


class Golden(unittest.TestCase):
    def test_golden_outputs(self):
        upd = os.environ.get("SKOPOST_UPDATE_GOLDEN") == "1"
        for name, raw in example_raws().items():
            res, cfg = typed(raw)
            base = name.replace(".json", "")
            for fmt, lang, ext in (("text", "ja", "ja.txt"), ("text", "en", "en.txt"), ("sarif", "ja", "sarif"),
                                   ("md", "ja", "md")):
                got = mask(R.render(res, cfg, fmt, lang=lang))
                p = os.path.join(GOLDEN, f"{base}.{ext}")
                if upd:
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(got)
                with open(p, encoding="utf-8") as f:
                    self.assertEqual(got, f.read(), p)

    def test_md_matches_v1_many(self):
        for name, raw in [(f"s{s}", gen_raw_config(random.Random(5000 + s), n_tools=random.Random(s).randint(1, 12)))
                          for s in range(300)]:
            legacy = M.validate(raw)
            res = V1.analyze(legacy)
            self.assertEqual(R.render(M.result_from_legacy(res), M.from_legacy(legacy), "md", explain=True),
                             V1.report_md(res, legacy, True), name)


class TextFormat(unittest.TestCase):
    def test_lines_and_langs(self):
        for name, res, cfg in all_cases(60):
            for lang in ("ja", "en"):
                out = R.render(res, cfg, "text", lang=lang)
                self.assertTrue(out.endswith("\n"))
                for p in res.paths:
                    self.assertIn(p.key, out)
                for t in res.checkpoints.primary:
                    self.assertIn(f"{t}", out)

    def test_bad_lang_and_md_en(self):
        _, res, cfg = all_cases(0)[0]
        with self.assertRaises(ValueError):
            R.render(res, cfg, "text", lang="fr")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            R.render(res, cfg, "md", lang="en")

    def test_control_chars_neutralised(self):
        raw = json.loads(json.dumps(example_raws()["example"]))
        raw["name"] = "evil\x1b[31m|`name"
        res, cfg = typed(raw)
        for fmt in ("text", "md"):
            out = R.render(res, cfg, fmt)
            self.assertNotIn("\x1b", out)


class SarifSpec(unittest.TestCase):
    """仕様の必須項目（スキーマ検証の代わり。スキーマ検証そのものは未実施＝不明）。"""

    def check(self, s, res):
        self.assertEqual(set(s) >= {"version", "runs"}, True)          # §3.13.2 version・runs は必須
        self.assertEqual(s["version"], "2.1.0")
        self.assertIsInstance(s["runs"], list)
        for run in s["runs"]:
            drv = run["tool"]["driver"]                                     # §3.14.6 tool は必須・§3.18.2 driver
            self.assertIsInstance(drv["name"], str)                         # §3.19.8 name は必須
            ids = [r["id"] for r in drv["rules"]]                           # reportingDescriptor.id は必須
            self.assertEqual(len(ids), len(set(ids)))
            for inv in run["invocations"]:
                self.assertIsInstance(inv["executionSuccessful"], bool)     # §3.20.14 必須
                for n in inv["toolExecutionNotifications"]:
                    self.assertTrue(n["message"]["text"])
            for r in run["results"]:
                self.assertTrue(r["message"]["text"])                       # §3.27.11 message は必須
                self.assertIn(r["level"], ("none", "note", "warning", "error"))
                self.assertEqual(ids[r["ruleIndex"]], r["ruleId"])           # ruleIndex と ruleId の整合
                for loc in r["locations"]:
                    pl = loc["physicalLocation"]
                    self.assertTrue(pl["artifactLocation"]["uri"])
                    self.assertGreaterEqual(pl["region"]["startLine"], 1)  # §3.30.5 1 始まり
            self.assertEqual(run["properties"]["notChecked"], list(res.not_checked))

    def test_spec_required_members(self):
        for name, res, cfg in all_cases(100):
            s = json.loads(R.render(res, cfg, "sarif"))
            self.check(s, res)

    def test_fingerprints_unique_and_stable(self):
        for name, res, cfg in all_cases(60):
            a = R.to_sarif(res, cfg, artifact_uri="x.json")
            fps = [json.dumps(r["partialFingerprints"], sort_keys=True) for r in a["runs"][0]["results"]]
            self.assertEqual(len(fps), len(set(fps)), name)
            self.assertEqual(a, R.to_sarif(res, cfg, artifact_uri="x.json"))

    def test_origin_used_for_location(self):
        res, cfg = typed(example_raws()["example"])
        if not res.paths:
            self.skipTest("例に道が無い")
        from dataclasses import replace
        tid = res.paths[0].tools[0]
        tools = tuple(replace(t, origin=M.Origin("src/mcp.json", "/tools/0", 7)) if t.id == tid else t for t in cfg.tools)
        s = R.to_sarif(res, replace(cfg, tools=tools), artifact_uri="skopost.json")
        loc = s["runs"][0]["results"][0]["locations"][0]
        self.assertEqual(loc["physicalLocation"]["artifactLocation"]["uri"], "src/mcp.json")
        self.assertEqual(loc["physicalLocation"]["region"]["startLine"], 7)
        self.assertEqual(loc["logicalLocations"][0]["fullyQualifiedName"], "/tools/0")

    def test_unknown_confidence_is_note(self):
        for name, res, cfg in all_cases(100):
            s = R.to_sarif(res, cfg, artifact_uri="x")
            for p, r in zip(res.paths, s["runs"][0]["results"]):
                if p.confidence == "不明":
                    self.assertEqual(r["level"], "note")


if __name__ == "__main__":
    unittest.main()
