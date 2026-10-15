"""ci の詳細試験（担当 E）。基準線の読み書きの誤り処理・雛形の中身。"""
from __future__ import annotations

import os
import random
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import PKG, gen_raw_config  # noqa: E402

from skopost import ci as C  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402

TDIR = os.path.join(PKG, "ci", "templates")


class BaselineIO(unittest.TestCase):
    def test_write_is_deterministic_and_sorted(self):
        for s in range(40):
            res = M.result_from_legacy(V1.analyze(M.validate(gen_raw_config(random.Random(s)))))
            a = C.write_baseline(res)
            self.assertEqual(a, C.write_baseline(res))
            self.assertEqual(C.parse_baseline(a), C.baseline_from_result(res))

    def test_bad_inputs_raise_skopost_error(self):
        bad = ["", "[]", "{}", '{"skopost_baseline": 2, "paths": []}', '{"skopost_baseline": true, "paths": []}',
               '{"skopost_baseline": 1}', '{"skopost_baseline": 1, "paths": [["evil", "a"]]}',
               '{"skopost_baseline": 1, "paths": [["exec"]]}', '{"skopost_baseline": 1, "paths": [["exec", ""]]}']
        for b in bad:
            with self.assertRaises(M.SkopostError, msg=b):
                C.parse_baseline(b)

    def test_load_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(M.SkopostError):
                C.load_baseline(os.path.join(d, "missing.json"))
            p = os.path.join(d, "b.json")
            with open(p, "wb") as f:
                f.write(b"\xff\xfe\x00")
            with self.assertRaises(M.SkopostError):
                C.load_baseline(p)

    def test_empty_baseline_regresses_on_any_path(self):
        for s in range(40):
            res = M.result_from_legacy(V1.analyze(M.validate(gen_raw_config(random.Random(s)))))
            self.assertEqual(C.diff(M.Baseline(frozenset()), res).regressed, bool(res.paths))
            self.assertFalse(C.diff(C.baseline_from_result(res), res).regressed)


class TemplateContent(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(TDIR, name), encoding="utf-8") as f:
            return f.read()

    def test_action_shape(self):
        t = self.read("action.yml")
        self.assertIn("using: composite", t)
        self.assertIn("github/codeql-action/upload-sarif@", t)
        self.assertIn("--format sarif", t)
        self.assertNotRegex(t, r"uses:\s*\S+@(v\d|main|master)\b")
        # 入力を run: に直接埋め込まない（式の注入を避け env 経由にする）
        for block in re.findall(r"run: \|\n((?:        .*\n)+)", t):
            self.assertNotIn("${{", block)

    def test_precommit_shape(self):
        t = self.read(".pre-commit-hooks.yaml")
        self.assertIn("id: skopost", t)
        self.assertIn("entry: python3 -m skopost check", t)
        self.assertIn("language: system", t)


if __name__ == "__main__":
    unittest.main()
