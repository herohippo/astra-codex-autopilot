# AGENTS.md — contributor policy

## Purpose
Maintain Astra Codex Autopilot as a conservative local supervisor for Codex CLI. The project must use documented Codex surfaces and must not scrape private ChatGPT endpoints or copy authentication tokens.

## Engineering rules
- Keep the runtime dependency-free beyond Python's standard library.
- Preserve Python 3.10+ compatibility.
- Treat ChatGPT-managed Codex auth and API-key auth as different billing paths.
- Never add automatic fallback to API-key billing when `auth_mode` is `chatgpt`.
- Prefer `codex exec --json` event parsing and repository checkpoint files over undocumented usage APIs.
- Keep `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, and the bundled `SKILL.md` aligned with current Codex plugin conventions.
- Add or update tests for behavior changes.
- Do not weaken the default `workspace-write` sandbox for convenience.

## Validation
Run `python -m pytest -q` and JSON-parse the plugin and marketplace manifests before considering a change complete.
