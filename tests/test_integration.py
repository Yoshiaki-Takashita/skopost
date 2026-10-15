"""結合試験（統合・段 2 の後）：ingest → infer → graph → report の通し、cli の新しい引数、雛形が呼ぶコマンド。

黄金ファイル：tests/fixtures/integration/<例>.<形式>（計算秒数は X に伏せる）。作り直すときは
``SKOPOST_UPDATE_GOLDEN=1 python3 -m unittest tests.test_integration``（差分を目で見てからコミットすること）。
"""
from __future__ import annotations

import io
import json
import os
import random
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import FIXTURES, ROOT, SEEDS, gen_raw_config, mask_seconds  # noqa: E402

from skopost import cli, pipeline  # noqa: E402
from skopost import infer as I  # noqa: E402
from skopost import ingest as IN  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402
from skopost.graph import harm_paths  # noqa: E402
from skopost.model import Fact, from_legacy, validate  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples", "integration")
GOLD = os.path.join(FIXTURES, "integration")
UPDATE = os.environ.get("SKOPOST_UPDATE_GOLDEN") == "1"
TEMPLATES = os.path.join(ROOT, "skopost", "ci", "templates")
#: 例 → 期待する終了コード（0＝道なし／2＝道あり）
EXPECTED_CODE = {
    "mcp-desktop-notes.mcp.json": 2,
    "openapi-shop.json": 2,
    "claude-settings-dev.json": 2,
    "native-support-bot.json": 2,
    "native-locked-down.json": 0,
}
FORMATS = ("text", "md", "json", "sarif")


