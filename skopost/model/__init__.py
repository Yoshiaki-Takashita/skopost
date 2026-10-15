"""model：型・検証・正規化・スキーマ・版移行。どの層にも依存しない（標準ライブラリだけ）。"""
from __future__ import annotations

from .constants import *  # noqa: F401,F403
from .convert import from_legacy, result_from_legacy, result_to_dict, to_dict, to_legacy
from .errors import NotImplementedYet, SkopostError
from .frozen import FrozenMap
from .migrate import migrate, spec_version_of
from .parse import load, parse
from .safe import safe
from .schema import SCHEMA_NAMES, get_schema, schema_errors
from .types import *  # noqa: F401,F403
from .validate import load_file, read_json_file, validate
from .version import __version__
