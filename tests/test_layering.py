"""依存の向きを機械で守る（ARCHITECTURE §1・X1・原則 9）。

各ファイルの import を ast で読み、表 ALLOWED に無い向き（逆向き・横向き）を失敗にする。
あわせて：標準ライブラリ以外の import 禁止・通信や外部プロセスの import 禁止・相対 import の解決。
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import PKG  # noqa: E402

#: 層 → import してよい skopost 内の層（自分自身は常に可）。上から下へだけ。
ALLOWED: dict[str, set[str]] = {
    "model": set(),
    "infer.rules": {"model"},
    "infer": {"model", "infer.rules"},
    "ingest": {"model", "infer.rules"},
    "graph": {"model", "infer", "infer.rules"},
    "report": {"model", "graph"},
    "ci": {"model", "report"},
    "enforce": {"model", "graph"},
    "compat": {"model"},
    "pipeline": {"model", "infer", "infer.rules", "ingest", "graph", "report", "ci"},
    "cli": {"model", "compat", "infer", "infer.rules", "ingest", "graph", "report", "ci", "enforce", "pipeline"},
    "__main__": {"cli"},
    "__init__": {"model", "compat", "cli", "infer", "infer.rules", "ingest", "graph", "report", "ci", "enforce",
                 "pipeline"},
}
FORBIDDEN_MODULES = {"socket", "ssl", "urllib", "http", "requests", "subprocess", "ftplib", "smtplib", "telnetlib",
                     "xmlrpc", "asyncio", "multiprocessing", "ctypes", "webbrowser", "pickle", "marshal", "shelve"}


def layer_of(modname: str) -> str:
    """'skopost.infer.rules' → 'infer.rules'、'skopost.graph.api' → 'graph'、'skopost' → '__init__'。"""
    parts = modname.split(".")
    assert parts[0] == "skopost", modname
    rest = parts[1:]
    if not rest:
        return "__init__"
    if rest[0] == "infer" and len(rest) > 1 and rest[1] == "rules":
        return "infer.rules"
    if rest[0] in ("cli", "__main__"):
        return rest[0]
    return rest[0]


def module_name(path: str, root: str = PKG) -> str:
    rel = os.path.relpath(path, os.path.dirname(root))[:-3].replace(os.sep, ".")
    return rel[: -len(".__init__")] if rel.endswith(".__init__") else rel


def iter_py(root: str = PKG):
    for d, _, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".py"):
                yield os.path.join(d, f)


def imports_of(path: str, root: str = PKG) -> list[tuple[str, int]]:
    """(絶対モジュール名, 行) の並び。相対 import は解決する。`from x import y` は x.y も候補に含める。"""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    me = module_name(path, root)
    is_pkg = path.endswith("__init__.py")
    base_parts = me.split(".") if is_pkg else me.split(".")[:-1]
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(a.name, node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = base_parts[: len(base_parts) - (node.level - 1)] if node.level > 1 else base_parts
                mod = ".".join(parts + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            out.append((mod, node.lineno))
            for a in node.names:
                if a.name != "*":
                    out.append((f"{mod}.{a.name}", node.lineno))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            out.append(("<dynamic __import__>", node.lineno))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"):
            out.append(("<dynamic import_module>", node.lineno))
    return out


def is_skopost_module(name: str) -> bool:
    # `from .model.types import Cap` は "skopost.model.types.Cap" も候補に入るが、層の判定は先頭 2〜3 段で足りる
    return name == "skopost" or name.startswith("skopost.")


def violations(root: str = PKG) -> list[str]:
    bad: list[str] = []
    stdlib = set(sys.stdlib_module_names)
    for path in iter_py(root):
        me = module_name(path, root)
        my_layer = layer_of(me)
        allowed = ALLOWED.get(my_layer)
        rel = os.path.relpath(path, os.path.dirname(root))
        if allowed is None:
            bad.append(f"{rel}: 層 {my_layer!r} が ALLOWED の表に無い（新しい層は ARCHITECTURE と表を先に更新）")
            continue
        for name, line in imports_of(path, root):
            if name.startswith("<dynamic"):
                bad.append(f"{rel}:{line}: 動的 import は禁止（{name}）")
                continue
            top = name.split(".")[0]
            if top in FORBIDDEN_MODULES:
                bad.append(f"{rel}:{line}: 通信・外部プロセス等の import は禁止（{top}）")
                continue
            if is_skopost_module(name):
                target = layer_of(name)
                if target in (my_layer,) or target in allowed:
                    continue
                # `from ..model import x` が x を層名と誤認しないよう、層として存在しない名前は親の層で判定済み
                if target not in ALLOWED:
                    continue
                bad.append(f"{rel}:{line}: {my_layer} → {target} は禁止の向き（{name}）")
            elif top and top not in stdlib and top != "__future__":
                bad.append(f"{rel}:{line}: 標準ライブラリ以外の import（{top}）")
    return list(dict.fromkeys(bad))


class Layering(unittest.TestCase):
    def test_no_reverse_or_sideways_imports(self):
        self.assertEqual(violations(), [])

    def test_every_layer_directory_is_known(self):
        for entry in os.listdir(PKG):
            p = os.path.join(PKG, entry)
            if os.path.isdir(p) and not entry.startswith("__"):
                self.assertIn(entry, ALLOWED, f"skopost/{entry}/ が依存の表に無い")
                self.assertTrue(os.path.exists(os.path.join(p, "__init__.py")), f"skopost/{entry}/__init__.py が無い")

    def test_model_depends_on_nothing(self):
        self.assertEqual(ALLOWED["model"], set())

    def test_graph_does_not_know_ingest(self):
        self.assertNotIn("ingest", ALLOWED["graph"])

    def test_report_does_not_know_ingest_or_infer(self):
        self.assertFalse({"ingest", "infer"} & ALLOWED["report"])

    def test_table_is_acyclic(self):
        seen: dict[str, int] = {}

        def visit(n: str, stack: tuple[str, ...]) -> None:
            self.assertNotIn(n, stack, f"循環：{' → '.join(stack + (n,))}")
            if seen.get(n) == 2:
                return
            for m in ALLOWED.get(n, ()):
                visit(m, stack + (n,))
            seen[n] = 2

        for n in ALLOWED:
            visit(n, ())


class LayeringCheckerSelfTest(unittest.TestCase):
    """検査そのものが違反を見つけられること（検査が常に緑になる壊れ方を防ぐ）。"""

    def _tree(self, files: dict[str, str]) -> list[str]:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "skopost")
            for rel, src in files.items():
                p = os.path.join(root, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(src)
            return violations(root)

    def test_detects_reverse_import(self):
        bad = self._tree({"__init__.py": "", "model/__init__.py": "from ..graph import api\n",
                          "graph/__init__.py": "", "graph/api.py": ""})
        self.assertTrue(any("model → graph" in b for b in bad), bad)

    def test_detects_sideways_import(self):
        bad = self._tree({"__init__.py": "", "graph/__init__.py": "from skopost.ingest import detect\n",
                          "ingest/__init__.py": ""})
        self.assertTrue(any("graph → ingest" in b for b in bad), bad)

    def test_detects_ingest_using_infer_api(self):
        bad = self._tree({"__init__.py": "", "ingest/x.py": "from ..infer.api import effective\n",
                          "infer/__init__.py": "", "infer/api.py": ""})
        self.assertTrue(any("ingest → infer" in b for b in bad), bad)

    def test_allows_ingest_using_infer_rules(self):
        bad = self._tree({"__init__.py": "", "ingest/x.py": "from ..infer.rules import Rule\n",
                          "infer/__init__.py": "", "infer/rules.py": ""})
        self.assertEqual(bad, [])

    def test_detects_third_party_and_network(self):
        bad = self._tree({"__init__.py": "", "model/__init__.py": "import yaml\nimport socket\nfrom urllib import request\n"})
        self.assertEqual(len([b for b in bad if "標準ライブラリ以外" in b]), 1, bad)
        self.assertEqual(len([b for b in bad if "通信" in b]), 2, bad)

    def test_detects_dynamic_import(self):
        bad = self._tree({"__init__.py": "", "model/__init__.py": "import importlib\nimportlib.import_module('x')\n"})
        self.assertTrue(any("動的" in b for b in bad), bad)

    def test_unknown_layer_flagged(self):
        bad = self._tree({"__init__.py": "", "plugins/__init__.py": ""})
        self.assertTrue(any("ALLOWED の表に無い" in b for b in bad), bad)


if __name__ == "__main__":
    unittest.main()
