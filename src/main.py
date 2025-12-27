#!/usr/bin/env python3
"""
Pipeline for syncing UniFi Talk call recordings, splitting channels, running
Whisper transcription, and merging the transcripts into a diarized
conversation log.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Sequence

import yaml

from ssh_downloader import SSHDownloader
from whisper_transcribe import WhisperTranscribe


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_config(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


def main(argv: Sequence[str]) -> int:
    base_dir = Path(__file__).resolve().parent.parent
    config = load_config(base_dir / "config.yml")

    work_dir = Path(config["global"]["work_dir"])
    if not work_dir.is_absolute(): 
        work_dir = base_dir / work_dir
    recording_dir = work_dir / config["global"]["recording_dir"]
    whisper_dir = work_dir / config["global"]["whisper_dir"]

    configure_logging(config["global"]["verbose"])    

    if not config["ssh"]["skip"]:
        SSHDownloader(
            remote_host=config["ssh"]["remote_host"],
            remote_dir=config["ssh"]["remote_path"],
            local_dir=recording_dir
        ).download()

    transcriber = WhisperTranscribe(
        input_root=recording_dir,
        output_root=whisper_dir,
        **config["whisper"],
    )
    transcriber.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
