"""契約試験そのものの自己検査（担当 A）。

契約試験は段 1 では空実装を相手に「未実装」で飛ぶだけなので、試験の側に誤りがあっても気づけない。そこで
v1 の参照実装（compat.v1）を型付きの署名に包んだ「参照の実装」を差し込み、契約試験が**参照実装で緑になる**
ことを確かめる。参照の実装は試験専用で、パッケージには入れない（段 2 の担当の作業を先取りしないため）。
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_contract_ci as CC  # noqa: E402
import test_contract_graph as CG  # noqa: E402
import test_contract_infer as CI  # noqa: E402
import test_contract_report as CR  # noqa: E402

from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402
from skopost.model import Assumed, Config  # noqa: E402

EFF = CI.EFF


# ---------------------------------------------------------------- 参照の実装（v1 を型で包むだけ）
def _legacy_stores(stores) -> dict:
    return {s.id: {"id": s.id, "label": s.label, "external": s.external, "executes": s.executes, "secret": s.secret}
            for s in stores.values()}


def ref_effective(tool, stores, layer):
    lt = M.to_legacy(Config(tools=(tool,), stores=tuple(stores.values())))["tools"][0]
    return CI.v1_effective_typed(tool.id, lt, _legacy_stores(stores), layer)


def ref_mismatches(cfg):
    out = []
    for m in V1.mismatches(M.to_legacy(cfg)):
        conv = (lambda v: frozenset(v) if isinstance(v, list) else v)
        out.append(M.Mismatch(m["tool"], m["cap"], conv(m["declared"]), conv(m["observed"]), m["confidence"],
                              m["evidence"], m["severity"]))
    return out


def ref_assumed(cfg):
    return [Assumed(a["tool"], a["cap"]) for a in V1.analyze(M.to_legacy(cfg))["assumed"]]


def ref_harm_paths(cfg, layer):
    return CG.typed_paths(V1.harm_paths(M.to_legacy(cfg), layer))


def ref_min_checkpoints(cfg, paths, *, exact_limit=20, max_alternatives=5, time_budget_s=5.0):
    legacy_paths = [{"kind": p.kind, "tools": list(p.tools), "via": list(p.via), "confidence": p.confidence} for p in paths]
    r = V1.min_checkpoints(M.to_legacy(cfg), legacy_paths)
    return M.Checkpoints(r["exact"], tuple(r["primary"]), tuple(tuple(a) for a in r["alternatives"][:max_alternatives]),
                         "exhaustive" if r["exact"] else "greedy", len(r["primary"]) if r["exact"] else 0)


def ref_apply(cfg, cut):
    return M.from_legacy(V1.apply_checkpoints(M.to_legacy(cfg), list(cut)))


def ref_explain(cfg, paths, cp):
    return {tid: [f"{p.kind}: {p.key}" for p in paths if tid in p.tools] for tid in cp.primary}


def ref_analyze(cfg):
    return M.result_from_legacy(V1.analyze(M.to_legacy(cfg)))


def ref_render(res, cfg, fmt, *, explain=False, lang="ja"):
    if fmt == "md":
        return V1.report_md(M.result_to_dict(res), M.to_legacy(cfg), explain)
    if fmt == "json":
        return json.dumps(M.result_to_dict(res), ensure_ascii=False, indent=2) + "\n"
    raise ValueError(fmt)


def ref_baseline(res):
    return M.Baseline(frozenset((p.kind, p.key) for p in res.paths))


def ref_write(res):
    return json.dumps({"skopost_baseline": 1, "paths": sorted(map(list, ref_baseline(res).entries))}, ensure_ascii=False)


def ref_load(path):
    with open(path, encoding="utf-8") as f:
        return M.Baseline(frozenset(tuple(x) for x in json.load(f)["paths"]))


def ref_diff(prev, cur):
    c = ref_baseline(cur).entries
    return M.BaselineDiff(tuple(sorted(c - prev.entries)), tuple(sorted(prev.entries - c)), tuple(sorted(c & prev.entries)))


REF_INFER = SimpleNamespace(effective=ref_effective, mismatches=ref_mismatches, assumed_unknown=ref_assumed)
REF_GRAPH = SimpleNamespace(harm_paths=ref_harm_paths, min_checkpoints=ref_min_checkpoints, apply_checkpoints=ref_apply,
                            explain=ref_explain, analyze=ref_analyze)
REF_REPORT = SimpleNamespace(render=ref_render, to_json=M.result_to_dict)
REF_CI = SimpleNamespace(baseline_from_result=ref_baseline, write_baseline=ref_write, load_baseline=ref_load, diff=ref_diff)


# ---------------------------------------------------------------- 差し込み
class InferEffectiveRef(CI.EffectiveMatchesV1):
    impl = REF_INFER


class GraphPathsRef(CG.HarmPathsMatchV1):
    impl = REF_GRAPH


class GraphCheckpointsRef(CG.MinCheckpoints):
    impl = REF_GRAPH


class GraphApplyRef(CG.ApplyAndExplain):
    impl = REF_GRAPH


class GraphAnalyzeRef(CG.AnalyzeMatchesV1):
    impl = REF_GRAPH


class ReportRef(CR.Render):
    impl = REF_REPORT
    formats = ("md", "json")      # 参照の実装は md・json だけ（text・sarif は担当 E）


class CiRef(CC.Baselines):
    impl = REF_CI


class NoSkipsInSelfcheck(unittest.TestCase):
    """参照で飛ばされる試験が想定外に増えていない（契約試験が全部「未実装」で素通りする壊れ方を防ぐ）。"""

    def test_reference_runs_contracts(self):
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for cls in (InferEffectiveRef, GraphPathsRef, GraphCheckpointsRef, GraphApplyRef, GraphAnalyzeRef, ReportRef, CiRef):
            suite.addTests(loader.loadTestsFromTestCase(cls))
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(result.failures + result.errors, [])
        self.assertEqual(result.skipped, [])
        self.assertGreaterEqual(result.testsRun, 20)


if __name__ == "__main__":
    unittest.main()
