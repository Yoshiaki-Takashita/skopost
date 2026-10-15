"""report の公開面。担当 E（段 2）。整形するだけ：計算しない・ファイルを書かない（書くのは cli）。

契約（tests/test_contract_report.py）：
- render(fmt="md", lang="ja") は compat.v1.report_md と**バイト一致**
- to_json は model.convert.result_to_dict と同値（SPEC §10）
- to_sarif は SARIF 2.1.0 の形。道 1 本＝result 1 件。ruleId は SKP-EXEC・SKP-ACT・SKP-EXFIL（・SKP-MISMATCH-UNDER）
- 全形式に「走らせなかった検査」（not_checked）の全行が現れる

SARIF の公式 JSON スキーマ（sarif-schema-2.1.0.json）は手元に無く、スキーマでの検証は未実施（不明）。
仕様（OASIS SARIF 2.1.0）の必須項目は tests/test_report_sarif.py で個別に確かめる。
"""
from __future__ import annotations

import json
from typing import Any, Literal

from ..model.constants import EXACT_LIMIT, SPEC_VERSION
from ..model.convert import result_to_dict
from ..model.safe import safe
from ..model.types import AnalysisResult, Config
from ..model.version import __version__

OWNER = "E：出力・CI"
Format = Literal["text", "json", "sarif", "md"]
Lang = Literal["ja", "en"]
FORMATS: tuple[str, ...] = ("text", "json", "sarif", "md")
RULE_IDS = {"exec": "SKP-EXEC", "act": "SKP-ACT", "exfil": "SKP-EXFIL", "mismatch-under": "SKP-MISMATCH-UNDER"}

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
KIND_JA = {"exec": "実行", "act": "取り返しのつかない操作", "exfil": "持ち出し"}
KIND_EN = {"exec": "execution", "act": "irreversible action", "exfil": "exfiltration"}
LEVEL_OF = {"確": "error", "論": "error", "推": "warning", "不明": "note", "宣言": "note"}

RULES = (
    ("SKP-EXEC", "HarmfulExecution", "信頼できない入力が実行に届く道（確認なしの道具だけで成り立つ）"),
    ("SKP-ACT", "IrreversibleAction", "信頼できない入力が取り返しのつかない操作に届く道"),
    ("SKP-EXFIL", "Exfiltration", "秘密を読む道具から外へ送る道具へ抜ける道"),
    ("SKP-MISMATCH-UNDER", "UnderDeclared", "観察が宣言より危ない（申告より危ない食い違い）"),
)


def render(res: AnalysisResult, cfg: Config, fmt: Format, *, explain: bool = False, lang: Lang = "ja") -> str:
    if lang not in ("ja", "en"):
        raise ValueError(f"未知の言語：{lang!r}")
    if fmt == "md":
        if lang != "ja":
            raise ValueError("md は ja だけ（v1 と バイト一致を守るため。en は text を使う）")
        return _md(res, cfg, explain)
    if fmt == "json":
        return json.dumps(to_json(res), ensure_ascii=False, indent=2) + "\n"
    if fmt == "sarif":
        return json.dumps(to_sarif(res, cfg, artifact_uri=_artifact_uri(cfg)), ensure_ascii=False, indent=2) + "\n"
    if fmt == "text":
        return _text(res, cfg, explain, lang)
    raise ValueError(f"未知の形式：{fmt!r}（{'・'.join(FORMATS)}）")


def to_json(res: AnalysisResult) -> dict[str, object]:
    return result_to_dict(res)


