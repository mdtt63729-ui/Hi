# Gitofy

Gitofy is a Telegram-first GitHub automation and CI/CD control platform. This distribution includes a **TheHostServer-safe stdlib runtime**: `bot.py` does not run `pip` at startup and does not depend on the host's shared Python package state.

## Production-oriented capabilities

- Telegram welcome UI + inline main menu
- GitHub PAT validation and scope discovery
- Repository listing/search/details and repository ownership checks
- ZIP validation: traversal, symlink, file-count and extracted-size limits
- Project-root and Android/Gradle/Kotlin/Java/Python/Node detection
- ZIP comparison and GitHub Git-data based repository synchronization
- Branch/commit support and optional automatic workflow dispatch
- Workflow discovery, YAML inspection, dispatch, run history, cancel and re-run
- Single editable Telegram build dashboard using actual GitHub jobs/steps
- Monotonic, GitHub-derived progress with no fabricated percentages
- Failure log retrieval + TXT report generation
- APK/AAB artifact detection and Telegram delivery for supported sizes
- Artifact history and large-artifact guidance
- AI provider abstraction for Gemini/OpenRouter
- Autonomous failed-build repair: inspect latest logs + repository snapshot, patch/push, and rebuild when AI_AUTOFIX_ENABLED=true
- Live workflow job/step dashboard with completion icons, success/failure notifications, and artifact file + direct-link delivery
- AI repository knowledge search, dependency/test inspection, code-review and issue/PR helpers
- Issue/PR/release automation
- Risk-based permission checks and destructive-operation confirmation
- SQLite persistent state, audit trail, memory, scheduled-task records
- Restart recovery for active workflow monitors
- `/healthz` and admin-only `/diag`
- Hourly safe cleanup
- Docker/Compose deployment templates
- No secrets in source; environment variables only

## Environment

Required: `BOT_TOKEN`.

Optional: `GEMINI_API_KEY`, `GEMINI_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `GITOFY_ENCRYPTION_KEY`, `ADMIN_IDS`, `PORT`, `BUILD_POLL_SECONDS`, `MAX_ZIP_BYTES`, `MAX_UNPACK_BYTES`, `CLEANUP_MINUTES`.

Normal GitHub configuration is performed through Telegram after deployment: `/start` → Connect GitHub → PAT → repository/workflow actions.

## TheHostServer

`requirements.txt` is intentionally empty for the host preparation phase. The runtime uses only the Python standard library. This avoids dependency-installation failures caused by a broken shared `/opt/venv` package state. No application code should attempt to repair or mutate the host's shared virtual environment.

## Security

The bot never echoes PATs, redacts credential-like values from errors, validates callback ownership, rejects unsafe ZIP entries, avoids arbitrary shell execution, uses GitHub Actions as the build infrastructure, and treats GitHub as the source of truth for build state.

## Native Git / libgit2
Gitofy v1.1 includes an optional `pygit2`/libgit2 engine. It is selected automatically when the
host image already provides a compatible native build (`GITOFY_GIT_ENGINE=auto`), or explicitly with
`GITOFY_GIT_ENGINE=libgit2`. Gitofy never installs native dependencies during bot startup. If libgit2
is unavailable, the GitHub API implementation remains the safe fallback.

Upload progress uses the original Telegram document byte size, while ZIP statistics are read from the
ZIP central directory after download so the exact non-directory file count and original archive size
are shown. Progress edits are throttled/coalesced so Telegram message updates do not serialize the
network transfer.

## AI team / multimodal inputs

When `AI_AUTOFIX_ENABLED=true`, Gitofy requires all three AI API families: `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, and `NVIDIA_API_KEY`. Gemini is the Head AI; OpenRouter and NVIDIA NIM are specialist pools. Auto mode is the default, while `/ai_models` lets the user manually select a provider/model.

NVIDIA NIM is called through `https://integrate.api.nvidia.com/v1/chat/completions` by default. Provider-qualified model options are used internally so an identifier that exists on both OpenRouter and NVIDIA can still be selected from either provider.

The AI Assistant accepts Telegram photos, videos, and ordinary documents. Gemini is the first multimodal reader; the resulting evidence is handed to the selected specialist. Text/code files are extracted locally. Unsupported or oversized binary attachments are not silently claimed to have been analyzed; they are represented with safe metadata.