def _read(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read()


def run_cli(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class Examples(unittest.TestCase):
    """実例風の設定 5 種を通しで走らせ、出力を黄金ファイルと照合する。"""

    def test_examples_exist(self):
        self.assertEqual(sorted(os.listdir(EXAMPLES)), sorted(EXPECTED_CODE))

    def test_golden(self):
        os.makedirs(GOLD, exist_ok=True)
        for name, want_code in EXPECTED_CODE.items():
            for fmt in FORMATS:
                with self.subTest(example=name, fmt=fmt):
                    code, out, _ = run_cli("check", os.path.join(EXAMPLES, name), "--adapter", "auto", "--format", fmt)
                    self.assertEqual(code, want_code)
                    got = mask_seconds(out)
                    gp = os.path.join(GOLD, f"{name}.{fmt}")
                    if UPDATE:
                        with open(gp, "w", encoding="utf-8") as f:
                            f.write(got)
                    with open(gp, encoding="utf-8") as f:
                        self.assertEqual(got, f.read())

    def test_json_and_sarif_parse(self):
        for name in EXPECTED_CODE:
            _, out, _ = run_cli("check", os.path.join(EXAMPLES, name), "--adapter", "auto", "--format", "json")
            self.assertEqual(json.loads(out)["exit_code"], EXPECTED_CODE[name])
            _, out, _ = run_cli("check", os.path.join(EXAMPLES, name), "--adapter", "auto", "--format", "sarif")
            s = json.loads(out)
            self.assertEqual(s["version"], "2.1.0")
            n_paths = json.loads(run_cli("check", os.path.join(EXAMPLES, name), "--adapter", "auto",
                                         "--format", "json")[1])["summary"]["paths"]
            kinds = [r["ruleId"] for r in s["runs"][0]["results"] if r["ruleId"] != "SKP-MISMATCH-UNDER"]
            self.assertEqual(len(kinds), n_paths, name)

    def test_ingest_notes_go_to_stderr(self):
        code, out, err = run_cli("check", os.path.join(EXAMPLES, "mcp-desktop-notes.mcp.json"), "--adapter", "auto",
                                 "--format", "text")
        self.assertIn("取り込み：", err)
        self.assertNotIn("取り込み：", out)

    def test_infer_is_used_end_to_end(self):
        """infer の規則が通しの中で効いている（推定の根拠が実効の札に載る）。"""
        cfg, facts, _ = pipeline.load_config(os.path.join(EXAMPLES, "claude-settings-dev.json"), "auto")
        cfg2 = pipeline.apply_inferred(cfg, facts)
        bash = cfg2.tool("Bash")
        self.assertEqual(bash.observed["exec"].source, "infer:R-CLAUDE-TOOL")
        self.assertEqual(bash.observed["exec"].confidence, "論")
        cfg, facts, _ = pipeline.load_config(os.path.join(EXAMPLES, "mcp-desktop-notes.mcp.json"), "auto")
        cfg2 = pipeline.apply_inferred(cfg, facts)
        self.assertTrue(cfg2.tool("web.fetch_url").observed["net_out"].source.startswith("infer:"))


class NewPipelineMatchesLegacy(unittest.TestCase):
    """既存の check（compat.v1）と新しい流れ（pipeline）が md・json で同じ出力になること（切り替えの根拠。
    切り替えはしていない：既存の check の md・json は compat.v1 のまま）。"""

    def _files(self):
        out = [os.path.join(ROOT, "examples", n) for n in ("notes-agent.json", "browser-agent.json")]
        out += [os.path.join(FIXTURES, "spec-v1", n) for n in sorted(os.listdir(os.path.join(FIXTURES, "spec-v1")))
                if n.startswith("ok-")]
        out += [os.path.join(EXAMPLES, n) for n in EXPECTED_CODE if n.startswith("native-")]
        return out

    def test_md_json_explain_same(self):
        for p in self._files():
            legacy_cfg = validate(json.loads(_read(p)))
            legacy = V1.analyze(legacy_cfg)
            o = pipeline.run(p)
            for explain in (False, True):
                self.assertEqual(mask_seconds(pipeline.render_outcome(o, "md", explain=explain)),
                                 mask_seconds(V1.report_md(legacy, legacy_cfg, explain)), (p, explain))
            self.assertEqual(mask_seconds(pipeline.render_outcome(o, "json")),
                             mask_seconds(json.dumps(legacy, ensure_ascii=False, indent=2) + "\n"), p)
            self.assertEqual(o.exit_code, legacy["exit_code"], p)

    def test_random_configs_same(self):
        for seed in SEEDS:
            raw = gen_raw_config(random.Random(9000 + seed))
            legacy_cfg = validate(raw)
            legacy = V1.analyze(legacy_cfg)
            cfg = from_legacy(legacy_cfg)
            from skopost.graph import analyze
            from skopost.report import render
            res = analyze(cfg)
            self.assertEqual(mask_seconds(render(res, cfg, "json")),
                             mask_seconds(json.dumps(legacy, ensure_ascii=False, indent=2) + "\n"), seed)
            self.assertEqual(mask_seconds(render(res, cfg, "md")), mask_seconds(V1.report_md(legacy, legacy_cfg, False)),
                             seed)


class CliNewOptions(unittest.TestCase):
    EX = os.path.join(ROOT, "examples", "notes-agent.json")

    def test_formats_exit_codes(self):
        for fmt in ("text", "sarif"):
            code, out, err = run_cli("check", self.EX, "--format", fmt)
            self.assertEqual((code, err), (2, ""), fmt)
            self.assertTrue(out)
        self.assertEqual(run_cli("check", self.EX, "--format", "xml")[0], 1)
        self.assertEqual(run_cli("check", self.EX, "--adapter", "nope")[0], 1)
        self.assertEqual(run_cli("check", self.EX, "--adapter")[0], 1)
        self.assertEqual(run_cli("check", self.EX, "--baseline")[0], 1)

    def test_legacy_md_json_untouched_by_adapter_native(self):
        """--adapter native で新しい流れを通しても、v1 の例は同じ出力。"""
        for fmt in ("md", "json"):
            a = mask_seconds(run_cli("check", self.EX, "--format", fmt)[1])
            b = mask_seconds(run_cli("check", self.EX, "--format", fmt, "--adapter", "native")[1])
            self.assertEqual(a, b, fmt)

    def test_baseline_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            bp = os.path.join(d, "base.json")
            self.assertEqual(run_cli("baseline", self.EX, "--out", bp)[0], 0)
            code, _, err = run_cli("check", self.EX, "--baseline", bp)
            self.assertEqual(code, 0, "道は 4 本あるが、基準線と同じなので 0")
            self.assertIn("増えた道 0", err)
            # 基準線から 1 本消す → その道が「増えた道」になって 2
            with open(bp, encoding="utf-8") as f:
                b = json.load(f)
            dropped = b["paths"].pop()
            bp2 = os.path.join(d, "base2.json")
            with open(bp2, "w", encoding="utf-8") as f:
                json.dump(b, f)
            code, _, err = run_cli("check", self.EX, "--format", "sarif", "--baseline", bp2)
            self.assertEqual(code, 2)
            self.assertIn(f"増えた道：{dropped[0]}: {dropped[1]}", err)
            # 壊れた基準線は入力の誤り（1）
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{}")
            code, out, err = run_cli("check", self.EX, "--baseline", bad)
            self.assertEqual((code, out), (1, ""))
            self.assertTrue(err.startswith("入力の誤り："))
            self.assertEqual(run_cli("check", self.EX, "--baseline", os.path.join(d, "missing.json"))[0], 1)

    def test_validate_with_adapter(self):
        code, out, _ = run_cli("validate", os.path.join(EXAMPLES, "openapi-shop.json"), "--adapter", "auto")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("OK：道具 3"))

    def test_legacy_rejects_non_native_without_adapter(self):
        """--adapter を付けなければ v1 と同じく宣言ファイルとしてしか読まない（入力の誤り・終了 1）。"""
        code, out, err = run_cli("check", os.path.join(EXAMPLES, "openapi-shop.json"))
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("入力の誤り："))