# ---------------------------------------------------------------- md（compat.v1.report_md とバイト一致）
def _md(res: AnalysisResult, cfg: Config, explain: bool) -> str:
    r = result_to_dict(res)
    L: list[str] = []
    labels = {t.id: safe(t.label, 40) for t in cfg.tools}
    s = r["summary"]
    L.append(f"# Skopost 報告：{safe(r['name'], 60) or '（名前なし）'}")
    L.append("")
    verdict = ("危ない道はありません（この札の範囲で）" if r["exit_code"] == 0
               else f"危ない道 {s['paths']} 本。関所 {r['checkpoints']['size']} か所で全部断てます")
    L.append(f"**結論**：{verdict}。")
    L.append("")
    L.append(f"- 道具 {s['tools']}（確認なし {s['allowed']}）／宣言だけの地図では道 {s['paths_declared_only']} 本"
             f"（見落とし {s['missed_by_declared']} 本）／宣言と観察の食い違い {s['mismatches']}／不明として危ない側に倒した項目 {s['assumed_unknown']}")
    L.append("")
    cps = r["checkpoints"]
    L.append("## 関所（ここに人の確認を置く）")
    L.append("")
    if not cps["primary"]:
        L.append("なし。")
    else:
        for tid in cps["primary"]:
            L.append(f"- **{tid}**（{labels.get(tid, tid)}）→ `mode: ask`")
            if explain:
                for x in cps["reasons"].get(tid, []):
                    L.append(f"  - 断つ道：{x}")
        if not cps["exact"]:
            L.append("")
            L.append(f"（道具が {EXACT_LIMIT} 個を超えるため近似。最小でない可能性があります）")
        if cps["alternatives"]:
            L.append("")
            L.append("代替案（同じ個数・手間の少ない順）：")
            for alt in cps["alternatives"]:
                L.append(f"- {', '.join(alt)}")
    L.append("")
    d = r["declared_only"]
    L.append("## 宣言だけで決めたらどうなるか")
    L.append("")
    if not d["cut"] and s["paths"] == 0:
        L.append("宣言でも観察でも道はありません。")
    elif d["holds"]:
        L.append(f"宣言だけの関所 {d['cut'] or '（なし）'} でも、観察の層の道は全部断てます。")
    else:
        L.append(f"宣言だけの関所 {d['cut'] or '（なし）'} では、観察の層で **{d['surviving_paths']} 本**の道が残ります："
                 + "、".join(f"`{x}`" for x in d["surviving"]))
        L.append("")
        L.append("これが「一覧で管理すると安全の錯覚になる」の具体です。")
    L.append("")
    L.append("## 危ない道")
    L.append("")
    if r["paths"]:
        L.append("| 種類 | 道 | 確度 | 経路 |")
        L.append("|---|---|---|---|")
        for p in r["paths"]:
            L.append(f"| {KIND_JA[p['kind']]} | {'>'.join(p['tools'])} | {p['confidence']} | {safe(' → '.join(p['via']), 80)} |")
    else:
        L.append("なし。")
    L.append("")
    L.append("## 宣言と観察の食い違い")
    L.append("")
    if r["mismatches"]:
        L.append("| 道具 | 項目 | 宣言 | 観察 | 確度 | 向き | 根拠 |")
        L.append("|---|---|---|---|---|---|---|")
        for m in r["mismatches"]:
            sev = "**申告より危ない**" if m["severity"] == "under" else "申告より安全"
            L.append(f"| {m['tool']} | {m['cap']} | {json.dumps(m['declared'], ensure_ascii=False)} | "
                     f"{json.dumps(m['observed'], ensure_ascii=False)} | {m['confidence']} | {sev} | {safe(m['evidence'], 60)} |")
    else:
        L.append("なし。")
    L.append("")
    L.append("## 不明として危ない側に倒した項目")
    L.append("")
    if r["assumed"]:
        L.append("観察の札を書けば、関所が減る可能性があります。")
        for a in r["assumed"]:
            L.append(f"- {a['tool']}.{a['cap']}")
    else:
        L.append("なし。")
    L.append("")
    L.append("## 走らせなかった検査・限界")
    L.append("")
    for x in r["not_checked"]:
        L.append(f"- {x}")
    L.append("")
    L.append(f"_Skopost v{SPEC_VERSION}・計算 {s['seconds']} 秒・外部通信なし・入力は変更していません_")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- text（端末向けの短縮版）
_T = {
    "ja": {"none": "危ない道なし（この札の範囲で）", "paths": "危ない道 {n} 本・関所 {c} か所",
           "cp": "関所", "assumed": "不明として危ない側に倒した項目", "under": "申告より危ない食い違い",
           "nc": "走らせなかった検査・限界", "approx": "（近似・最小でない可能性）", "kind": KIND_JA},
    "en": {"none": "no harmful paths (within these declarations)", "paths": "{n} harmful path(s), {c} checkpoint(s)",
           "cp": "checkpoints", "assumed": "unknown items assumed dangerous", "under": "under-declared mismatches",
           "nc": "checks not run / limits", "approx": " (approximate; may not be minimal)", "kind": KIND_EN},
}


