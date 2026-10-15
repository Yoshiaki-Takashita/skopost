"""パッケージの版（SemVer）。CLI の互換を壊すのは 2.0.0 のときだけ（ARCHITECTURE §2.3）。

- 1.0.0：単一ファイル skopost.py（段 0 まで）
- 1.1.0.dev0：段 1（パッケージ化。CLI・終了コード・JSON 出力は 1.0.0 と同一）
"""
from __future__ import annotations

__version__ = "1.1.0.dev0"