class FactKeys(unittest.TestCase):
    """ingest が出す事実の鍵と、infer の規則が読む鍵の突き合わせ。"""

    #: infer/rules.py の表（規則が読む鍵）
    READ_BY_RULES = ("name", "description", "schema.properties", "openapi.method", "openapi.server_external",
                     "mcp.annotation.destructiveHint", "mcp.annotation.openWorldHint", "claude.tool")

    def _all_facts(self):
        files = [os.path.join(EXAMPLES, n) for n in EXPECTED_CODE if not n.startswith("native-")]
        for sub in ("mcp", "openapi", "claude-settings"):
            dd = os.path.join(FIXTURES, "ingest", sub)
            files += [os.path.join(dd, n) for n in os.listdir(dd)]
        facts = []
        for p in files:
            facts += list(IN.ingest(p).facts)
        return facts

    def test_every_rule_key_is_emitted_by_ingest(self):
        emitted = {f.key for f in self._all_facts()}
        self.assertEqual(set(self.READ_BY_RULES) - emitted, set())

    def test_every_rule_fires_on_ingest_output(self):
        facts = self._all_facts()
        fired = {r.id for r in I.DEFAULT_RULES if any(r.applies(f) for f in facts)}
        self.assertEqual({r.id for r in I.DEFAULT_RULES} - fired, set())

    def test_rule_keys_match_source(self):
        src = _read(os.path.join(ROOT, "skopost", "infer", "rules.py"))
        for k in self.READ_BY_RULES:
            self.assertIn(f'"{k}"', src, k)

    def test_description_fact_is_scrubbed(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.mcp.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"mcpServers": {"s": {"command": "x", "tools": [
                    {"name": "t", "description": "uses key sk-" + "A" * 30 + " to post"}]}}}, f)
            res = IN.ingest(p)
            descs = [f.value for f in res.facts if f.key == "description"]
            self.assertEqual(len(descs), 1)
            self.assertNotIn("A" * 30, descs[0])


