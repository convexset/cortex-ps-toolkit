"""Run dev server with profile-context index patching."""

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

    uvicorn.run(
        "cortex_ps_toolkit.server.app_with_profile_context:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        loop="asyncio",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
