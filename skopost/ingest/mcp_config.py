"""mcp アダプタ：`mcpServers` 形式（Claude Desktop・Claude Code の `.mcp.json` 等）。

出典（確認日：2026-10-13）：
- Claude Code の MCP 文書 https://code.claude.com/docs/en/mcp.md
  （`mcpServers` の下に サーバー名 → {command, args, env} または {type: http|sse|ws, url, headers}。
   `type` が無い項目は stdio として読まれる。`type: "sdk"` は .mcp.json では読み飛ばされる）
- MCP 仕様 schema 2025-06-18 https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2025-06-18/schema.ts
  （Tool.annotations：title・readOnlyHint・destructiveHint・idempotentHint・openWorldHint。すべて任意の「ヒント」）

読むもの：サーバー名・接続の種類・起動コマンドの名前（引数の中身は読まない）・env と headers の**鍵名**（値は捨てる）・URL のホスト名。
`tools/list` の静的な写しは標準の置き場が無い。**本アダプタの仮定**として、サーバー項目の中の `tools`（MCP の Tool の配列）
だけを読む（notes に仮定と書く）。annotations は「ヒント」なので宣言（declared）の層に入れ、観察の札は作らない（不明のまま）。
サーバーには接続しない（外部通信なし）。
"""
from __future__ import annotations

from typing import Any, ClassVar

from ..model.constants import MAX_TOOLS
from ..model.errors import SkopostError
from ..model.types import Cap, Config, IngestResult, Tool
from .base import Notes, fact_names, fact_text, has_secret, host_of, is_local_host, ptr, short_label

