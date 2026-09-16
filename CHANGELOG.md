# Changelog

## 0.2.0

- Separate native Codex app heartbeat workflow from standalone CLI execution.
- Native app ownership, saved automation binding, pause and mode handoff helpers.
- Detached CLI start with readiness check; graceful and immediate process-tree stop.
- OS-held project lock; crash recovery without force-stealing live work.
- Durable retry times and per-turn ChatGPT login checks; restrict unsafe config overrides.
- Immutable steering queue prevents losing instructions added during a turn.
- Bounded output tails/log retention and optional runtime/turn limits.
- Private runtime ignore rules; nullable usage when Codex does not report it.
- Korean quickstart with app and CLI examples; Windows/Linux test workflow.
- Removed unverified v0.1 login-autostart scripts; install does not modify OS scheduling.

Validation uses fake Codex subprocesses without consuming actual model allowance. App coordination tests do not establish a real quota-exhaustion/reset recovery cycle. See the release verification report for executed checks.

## 0.1.0

Original reference implementation: CLI checkpoint loop, quota retry, plugin scaffold.
