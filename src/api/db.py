from __future__ import annotations

import os
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://calliq:calliq@localhost:5432/calliq",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
