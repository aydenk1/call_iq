#!/usr/bin/env python3
"""
Pipeline for syncing UniFi Talk call recordings, splitting channels, running
Whisper transcription, and merging the transcripts into a diarized
conversation log.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Sequence


import yaml

from api.db import Database
from api.models import PipelineStatus
from pipeline.utils import configure_logging, update_call_record_status
from pipeline.workers.ssh_downloader import SSHDownloader
from pipeline.workers.unifi_ingest import UniFiCallIngestion, UniFiOSClient
from pipeline.workers.whisper_transcribe import WhisperTranscribe


def get_call_ids() -> list[str]:
    return [
        "5a671b39-e6bb-4763-926a-e23e2284ec07",
        "6c47a50b-9b08-44ee-94c3-27518119bfaa",
        "c4cf9a84-cdcc-426d-8e3e-197c14f561b2",
        "a91d0c0d-75f5-4ed8-b990-2b93186a6d31",
        "f2f50636-8acb-4fee-9a41-5a8df499cb42",
        "e20f009b-d50e-452b-8eb2-aab7cc76983c",
        "486180c7-6c08-4fb0-964a-9772ca835bf3",
        "148a59c5-4977-4d8e-b9a2-10c5319012f4",
        "26aca4cc-af68-43ed-a372-31a7ef183536",
        "63661b57-1db1-4f3b-bd0f-43b22b11adde",
        "18065f43-3373-40bb-9444-fe1bf7529533",
        "668bbfac-cfff-4781-bbe7-34eabbf264f6",
        "7d315dcb-e751-4602-b0d3-c84be5d2071f",
        "cf39ca5f-1c0c-4fcd-8471-c20471fa9650",
        "f29d5f28-254d-45c5-8429-21f0e4f51ca6",
        "6a2bf287-9d39-407e-82c5-49e484a89aa4",
        "f8893189-fdd7-49b8-857c-ca9b32709443",
        "dfabefad-3079-4390-b5b2-ab604ed2e2b6",
        "c07c5a89-3b3e-4dbe-aea4-75f06eaa99a8",
        "9417759d-d5e1-469e-a7b6-701c79602ba1",
        "eb6b71e5-47b2-4800-afd2-ac2942cb8f59",
        "d7f959fa-53ce-4ccf-944b-481b410489f6",
        "8c3c9ba9-d167-4ff4-8c8c-80c962169ae3",
        "d33269f6-4ee8-48f5-ae8e-688bc7ad10fd",
        "a1c17a02-2e91-4cf4-a71e-ae41b679ab2f",
        "46b181d1-8ddc-4996-9790-383820a15464",
        "47c35a77-f114-4dd1-b4fd-056f708f0a89",
        "1e2820d0-5f71-4ebc-84c6-14a0112810a5",
        "40f1997b-539e-43f0-b88a-51967a242f41",
        "e5a748d4-5983-4c7d-8125-285787b3931b",
        "e9d8cc8f-9204-4d29-805c-8f2dbab27d16",
        "c35a6927-f05f-4ede-b100-3b2427156d75",
    ]


def load_config(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


def main(argv: Sequence[str]) -> int:
    base_dir = Path(__file__).resolve().parents[2]
    config = load_config(base_dir / "config.yml")

    work_dir = Path(config["global"]["work_dir"])
    if not work_dir.is_absolute(): 
        work_dir = base_dir / work_dir
    recording_dir = work_dir / config["global"]["recording_dir"]
    whisper_dir = work_dir / config["global"]["whisper_dir"]

    log_level = logging.DEBUG if config["global"]["verbose"] else logging.INFO
    configure_logging(log_level)
    log_dir = work_dir / "logs"

    stop_requested = False

    def handle_signal(_signum: int, _frame: object | None) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    db = Database()
    db.create_db_and_tables()
    unifi_ingestion = None
    downloader = None
    transcriber = None

    update_call_record_status(db, get_call_ids(), PipelineStatus.DOWNLOADED)


    if config["unifi_ingestion"].pop("activate"):
        unifi_client = UniFiOSClient(
            base_url=config["unifi_ingestion"]["base_url"],
            username=os.getenv("UNIFI_USERNAME", ""),
            password=os.getenv("UNIFI_PASSWORD", "")
            )
        unifi_ingestion = UniFiCallIngestion(
            unifi_client=unifi_client,
            call_url=config["unifi_ingestion"]["call_url"],
            page_size=config["unifi_ingestion"]["page_size"],
            sleep_between_request_s=config["unifi_ingestion"]["sleep_between_request_s"],
            sleep_same_request_s=config["unifi_ingestion"]["sleep_same_request_s"],
            log_level=log_level,
            log_dir=log_dir,

        )
        unifi_ingestion.start()

    if config["ssh"].pop("activate"):
        downloader = SSHDownloader(
            remote_host=config["ssh"]["remote_host"],
            remote_dir=config["ssh"]["remote_path"],
            local_dir=recording_dir,
            log_level=log_level,
            log_dir=log_dir,
        )
        time.sleep(3)
        downloader.start()
    
    if config["whisper"].pop("activate"):
        transcriber = WhisperTranscribe(
            input_root=recording_dir,
            output_root=whisper_dir,
            **config["whisper"],
            log_level=log_level,
            log_dir=log_dir,
        )
        time.sleep(3)
        transcriber.start()

    try:
        while True:
            if stop_requested:
                break
            time.sleep(1)
    finally:
        if unifi_ingestion is not None:
            unifi_ingestion.stop()
        if downloader is not None:
            downloader.stop()
        if transcriber is not None:
            transcriber.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
