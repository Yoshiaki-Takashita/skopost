"""ci の契約試験（担当 A 所有・担当 E の受け入れ条件）。C1・C2。"""
from __future__ import annotations

import os
import random
import re
import sys
import tempfile
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import PKG, SEEDS, call_or_skip, example_raws, gen_raw_config  # noqa: E402

from skopost import ci as C  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402


def results():
    raws = list(example_raws().values()) + [gen_raw_config(random.Random(s)) for s in SEEDS]
    return [M.result_from_legacy(V1.analyze(M.validate(r))) for r in raws]


def with_paths(res: M.AnalysisResult, paths) -> M.AnalysisResult:
    paths = tuple(paths)
    return replace(res, paths=paths, summary=replace(res.summary, paths=len(paths),
                                                     missed_by_declared=min(res.summary.missed_by_declared, len(paths))))


class Baselines(unittest.TestCase):
    impl = C

    def test_entries_are_kind_and_key(self):
        for res in results():
            b = call_or_skip(self, self.impl.baseline_from_result, res)
            self.assertEqual(b.entries, frozenset((p.kind, p.key) for p in res.paths))

    def test_roundtrip_through_text(self):
        for res in results():
            text = call_or_skip(self, self.impl.write_baseline, res)
            self.assertIsInstance(text, str)
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, "baseline.json")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
                self.assertEqual(call_or_skip(self, self.impl.load_baseline, p),
                                 call_or_skip(self, self.impl.baseline_from_result, res))

    def test_diff_is_order_invariant(self):
        rng = random.Random(5)
        for res in results():
            prev = call_or_skip(self, self.impl.baseline_from_result, with_paths(res, res.paths[: len(res.paths) // 2]))
            shuffled = list(res.paths)
            rng.shuffle(shuffled)
            a = call_or_skip(self, self.impl.diff, prev, res)
            b = call_or_skip(self, self.impl.diff, prev, with_paths(res, shuffled))
            self.assertEqual((sorted(a.added), sorted(a.removed), sorted(a.unchanged)),
                             (sorted(b.added), sorted(b.removed), sorted(b.unchanged)))

    def test_diff_sets(self):
        for res in results():
            cur = frozenset((p.kind, p.key) for p in res.paths)
            prev = M.Baseline(frozenset(list(cur)[: len(cur) // 2]) | {("exec", "gone_tool")})
            d = call_or_skip(self, self.impl.diff, prev, res)
            self.assertEqual(set(d.added), cur - prev.entries)
            self.assertEqual(set(d.removed), prev.entries - cur)
            self.assertEqual(set(d.unchanged), cur & prev.entries)
            self.assertEqual(d.regressed, bool(cur - prev.entries))


class Templates(unittest.TestCase):
    def test_external_actions_pinned_by_sha(self):
        """C2：雛形の `uses:` は 40 桁の SHA で固定（段 2 で雛形が置かれた時点で効く）。"""
        tdir = os.path.join(PKG, "ci", "templates")
        if not os.path.isdir(tdir):
            self.skipTest("未実装：ci/templates（担当 E）")
        for d, _, files in os.walk(tdir):
            for f in files:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    for i, line in enumerate(fh, 1):
                        m = re.search(r"uses:\s*([^\s#]+)", line)
                        if m and not m.group(1).startswith("./"):
                            self.assertRegex(m.group(1), r"@[0-9a-f]{40}$", f"{f}:{i}")


if __name__ == "__main__":
    unittest.main()
