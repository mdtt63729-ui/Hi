# TheHostServer deployment recovery

This build intentionally leaves `requirements.txt` dependency-free because the
host's shared Python 3.12 environment reports an invalid `~honenumbers`
distribution before the bot starts. That warning is outside this ZIP.

The bot now bootstraps its runtime packages into `.gitofy_runtime` only after
TheHostServer has accepted the Python project.

Requirements for runtime bootstrap:
- Python 3.10+
- outbound HTTPS access to PyPI
- permission to run `python -m pip`
- normal writable project directory

No `phonenumbers` package is required by Gitofy and it is deliberately absent.
