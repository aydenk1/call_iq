from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Caller(SQLModel, table=True):
    __tablename__ = "callers"

    id: str = Field(primary_key=True, index=True)
    implied_name: str | None = None
    profile: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True),
    )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def to_camel_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "impliedName": self.implied_name,
            "profile": self.profile,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
