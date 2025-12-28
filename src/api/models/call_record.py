from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Enum as SAEnum
from sqlmodel import Field, Session, SQLModel, select


class PipelineStatus(Enum):
    FAILED = -1
    QUEUED = 0
    DOWNLOADED = 1
    TRANSCRIBED = 2
    FINISHED = 3
    


class CallRecord(SQLModel, table=True):
    __tablename__ = "call_records"

    id: str = Field(primary_key=True, index=True)
    created_at: datetime = Field(index=True)
    duration_sec: int
    summary: str
    implied_name: str | None = None
    external_number: str | None = None
    audio_file_path: str | None = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    outcome: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    transcript: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB))
    audio: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    suggested_tasks: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    contact_profile: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    status: PipelineStatus = Field(
        default=PipelineStatus.QUEUED,
        sa_column=Column(SAEnum(PipelineStatus, name="pipeline_status"), index=True),
    )

    @classmethod
    def list_records(cls, session: Session, limit: int = 200, offset: int = 0) -> list[CallRecord]:
        statement = (
            select(cls)
            .order_by(cls.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(session.exec(statement))

    @classmethod
    def get(cls, session: Session, call_id: str) -> CallRecord | None:
        return session.get(cls, call_id)

    @classmethod
    def list_ids(
        cls,
        session: Session,
        status: PipelineStatus | None = None,
    ) -> set[str]:
        statement = select(cls.id)
        if status is not None:
            statement = statement.where(cls.status == status)
        return set(session.exec(statement).all())

    def to_camel_dict(self) -> dict[str, Any]:
        """Return API-friendly camelCase keys without reshaping DB columns."""
        return {
            "id": self.id,
            "createdAt": self.created_at,
            "durationSec": self.duration_sec,
            "summary": self.summary,
            "impliedName": self.implied_name,
            "externalNumber": self.external_number,
            "audioFilePath": self.audio_file_path,
            "tags": self.tags,
            "outcome": self.outcome,
            "transcript": self.transcript,
            "audio": self.audio,
            "suggestedTasks": self.suggested_tasks,
            "contactProfile": self.contact_profile,
            "status": self.status,
        }
