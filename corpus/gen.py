#!/usr/bin/env python3
"""評価用コーパスの生成器（段 3・担当 F）。標準ライブラリのみ・外部通信なし・種で決定的。

2 種類を作る。

1. 合成（synth）：SPEC v1 の native 構成。道具 10〜64 個。``synth(seed, n, i)`` は (種, 道具数, 番号) だけで決まる。
2. 実例風（real）：MCP の設定・OpenAPI 3.x・Claude Code の settings.json を各 24 件。**すべて自作の合成**
   （実在の第三者の設定は写さない。ホスト名は example.com/example.org/localhost だけ）。各ファイルに
   「その形式の読み手が解釈しない鍵」を 0〜3 個植え、植えた場所（JSON Pointer）を MANIFEST.json に記録する
   （ingest の「読めなかった鍵の記録率」の正解表）。

  python3 corpus/gen.py real --write     # corpus/real/ を作り直す（同じ種なら同じバイト列）
  python3 corpus/gen.py synth --n 16     # 合成を 1 件標準出力へ

既定の種：SEED = 20261013（PREREG.md と同じ）。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REAL_DIR = os.path.join(HERE, "real")

SEED = 20261013
N_MIN, N_MAX = 10, 64
N_REAL = 24  # 形式ごとの件数（要件は 20 件以上）

ACT_KINDS = ("send", "purchase", "delete", "publish", "grant", "pay")
BOOL_CAPS = ("reads_untrusted", "reads_secret", "net_out", "exec", "args_leave")


def rng_for(*parts: object) -> random.Random:
    """文字列の種（random は str を sha512 で種にするので Python の hash 乱数化に依らず決定的）。"""
    return random.Random(":".join(str(p) for p in parts))


# ============================================================ 1. 合成（native）
def synth(seed: int, n: int, i: int = 0, *, p_unknown: float = 0.15, p_store_unknown: float = 0.15) -> dict:
    """SPEC v1 の正しい入力（辞書）。道具 n 個（10〜64）。

    分布（推）：読むだけの道具が多く、秘密を読む 25%・ネット 20%・実行 7%・操作 10%。置き場は 3〜5 個で、
    書く／読むの札は 30% の道具が持つ。観察の札は宣言の写しに「宣言に無い能力」を 10% で 1 つ足し、
    真偽の札は p_unknown、置き場の札は p_store_unknown で不明にする。mode は 75% allow。
    """
    if not (N_MIN <= n <= N_MAX):
        raise ValueError(f"n は {N_MIN}〜{N_MAX}")
    r = rng_for("synth", seed, n, i)
    n_stores = r.randint(3, 5)
    stores = []
    for k in range(n_stores):
        stores.append({"id": f"s{k}", "label": f"置き場{k}", "external": r.random() < 0.3,
                       "executes": r.random() < 0.2, "secret": r.random() < 0.3})
    sids = [s["id"] for s in stores]
    tools = []
    for t in range(n):
        dec = {"reads_untrusted": r.random() < 0.5, "reads_secret": r.random() < 0.25, "net_out": r.random() < 0.20,
               "exec": r.random() < 0.07, "args_leave": r.random() < 0.05,
               "acts": sorted(r.sample(ACT_KINDS, 1)) if r.random() < 0.10 else [],
               "writes_stores": sorted(r.sample(sids, 1)) if r.random() < 0.3 else [],
               "reads_stores": sorted(r.sample(sids, 1)) if r.random() < 0.3 else []}
        obs_v = {k: (list(v) if isinstance(v, list) else v) for k, v in dec.items()}
        if r.random() < 0.10:
            kind = r.choice(("args_leave", "net_out", "exec", "reads_secret", "acts", "writes_stores"))
            if kind == "acts":
                obs_v["acts"] = sorted(set(obs_v["acts"]) | {r.choice(ACT_KINDS)})
            elif kind == "writes_stores":
                obs_v["writes_stores"] = sorted(set(obs_v["writes_stores"]) | {r.choice(sids)})
            else:
                obs_v[kind] = True
        observed = {k: {"value": v, "confidence": r.choice(("確", "論", "推")), "evidence": "synthetic"}
                    for k, v in obs_v.items()}
        for k in BOOL_CAPS + ("acts",):  # 乱数を引く回数を固定（分布を変えても系列がずれにくい）
            if r.random() < p_unknown:
                observed[k] = {"confidence": "不明", "evidence": "synthetic"}
        for k in ("writes_stores", "reads_stores"):
            if r.random() < p_store_unknown:
                observed[k] = {"confidence": "不明", "evidence": "synthetic"}
        tools.append({"id": f"t{t}", "label": f"道具{t}", "mode": "allow" if r.random() < 0.75 else "ask",
                      "frequency": r.randint(1, 9), "declared": dec, "observed": observed})
    return {"skopost": 1, "name": f"synth-{seed}-{n}-{i}", "untrusted_in_context": True,
            "stores": stores, "tools": tools}


def synth_corpus(seed: int = SEED, sizes=(10, 16, 24, 32, 48, 64), per_size: int = 20):
    """(名前, 辞書) の並び。"""
    for n in sizes:
        for i in range(per_size):
            yield f"synth-n{n}-{i}", synth(seed, n, i)


# ============================================================ 2. 実例風（自作の合成）
def pointer(*parts: object) -> str:
    """RFC 6901（正解表は読み手の実装から独立に作る）。"""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


# 架空の道具の語彙（領域 → (名前, 説明, 読むだけか, 壊すか, 外の世界か, 引数)）
VOCAB = {
    "notes": [("search_notes", "Search notes by keyword.", True, False, False, ["query", "limit"]),
              ("create_note", "Create a new note.", False, False, False, ["title", "body"]),
              ("delete_note", "Delete a note permanently.", False, True, False, ["id"])],
    "files": [("read_file", "Read a file from the workspace.", True, False, False, ["path"]),
              ("write_file", "Write text to a file in the workspace.", False, True, False, ["path", "content"]),
              ("list_dir", "List entries of a directory.", True, False, False, ["path"])],
    "web": [("fetch_page", "Fetch a web page and return its text.", True, False, True, ["url"]),
            ("search_web", "Search the web and return result snippets.", True, False, True, ["query"])],
    "mail": [("list_inbox", "List recent messages in the inbox.", True, False, True, ["folder", "limit"]),
             ("send_message", "Send an email message to a recipient.", False, False, True, ["to", "subject", "body"])],
    "calendar": [("list_events", "List calendar events in a range.", True, False, False, ["start", "end"]),
                 ("create_event", "Create a calendar event and invite attendees.", False, False, True, ["title", "attendees"])],
    "shell": [("run_command", "Run a shell command in the project directory.", False, True, False, ["command"])],
    "git": [("git_status", "Show the working tree status.", True, False, False, []),
            ("git_push", "Push the current branch to the remote.", False, False, True, ["remote", "branch"])],
    "db": [("query_db", "Run a read-only SQL query.", True, False, False, ["sql"]),
           ("drop_table", "Drop a database table.", False, True, False, ["table"])],
    "tickets": [("search_tickets", "Search support tickets.", True, False, True, ["query"]),
                ("post_comment", "Post a public comment on a ticket.", False, False, True, ["ticket", "text"])],
    "payments": [("list_invoices", "List invoices for the account.", True, False, True, ["status"]),
                 ("refund_payment", "Refund a payment to the customer.", False, True, True, ["payment", "amount"])],
    "vault": [("get_secret", "Read a named credential from the local vault.", True, False, False, ["name"])],
}
UNKNOWN_SERVER_KEYS = ("disabled", "timeoutMs", "autoApprove", "restartPolicy", "displayName")
UNKNOWN_TOOL_KEYS = ("category", "costHint", "version", "examples")
UNKNOWN_ANNOT_KEYS = ("networkHint", "costlyHint", "experimentalHint")
UNKNOWN_TOP_MCP = ("version", "defaults", "profile")


def _mcp_tool(r: random.Random, spec, plants: list, p: str) -> dict:
    name, desc, ro, destr, world, args = spec
    t: dict = {"name": name, "description": desc,
               "inputSchema": {"type": "object", "properties": {a: {"type": "string"} for a in args}}}
    if r.random() < 0.7:
        ann = {"readOnlyHint": ro, "openWorldHint": world}
        if not ro:
            ann["destructiveHint"] = destr
        if r.random() < 0.15:
            k = r.choice(UNKNOWN_ANNOT_KEYS)
            ann[k] = True
            plants.append(p + pointer("annotations", k))
        t["annotations"] = ann
    if r.random() < 0.12:
        k = r.choice(UNKNOWN_TOOL_KEYS)
        t[k] = "x"
        plants.append(p + pointer(k))
    return t


def make_mcp(i: int, seed: int = SEED) -> tuple[str, dict, list]:
    r = rng_for("mcp", seed, i)
    plants: list[str] = []
    servers: dict = {}
    for dom in r.sample(sorted(VOCAB), r.randint(1, 4)):
        p = pointer("mcpServers", dom)
        srv: dict = {}
        kind = r.random()
        if kind < 0.6:
            srv["command"] = r.choice(("node", "python3", "npx", "uvx", "./bin/server"))
            srv["args"] = [f"./servers/{dom}/main"] if srv["command"] != "npx" else ["-y", f"example-{dom}-server"]
            if r.random() < 0.3:
                srv["env"] = {"LOG_LEVEL": "info"}
        else:
            srv["type"] = r.choice(("http", "sse"))
            srv["url"] = r.choice((f"https://{dom}.example.com/mcp", f"http://localhost:{r.randint(3000, 9000)}/mcp",
                                   f"https://mcp.example.org/{dom}"))
            if r.random() < 0.3:
                srv["headers"] = {"X-Client": "corpus"}
        if r.random() < 0.85:
            specs = r.sample(VOCAB[dom], r.randint(1, len(VOCAB[dom])))
            srv["tools"] = [_mcp_tool(r, s, plants, p + pointer("tools", j)) for j, s in enumerate(specs)]
        if r.random() < 0.2:
            k = r.choice(UNKNOWN_SERVER_KEYS)
            srv[k] = False if k == "disabled" else "x"
            plants.append(p + pointer(k))
        servers[dom] = srv
    data: dict = {"mcpServers": servers}
    if r.random() < 0.15:
        k = r.choice(UNKNOWN_TOP_MCP)
        data[k] = 1
        plants.append(pointer(k))
    fn = f"mcp-{i:02d}.mcp.json" if i % 3 else f"mcp-{i:02d}.json"
    return fn, data, plants


OA_METHOD_FOR = {True: "get", False: "post"}
UNKNOWN_OP_KEYS = ("rateLimit", "owner", "stability")
UNKNOWN_ITEM_KEYS = ("visibility", "cacheTtl")
UNKNOWN_TOP_OA = ("generator", "contact")


def make_openapi(i: int, seed: int = SEED) -> tuple[str, dict, list]:
    r = rng_for("openapi", seed, i)
    plants: list[str] = []
    dom = r.choice(sorted(VOCAB))
    data: dict = {"openapi": r.choice(("3.0.3", "3.1.0", "3.0.1")),
                  "info": {"title": f"Synthetic {dom} API", "version": str(r.randint(1, 9))}}
    if r.random() < 0.8:
        data["servers"] = [{"url": r.choice((f"https://api.example.com/{dom}", "http://localhost:8080",
                                             f"https://{dom}.example.org/v1"))}]
    paths: dict = {}
    specs = list(VOCAB[dom]) + r.sample([s for d in sorted(VOCAB) for s in VOCAB[d] if d != dom], r.randint(0, 3))
    for name, desc, ro, destr, world, args in specs:
        path = "/" + name.split("_", 1)[-1] + ("/{id}" if destr else "")
        method = "delete" if destr and r.random() < 0.6 else OA_METHOD_FOR[ro]
        item = paths.setdefault(path, {})
        if method in item:
            continue
        op: dict = {"operationId": name, "summary": desc}
        if args and method == "get":
            op["parameters"] = [{"name": a, "in": "query", "schema": {"type": "string"}} for a in args]
        elif args:
            op["requestBody"] = {"content": {"application/json": {"schema": {
                "type": "object", "properties": {a: {"type": "string"} for a in args}}}}}
        op["responses"] = {"200": {"description": "ok"}}
        ip = pointer("paths", path)
        if r.random() < 0.08:
            k = r.choice(UNKNOWN_OP_KEYS)
            op[k] = "x"
            plants.append(ip + pointer(method, k))
        if r.random() < 0.08:
            op["x-internal"] = True
            plants.append(ip + pointer(method, "x-internal"))
        item[method] = op
        if r.random() < 0.06:
            k = r.choice(UNKNOWN_ITEM_KEYS)
            item[k] = "x"
            plants.append(ip + pointer(k))
        if r.random() < 0.06:
            item["x-team"] = "corpus"
            plants.append(ip + pointer("x-team"))
    data["paths"] = paths
    if r.random() < 0.3:
        data["components"] = {"securitySchemes": {"key": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}}}
        data["security"] = [{"key": []}]
    if r.random() < 0.2:
        k = r.choice(UNKNOWN_TOP_OA)
        data[k] = "x"
        plants.append(pointer(k))
    if r.random() < 0.2:
        data["x-logo"] = "corpus"
        plants.append(pointer("x-logo"))
    return f"openapi-{i:02d}.json", data, plants


CLAUDE_TOOLS = ("Read", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch", "Bash", "NotebookEdit")
BASH_RULES = ("Bash(npm test)", "Bash(npm run build)", "Bash(git status)", "Bash(git diff *)", "Bash(git push *)",
              "Bash(make *)", "Bash(rm *)", "Bash(curl *)", "Bash(python3 *)")
UNKNOWN_TOP_CLAUDE = ("themeColor", "telemetryProfile", "editorHints")
UNKNOWN_PERM_CLAUDE = ("review", "temporary")


def make_claude(i: int, seed: int = SEED) -> tuple[str, dict, list]:
    r = rng_for("claude", seed, i)
    plants: list[str] = []
    pool = list(CLAUDE_TOOLS) + list(BASH_RULES) + ["WebFetch(domain:docs.example.com)", "Read(./.env)",
                                                    "mcp__notes__search_notes", "mcp__mail__send_message"]
    r.shuffle(pool)
    a, b, c = r.randint(1, 6), r.randint(0, 3), r.randint(0, 2)
    perms: dict = {"allow": pool[:a]}
    if b:
        perms["ask"] = pool[a:a + b]
    if c:
        perms["deny"] = pool[a + b:a + b + c]
    if r.random() < 0.5:
        perms["defaultMode"] = r.choice(("default", "acceptEdits", "plan"))
    if r.random() < 0.15:
        k = r.choice(UNKNOWN_PERM_CLAUDE)
        perms[k] = []
        plants.append(pointer("permissions", k))
    data: dict = {"permissions": perms}
    if r.random() < 0.2:
        k = r.choice(UNKNOWN_TOP_CLAUDE)
        data[k] = "x"
        plants.append(pointer(k))
    if r.random() < 0.15:
        data["model"] = "default"  # 実在の鍵だが、この読み手は解釈しない（読まない鍵として記録されるべき）
        plants.append(pointer("model"))
    fn = ("settings.json", "settings.local.json", f"claude-{i:02d}.json")[i % 3]
    return f"claude-{i:02d}/{fn}" if i % 3 != 2 else fn, data, plants


MAKERS = {"mcp": make_mcp, "openapi": make_openapi, "claude-settings": make_claude}


def real_corpus(seed: int = SEED, n: int = N_REAL):
    """(相対パス, 形式, 辞書, 植えた鍵) の並び。"""
    for fmt, mk in MAKERS.items():
        for i in range(n):
            fn, data, plants = mk(i, seed)
            yield f"{fmt}/{fn}", fmt, data, plants


def write_real(seed: int = SEED, out: str = REAL_DIR) -> dict:
    manifest = {"seed": seed, "note": "すべて自作の合成。実在の第三者の設定は写していない。生成：corpus/gen.py real --write",
                "files": {}}
    for rel, fmt, data, plants in real_corpus(seed):
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        manifest["files"][rel] = {"format": fmt, "planted_unread": plants}
    with open(os.path.join(out, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("real")
    a.add_argument("--write", action="store_true")
    a.add_argument("--seed", type=int, default=SEED)
    s = sub.add_parser("synth")
    s.add_argument("--n", type=int, default=16)
    s.add_argument("--i", type=int, default=0)
    s.add_argument("--seed", type=int, default=SEED)
    ns = ap.parse_args(argv)
    if ns.cmd == "synth":
        json.dump(synth(ns.seed, ns.n, ns.i), sys.stdout, ensure_ascii=False, indent=1)
        print()
    elif ns.write:
        m = write_real(ns.seed)
        print(f"{len(m['files'])} 件を {REAL_DIR} に書きました")
    else:
        for rel, fmt, _d, plants in real_corpus(ns.seed):
            print(rel, fmt, len(plants))
    return 0


if __name__ == "__main__":
    sys.exit(main())
