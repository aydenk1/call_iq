from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Enum as SAEnum
from sqlmodel import Field, SQLModel


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

    def to_camel_dict(self) -> dict[str, Any]:
        """Return API-friendly camelCase keys without reshaping DB columns."""
        return {
            "id": self.id,
            "createdAt": self.created_at,
            "durationSec": self.duration_sec,
            "summary": self.summary,
            "impliedName": self.implied_name,
            "externalNumber": self.external_number,
            "tags": self.tags,
            "outcome": self.outcome,
            "transcript": self.transcript,
            "audio": self.audio,
            "suggestedTasks": self.suggested_tasks,
            "contactProfile": self.contact_profile,
            "status": self.status,
        }
