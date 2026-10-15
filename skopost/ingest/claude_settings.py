"""claude-settings アダプタ：Claude Code の settings.json（`.claude/settings.json`・`settings.local.json`・`~/.claude/settings.json`）。

出典（確認日：2026-10-13）：
- https://code.claude.com/docs/en/permissions.md
  （規則は `Tool` か `Tool(specifier)`。評価順は deny → ask → allow で最初の一致が勝つ。`Bash(*)` は `Bash` と同じ。
   素の道具名の deny は道具を文脈から外す。範囲つきの deny は道具を残す。`mcp__` の規則に括弧があると読み飛ばされる。
   `*` はワイルドカード）
- https://code.claude.com/docs/en/settings-reference.md
  （`permissions.allow`・`permissions.ask`・`permissions.deny`・`permissions.defaultMode`
   ＝ default|acceptEdits|plan|auto|dontAsk|bypassPermissions|manual・`permissions.additionalDirectories`・`hooks`・`env`）
- 文書自身が「鍵は版で変わる」と書いているので、ここに無い鍵は読まずに notes（unread_key）に出す。

読むもの（構文上の事実＝確として Tool.mode に入れる）：道具ごとの mode（allow／ask／deny→除外）。
パターンが実際に何に一致するかは分からない：広い方（危ない側）に読む。
hooks は解釈しない（PreToolUse フックが許可・拒否を変え得る＝notes に不明と書く）。env の値は捨てる。
"""
from __future__ import annotations

import re
from typing import ClassVar

from ..model.constants import MAX_TOOLS
from ..model.errors import SkopostError
from ..model.types import Config, IngestResult, Tool
from .base import Notes, has_secret, ptr

RULE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)(?:\((.*)\))?$", re.S)
LISTS = ("deny", "ask", "allow")          # 評価順
PERM_KNOWN = {"allow", "ask", "deny", "defaultMode", "additionalDirectories"}
DEFAULT_MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions", "manual")


