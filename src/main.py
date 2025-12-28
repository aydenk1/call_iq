#!/usr/bin/env python3
"""Compatibility entrypoint for pipeline.main."""

from __future__ import annotations

import sys

from pipeline.main import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
