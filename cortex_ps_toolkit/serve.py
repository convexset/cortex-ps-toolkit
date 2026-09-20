"""Run the local asyncio dev web server (Starlette + uvicorn)."""

from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cortex_ps_toolkit serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--reload", action="store_true", help="Auto-reload on Python changes")
    parser.add_argument("--debug", action="store_true", help="Verbose errors and logging")
    args = parser.parse_args(argv)

    if args.debug:
        os.environ["CORTEX_PS_DEBUG"] = "1"

    import uvicorn

    # Blocking toolkit work (HTTP to tenants, disk cache) runs in asyncio.to_thread
    # from route handlers so multiple API requests can progress concurrently.
    uvicorn.run(
        "cortex_ps_toolkit.server.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        loop="asyncio",
    )
    return 0
