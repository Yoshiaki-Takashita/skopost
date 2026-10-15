# Changelog

## 0.1.0-preview — unreleased

First public research preview. Nothing here is a guarantee; see LIMITATIONS.md.

License: Apache-2.0. Version note: the distribution version is 0.1.0; `1.1.0.dev0` in the code (`skopost/model/version.py`) and in SARIF output is the schema/format version, not the distribution version (docs/ARCHITECTURE.md section 2.3).

- Static analysis of AI agent tool setups: enumerates dangerous paths created by *combinations* of tools (untrusted text → command execution, irreversible actions, or secret exfiltration, including via shared stores).
- Minimum checkpoint set computed exactly (forced points → max-flow on bipartite cases → branch and bound), with reasons and alternatives.
- Input adapters: native JSON sheet, MCP server configs, Claude settings, OpenAPI (`--adapter auto` by default). Unread keys are listed in the report, not silently skipped; secret-looking values are discarded on read.
- Confidence marks per capability (確 confirmed / 論 reasoned / 推 guessed / 不明 unknown); unknown is treated as dangerous; inference never removes a path.
- Output: Markdown, text, JSON, SARIF 2.1.0; `baseline` command and `--baseline` to fail only on new paths.
- Read-only: no network, no telemetry, writes only with `--out` and never overwrites.
- Python 3.10–3.13, standard library only; `pip install .` provides the `skopost` command (not on PyPI).
- Evaluation is synthetic only: 304 unit tests, a synthetic benchmark (4 of 9 preregistered predictions missed in the full run) and a self-made synthetic corpus of 72 files. Real-world accuracy is unknown.
