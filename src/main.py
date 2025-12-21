#!/usr/bin/env python3
"""
Pipeline for syncing UniFi Talk call recordings, splitting channels, running
Whisper transcription, and merging the transcripts into a diarized
conversation log.
"""

from __future__ import annotations

import argparse
import yaml

import logging
import os
import sys

from pathlib import Path
from typing import Sequence


from ssh_downloader import SSHDownloader
from whisper_transcribe import WhisperTranscribe


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args(argv: Sequence[str]) -> dict:
    base_dir = Path(__file__).resolve().parent.parent
    default_config_path = base_dir / "config.yml"
    parser = argparse.ArgumentParser(description="Sync and process UniFi Talk call recordings.")
    parser.add_argument("--config", default=str(default_config_path), help="Path to config YAML file.")
    parser.add_argument("--remote-host", default=None, help="user@host for rsync.")
    parser.add_argument("--remote-path", default=None, help="Remote path containing mp3 files.")
    parser.add_argument("--whisper-model", default=None, help="faster-whisper model size.")
    parser.add_argument("--whisper-language", default=None, help="Set when all calls are the same language to skip auto-detect.")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size passed to faster-whisper.")
    parser.add_argument("--whisper-workers", type=int, default=None, help="Worker threads for faster-whisper (default half logical cores).")
    parser.add_argument("--speaker-left", default=None, help="Label for the left channel speaker.")
    parser.add_argument("--speaker-right", default=None, help="Label for the right channel speaker.")
    parser.add_argument("--force-preprocess", action="store_true", default=None, help="Reprocess audio files even if output exists.")
    parser.add_argument("--force-transcribe", action="store_true", default=None, help="Force recreation of all transcriptions.")
    parser.add_argument("--force-postprocess", action="store_true", default=None, help="Force transcription post-processing of all transcriptions.")
    parser.add_argument("--no-sync", action="store_true", default=None, help="Skip rsync step and process existing local files.")
    parser.add_argument("--split-workers", type=int, default=None, help="Number of concurrent ffmpeg channel split processes (defaults to CPU count).",)
    parser.add_argument("--verbose", action="store_true", default=None, help="Enable debug logging.")
    return vars(parser.parse_args(argv))


def load_config(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data

def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    config_path = Path(args.pop("config"))
    config = load_config(config_path)

    base_dir = Path(__file__).resolve().parent.parent
    work_dir = Path(config.get("work_dir") or (base_dir / "data"))
    defaults = {
        "work_dir": str(work_dir),
        "recording_dir": str(config.get("recording_dir") or (work_dir / "recordings")),
        "whisper_dir": str(config.get("whisper_dir") or (work_dir / "whisper")),
        "no_sync": False,
        "verbose": False,
    }
    merged = {**defaults, **config, **{k: v for k, v in args.items() if v is not None}}

    if not merged.get("no_sync") and (not merged.get("remote_host") or not merged.get("remote_path")):
        raise SystemExit("Remote host and remote path are required (set via config or args).")

    configure_logging(merged["verbose"])

    if not merged["no_sync"]:
        SSHDownloader(
            remote_host=merged["remote_host"],
            remote_dir=merged["remote_path"],
            local_dir=merged["recording_dir"]
        ).download()

    transcriber = WhisperTranscribe(
        input_root=merged["recording_dir"],
        output_root=merged["whisper_dir"],
        model_name=merged.get("whisper_model", "large-v3-turbo"),
        language=merged.get("whisper_language", "en"),
        batch_size=merged.get("batch_size", 16),
        num_workers=merged.get("whisper_workers"),
        force_preprocess=merged.get("force_preprocess", False),
        force_transcribe=merged.get("force_transcribe", False),
        force_postprocess=merged.get("force_postprocess", False),
        initial_prompt=merged.get("initial_prompt"),
        hotwords=merged.get("hotwords"),
        merge_segments_s=merged.get("merge_segments_s", 2.0),
        vad_min_silence_duration_ms=merged.get("vad_min_silence_duration_ms", 3000),
    )
    transcriber.run()
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
