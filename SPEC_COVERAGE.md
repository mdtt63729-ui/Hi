# Specification implementation audit

This release was reviewed against `text.txt`, including the mandatory real-time GitHub Actions monitoring specification.

## Implemented / wired

- Telegram-first Gitofy welcome and inline main menu
- Command set from the specification plus operational commands
- GitHub PAT validation and scope discovery
- Secure credential persistence when `GITOFY_ENCRYPTION_KEY` is configured; otherwise session-only credential mode
- Repository list, details, create, delete confirmation, branches and commit history
- ZIP upload, streaming download, traversal/symlink/file-count/extracted-size protection
- Project root/type detection and comparison
- GitHub Git Data API synchronization with repository mutex and no-change detection
- Branch-aware update and optional automatic workflow dispatch
- Workflow discovery and YAML viewing
- Workflow dispatch with optional JSON inputs, run discovery, cancel and re-run
- Single editable Telegram build message
- Actual GitHub job/step state tracking and mathematically derived progress
- Final synchronization before terminal state
- Failure identification, GitHub log retrieval and TXT failure report
- Artifact discovery, APK/AAB-friendly artifact listing and small artifact Telegram delivery
- Large artifact signed streaming proxy hooks through `/download/*`
- Artifact history persistence
- SQLite persistent users, repositories, settings, operations, workflow runs, webhook events, audit log, memories, schedules and locks
- Restart recovery for active monitors
- Webhook signature verification + duplicate delivery storage + monitor wake-up
- Polling fallback
- Risk-aware operation model and explicit confirmation for destructive actions
- AI provider abstraction for Gemini/OpenRouter and repository-aware AI search
- Dependency/test/review/issue/PR/release engineering helper modules retained and documented
- `/healthz`, admin `/diag`, cleanup scheduler and Docker/Compose files
- No arbitrary shell execution in the Telegram runtime
- Secret redaction in errors/log-facing output

## Mandatory monitoring rules

The monitor uses GitHub run/jobs/steps as the source of truth. It does not invent run IDs, step names, percentages, artifacts, commits or success states. Progress is `terminal trackable units / total trackable units * 100`, rendered in one editable message. A failed terminal run is never presented as successful.

## Host compatibility

`requirements.txt` is intentionally empty. TheHostServer's shared `/opt/venv` is never modified and no runtime pip bootstrap is executed. This avoids the observed invalid `~honenumbers` environment warning and the previous isolated pip process kill (`exit code -9`).

## Remaining deployment-dependent capabilities

Some infrastructure features cannot be fully exercised inside an arbitrary Telegram host without its corresponding infrastructure: PostgreSQL/Redis distributed workers, object-storage credentials, public HTTPS webhook routing, and Telegram Local Bot API. The project contains the abstractions/configuration hooks for those integrations; production deployment must supply them. No fake health/build/artifact result is generated to hide missing infrastructure.
