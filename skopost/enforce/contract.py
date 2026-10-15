"""enforce の契約（型と Protocol だけ。**実装は無い**）。

利用者の承認（2026-10-13）：enforce 層は作ってよい。ただし防御専用・既定ドライラン・締める方向のみ。段 1 では型と
契約までで、実装クラスは作らない。

将来の実装が守ること（tests/test_contract_enforce.py が型の上で守れる部分を確かめる）：
1. **締める方向だけ**：allow → ask の移し替えのみ。緩める変更（ask → allow、deny の削除、確認の撤去）は
   `PlannedChange` で表せない（生成時に ValueError）。
2. **既定ドライラン**：`EnforcementPlan.dry_run` の既定は True。`plan()` は何も書かない。
3. 適用には `--apply` と、計画の内容から計算した確認文字列の手入力を要求する。適用前に元ファイルの複製を残し、
   上書き前に差分を表示する。
4. 外部通信なし・他人のシステムに触れない。実行時の遮断（フックで道具呼び出しを止める等）はこの契約の外。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from ..model.constants import ID_RE, SHA256_RE
from ..model.errors import NotImplementedYet
from ..model.types import Checkpoints, Config

Target = Literal["claude-settings"]      # 最初の対象案（他の対象は未定＝不明）
TARGETS: tuple[str, ...] = ("claude-settings",)


@dataclass(frozen=True, slots=True)
class PlannedChange:
    """1 つの変更。before は "allow"、after は "ask" に固定（それ以外は生成できない）。"""
    tool_id: str
    file: str
    pointer: str                         # 変更する箇所の JSON Pointer
    before: Literal["allow"] = "allow"
    after: Literal["ask"] = "ask"

    def __post_init__(self) -> None:
        if not (isinstance(self.tool_id, str) and ID_RE.match(self.tool_id)):
            raise ValueError(f"PlannedChange.tool_id が不正：{self.tool_id!r}")
        if not (isinstance(self.file, str) and self.file):
            raise ValueError("PlannedChange.file が要る")
        if not (isinstance(self.pointer, str) and (self.pointer == "" or self.pointer.startswith("/"))):
            raise ValueError("PlannedChange.pointer は JSON Pointer")
        if self.before != "allow" or self.after != "ask":
            raise ValueError("enforce は締める方向（allow → ask）だけを表せます")


@dataclass(frozen=True, slots=True)
class EnforcementPlan:
    target: Target
    changes: tuple[PlannedChange, ...]
    source_sha256: str                   # 計画を作った時点の対象ファイルの sha256（適用時に一致を確かめる）
    dry_run: bool = True

    def __post_init__(self) -> None:
        if self.target not in TARGETS:
            raise ValueError(f"EnforcementPlan.target は {TARGETS} のどれか")
        if not isinstance(self.changes, tuple) or not all(isinstance(c, PlannedChange) for c in self.changes):
            raise ValueError("EnforcementPlan.changes は PlannedChange の tuple")
        if len({c.tool_id for c in self.changes}) != len(self.changes):
            raise ValueError("同じ道具への変更が重複")
        if not (isinstance(self.source_sha256, str) and SHA256_RE.match(self.source_sha256)):
            raise ValueError("source_sha256 は小文字 16 進 64 字")
        if not isinstance(self.dry_run, bool):
            raise ValueError("dry_run は真偽値")


@dataclass(frozen=True, slots=True)
class ApplyReport:
    applied: tuple[PlannedChange, ...]
    backup_path: str                     # 適用前の複製の場所
    diff_text: str                       # 表示した差分
    dry_run: bool


@runtime_checkable
class Enforcer(Protocol):
    target: Target

    def plan(self, cfg: Config, cp: Checkpoints) -> EnforcementPlan:
        """何も書かない。cp.primary の道具を allow → ask にする計画だけを返す。"""
        ...

    def apply(self, plan: EnforcementPlan, *, confirm_token: str) -> ApplyReport:
        """plan.dry_run が True なら何も書かない。False でも確認文字列が一致しなければ書かない。"""
        ...


def get_enforcer(target: str) -> Enforcer:
    """実装は利用者の承認まで無い。常に NotImplementedYet。"""
    raise NotImplementedYet(f"enforce.get_enforcer({target!r})", "（未割当・利用者の承認待ち）")
