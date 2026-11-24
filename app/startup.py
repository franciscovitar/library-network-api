"""Run the reviewed schema migrations before starting the API.

This small portfolio deployment uses the existing free web service as its migration runner.
Alembic is idempotent at the current head; if migration fails, the API process will not start.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
    )


if __name__ == "__main__":
    main()
