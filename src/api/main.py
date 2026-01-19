from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, Sequence

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from .db import Database
from .models import CallRecord, PipelineStatus


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


class StatusUpdate(BaseModel):
    status: str | int
    source: str | None = None
    force: bool = True


def parse_pipeline_status(value: Any) -> PipelineStatus:
    if isinstance(value, PipelineStatus):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Empty status")
        if trimmed.lstrip("-").isdigit():
            return PipelineStatus(int(trimmed))
        key = trimmed.split(".")[-1].upper()
        return PipelineStatus[key]
    if isinstance(value, (int, float)) and float(value).is_integer():
        return PipelineStatus(int(value))
    raise ValueError("Unsupported status value")


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


@app.patch("/calls/{call_id}/status")
def update_call_status(
    call_id: str,
    payload: StatusUpdate,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    call = CallRecord.get(session=session, call_id=call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    try:
        new_status = parse_pipeline_status(payload.status)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    call.set_status(
        session,
        new_status,
        source=payload.source or "ui",
        force=payload.force,
        detail={"updated_via": "api"},
    )
    session.add(call)
    session.commit()
    session.refresh(call)
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