class InferNeverRemovesPaths(unittest.TestCase):
    """推定（apply_inferred）で道が減らない（不明を危ない側に倒す約束）。乱数の構成と乱数の事実で確かめる。"""

    WORDS = ["bash", "fetch", "sendEmail", "delete_file", "pay", "read", "list", "slack", "削除", "送信", "x"]

    def test_property(self):
        for seed in SEEDS:
            rng = random.Random(7000 + seed)
            cfg = from_legacy(validate(gen_raw_config(rng)))
            facts = []
            for t in cfg.tools:
                for _ in range(rng.randint(0, 3)):
                    k = rng.choice(["name", "description", "claude.tool", "openapi.method",
                                    "mcp.annotation.destructiveHint", "mcp.annotation.openWorldHint",
                                    "schema.properties"])
                    if k.startswith("mcp."):
                        v: object = rng.random() < 0.5
                    elif k == "schema.properties":
                        v = tuple(rng.sample(["url", "to", "amount", "command", "q"], 2))
                    elif k == "openapi.method":
                        v = rng.choice(["GET", "POST", "DELETE"])
                    else:
                        v = " ".join(rng.sample(self.WORDS, 2))
                    facts.append(Fact(t.id, k, v))
            after = pipeline.apply_inferred(cfg, facts)
            for layer in ("declared", "observed"):
                b = {(p.kind, p.key) for p in harm_paths(cfg, layer)}
                a = {(p.kind, p.key) for p in harm_paths(after, layer)}
                self.assertLessEqual(b, a, (seed, layer))

    def test_no_facts_no_change(self):
        cfg = from_legacy(validate(gen_raw_config(random.Random(1))))
        self.assertIs(pipeline.apply_inferred(cfg, []), cfg)


class Templates(unittest.TestCase):
    """GitHub Action 雛形・pre-commit 雛形が呼ぶコマンドが実在し、期待どおりの終了コードを返すこと。"""

    def _run(self, argv: list[str], cwd: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPATH=ROOT)
        return subprocess.run([sys.executable, "-m", "skopost", *argv], cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=60)

    def _action_args(self) -> tuple[list[str], list[str]]:
        y = _read(os.path.join(TEMPLATES, "action.yml"))
        self.assertIn('python3 -m skopost "${args[@]}"', y)
        base = shlex.split(re.search(r"^\s*args=\((.*)\)\s*$", y, re.M).group(1))
        extra = shlex.split(re.search(r"args\+=\((.*?)\)", y).group(1))
        return base, extra

    def test_action_command(self):
        base, extra = self._action_args()
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "skopost.json")
            with open(os.path.join(ROOT, "examples", "notes-agent.json"), encoding="utf-8") as f, \
                    open(cfg, "w", encoding="utf-8") as g:
                g.write(f.read())
            sub = {"$SKOPOST_CONFIG": cfg}
            argv = [sub.get(a, a) for a in base]
            r = self._run(argv, d)
            self.assertEqual(r.returncode, 2, r.stderr)
            sarif = json.loads(_read(os.path.join(d, "skopost.sarif")))
            self.assertEqual(sarif["version"], "2.1.0")
            # 基準線つき：同じ道なら 0
            os.remove(os.path.join(d, "skopost.sarif"))
            bp = os.path.join(d, "base.json")
            self.assertEqual(self._run(["baseline", cfg, "--out", bp], d).returncode, 0)
            sub["$SKOPOST_BASELINE"] = bp
            argv = [sub.get(a, a) for a in base + extra]
            r = self._run(argv, d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.exists(os.path.join(d, "skopost.sarif")))

    def test_precommit_command(self):
        y = _read(os.path.join(TEMPLATES, ".pre-commit-hooks.yaml"))
        entry = shlex.split(re.search(r"^\s*entry:\s*(.+)$", y, re.M).group(1))
        self.assertEqual(entry[:3], ["python3", "-m", "skopost"])
        with tempfile.TemporaryDirectory() as d:
            ok = os.path.join(EXAMPLES, "native-locked-down.json")
            bad = os.path.join(ROOT, "examples", "notes-agent.json")
            self.assertEqual(self._run(entry[3:] + [ok], d).returncode, 0)
            self.assertEqual(self._run(entry[3:] + [bad], d).returncode, 2)


if __name__ == "__main__":
    unittest.main()
