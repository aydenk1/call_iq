from __future__ import annotations

from sqlmodel import Session, select

from .models import CallRecord, PipelineStatus


def list_calls(session: Session, limit: int = 200, offset: int = 0) -> list[CallRecord]:
    statement = (
        select(CallRecord)
        .order_by(CallRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement))


def get_call(session: Session, call_id: str) -> CallRecord | None:
    return session.get(CallRecord, call_id)


def list_call_ids(session: Session, status: PipelineStatus | None = None) -> set[str]:
    statement = select(CallRecord.id)
    if status is not None:
        statement = statement.where(CallRecord.status == status)
    return {call_id for (call_id,) in session.exec(statement)}