def _text(res: AnalysisResult, cfg: Config, explain: bool, lang: str) -> str:
    t = _T[lang]
    labels = {x.id: safe(x.label, 40) for x in cfg.tools}
    L = [f"skopost: {safe(res.name, 60)}"]
    L.append(t["none"] if not res.paths else t["paths"].format(n=len(res.paths), c=res.checkpoints.size))
    for p in res.paths:
        L.append(f"  [{p.confidence}] {t['kind'][p.kind]}: {p.key}  ({safe(' -> '.join(p.via), 80)})")
    if res.checkpoints.primary:
        L.append(f"{t['cp']}{'' if res.checkpoints.exact else t['approx']}:")
        for tid in res.checkpoints.primary:
            lab = labels.get(tid, "")
            L.append(f"  {tid}{f' ({lab})' if lab else ''} -> mode: ask")
            if explain:
                for x in res.reasons.get(tid, ()):
                    L.append(f"    - {x}")
    under = [m for m in res.mismatches if m.severity == "under"]
    if under:
        L.append(f"{t['under']}: " + ", ".join(f"{m.tool}.{m.cap}" for m in under))
    if res.assumed:
        L.append(f"{t['assumed']}: " + ", ".join(f"{a.tool}.{a.cap}" for a in res.assumed))
    L.append(f"{t['nc']}:")
    for x in res.not_checked:
        L.append(f"  - {x}")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- SARIF 2.1.0
def _artifact_uri(cfg: Config) -> str:
    for t in cfg.tools:
        if t.origin is not None and t.origin.file:
            return t.origin.file
    return "skopost.json"


def _location(uri: str, line: int | None, pointer: str = "") -> dict[str, Any]:
    loc: dict[str, Any] = {"physicalLocation": {"artifactLocation": {"uri": uri},
                                                "region": {"startLine": line if line and line >= 1 else 1}}}
    if pointer:
        loc["logicalLocations"] = [{"fullyQualifiedName": pointer, "kind": "member"}]
    return loc


def _tool_location(cfg: Config, tool_id: str, artifact_uri: str) -> dict[str, Any]:
    for t in cfg.tools:
        if t.id == tool_id and t.origin is not None:
            return _location(t.origin.file or artifact_uri, t.origin.line, t.origin.pointer)
    return _location(artifact_uri, 1)


def to_sarif(res: AnalysisResult, cfg: Config, *, artifact_uri: str) -> dict[str, object]:
    rule_index = {rid: i for i, (rid, _, _) in enumerate(RULES)}
    results: list[dict[str, Any]] = []
    for p in res.paths:
        rid = RULE_IDS[p.kind]
        msg = f"{KIND_JA[p.kind]}の道 {p.key}（確度 {p.confidence}）：{safe(' → '.join(p.via), 200)}"
        results.append({
            "ruleId": rid, "ruleIndex": rule_index[rid], "level": LEVEL_OF.get(p.confidence, "note"),
            "message": {"text": msg},
            "locations": [_tool_location(cfg, p.tools[0], artifact_uri)],
            "partialFingerprints": {"skopostPath/v1": f"{p.kind}:{p.key}"},
            "properties": {"kind": p.kind, "tools": list(p.tools), "via": list(p.via), "confidence": p.confidence},
        })
    for m in res.mismatches:
        if m.severity != "under":
            continue
        rid = RULE_IDS["mismatch-under"]
        results.append({
            "ruleId": rid, "ruleIndex": rule_index[rid], "level": "warning",
            "message": {"text": f"{m.tool}.{m.cap}：宣言より観察が危ない（確度 {m.confidence}）。根拠：{safe(m.evidence, 120) or '（なし）'}"},
            "locations": [_tool_location(cfg, m.tool, artifact_uri)],
            "partialFingerprints": {"skopostMismatch/v1": f"{m.tool}:{m.cap}"},
        })
    notes = [{"level": "note", "message": {"text": x}, "descriptor": {"id": "SKP-NOT-CHECKED"}} for x in res.not_checked]
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {"driver": {
                "name": "Skopost", "version": __version__, "semanticVersion": __version__,
                "rules": [{"id": rid, "name": name, "shortDescription": {"text": desc}, "fullDescription": {"text": desc},
                           "defaultConfiguration": {"level": "warning" if rid == "SKP-MISMATCH-UNDER" else "error"}}
                          for rid, name, desc in RULES],
            }},
            "invocations": [{"executionSuccessful": True, "toolExecutionNotifications": notes}],
            "artifacts": [{"location": {"uri": artifact_uri}}],
            "results": results,
            "properties": {
                "notChecked": list(res.not_checked),
                "assumed": [f"{a.tool}.{a.cap}" for a in res.assumed],
                "checkpoints": list(res.checkpoints.primary), "exact": res.checkpoints.exact,
            },
        }],
    }
