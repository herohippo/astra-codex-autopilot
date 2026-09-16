# Security

Astra Autopilot is an independent local automation tool for trusted repositories and machines. It is not a sandbox boundary of its own.

- Runtime has no third-party Python dependencies. It invokes installed Git and Codex tools.
- ChatGPT login is required. CLI runs set `forced_login_method="chatgpt"` and the OpenAI provider, remove API-key environment overrides, and recheck login before each turn. There is no automatic API-key fallback, reset redemption, or credit purchase. Existing account credit settings are outside this tool's control.
- The configured Codex executable and repository instructions are trusted input. Inspect repositories, plugins, hooks, and executable paths before running unattended work. Inherited host configuration and external tools can have their own effects.
- Default sandbox is workspace-write. Arbitrary extra CLI arguments and danger-full-access are rejected. The project cannot grant permissions beyond the host's actual authorization.
- `.autopilot` is ignored by Git when initialized. Previously tracked files remain tracked. Goals, steering, and bounded output logs may contain confidential project content; do not publish them blindly.
- App mode uses the host scheduler and a cooperative ownership binding. Stop active app edits and pause the heartbeat before switching modes. CLI locks prevent competing compliant supervisors; they do not prevent arbitrary editors or manual shell commands.
- Immediate CLI stop terminates managed subprocesses. It does not roll back edits or undo effects already sent to an external service.
- No public quota endpoint, browser scraping, credential copying, or usage-limit bypass is used.

For a vulnerability, avoid public issues containing credentials or exploit-sensitive project data. Contact the repository maintainer through an available private GitHub channel. Do not upload private project logs without review.
