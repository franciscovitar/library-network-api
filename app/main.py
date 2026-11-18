"""HTTP entrypoint: system checks plus the /api/v1 interlibrary-lending routes."""

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.api.errors import register_error_handlers
from app.api.routes import router
from app.db import get_engine

app = FastAPI(
    title="Library Network API",
    description=(
        "Local demonstration of reliable interlibrary lending. "
        "Unauthenticated: local use only, never expose publicly."
    ),
    version="0.2.0",
)
register_error_handlers(app)
app.include_router(router)


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
