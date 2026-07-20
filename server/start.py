"""
Life Online backend entry point.

Usage:
    uv run python start.py                  # dev (reload)
    uv run python start.py --prod           # production (multi-worker, no reload)
    uv run python start.py --port 9000      # custom port
    PORT=9000 uv run python start.py        # via env
"""
from __future__ import annotations

import argparse

import uvicorn

from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Life Online API server")
    parser.add_argument("--host", default=settings.app.host, help="bind host")
    parser.add_argument("--port", type=int, default=settings.app.port, help="bind port")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="worker count (prod mode). defaults to settings.app.workers",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="production mode: no reload, multi-worker",
    )
    args = parser.parse_args()

    if args.prod:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            workers=args.workers or settings.app.workers,
            log_level=settings.app.log_level.lower(),
            access_log=True,
            reload=False,
        )
    else:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=["app"],
            log_level=settings.app.log_level.lower(),
        )


if __name__ == "__main__":
    main()