SERVER_KEYS = {"command", "args", "env", "type", "url", "headers", "tools", "cwd"}
TOOL_KEYS = {"name", "title", "description", "inputSchema", "outputSchema", "annotations"}
ANNOTATION_KEYS = ("title", "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
TRANSPORTS = ("stdio", "http", "sse", "ws")
SRC = "ingest:mcp"


class McpConfigAdapter:
    name: ClassVar[str] = "mcp"

    def sniff(self, data: object, filename: str) -> float:
        try:
            if not isinstance(data, dict) or "mcpServers" not in data:
                return 0.0
            if not isinstance(data["mcpServers"], dict):
                return 0.1
            score = 0.9 if not ({"permissions", "openapi", "skopost"} & set(data)) else 0.6
            if str(filename).endswith(".mcp.json"):
                score = min(1.0, score + 0.05)
            return float(score)
        except Exception:  # noqa: BLE001
            return 0.0

    def read(self, data: object, *, filename: str) -> IngestResult:
        if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
            raise SkopostError("mcp：`mcpServers` の対応表がありません")
        n = Notes(self.name, filename)
        for k in data:
            if k != "mcpServers":
                n.unread(ptr(k))
        tools: list[Tool] = []
        for sname, srv in data["mcpServers"].items():
            p = ptr("mcpServers", sname)
            if not isinstance(srv, dict):
                n.drop(p, "サーバーの項目が対応表でないので捨てました")
                continue
            tools += self._server(n, sname, srv, p)
            if len(tools) > MAX_TOOLS:
                raise SkopostError(f"mcp：道具が {MAX_TOOLS} 個を超えます（黙って削らずに止めました）")
        if not tools:
            n.add("assumption", "/mcpServers", "読める道具がありませんでした")
        n.add("assumption", "", "MCP の設定に許可の欄は無いので mode は allow（関所なし）と置きました（危ない側）")
        cfg = Config(name=short_label(filename), tools=tuple(tools))
        return IngestResult(config=cfg, notes=tuple(n.notes), dropped=tuple(n.dropped), facts=tuple(n.facts))

    # ------------------------------------------------------------ サーバー 1 つ
    def _server(self, n: Notes, sname: str, srv: dict, p: str) -> list[Tool]:
        for k in srv:
            if k not in SERVER_KEYS:
                n.unread(ptr("mcpServers", sname, k))
        transport = srv.get("type", "stdio")
        if transport not in TRANSPORTS:
            if transport == "sdk":
                n.drop(p, "type が sdk のサーバーは設定ファイルからは登録されないので捨てました")
                return []
            n.add("unsupported", p + "/type", "知らない接続の種類です。stdio とも http とも決めません")
            transport = None
        if "url" in srv and "type" not in srv:
            n.add("assumption", p, "url があるのに type が無い（Claude Code は stdio と読み、この項目は失敗する）")

        sid = n.tool_id(sname, p)
        facts: list[tuple[str, Any, str]] = []
        if transport:
            facts.append(("mcp.server.transport", transport, p + "/type"))
        cmd = srv.get("command")
        if isinstance(cmd, str):
            if has_secret(cmd):
                n.secret(p + "/command", "起動コマンド")
            else:
                base = cmd.replace("\\", "/").rsplit("/", 1)[-1][:128]
                facts.append(("mcp.server.command", base, p + "/command"))
        elif cmd is not None:
            n.drop(p + "/command", "command が文字列でないので捨てました")
        args = srv.get("args")
        if isinstance(args, list):
            facts.append(("mcp.server.args_count", len(args), p + "/args"))
            if any(has_secret(a) for a in args):
                n.secret(p + "/args", "引数の中の秘密らしき文字列")
            n.add("assumption", p + "/args", "引数の中身は読みません（数だけ）")
        for key in ("env", "headers"):
            v = srv.get(key)
            if isinstance(v, dict):
                names = tuple(sorted(k for k in v if isinstance(k, str) and not has_secret(k)))[:64]
                facts.append((f"mcp.server.{key}_keys", names, p + "/" + key))
                if v:
                    n.secret(p + "/" + key, f"{key} の各項目")
            elif v is not None:
                n.drop(p + "/" + key, f"{key} が対応表でないので捨てました")
        if "url" in srv:
            host = host_of(srv["url"])
            local = is_local_host(host)
            if local is None:
                n.add("unread_key", p + "/url", "URL のホスト名が読めません（外部かどうか不明）")
            else:
                facts.append(("mcp.server.remote_host", not local, p + "/url"))
            if has_secret(srv["url"]):
                n.secret(p + "/url", "URL の中の秘密らしき文字列")

        listed = srv.get("tools")
        out: list[Tool] = []
        if isinstance(listed, list) and listed:
            n.add("assumption", p + "/tools", "サーバー項目の tools を tools/list の静的な写しとして読みました（本アダプタの仮定）")
            for i, t in enumerate(listed):
                tp = f"{p}/tools/{i}"
                if not isinstance(t, dict) or not isinstance(t.get("name"), str) or not t["name"]:
                    n.drop(tp, "name の無い道具を捨てました")
                    continue
                tid = n.tool_id(f"{sname}.{t['name']}", tp)
                for k, v, fp in facts:
                    n.fact(tid, k, v, fp)
                n.fact(tid, "mcp.server", sid, p)
                out.append(self._tool(n, tid, t, tp))
        else:
            if listed is not None and not isinstance(listed, list):
                n.drop(p + "/tools", "tools が配列でないので捨てました")
            for k, v, fp in facts:
                n.fact(sid, k, v, fp)
            n.add("assumption", p, "道具の一覧が無いので、サーバー全体を 1 つの道具として扱いました")
            out.append(Tool(id=sid, label="", origin=n.origin(p)))
        return out

    # ------------------------------------------------------------ 道具 1 つ
    def _tool(self, n: Notes, tid: str, t: dict, tp: str) -> Tool:
        for k in t:
            if k not in TOOL_KEYS:
                n.unread(tp + "/" + k)
        label = short_label(t.get("title") or t.get("description") or "")
        # infer の規則が読む事実（鍵名は infer/rules.py の表に合わせる：name・description・schema.properties）
        n.fact(tid, "name", t["name"][:200] if not has_secret(t["name"]) else "", tp + "/name")
        desc = fact_text(t.get("description"))
        if desc:
            n.fact(tid, "description", desc, tp + "/description")
        sch = t.get("inputSchema")
        props = fact_names(sch.get("properties")) if isinstance(sch, dict) else ()
        if props:
            n.fact(tid, "schema.properties", props, tp + "/inputSchema/properties")
        declared: dict[str, Cap] = {}
        ann = t.get("annotations")
        if isinstance(ann, dict):
            ap = tp + "/annotations"
            for k, v in ann.items():
                if k not in ANNOTATION_KEYS:
                    n.unread(f"{ap}/{k}", "知らない annotations の鍵です（読みません）")
                elif k != "title" and not isinstance(v, bool):
                    n.drop(f"{ap}/{k}", "ヒントが真偽値でないので捨てました")
                elif k != "title":
                    n.fact(tid, f"mcp.annotation.{k}", v, f"{ap}/{k}")
            # 宣言の層（作者の主張）。仕様上 destructive・idempotent は readOnlyHint が偽のときだけ意味を持つ。
            if ann.get("readOnlyHint") is True:
                declared["acts"] = Cap(frozenset(), None, "annotations.readOnlyHint=true", SRC)
                declared["writes_stores"] = Cap(frozenset(), None, "annotations.readOnlyHint=true", SRC)
            elif ann.get("readOnlyHint") is False and ann.get("destructiveHint") is not False:
                n.add("assumption", ap, "readOnlyHint が偽で destructiveHint が偽でない：破壊的な更新があり得る（宣言には入れず事実だけ）")
            if isinstance(ann.get("openWorldHint"), bool):
                declared["net_out"] = Cap(ann["openWorldHint"], None, f"annotations.openWorldHint={str(ann['openWorldHint']).lower()}", SRC)
        elif ann is not None:
            n.drop(tp + "/annotations", "annotations が対応表でないので捨てました")
        return Tool(id=tid, label=label, declared=declared, origin=n.origin(tp))
