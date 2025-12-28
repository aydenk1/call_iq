from __future__ import annotations

import os
from typing import Sequence

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from .crud import get_call, list_calls
from .db import Database


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
    calls = list_calls(session=session, limit=limit, offset=offset)
    return [call.to_camel_dict() for call in calls]


@app.get("/calls/{call_id}")
def get_call_record(call_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    call = get_call(session=session, call_id=call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call.to_camel_dict()
