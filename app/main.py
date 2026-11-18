"""HTTP entrypoint. Business endpoints will be added incrementally."""

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_engine

app = FastAPI(
    title="Library Network API",
    description="Local demonstration of reliable interlibrary lending (under development).",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness does not imply database readiness."""
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def ready(engine: Engine = Depends(get_engine)) -> dict[str, str]:
    """Readiness confirms a successful database query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready"}
