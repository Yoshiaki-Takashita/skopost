"""段 2 の公開面の署名（担当 A 所有）。名前・引数・注釈・既定値を固定する。

段 2 の担当が署名を変えたいときは担当 A に依頼し、A がこの表と model/types.py を 1 コミットで更新する
（ARCHITECTURE §4 の境界の規則）。署名が固定されていれば 4 担当は互いの中身を待たずに並行で書ける。
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import signature_of  # noqa: E402

from skopost.model.errors import NotImplementedYet  # noqa: E402

EXPECTED = {
    "skopost.infer.infer_caps": "(facts: 'Sequence[Fact]', rules: 'Sequence[Rule]' = DEFAULT_RULES) -> 'dict[str, dict[str, Cap]]'",
    "skopost.infer.combine": "(a: 'Cap', b: 'Cap') -> 'Cap'",
    "skopost.infer.effective": "(tool: 'Tool', stores: 'Mapping[str, Store]', layer: 'Layer') -> 'EffectiveCaps'",
    "skopost.infer.mismatches": "(cfg: 'Config') -> 'list[Mismatch]'",
    "skopost.infer.assumed_unknown": "(cfg: 'Config') -> 'list[Assumed]'",
    "skopost.ingest.detect": "(data: 'object', filename: 'str') -> 'Adapter'",
    "skopost.ingest.ingest": "(path: 'str', *, adapter: 'Optional[str]' = None) -> 'IngestResult'",
    "skopost.ingest.merge": "(base: 'Config', overlay: 'Config') -> 'Config'",
    "skopost.graph.harm_paths": "(cfg: 'Config', layer: 'Layer') -> 'list[HarmPath]'",
    "skopost.graph.min_checkpoints": "(cfg: 'Config', paths: 'Sequence[HarmPath]', *, exact_limit: 'int' = 20, "
                                     "max_alternatives: 'int' = 5, time_budget_s: 'float' = 5.0) -> 'Checkpoints'",
    "skopost.graph.apply_checkpoints": "(cfg: 'Config', cut: 'Iterable[str]') -> 'Config'",
    "skopost.graph.explain": "(cfg: 'Config', paths: 'Sequence[HarmPath]', cp: 'Checkpoints') -> 'dict[str, list[str]]'",
    "skopost.graph.analyze": "(cfg: 'Config') -> 'AnalysisResult'",
    "skopost.report.render": "(res: 'AnalysisResult', cfg: 'Config', fmt: 'Format', *, explain: 'bool' = False, "
                             "lang: 'Lang' = 'ja') -> 'str'",
    "skopost.report.to_json": "(res: 'AnalysisResult') -> 'dict[str, object]'",
    "skopost.report.to_sarif": "(res: 'AnalysisResult', cfg: 'Config', *, artifact_uri: 'str') -> 'dict[str, object]'",
    "skopost.ci.baseline_from_result": "(res: 'AnalysisResult') -> 'Baseline'",
    "skopost.ci.load_baseline": "(path: 'str') -> 'Baseline'",
    "skopost.ci.diff": "(prev: 'Baseline', cur: 'AnalysisResult') -> 'BaselineDiff'",
    "skopost.ci.write_baseline": "(res: 'AnalysisResult') -> 'str'",
    "skopost.enforce.get_enforcer": "(target: 'str') -> 'Enforcer'",
}


def resolve(qual: str):
    mod, name = qual.rsplit(".", 1)
    return getattr(importlib.import_module(mod), name)


class Signatures(unittest.TestCase):
    def test_signatures_fixed(self):
        for qual, sig in EXPECTED.items():
            with self.subTest(qual=qual):
                self.assertEqual(signature_of(resolve(qual)), sig)

    def test_public_surface_exported(self):
        for qual in EXPECTED:
            mod, name = qual.rsplit(".", 1)
            self.assertIn(name, importlib.import_module(mod).__all__, qual)

    def test_stub_or_implemented(self):
        """空実装は NotImplementedYet を投げ、担当名を名乗る（どれが未実装かを報告できるように）。"""
        for qual in EXPECTED:
            fn = resolve(qual)
            src = inspect.getsource(fn)
            if "NotImplementedYet(" in src:
                n_req = sum(1 for p in inspect.signature(fn).parameters.values()
                            if p.default is inspect.Parameter.empty and p.kind is not p.KEYWORD_ONLY)
                kw = {p.name: None for p in inspect.signature(fn).parameters.values()
                      if p.default is inspect.Parameter.empty and p.kind is p.KEYWORD_ONLY}
                with self.assertRaises(NotImplementedYet) as cm:
                    fn(*([None] * n_req), **kw)
                self.assertTrue(cm.exception.owner)


if __name__ == "__main__":
    unittest.main()
