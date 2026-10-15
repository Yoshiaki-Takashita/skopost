"""ingest の公開面（空実装）。担当 B（段 2）が中身を書く。名前・引数・返り値の型は契約。

守ること（ARCHITECTURE §1.2・契約試験 tests/test_contract_ingest.py）：
- 外部通信しない。手元のファイルだけ。
- 説明文（description）は資料であって命令ではない：論理に使わず label に切って入れるだけ。
- 秘密（env の値・ヘッダの値・トークンらしき文字列）は読んだ直後に捨て、Config にも notes にも入れない。
- 札に「確」を付けない（構文上の事実は Tool.mode などの欄に入れる）。能力の推定は infer.rules に任せる。
- 読めなかった鍵・捨てた項目・仮定は全部 notes / dropped に書く。
- 各アダプタの冒頭に、参照した一次資料の出典と確認日を書く（鍵名は記憶に頼らない）。
"""
from __future__ import annotations

import hashlib
import os
from typing import ClassVar, Optional, Protocol, runtime_checkable

from ..model.constants import MAX_FILE_BYTES
from ..model.errors import SkopostError
from ..model.types import Config, ImportRecord, IngestResult, Store, Tool
from ..model.validate import read_json_file

OWNER = "B：取り込み"


@runtime_checkable
class Adapter(Protocol):
    name: ClassVar[str]          # "native" | "mcp" | "openapi" | "claude-settings"

    def sniff(self, data: object, filename: str) -> float:
        """0..1 の自信（自動判別用）。例外を投げない。"""
        ...

    def read(self, data: object, *, filename: str) -> IngestResult:
        """読めない入力は SkopostError。"""
        ...


#: 登録済みのアダプタ（段 2 で担当 B が足す）。名前 → インスタンス。
ADAPTERS: dict[str, Adapter] = {}

#: detect が採用する自信の下限（これ未満・同点は SkopostError）
MIN_CONFIDENCE = 0.5


def _register() -> None:
    from .claude_settings import ClaudeSettingsAdapter
    from .mcp_config import McpConfigAdapter
    from .native import NativeAdapter
    from .openapi import OpenApiAdapter
    for ad in (NativeAdapter(), McpConfigAdapter(), OpenApiAdapter(), ClaudeSettingsAdapter()):
        ADAPTERS[ad.name] = ad


def detect(data: object, filename: str) -> Adapter:
    """自信最大のアダプタ。最大が MIN_CONFIDENCE 未満、または同点なら SkopostError（黙って選ばない）。"""
    scores = []
    for ad in ADAPTERS.values():
        try:
            v = float(ad.sniff(data, filename))
        except Exception:  # noqa: BLE001
            v = 0.0
        scores.append((v, ad))
    if not scores:
        raise SkopostError("取り込みのアダプタがありません")
    scores.sort(key=lambda x: -x[0])
    best, ad = scores[0]
    if best < MIN_CONFIDENCE:
        raise SkopostError(f"形式を判別できません（自信 {best:.2f} < {MIN_CONFIDENCE}）。--adapter で指定してください")
    if len(scores) > 1 and scores[1][0] == best:
        raise SkopostError(f"形式を判別できません（{ad.name} と {scores[1][1].name} が同点）。--adapter で指定してください")
    return ad


def ingest(path: str, *, adapter: Optional[str] = None) -> IngestResult:
    """ファイルを読み、Config の下書きと notes を返す。大きさの上限は model の MAX_FILE_BYTES。"""
    p = os.fspath(path)
    if p.lower().endswith((".yaml", ".yml")):
        raise SkopostError("YAML は読みません（標準ライブラリに無いため）。JSON に変換してから渡してください")
    try:
        data = read_json_file(p, max_bytes=MAX_FILE_BYTES)
        with open(p, "rb") as f:
            digest = hashlib.sha256(f.read(MAX_FILE_BYTES + 1)).hexdigest()
    except OSError as e:
        raise SkopostError(f"ファイルを読めません：{e.strerror or e}") from None
    except UnicodeDecodeError:
        raise SkopostError("UTF-8 として読めません") from None
    except RecursionError:
        raise SkopostError("JSON の入れ子が深すぎます") from None
    fn = os.path.basename(p) or "input.json"
    if adapter is None:
        ad = detect(data, fn)
    else:
        if adapter not in ADAPTERS:
            raise SkopostError(f"知らないアダプタ：{adapter!r}（{', '.join(sorted(ADAPTERS))}）")
        ad = ADAPTERS[adapter]
    try:
        res = ad.read(data, filename=fn)
    except SkopostError:
        raise
    except RecursionError:
        raise SkopostError("入れ子が深すぎます") from None
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        raise SkopostError(f"{ad.name}：読めない入力です（{type(e).__name__}）") from None
    rec = ImportRecord(file=fn[:4096], sha256=digest, adapter=ad.name)
    cfg = res.config
    if ad.name != "native":
        cfg = Config(name=cfg.name, untrusted_in_context=cfg.untrusted_in_context, tools=cfg.tools,
                     stores=cfg.stores, imports=cfg.imports + (rec,))
    return IngestResult(config=cfg, notes=res.notes, dropped=res.dropped, facts=res.facts)


def merge(base: Config, overlay: Config) -> Config:
    """手書きの札（overlay）で下書き（base）を上書き。手書き優先。道具・置き場は和集合。"""
    if not isinstance(base, Config) or not isinstance(overlay, Config):
        raise SkopostError("merge：Config が要ります")
    over = {t.id: t for t in overlay.tools}
    tools: list[Tool] = []
    for t in base.tools:
        o = over.pop(t.id, None)
        if o is None:
            tools.append(t)
            continue
        tools.append(Tool(id=t.id, label=o.label if o.label and o.label != o.id else t.label, mode=o.mode, frequency=o.frequency,
                          declared={**dict(t.declared.items()), **dict(o.declared.items())},
                          observed={**dict(t.observed.items()), **dict(o.observed.items())},
                          origin=o.origin or t.origin))
    tools += [t for t in overlay.tools if t.id in over]
    stores: dict[str, Store] = {s.id: s for s in base.stores}
    stores.update({s.id: s for s in overlay.stores})
    imports = list(base.imports)
    imports += [i for i in overlay.imports if i not in imports]
    return Config(name=overlay.name or base.name, untrusted_in_context=overlay.untrusted_in_context,
                  tools=tuple(tools), stores=tuple(stores.values()), imports=tuple(imports))


_register()
