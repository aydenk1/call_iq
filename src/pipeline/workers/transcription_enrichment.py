from __future__ import annotations

from collections.abc import Callable
import dataclasses
import gc
import json
import logging
import time
from datetime import date, timedelta
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
from pipeline.workers.google_ads_integration import GoogleAdsIntegration


class CallEnrichmentService:
    """Uses OpenAI to enrich one transcript/call into structured business intelligence."""



class CallerProfileService:
    """Uses OpenAI to enrich one transcript/call into structured business intelligence."""


class TranscriptionEnrichmentPipeline(PipelineWorker):
    """Uses OpenAI to enrich one transcript/call into structured business intelligence."""

    def __init__(self,
                 sleep_s: int = 60,
                 log_level: int | None = None,
                 log_dir: Path | None = None,
                 google_ads_integration: GoogleAdsIntegration | None = None,
                 google_ads_call_ingestion_config: Mapping[str, Any] | None = None) -> None:
        
        super().__init__(log_level=log_level, log_dir=log_dir)
        self.sleep_s = sleep_s
        self.google_ads_integration = google_ads_integration
        self.google_ads_call_ingestion_config = google_ads_call_ingestion_config or {}
    
    def google_ads_enrichment(self) -> None:
        if self.google_ads_integration is None:
            self.logger.info("Google Ads integration not configured, skipping enrichment.")
            return

        days_back = int(self.google_ads_call_ingestion_config.get("lookback_days", 7))
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)

        campaign_ids = self.google_ads_call_ingestion_config.get("campaign_ids")
        ids = [str(campaign_id).strip() for campaign_id in campaign_ids if str(campaign_id).strip()] if campaign_ids else None

        call_rows = self.google_ads_integration.fetch_calls_for_date_range(
            start_date=start_date,
            end_date=end_date,
            campaign_ids=ids,
            limit=int(self.google_ads_call_ingestion_config.get("query_limit", 1000)),
        )

        self.logger.info("Fetched %s Google Ads call rows from %s to %s", len(call_rows), start_date, end_date)
        return
        


    def run(self) -> None:
        """Fetch recent Google Ads call records for enrichment workflows."""
        if self.log_level is not None:
            if self.log_dir is None:
                raise ValueError("log_dir is required when log_level is set.")
            self.logger = setup_worker_logging(self.name, self.log_level, self.log_dir)

        while not self._stop_event.is_set():
            self.google_ads_enrichment()

            self._stop_event.wait(self.sleep_s)
