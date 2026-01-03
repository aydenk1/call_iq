from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Enum as SAEnum
from sqlmodel import Field, Session, SQLModel, select


class PipelineStatus(Enum):
    FAILED = -1
    CALL_IN_PROGRESS = 0
    DOWNLOAD_QUEUED = 1
    DOWNLOADED = 2
    TRANSCRIBED = 3
    FINISHED = 4
    


class CallRecord(SQLModel, table=True):
    __tablename__ = "call_records"

    id: str = Field(primary_key=True, index=True)
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))
    duration_sec: int
    summary: str
    implied_name: str | None = None
    external_number: str | None = None
    audio_file_path: str | None = None
    recording: bool
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    outcome: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    raw_whisper_transcript: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB))
    transcript_text: str | None = None
    audio: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    suggested_tasks: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    contact_profile: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    raw_call_log: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    status: PipelineStatus = Field(
        default=PipelineStatus.CALL_IN_PROGRESS,
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
    def get_from_id(cls, session: Session, call_ids: Collection[str]) -> dict[str, CallRecord]:
        statement = (
            select(cls)
            .where(CallRecord.id.in_(call_ids))
            .order_by(cls.created_at.desc())
        )
        return {call.id: call for call in session.exec(statement).all()}

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

    def set_status(
        self,
        session: Session,
        new_status: PipelineStatus,
        source: str | None = None,
        detail: dict[str, Any] | None = None,
        initial: bool = False,
    ) -> bool:
        if not initial and self.status == new_status:
            return False

        previous_status = None if initial else self.status
        self.status = new_status
        event = CallRecordStatusEvent(
            call_id=self.id,
            from_status=previous_status,
            to_status=new_status,
            source=source,
            detail=detail or {},
        )
        session.add(event)
        return True

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
            "recording": self.recording,
            "tags": self.tags,
            "outcome": self.outcome,
            "rawWhisperTranscript": self.raw_whisper_transcript,
            "transcriptText": self.transcript_text,
            "audio": self.audio,
            "suggestedTasks": self.suggested_tasks,
            "contactProfile": self.contact_profile,
            "rawCallLog": self.raw_call_log,
            "status": self.status,
        }


class CallRecordStatusEvent(SQLModel, table=True):
    __tablename__ = "call_record_status_events"

    id: int | None = Field(default=None, primary_key=True)
    call_id: str = Field(foreign_key="call_records.id", index=True)
    from_status: PipelineStatus | None = Field(default=None)
    to_status: PipelineStatus
    changed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    source: str | None = Field(default=None)
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
