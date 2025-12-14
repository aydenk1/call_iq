#!/usr/bin/env python3
"""
Pipeline for syncing UniFi Talk call recordings, splitting channels, running
Whisper transcription, and merging the transcripts into a diarized
conversation log.
"""

from __future__ import annotations

import argparse

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
    parser = argparse.ArgumentParser(description="Sync and process UniFi Talk call recordings.")
    parser.add_argument("--remote-host", default=os.environ.get("UNIFI_REMOTE_HOST"), help="user@host for rsync.")
    parser.add_argument("--remote-path", default=os.environ.get("UNIFI_REMOTE_PATH"), help="Remote path containing mp3 files.")
    parser.add_argument("--whisper-model", default=os.environ.get("WHISPER_MODEL", "large-v3-turbo"), help="faster-whisper model size.")
    parser.add_argument("--whisper-language", default="en", help="Set when all calls are the same language to skip auto-detect.")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size passed to faster-whisper (default 4).")
    parser.add_argument("--whisper-workers", type=int, default=None, help="Worker threads for faster-whisper (default half logical cores).")
    parser.add_argument("--speaker-left", default="Speaker A", help="Label for the left channel speaker.")
    parser.add_argument("--speaker-right", default="Speaker B", help="Label for the right channel speaker.")
    parser.add_argument("--overwrite", action="store_true", help="Reprocess files even when outputs exist.")
    parser.add_argument("--no-sync", action="store_true", help="Skip rsync step and process existing local files.")
    parser.add_argument("--split-workers", type=int, default=None, help="Number of concurrent ffmpeg channel split processes (defaults to CPU count).",)
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args(argv)

    if not args.remote_host or not args.remote_path:
        parser.error("Remote host and remote path are required (set via args or UNIFI_REMOTE_* env vars).")

    work_dir = Path(__file__).resolve().parent / "data"
    recording_dir = work_dir / "recordings"
    whisper_dir = work_dir / "whisper"
    default_args = {
        "work_dir": str(work_dir),
        "recording_dir": str(recording_dir),
        "whisper_dir": str(whisper_dir)
    }
    default_args.update({k: v for k, v in vars(args) if v is not None})
    return default_args

def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    configure_logging(args["verbose"])

    if not args["no_sync"]:
        SSHDownloader(
            remote_host=args["remote_host"],                 
            remote_dir=args["remote_path"],
            local_dir=args["recording_dir"]
        ).download()

    transcriber = WhisperTranscribe(
        input_root=args["recording_dir"],
        output_root=args["whisper_dir"],
        model_name=args["whisper-model"],
        language=args["whisper_language"],
        batch_size=args["batch_size"],
        overwrite=args["overwrite"]
    )
    transcriber.run()
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
