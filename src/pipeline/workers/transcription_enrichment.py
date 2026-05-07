from __future__ import annotations

from collections.abc import Callable
import dataclasses
import gc
import json
import logging
import os
import time
from dataclasses import dataclass
from multiprocessing import Event, Process
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Self

from sqlmodel import select
from tqdm import tqdm

from api.db import Database
from api.models import CallDirection, CallRecord, PipelineStatus
from pipeline.utils import AUDIO_EXTS, SubprocessPool, chunked, configure_logging, setup_worker_logging, update_call_record_status
from pipeline.workers.base import PipelineWorker



class CallEnrichmentService:
    """Uses OpenAI to enrich one transcript/call into structured business intelligence."""



class CallerProfileService:
    """Uses OpenAI to enrich one transcript/call into structured business intelligence."""


class TranscriptionEnrichmentPipeline(PipelineWorker):
    """Uses OpenAI to enrich one transcript/call into structured business intelligence."""

    def __init__(self,
                 sleep_s: int = 60,
                 log_level: int | None = None,
                 log_dir: Path | None = None) -> None:
        super().__init__(log_level=log_level, log_dir=log_dir)
        

