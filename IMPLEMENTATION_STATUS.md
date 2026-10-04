# Gitofy implementation status

This ZIP is the **stdlib host-safe implementation**, not the earlier command-only fallback. The source is wired around the product specification and real external APIs.

## Core product requirements

Implemented in `bot.py`:

- Telegram-first welcome + inline main menu
- `/start`, `/help`, `/github`, `/connect`, `/disconnect`, `/repos`, `/repo`, `/upload`, `/update`, `/workflows`, `/workflow`, `/run`, `/runs`, `/cancel`, `/rerun`, `/status`, `/logs`, `/artifacts`, `/download`, `/settings`
- PAT validation against GitHub `/user` with returned OAuth scope inspection
- SQLite persistence for users, GitHub connections, repositories, repository settings, operations, workflow runs, webhook events, audit entries, memories, schedules, artifact history and locks
- secure ZIP validation/root/project detection
- repository synchronization through GitHub Git Data APIs
- workflow dispatch + real run discovery
- persistent single-message build monitoring with actual jobs/steps
- final synchronization before final Telegram state
- failure logs and TXT report
- artifact metadata, APK/AAB recognition and Telegram delivery for supported sizes
- restart monitor recovery
- admin diagnostics and health endpoint
- AI provider HTTP abstraction
- repository-aware AI search
- issue/PR/release helpers
- risk-based permission model and audit trail
- cleanup scheduler

## Important runtime boundary

TheHostServer's shared `/opt/venv` is never modified. The ZIP intentionally has no startup `pip install`. This is required by the observed host environment where `~honenumbers` was reported as an invalid distribution and isolated pip installation was killed with exit code `-9`.

## No fabricated results

Gitofy only reports a workflow/run/artifact after the corresponding GitHub API result exists. Progress is calculated from returned job/step terminal states. It does not manufacture a percentage, run ID, commit SHA, PR number, artifact or test result.
