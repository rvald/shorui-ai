#!/usr/bin/env python3
"""
CLI utility to clean up raw upload artifacts older than the TTL.

Usage:
    UV_CACHE_DIR=/tmp/uv uv run scripts/cleanup_raw_uploads.py --ttl-days 30
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingestion.services.cleanup import cleanup_raw_uploads


def main():
    parser = argparse.ArgumentParser(description="Cleanup raw upload artifacts")
    parser.add_argument(
        "--ttl-days",
        type=int,
        default=None,
        help="Override TTL in days (defaults to settings.RAW_UPLOAD_TTL_DAYS)",
    )
    args = parser.parse_args()

    result = cleanup_raw_uploads(ttl_days=args.ttl_days)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
