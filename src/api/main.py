from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Sequence

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlmodel import Session

from .db import Database
from .models import CallRecord


def parse_origins(raw_origins: str | None) -> list[str]:
    if not raw_origins:
        return ["http://localhost:3000"]
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


db = Database()


def get_session():
    with db.session() as session:
        yield session


app = FastAPI(title="Call IQ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_origins(os.getenv("CORS_ORIGINS")),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    if os.getenv("SQLMODEL_CREATE_TABLES") == "1":
        db.create_db_and_tables()


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/calls")
def list_call_records(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> Sequence[dict[str, object]]:
    calls = CallRecord.list_records(session=session, limit=limit, offset=offset)
    return [call.to_camel_dict() for call in calls]


@app.get("/calls/{call_id}")
def get_call_record(call_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    call = CallRecord.get(session=session, call_id=call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call.to_camel_dict()


@app.get("/audio/{call_id}")
def stream_call_audio(call_id: str, session: Session = Depends(get_session)) -> FileResponse:
    call = CallRecord.get(session=session, call_id=call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if not call.audio_file_path:
        raise HTTPException(status_code=404, detail="Audio file not available")

    audio_path = Path(call.audio_file_path)
    if not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")

    media_type, _ = mimetypes.guess_type(str(audio_path))
    return FileResponse(path=audio_path, media_type=media_type or "application/octet-stream")
