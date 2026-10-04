# TheHostServer deployment

Use the root `bot.py` entrypoint. This deployment intentionally has an empty `requirements.txt` and uses only Python standard library for startup.

Required environment variable:
- `BOT_TOKEN`

Optional AI variables:
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`

GitHub PATs are kept in process memory only by the host-safe control plane. No pip install or virtualenv creation occurs at startup.

Supported Telegram commands are listed by `/help`.

### Optional native libgit2
If the host image already contains a compatible `pygit2` + native `libgit2`, set
`GITOFY_GIT_ENGINE=auto` (default) or `libgit2`. Gitofy will then use native clone/index/
commit/push for repository synchronization. The runtime deliberately does not pip-install
pygit2 because native dependency installation previously caused constrained-host startup
failures. If unavailable, Gitofy falls back to its parallel GitHub Git Data API implementation.

## Large-project Git transport

Gitofy prefers libgit2/pygit2 when it is already installed. If it is not available,
Gitofy automatically uses the system `git` smart-HTTP transport when `git` is present.
This is important for large ZIP projects: the REST Git-Data blob API can issue one
request per file and trigger GitHub secondary rate limits, while smart HTTP packs
Git objects into a transfer and avoids that per-file API pattern.

`GITOFY_GIT_ENGINE=auto` (default) = libgit2 -> git CLI -> REST fallback.
`GITOFY_GIT_ENGINE=libgit2` = require libgit2.
`GITOFY_GIT_ENGINE=git-cli` = require system Git.

## ZIP upload limit and `/update` behavior

- Maximum accepted ZIP size is **50 MiB** (`MAX_ZIP_BYTES=52428800`).
- `/upload` / **Upload Project** remains the full replacement operation: it syncs the ZIP as the repository tree and may remove files not present in the ZIP.
- `/update` / **Update Project** is now strictly **non-destructive**: it overlays the ZIP on the selected branch, commits only added/changed files, and never deletes repository files that are absent from the ZIP.
- The update path uses the system Git smart-HTTP engine and will not call the old full-replacement sync function.

### Telegram's 20 MiB download limitation

Telegram's official cloud Bot API currently limits `getFile` downloads to 20 MiB. A 50 MiB document can be sent to a bot, but the bot cannot download it through the cloud `getFile` endpoint. To actually accept ZIPs above 20 MiB, run Telegram's Local Bot API Server and set:

```env
TELEGRAM_API_BASE_URL=http://127.0.0.1:8081
TELEGRAM_FILE_BASE_URL=http://127.0.0.1:8081/file
MAX_ZIP_BYTES=52428800
```

The code automatically uses those endpoints; no source-code change is required when switching between cloud and local Bot API. Telegram documents unlimited downloads and up to 2000 MB uploads for a Local Bot API Server.