class ClaudeSettingsAdapter:
    name: ClassVar[str] = "claude-settings"

    def sniff(self, data: object, filename: str) -> float:
        try:
            if not isinstance(data, dict):
                return 0.0
            fn = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
            named = fn in ("settings.json", "settings.local.json", "managed-settings.json")
            if isinstance(data.get("permissions"), dict):
                return 0.95 if named else 0.85
            if "permissions" in data:
                return 0.2
            if named and isinstance(data.get("hooks"), dict):
                return 0.6
            return 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    def read(self, data: object, *, filename: str) -> IngestResult:
        if not isinstance(data, dict):
            raise SkopostError("claude-settings：最上位が対応表ではありません")
        if "permissions" not in data:
            raise SkopostError("claude-settings：`permissions` がありません（許可の規則が無いと何も読めません）")
        perms = data["permissions"]
        if not isinstance(perms, dict):
            raise SkopostError("claude-settings：`permissions` が対応表ではありません")
        n = Notes(self.name, filename)
        for k, v in data.items():
            if k == "permissions":
                continue
            if k == "env" and isinstance(v, dict):
                if v:
                    n.secret("/env", "env の各項目")
            elif k == "hooks":
                n.add("unsupported", "/hooks", "hooks は解釈しません。PreToolUse フックが許可・拒否を変え得るので、mode は不明の分を含みます")
            elif k == "mcpServers":
                n.unread("/mcpServers", "MCP サーバーの定義は読みません（--adapter mcp で別に取り込んでください）")
            elif k == "apiKeyHelper":
                n.secret("/apiKeyHelper", "apiKeyHelper")
            else:
                n.unread(ptr(k))
        for k in perms:
            if k not in PERM_KNOWN:
                n.unread(ptr("permissions", k))
        if "additionalDirectories" in perms:
            n.unread("/permissions/additionalDirectories", "追加の作業ディレクトリは置き場として読みません")

        # 道具名 → {"deny": [...], "ask": [...], "allow": [...]}（指定子。"" は素の道具名）
        rules: dict[str, dict[str, list[str]]] = {}
        order: list[str] = []
        where: dict[str, list[tuple[str, str, str]]] = {}
        for lst in LISTS:
            arr = perms.get(lst)
            if arr is None:
                continue
            lp = ptr("permissions", lst)
            if not isinstance(arr, list):
                n.drop(lp, f"permissions.{lst} が配列でないので捨てました")
                continue
            for i, r in enumerate(arr):
                rp = f"{lp}/{i}"
                if not isinstance(r, str):
                    n.drop(rp, "規則が文字列でないので捨てました")
                    continue
                if has_secret(r):
                    n.secret(rp, "規則の中の秘密らしき文字列")
                    n.dropped.append(rp)  # 値は notes に入れない
                    continue
                m = RULE_RE.match(r.strip())
                if not m:
                    n.drop(rp, "規則の形（Tool か Tool(指定子)）に合わないので捨てました", "unsupported")
                    continue
                tool, spec = m.group(1), m.group(2)
                if tool.startswith("mcp__") and spec is not None:
                    n.drop(rp, "mcp__ の規則に括弧があると Claude Code は読み飛ばすので捨てました")
                    continue
                spec = "" if spec is None or spec.strip() == "*" else spec
                if tool not in rules:
                    rules[tool] = {k: [] for k in LISTS}
                    order.append(tool)
                rules[tool][lst].append(spec)
                where.setdefault(tool, []).append((lst, spec[:500], rp))
                if "*" in spec:
                    n.add("assumption", rp, "ワイルドカードは広い方（危ない側）に読みました")

        dm = perms.get("defaultMode")
        if dm is not None and dm not in DEFAULT_MODES:
            n.add("unsupported", "/permissions/defaultMode", "知らない defaultMode です（意味を決めません）")
        bypass = dm in ("bypassPermissions", "auto")
        if bypass:
            n.add("assumption", "/permissions/defaultMode",
                  "defaultMode が確認なしで走る種類なので、拒否されていない道具は全部 allow と読みました（危ない側。"
                  "この値が project・local の設定からは効かないことは区別しません）")

        tools: list[Tool] = []
        for tool in order:
            r = rules[tool]
            tid = n.tool_id(tool, "/permissions")
            tp = "/permissions"
            if "" in r["deny"]:
                n.drop(tp + "/deny", f"{tid}：素の道具名の deny は道具を外すので除外しました")
                continue
            if r["deny"]:
                n.add("assumption", tp + "/deny", f"{tid}：範囲つきの deny は道具を残すので、残りの呼び出しで判断しました")
            if bypass:
                mode = "allow"
            elif "" in r["ask"]:
                mode = "ask"
            elif r["allow"]:
                mode = "allow"
                if "" not in r["allow"]:
                    n.add("assumption", tp + "/allow", f"{tid}：一部だけ allow の道具を allow と読みました（危ない側）")
            else:
                mode = "ask"
                n.add("assumption", tp + "/ask", f"{tid}：一部だけ ask の道具。一致しない呼び出しは既定の扱い（不明）")
            for lst, spec, rp in where[tool]:
                n.fact(tid, "claude.permission", (lst, spec), rp)
            n.fact(tid, "claude.mode", mode, tp)
            # infer の規則（R-CLAUDE-TOOL）が読む事実：Claude Code の道具名
            n.fact(tid, "claude.tool", tool[:200], tp)
            tools.append(Tool(id=tid, label="" if tool == tid else tool, mode=mode, origin=n.origin(tp)))
            if len(tools) > MAX_TOOLS:
                raise SkopostError(f"claude-settings：道具が {MAX_TOOLS} 個を超えます（黙って削らずに止めました）")
        n.add("assumption", "", "settings に出てこない道具は不明（ここには載せません）")
        cfg = Config(name="claude-settings", tools=tuple(tools))
        return IngestResult(config=cfg, notes=tuple(n.notes), dropped=tuple(n.dropped), facts=tuple(n.facts))

