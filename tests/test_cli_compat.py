"""互換の試験（担当 A）：import の優先順位・旧 API の名前・CLI の出力と終了コード（L1・L2）。

黄金ファイル tests/fixtures/golden-v1.0.0/ は、パッケージ化する前の単一ファイル skopost.py（v1.0.0）で
`check`・`--explain`・`--format json`・`example`・`--help`・`validate`・未知のコマンドを走らせた出力
（計算秒数だけ X に伏せた）。
"""
from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import FIXTURES, ROOT, mask_seconds  # noqa: E402

import skopost as S  # noqa: E402
from skopost import cli  # noqa: E402

GOLDEN = os.path.join(FIXTURES, "golden-v1.0.0")


def golden(name: str) -> str:
    with open(os.path.join(GOLDEN, name), encoding="utf-8") as f:
        return f.read()


def run_main(fn, *args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = fn(list(args))
    return code, out.getvalue(), err.getvalue()


class ImportPrecedence(unittest.TestCase):
    """同じ sys.path 要素に `m.py` と `m/__init__.py` があると、どちらが import されるか。"""

    def _fresh(self, name: str, d: str):
        sys.path.insert(0, d)
        try:
            importlib.invalidate_caches()
            sys.modules.pop(name, None)
            return importlib.import_module(name)
        finally:
            sys.path.remove(d)
            sys.modules.pop(name, None)

    def test_regular_package_wins_over_module(self):
        with tempfile.TemporaryDirectory() as d:
            name = "skp_prec_probe_a"
            with open(os.path.join(d, name + ".py"), "w") as f:
                f.write('WHO = "module"\n')
            os.mkdir(os.path.join(d, name))
            with open(os.path.join(d, name, "__init__.py"), "w") as f:
                f.write('WHO = "package"\n')
            self.assertEqual(self._fresh(name, d).WHO, "package")

    def test_module_wins_over_namespace_package(self):
        # __init__.py の無いディレクトリ（名前空間パッケージ）より、同名の .py が優先される
        with tempfile.TemporaryDirectory() as d:
            name = "skp_prec_probe_b"
            with open(os.path.join(d, name + ".py"), "w") as f:
                f.write('WHO = "module"\n')
            os.mkdir(os.path.join(d, name))
            self.assertEqual(self._fresh(name, d).WHO, "module")

    def test_real_skopost_resolves_to_package(self):
        spec = importlib.util.find_spec("skopost")
        self.assertIsNotNone(spec)
        self.assertEqual(os.path.abspath(spec.origin), os.path.join(ROOT, "skopost", "__init__.py"))
        self.assertTrue(spec.submodule_search_locations)
        self.assertEqual(os.path.abspath(S.__file__), os.path.join(ROOT, "skopost", "__init__.py"))

    def test_script_entry_runs_package_cli(self):
        argv = sys.argv
        out, err = io.StringIO(), io.StringIO()
        try:
            sys.argv = [os.path.join(ROOT, "skopost.py"), "check", os.path.join(ROOT, "examples", "notes-agent.json"),
                        "--format", "json"]
            with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                runpy.run_path(os.path.join(ROOT, "skopost.py"), run_name="__main__")
        finally:
            sys.argv = argv
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(mask_seconds(out.getvalue()), golden("notes-agent.json"))

    def test_python_m_entry(self):
        argv = sys.argv
        out = io.StringIO()
        try:
            sys.argv = ["skopost", "validate", os.path.join(ROOT, "examples", "notes-agent.json")]
            with redirect_stdout(out), self.assertRaises(SystemExit) as cm:
                runpy.run_module("skopost", run_name="__main__", alter_sys=False)
        finally:
            sys.argv = argv
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(out.getvalue(), golden("val.out"))

    def test_thin_entry_is_thin(self):
        with open(os.path.join(ROOT, "skopost.py"), encoding="utf-8") as f:
            n = sum(1 for _ in f)
        self.assertLessEqual(n, 50, "skopost.py は 50 行以下の薄い入口（ARCHITECTURE §0）")


class V1Names(unittest.TestCase):
    def test_all_v1_names_reexported(self):
        for name in S.V1_NAMES:
            self.assertTrue(hasattr(S, name), name)
        for name in ("_usage", "_layer_value", "_min_conf", "_expect", "_norm_cap_value", "_norm_conf"):
            self.assertTrue(hasattr(S, name), name)

    def test_v1_constants_unchanged(self):
        self.assertEqual((S.SPEC_VERSION, S.MAX_FILE_BYTES, S.MAX_TOOLS, S.MAX_STORES, S.MAX_ID_LEN, S.EXACT_LIMIT,
                          S.MAX_ALTERNATIVES, S.DISPLAY_LEN), (1, 2 * 1024 * 1024, 64, 32, 64, 20, 5, 120))
        self.assertEqual(S.ACT_KINDS, ("send", "purchase", "delete", "publish", "grant", "pay"))
        self.assertEqual(S.ALL_CAPS, ("reads_untrusted", "reads_secret", "net_out", "args_leave", "exec",
                                      "acts", "writes_stores", "reads_stores"))

    def test_version_is_semver_1x(self):
        major = int(S.__version__.split(".")[0])
        self.assertEqual(major, 1, "CLI の互換を壊すのは 2.0.0 だけ")


class GoldenOutputs(unittest.TestCase):
    """L2：既存の例で、出力のバイト列と終了コードが v1.0.0 と同一。"""

    def test_check_md_json_explain(self):
        for ex in ("notes-agent", "browser-agent"):
            p = os.path.join(ROOT, "examples", ex + ".json")
            for args, suffix in (((), ".md"), (("--explain",), ".x.md"), (("--format", "json"), ".json")):
                code, out, err = run_main(S.main, "check", p, *args)
                self.assertEqual(code, 2, (ex, args))
                self.assertEqual(err, "")
                self.assertEqual(mask_seconds(out), golden(ex + suffix), (ex, args))

    def test_example_help_validate_unknown(self):
        self.assertEqual(run_main(S.main, "example"), (0, golden("example.out"), ""))
        self.assertEqual(run_main(S.main, "--help"), (0, golden("help.out"), ""))
        self.assertEqual(run_main(S.main), (0, golden("help.out"), ""))
        self.assertEqual(run_main(S.main, "validate", os.path.join(ROOT, "examples", "notes-agent.json")),
                         (0, golden("val.out"), ""))
        self.assertEqual(run_main(S.main, "bogus"), (1, "", golden("bogus.err")))

    def test_usage_text_identical(self):
        self.assertEqual(cli.USAGE + "\n", golden("help.out"))

    def test_error_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write('{"skopost": 1, "tools": []}')
            code, out, err = run_main(S.main, "check", p)
            self.assertEqual((code, out), (1, ""))
            self.assertTrue(err.startswith("入力の誤り："))
            self.assertEqual(run_main(S.main, "check")[0], 1)
            self.assertEqual(run_main(S.main, "check", p, "--bogus")[0], 1)
            self.assertEqual(run_main(S.main, "check", p, "--format")[0], 1)

    def test_no_paths_exit_zero(self):
        cfg = {"skopost": 1, "tools": [{"id": "a", "observed": {
            c: {"value": False if c not in ("acts", "writes_stores", "reads_stores") else [], "confidence": "確"}
            for c in S.ALL_CAPS}}]}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ok.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
            code, out, _ = run_main(S.main, "check", p, "--format", "json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["exit_code"], 0)

    def test_cli_module_has_no_analysis_logic(self):
        # cli は配線だけ：関数定義は main と _usage だけ
        import ast
        with open(cli.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertEqual(funcs, {"main", "_usage"})


if __name__ == "__main__":
    unittest.main()
