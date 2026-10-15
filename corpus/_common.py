"""corpus の試験の共通部品（標準ライブラリのみ）。"""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import gen  # noqa: E402


def manifest() -> dict:
    with open(os.path.join(gen.REAL_DIR, "MANIFEST.json"), encoding="utf-8") as f:
        return json.load(f)


def load_real(rel: str):
    with open(os.path.join(gen.REAL_DIR, rel), encoding="utf-8") as f:
        return json.load(f)


class TmpFiles:
    """一時ディレクトリに JSON を書いて道を返す（試験の終わりに消す）。"""

    def __init__(self) -> None:
        self.dir = tempfile.TemporaryDirectory(prefix="skopost-corpus-")

    def write(self, name: str, data, raw: bytes | None = None) -> str:
        p = os.path.join(self.dir.name, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(raw if raw is not None else json.dumps(data, ensure_ascii=False).encode("utf-8"))
        return p

    def close(self) -> None:
        self.dir.cleanup()
