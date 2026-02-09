from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://calliq:calliq@localhost:5432/calliq",
)


class Database:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or DATABASE_URL
        self._engine = None

    def create_db_and_tables(self) -> None:
        from api import models
        with self.engine.begin() as conn:
            # Some DB roles have an empty search_path; set a schema explicitly
            # so PostgreSQL enum and table DDL can be created reliably.
            conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS public")
            conn.exec_driver_sql("SET search_path TO public")
            try:
                conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            except Exception:
                logging.warning("Could not enable pg_trgm extension; trigram indexes may be unavailable.")
            SQLModel.metadata.create_all(conn)

    @property
    def engine(self):
        if self._engine is None:
            self._engine = create_engine(self._database_url, pool_pre_ping=True)
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        with Session(self.engine) as session:
            yield session
