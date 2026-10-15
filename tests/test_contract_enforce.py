"""enforce の契約試験（担当 A）。E1・E2：段 1 で書き込みの経路が 0、緩める変更は型で表せない、既定ドライラン。"""
from __future__ import annotations

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import PKG  # noqa: E402

from skopost import enforce as E  # noqa: E402
from skopost.model import NotImplementedYet  # noqa: E402

SHA = "0" * 64


class Contract(unittest.TestCase):
    def test_only_tightening_representable(self):
        E.PlannedChange("bash", "settings.json", "/permissions/allow/0")
        for before, after in (("ask", "allow"), ("allow", "allow"), ("deny", "allow"), ("allow", "deny-removed")):
            with self.subTest(before=before, after=after), self.assertRaises(ValueError):
                E.PlannedChange("bash", "settings.json", "/x", before=before, after=after)  # type: ignore[arg-type]

    def test_dry_run_by_default(self):
        plan = E.EnforcementPlan("claude-settings", (E.PlannedChange("a", "s.json", "/p"),), SHA)
        self.assertTrue(plan.dry_run)

    def test_plan_validation(self):
        c = E.PlannedChange("a", "s.json", "/p")
        for bad in (dict(target="other", changes=(c,), source_sha256=SHA),
                    dict(target="claude-settings", changes=[c], source_sha256=SHA),
                    dict(target="claude-settings", changes=(c, c), source_sha256=SHA),
                    dict(target="claude-settings", changes=(c,), source_sha256="x"),
                    dict(target="claude-settings", changes=(c,), source_sha256=SHA, dry_run=0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                E.EnforcementPlan(**bad)  # type: ignore[arg-type]

    def test_no_implementation_yet(self):
        for t in ("claude-settings", "anything"):
            with self.assertRaises(NotImplementedYet):
                E.get_enforcer(t)
        # Protocol を満たす具象クラスがパッケージ内に無い
        src = self._sources()
        for path, tree in src.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.assertIn(node.name, {"PlannedChange", "EnforcementPlan", "ApplyReport", "Enforcer"},
                                  f"{path}: 段 1 に実装クラスは置かない（{node.name}）")

    def _sources(self) -> dict[str, ast.AST]:
        out = {}
        d = os.path.join(PKG, "enforce")
        for f in sorted(os.listdir(d)):
            if f.endswith(".py"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    out[f] = ast.parse(fh.read())
        return out

    def test_no_write_paths(self):
        """E1：enforce に書き込み・削除・外部実行の呼び出しが無い（静的検査）。"""
        banned_calls = {"open", "write", "write_text", "write_bytes", "remove", "unlink", "rename", "replace",
                        "rmtree", "copy", "copyfile", "move", "system", "popen", "makedirs", "mkdir", "chmod"}
        banned_mods = {"shutil", "os", "pathlib", "tempfile", "io"}
        for path, tree in self._sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                    self.assertNotIn(name, banned_calls, f"{path}:{node.lineno}")
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    for m in mods:
                        self.assertNotIn(m.split(".")[0], banned_mods, f"{path}:{node.lineno}")


if __name__ == "__main__":
    unittest.main()
