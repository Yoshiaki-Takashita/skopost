"""openapi アダプタ：OpenAPI 3.x（JSON のみ。YAML は標準ライブラリに無いので非対応）。

出典：OpenAPI Specification 3.1.0 https://spec.openapis.org/oas/v3.1.0 （3.0.3 も同じ鍵：openapi・servers・paths・
Path Item の get/put/post/delete/options/head/patch/trace・operationId・summary・security・components.securitySchemes）。
確認日：2026-10-13（鍵名は 3.0 以来変わっていない。3.2 以降の追加の鍵は読まずに notes に出す）

1 操作 = 1 道具。読む事実（構文上）：method・path・servers が外部か・security の要求の有無。
副作用の実態は分からない（規則 infer.rules に任せる。ここでは札を作らない）。
"""
from __future__ import annotations

from typing import ClassVar

from ..model.constants import MAX_TOOLS
from ..model.errors import SkopostError
from ..model.types import Config, IngestResult, Tool
from .base import Notes, fact_text, has_secret, host_of, is_local_host, ptr, short_label

METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
PATH_ITEM_KEYS = set(METHODS) | {"summary", "description", "servers", "parameters", "$ref"}
TOP_KNOWN = {"openapi", "info", "servers", "paths", "components", "security", "tags", "externalDocs",
             "webhooks", "jsonSchemaDialect"}
OP_READ = {"operationId", "summary", "description", "security", "servers"}


def _servers_external(n: Notes, servers: object, p: str):
    """servers のどれかが外部なら True・全部手元なら False・分からなければ None。"""
    if not isinstance(servers, list) or not servers:
        return None
    ext = []
    for i, s in enumerate(servers):
        url = s.get("url") if isinstance(s, dict) else None
        if has_secret(url):
            n.secret(f"{p}/{i}/url", "servers の URL の中の秘密らしき文字列")
        host = host_of(url)
        local = is_local_host(host)
        if local is None:
            n.add("unread_key", f"{p}/{i}/url", "相対 URL かホスト名が読めない（外部かどうか不明）")
            ext.append(None)
        else:
            ext.append(not local)
    if any(e is True for e in ext):
        return True
    if all(e is False for e in ext):
        return False
    return None


class OpenApiAdapter:
    name: ClassVar[str] = "openapi"

    def sniff(self, data: object, filename: str) -> float:
        try:
            if not isinstance(data, dict):
                return 0.0
            v = data.get("openapi")
            if isinstance(v, str) and v.startswith("3."):
                return 0.95 if isinstance(data.get("paths"), dict) else 0.4
            if "swagger" in data:
                return 0.3
            return 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    def read(self, data: object, *, filename: str) -> IngestResult:
        if not isinstance(data, dict):
            raise SkopostError("openapi：最上位が対応表ではありません")
        v = data.get("openapi")
        if "swagger" in data and v is None:
            raise SkopostError("openapi：Swagger 2.0 は非対応です（OpenAPI 3.x の JSON だけ）")
        if not (isinstance(v, str) and v.startswith("3.")):
            raise SkopostError("openapi：`openapi` が 3.x の文字列ではありません")
        paths = data.get("paths")
        if not isinstance(paths, dict):
            raise SkopostError("openapi：`paths` の対応表がありません")
        n = Notes(self.name, filename)
        for k in data:
            if k not in TOP_KNOWN and not str(k).startswith("x-"):
                n.unread(ptr(k))
            elif str(k).startswith("x-") or k in ("webhooks", "tags", "externalDocs", "jsonSchemaDialect"):
                n.unread(ptr(k), "拡張・付帯情報の鍵は読みません")
        top_ext = _servers_external(n, data.get("servers"), "/servers")
        schemes = data.get("components", {}).get("securitySchemes") if isinstance(data.get("components"), dict) else None
        if isinstance(schemes, dict):
            n.add("assumption", "/components/securitySchemes", "securitySchemes は種類の有無だけ読み、値は読みません")
        top_sec = data.get("security")

        tools: list[Tool] = []
        for path, item in paths.items():
            ip = ptr("paths", path)
            if not isinstance(item, dict):
                n.drop(ip, "Path Item が対応表でないので捨てました")
                continue
            if "$ref" in item:
                n.add("unsupported", ip + "/$ref", "$ref は辿りません（外部ファイルを読まない）")
            for k in item:
                if k not in PATH_ITEM_KEYS:
                    n.unread(f"{ip}/{ptr(k)[1:]}")
            path_ext = _servers_external(n, item.get("servers"), ip + "/servers")
            for m in METHODS:
                op = item.get(m)
                if op is None:
                    continue
                op_p = f"{ip}/{m}"
                if not isinstance(op, dict):
                    n.drop(op_p, "操作が対応表でないので捨てました")
                    continue
                raw = op.get("operationId") if isinstance(op.get("operationId"), str) and op.get("operationId") else f"{m}_{path}"
                tid = n.tool_id(raw, op_p)
                for k in op:
                    if k not in OP_READ and k not in ("parameters", "requestBody", "responses", "tags", "deprecated",
                                                      "callbacks", "externalDocs"):
                        n.unread(f"{op_p}/{ptr(k)[1:]}")
                n.fact(tid, "openapi.method", m.upper(), op_p)
                # infer の規則が読む事実（鍵名は infer/rules.py の表に合わせる：name・description）
                if isinstance(op.get("operationId"), str) and op["operationId"] and not has_secret(op["operationId"]):
                    n.fact(tid, "name", op["operationId"][:200], op_p + "/operationId")
                for dk in ("summary", "description"):
                    dt = fact_text(op.get(dk))
                    if dt:
                        n.fact(tid, "description", dt, f"{op_p}/{dk}")
                n.fact(tid, "openapi.path", path[:1000] if not has_secret(path) else "", ip)
                ext = _servers_external(n, op.get("servers"), op_p + "/servers")
                if ext is None:
                    ext = path_ext if path_ext is not None else top_ext
                if ext is None:
                    n.add("assumption", op_p, "接続先が外部かどうか不明（servers が無いか読めない）")
                else:
                    n.fact(tid, "openapi.server_external", ext, op_p)
                sec = op.get("security", top_sec)
                if isinstance(sec, list):
                    n.fact(tid, "openapi.security_required", any(isinstance(s, dict) and s for s in sec), op_p)
                if "requestBody" in op:
                    n.fact(tid, "openapi.has_request_body", True, op_p + "/requestBody")
                tools.append(Tool(id=tid, label=short_label(op.get("summary") or ""), origin=n.origin(op_p)))
                if len(tools) > MAX_TOOLS:
                    raise SkopostError(f"openapi：操作が {MAX_TOOLS} 個を超えます（黙って削らずに止めました）")
        if not tools:
            n.add("assumption", "/paths", "操作がありませんでした")
        n.add("assumption", "", "OpenAPI に許可の欄は無いので mode は allow（関所なし）と置きました（危ない側）")
        info = data.get("info") if isinstance(data.get("info"), dict) else {}
        cfg = Config(name=short_label(info.get("title") or filename), tools=tuple(tools))
        return IngestResult(config=cfg, notes=tuple(n.notes), dropped=tuple(n.dropped), facts=tuple(n.facts))
