"""ingest の詳細試験（担当 B）。各アダプタの読み方・確度・秘密・壊れた入力。"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import FIXTURES  # noqa: E402

from skopost import ingest as IN  # noqa: E402
from skopost import model as M  # noqa: E402

FX = os.path.join(FIXTURES, "ingest")
SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,}|-----BEGIN [A-Z ]+-----|ghp_[A-Za-z0-9]{20,}")
SECRETS = ("sk-" + "Z" * 40, "AKIA" + "Q" * 16, "-----BEGIN RSA PRIVATE KEY-----", "ghp_" + "a1" * 15)


def write_tmp(d, name, data):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))
    return p


def no_sure_caps(tc, res):
    for t in res.config.tools:
        for layer in (t.observed, t.declared):
            for c in layer.values():
                tc.assertNotEqual(c.confidence, "確")


class Detect(unittest.TestCase):
    def test_each_fixture_detected_as_its_directory(self):
        for name in IN.ADAPTERS:
            d = os.path.join(FX, name)
            for f in sorted(os.listdir(d)):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    self.assertEqual(IN.detect(json.load(fh), f).name, name, f)

    def test_tie_is_refused(self):
        class Twin:
            name = "twin"
            def sniff(self, data, filename): return 0.95
            def read(self, data, *, filename): raise AssertionError
        IN.ADAPTERS["twin"] = Twin()
        try:
            with self.assertRaises(M.SkopostError):
                IN.detect({"skopost": 1}, "x.json")
        finally:
            del IN.ADAPTERS["twin"]

    def test_settings_with_mcp_servers_goes_to_settings(self):
        self.assertEqual(IN.detect({"permissions": {}, "mcpServers": {}}, "settings.json").name, "claude-settings")

    def test_unknown_adapter_name(self):
        with self.assertRaises(M.SkopostError):
            IN.ingest(os.path.join(FX, "native", "small.json"), adapter="nope")


class Mcp(unittest.TestCase):
    def setUp(self):
        self.res = IN.ingest(os.path.join(FX, "mcp", "desktop.mcp.json"))

    def test_tools_and_sdk_dropped(self):
        ids = [t.id for t in self.res.config.tools]
        self.assertEqual(ids, ["files", "remote", "local", "listed.read_note", "listed.send_mail", "listed.bad_id_with_space"])
        self.assertIn("/mcpServers/inproc", self.res.dropped)
        self.assertIn("/mcpServers/listed/tools/3", self.res.dropped)

    def test_annotations_go_to_declared_only(self):
        t = self.res.config.tool("listed.read_note")
        self.assertEqual(t.declared["acts"].value, frozenset())
        self.assertIs(t.declared["net_out"].value, False)
        self.assertEqual(dict(t.observed), {})
        self.assertEqual(t.declared["net_out"].source, "ingest:mcp")
        no_sure_caps(self, self.res)

    def test_description_is_material_not_command(self):
        """説明文は label と事実（"description"）に入るが、札は作らない（宣言・観察とも説明文に由来しない）。
        統合で infer の R-DESC-WORDS が読む鍵に合わせた。infer は説明文から危ない側の札を「推」で足すだけ。"""
        t = self.res.config.tool("listed.read_note")
        self.assertIn("Ignore previous", t.label)
        self.assertFalse(any("description" in c.evidence for c in t.declared.values()))
        self.assertEqual(dict(t.observed), {})
        descs = [f for f in self.res.facts if f.tool_id == t.id and f.key == "description"]
        self.assertEqual(len(descs), 1)
        from skopost import infer as I
        for c in I.infer_caps(descs).get(t.id, {}).values():
            self.assertNotEqual(c.confidence, "確")
            self.assertTrue(c.value is True or (isinstance(c.value, frozenset) and c.value), "安全側の札を作らない")

    def test_unknown_annotation_noted(self):
        ptrs = {(n.kind, n.pointer) for n in self.res.notes}
        self.assertIn(("unread_key", "/mcpServers/listed/tools/1/annotations/futureHint"), ptrs)
        self.assertIn(("unread_key", "/globalShortcut"), ptrs)

    def test_facts(self):
        f = {(x.tool_id, x.key): x.value for x in self.res.facts}
        self.assertEqual(f[("files", "mcp.server.command")], "npx")
        self.assertEqual(f[("files", "mcp.server.env_keys")], ("LOG_LEVEL",))
        self.assertIs(f[("remote", "mcp.server.remote_host")], True)
        self.assertIs(f[("local", "mcp.server.remote_host")], False)
        self.assertEqual(f[("remote", "mcp.server.headers_keys")], ("Authorization",))
        self.assertNotIn("PLACEHOLDER", repr(self.res))

    def test_imports_recorded(self):
        (rec,) = self.res.config.imports
        self.assertEqual(rec.adapter, "mcp")
        self.assertRegex(rec.sha256, r"^[0-9a-f]{64}$")

    def test_origin_pointer(self):
        self.assertEqual(self.res.config.tool("listed.send_mail").origin.pointer, "/mcpServers/listed/tools/1")

    def test_config_roundtrips_through_parse(self):
        """宣言の札の evidence・source は v2 の入力形式に欄が無く落ちる（model 側の仕様。値・ID・mode は残る）。"""
        cfg = self.res.config
        back = M.parse(M.to_dict(cfg))
        self.assertEqual([(t.id, t.mode, {k: c.value for k, c in t.declared.items()}) for t in back.tools],
                         [(t.id, t.mode, {k: c.value for k, c in t.declared.items()}) for t in cfg.tools])


class OpenApi(unittest.TestCase):
    def setUp(self):
        self.res = IN.ingest(os.path.join(FX, "openapi", "petstore.json"))
        self.f = {(x.tool_id, x.key): x.value for x in self.res.facts}

    def test_operations(self):
        self.assertEqual([t.id for t in self.res.config.tools], ["listPets", "createPet", "delete__pets__id_", "rel"])
        self.assertEqual(self.f[("listPets", "openapi.method")], "GET")
        self.assertEqual(self.res.config.name, "Pet store")

    def test_server_externality_layers(self):
        self.assertIs(self.f[("listPets", "openapi.server_external")], True)
        self.assertIs(self.f[("delete__pets__id_", "openapi.server_external")], False)

    def test_security(self):
        self.assertIs(self.f[("listPets", "openapi.security_required")], False)
        self.assertIs(self.f[("createPet", "openapi.security_required")], True)

    def test_no_caps_from_adapter(self):
        for t in self.res.config.tools:
            self.assertEqual(dict(t.observed), {})

    def test_swagger2_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, "s.json", {"swagger": "2.0", "paths": {}})
            with self.assertRaises(M.SkopostError):
                IN.ingest(p, adapter="openapi")


class ClaudeSettings(unittest.TestCase):
    def setUp(self):
        self.res = IN.ingest(os.path.join(FX, "claude-settings", "settings.json"))
        self.modes = {t.id: t.mode for t in self.res.config.tools}

    def test_modes(self):
        self.assertEqual(self.modes, {"Read": "allow", "Write": "ask", "mcp__github__get_issue": "allow", "WebFetch": "allow"})

    def test_bare_deny_removes_tool(self):
        self.assertNotIn("WebSearch", self.modes)
        self.assertNotIn("Bash", self.modes)   # Bash(*) は Bash と同じ

    def test_mcp_rule_with_parens_dropped(self):
        self.assertIn("/permissions/deny/3", self.res.dropped)

    def test_hooks_and_unknown_keys_noted(self):
        kinds = {(n.kind, n.pointer) for n in self.res.notes}
        self.assertIn(("unsupported", "/hooks"), kinds)
        self.assertIn(("unread_key", "/permissions/futureKey"), kinds)
        self.assertIn(("unread_key", "/model"), kinds)

    def test_ask_beats_allow(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, "settings.json", {"permissions": {"allow": ["Bash"], "ask": ["Bash(*)"]}})
            self.assertEqual(IN.ingest(p).config.tool("Bash").mode, "ask")

    def test_bypass_makes_everything_allow(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, "settings.json", {"permissions": {"ask": ["Bash"], "defaultMode": "bypassPermissions"}})
            self.assertEqual(IN.ingest(p).config.tool("Bash").mode, "allow")

    def test_partial_ask_only_is_ask_with_note(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, "settings.json", {"permissions": {"ask": ["Bash(git push *)"]}})
            r = IN.ingest(p)
            self.assertEqual(r.config.tool("Bash").mode, "ask")
            self.assertTrue(any("一部だけ ask" in n.message for n in r.notes))


class Secrets(unittest.TestCase):
    def test_secrets_everywhere_never_leak(self):
        """I2：秘密らしき文字列をあらゆる欄に埋めても結果に現れない（200 例）。"""
        rng = random.Random(7)
        for i in range(200):
            s = rng.choice(SECRETS)
            kind = i % 3
            if kind == 0:
                data = {"mcpServers": {"x": {"command": rng.choice(["node", s]), "args": [s], "env": {"K": s},
                                             "url": f"https://u:{s}@h.example/{s}", "type": "http",
                                             "headers": {"H": s},
                                             "tools": [{"name": rng.choice(["t", s]), "description": s, "title": s}]}}}
                fn = "a.mcp.json"
            elif kind == 1:
                data = {"openapi": "3.1.0", "info": {"title": s}, "servers": [{"url": f"https://h/{s}"}],
                        "paths": {f"/{s}": {"get": {"operationId": rng.choice(["op", s]), "summary": s}}}}
                fn = "api.json"
            else:
                data = {"permissions": {"allow": [f"Bash(curl -H {s})", "Read"], "ask": [s]},
                        "env": {"TOKEN": s}, "apiKeyHelper": s}
                fn = "settings.json"
            with tempfile.TemporaryDirectory() as d:
                res = IN.ingest(write_tmp(d, fn, data))
            blob = repr(res)
            self.assertIsNone(SECRET_RE.search(blob), (i, kind))
            self.assertTrue(any(n.kind == "secret_discarded" for n in res.notes), (i, kind))


class Broken(unittest.TestCase):
    CASES = [
        ("broken.json", "{not json"),
        ("empty.json", ""),
        ("x.yaml", "openapi: 3.0.0"),
        ("arr.json", "[1,2,3]"),
        ("null.json", "null"),
        ("mcp.json", {"mcpServers": []}),
        ("api.json", {"openapi": "3.0.0", "paths": []}),
        ("api2.json", {"openapi": 3, "paths": {}}),
        ("settings.json", {"permissions": "x"}),
        ("deep.json", "[" * 5000 + "]" * 5000),
    ]

    def test_broken_inputs_raise_only_skopost_error(self):
        for fn, data in self.CASES:
            with self.subTest(fn=fn), tempfile.TemporaryDirectory() as d:
                with self.assertRaises(M.SkopostError):
                    IN.ingest(write_tmp(d, fn, data))

    def test_forced_adapter_on_wrong_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, "x.json", {"a": 1})
            for name in IN.ADAPTERS:
                with self.subTest(name=name), self.assertRaises(M.SkopostError):
                    IN.ingest(p, adapter=name)

    def test_missing_file(self):
        with self.assertRaises(M.SkopostError):
            IN.ingest("/nonexistent/skopost-x.json")

    def test_too_big(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, "big.json", '{"mcpServers": {}, "x": "' + "a" * (M.MAX_FILE_BYTES + 10) + '"}')
            with self.assertRaises(M.SkopostError):
                IN.ingest(p)

    def test_too_many_tools_refused_not_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            data = {"mcpServers": {f"s{i}": {"command": "x"} for i in range(M.MAX_TOOLS + 1)}}
            with self.assertRaises(M.SkopostError):
                IN.ingest(write_tmp(d, "a.mcp.json", data))

    def test_fuzz_mutations(self):
        """壊した入力でも例外は SkopostError だけ（各フィクスチャを 150 回ずつ乱す）。"""
        rng = random.Random(11)
        junk = [None, 0, -1, 1.5, "", "x", [], {}, [None], {"a": None}, True]

        def mutate(v, depth=0):
            if depth > 6 or rng.random() < 0.15:
                return rng.choice(junk)
            if isinstance(v, dict):
                out = {k: mutate(x, depth + 1) if rng.random() < 0.4 else x for k, x in v.items()}
                if rng.random() < 0.1:
                    out[rng.choice(["name", "tools", "type", "url", "allow", "get"])] = rng.choice(junk)
                return out
            if isinstance(v, list):
                return [mutate(x, depth + 1) if rng.random() < 0.4 else x for x in v]
            return v

        for name in IN.ADAPTERS:
            d0 = os.path.join(FX, name)
            for f in os.listdir(d0):
                with open(os.path.join(d0, f), encoding="utf-8") as fh:
                    base = json.load(fh)
                for _ in range(150):
                    data = mutate(base)
                    with tempfile.TemporaryDirectory() as d:
                        p = write_tmp(d, f, data)
                        try:
                            res = IN.ingest(p, adapter=name)
                        except M.SkopostError:
                            continue
                        self.assertIsInstance(res, M.IngestResult)
                        no_sure_caps(self, res)


class Merge(unittest.TestCase):
    def test_draft_then_manual(self):
        draft = IN.ingest(os.path.join(FX, "openapi", "petstore.json")).config
        manual = M.parse({"skopost": 2, "tools": [
            {"id": "listPets", "mode": "ask", "observed": {"net_out": {"value": True, "confidence": "確", "evidence": "読んだ"}}}]})
        out = IN.merge(draft, manual)
        t = out.tool("listPets")
        self.assertEqual(t.mode, "ask")
        self.assertEqual(t.label, "List pets")
        self.assertEqual(t.observed["net_out"].confidence, "確")
        self.assertEqual(len(out.tools), 4)
        self.assertEqual(out.imports, draft.imports)

    def test_stores_union_overlay_wins(self):
        a = M.Config(stores=(M.Store("s", "old"),))
        b = M.Config(stores=(M.Store("s", "new", external=True), M.Store("t")))
        out = IN.merge(a, b)
        self.assertEqual([(s.id, s.label) for s in out.stores], [("s", "new"), ("t", "")])


if __name__ == "__main__":
    unittest.main()
