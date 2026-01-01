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
from pipeline.workers.ssh_downloader import SSHDownloader
from pipeline.workers.unifi_ingest import UniFiCallIngestion, UniFiOSClient
from pipeline.workers.whisper_transcribe import WhisperTranscribe


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] [%(processName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(level)

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

    configure_logging(config["global"]["verbose"])    

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

        )
        unifi_ingestion.start()

    if config["ssh"].pop("activate"):
        downloader = SSHDownloader(
            remote_host=config["ssh"]["remote_host"],
            remote_dir=config["ssh"]["remote_path"],
            local_dir=recording_dir
        )
        downloader.start()
    
    if config["whisper"].pop("activate"):
        transcriber = WhisperTranscribe(
            input_root=recording_dir,
            output_root=whisper_dir,
            use_db=True,
            **config["whisper"],
        )
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
