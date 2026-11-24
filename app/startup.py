"""Apply reviewed Alembic revisions using the QA migrator, then start FastAPI.

The single existing free API service is the temporary migration runner. Its migration
credential is kept in Render and removed from the process environment before Uvicorn starts.
"""

from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy.engine import make_url


def main() -> None:
    app_database_url = os.environ["DATABASE_URL"]
    migration_password = os.environ.get("MIGRATION_DB_PASSWORD")
    migration_user = os.environ.get("MIGRATION_DB_USER", "library_qa_migrator")
    if not migration_password:
        raise RuntimeError("MIGRATION_DB_PASSWORD is required for the QA migration")

    migration_url = make_url(app_database_url).set(
        username=migration_user,
        password=migration_password,
    )
    os.environ["DATABASE_URL"] = migration_url.render_as_string(hide_password=False)
    try:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    finally:
        os.environ["DATABASE_URL"] = app_database_url
        os.environ.pop("MIGRATION_DB_PASSWORD", None)
        os.environ.pop("MIGRATION_DB_USER", None)

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
