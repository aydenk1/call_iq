from multiprocessing import Event, Process
import os
from api.db import Database
from pipeline.utils import setup_worker_logging
from pathlib import Path


class PipelineWorker(Process):
    def __init__(self, *, log_level: int | None = None, log_dir: Path | None = None) -> None:
        super().__init__()
        self.log_level = log_level
        self.log_dir = log_dir
        self._stop_event = Event()
        self._db: Database | None = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = Database()
        return self._db

    def setup_logging(self) -> None:
        if self.log_level is None:
            return
        if self.log_dir is None:
            raise ValueError("log_dir is required when log_level is set.")
        setup_worker_logging(self.name, self.log_level, self.log_dir)

    def stop(self, timeout: float = 60.0, terminate_timeout: float = 10.0) -> None:
        self._stop_event.set()
        if os.getpid() == self.pid or self.pid is None:
            return
        self.join(timeout=timeout)
        if self.is_alive():
            self.terminate()
            self.join(timeout=terminate_timeout)
