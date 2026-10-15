"""report の契約試験（担当 A 所有・担当 E の受け入れ条件）。R1・R3 と SARIF の最小の形。

SARIF の公式スキーマでの検証（R2）は段 2 で担当 E が公式スキーマを入手できた場合に足す（現時点は手元に無い＝不明）。
"""
from __future__ import annotations

import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import SEEDS, call_or_skip, example_raws, gen_raw_config  # noqa: E402

from skopost import model as M  # noqa: E402
from skopost import report as R  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402


def cases():
    raws = list(example_raws().items()) + [(f"seed{s}", gen_raw_config(random.Random(s))) for s in SEEDS]
    for name, raw in raws:
        legacy = M.validate(raw)
        res = V1.analyze(legacy)
        yield name, legacy, res, M.result_from_legacy(res), M.from_legacy(legacy)


class Render(unittest.TestCase):
    impl = R
    formats: tuple[str, ...] = R.FORMATS

    def test_md_byte_identical_to_v1(self):
        for name, legacy, res, tres, cfg in cases():
            for explain in (False, True):
                got = call_or_skip(self, self.impl.render, tres, cfg, "md", explain=explain)
                self.assertEqual(got, V1.report_md(res, legacy, explain), (name, explain))

    def test_json_same_as_cli(self):
        for name, _, res, tres, cfg in cases():
            self.assertEqual(call_or_skip(self, self.impl.to_json, tres), M.result_to_dict(tres), name)
            got = call_or_skip(self, self.impl.render, tres, cfg, "json")
            self.assertEqual(got, json.dumps(res, ensure_ascii=False, indent=2) + "\n", name)

    def test_not_checked_in_every_format(self):
        for name, _, _, tres, cfg in cases():
            for fmt in self.formats:
                out = call_or_skip(self, self.impl.render, tres, cfg, fmt)
                self.assertIsInstance(out, str)
                text = json.loads(out) if fmt in ("json", "sarif") else out
                blob = json.dumps(text, ensure_ascii=False) if fmt in ("json", "sarif") else text
                for line in tres.not_checked:
                    self.assertIn(line, blob, (name, fmt))

    def test_unknown_format_rejected(self):
        name, _, _, tres, cfg = next(iter(cases()))
        try:
            self.impl.render(tres, cfg, "xml")  # type: ignore[arg-type]
        except M.NotImplementedYet as e:
            self.skipTest(f"未実装：{e.what}")
        except ValueError:
            return
        self.fail("未知の形式は ValueError")

    def test_render_does_not_mutate(self):
        for name, _, _, tres, cfg in cases():
            before = M.result_to_dict(tres)
            for fmt in self.formats:
                call_or_skip(self, self.impl.render, tres, cfg, fmt)
            self.assertEqual(M.result_to_dict(tres), before)


class Sarif(unittest.TestCase):
    impl = R

    def test_minimal_shape(self):
        for name, _, _, tres, cfg in cases():
            s = call_or_skip(self, self.impl.to_sarif, tres, cfg, artifact_uri="skopost.json")
            json.dumps(s, ensure_ascii=False)
            self.assertEqual(s["version"], "2.1.0")
            self.assertIn("$schema", s)
            self.assertEqual(len(s["runs"]), 1)
            run = s["runs"][0]
            self.assertEqual(run["tool"]["driver"]["name"], "Skopost")
            results = run["results"]
            path_results = [r for r in results if r["ruleId"] in ("SKP-EXEC", "SKP-ACT", "SKP-EXFIL")]
            self.assertEqual(len(path_results), len(tres.paths), name)
            for r in results:
                self.assertIn(r["ruleId"], set(R.RULE_IDS.values()))
                self.assertIn(r["level"], ("error", "warning", "note"))
                self.assertTrue(r["message"]["text"])
            want_level = {"確": "error", "論": "error", "推": "warning"}
            for p, r in zip(tres.paths, path_results):
                self.assertEqual(r["ruleId"], R.RULE_IDS[p.kind])
                if p.confidence in want_level:
                    self.assertEqual(r["level"], want_level[p.confidence], (name, p))


if __name__ == "__main__":
    unittest.main()
