"""例外。入力の誤りは SkopostError だけで表す（ファズで他の例外が出たら不具合）。"""
from __future__ import annotations


class SkopostError(Exception):
    """入力の誤り。メッセージは 1 行で、どこが悪いかを言う。"""

    def __init__(self, msg: str, *, where: str = "") -> None:
        super().__init__(msg)
        #: どこが悪いか（JSON Pointer 風の位置。旧 API は msg に位置を含めるので空でよい）
        self.where = where


class NotImplementedYet(NotImplementedError):
    """段 2 以降で実装する公開関数の空実装が投げる例外。契約試験はこれを見て「未実装」として飛ばす。"""

    def __init__(self, what: str, owner: str) -> None:
        super().__init__(f"{what} は未実装（担当 {owner}・段 2）")
        self.what = what
        self.owner = owner
