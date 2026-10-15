"""不変で hash できる対応表。frozen dataclass の中に dict を置くと hash できず、後から書き換えもできてしまうため。"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class FrozenMap(Mapping[K, V], Generic[K, V]):
    """挿入順を保つ読み取り専用の対応表。等価は内容（順序は無視）、hash も内容から。"""

    __slots__ = ("_d", "_h")

    def __init__(self, items: Mapping[K, V] | None = None, /, **kw: V) -> None:
        d: dict[K, V] = dict(items or {})
        d.update(kw)  # type: ignore[arg-type]
        object.__setattr__(self, "_d", d)
        object.__setattr__(self, "_h", None)

    def __getitem__(self, key: K) -> V:
        return self._d[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)

    def __hash__(self) -> int:
        h = self._h
        if h is None:
            h = hash(frozenset(self._d.items()))
            object.__setattr__(self, "_h", h)
        return h

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FrozenMap):
            return self._d == other._d
        if isinstance(other, Mapping):
            return self._d == dict(other)
        return NotImplemented

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("FrozenMap は変更できません")

    def __repr__(self) -> str:
        return f"FrozenMap({self._d!r})"

    def to_dict(self) -> dict[K, V]:
        return dict(self._d)


EMPTY: FrozenMap = FrozenMap()
