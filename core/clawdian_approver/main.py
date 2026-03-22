from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import Config
from .logging import init_logging
from .service import ClawdianApproverService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawdian-approver",
        description="Bridge OpenClaw exec approvals to Latch 2FA",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Run the approver service")
    sub.add_parser("check", help="Validate env config and exit")
    return parser


async def _run() -> int:
    config = Config.from_env()
    service = ClawdianApproverService(config)
    await service.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    init_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = Config.from_env()
    except Exception as exc:
        logging.getLogger(__name__).error("Invalid configuration: %s", exc)
        return 2

    if args.command == "check":
        logging.getLogger(__name__).info(
            "Configuration looks valid. gateway=%s latch=%s allow=%s",
            config.gateway_ws_url,
            config.latch_base_url,
            config.allow_decision,
        )
        return 0

    if args.command == "run":
        try:
            return asyncio.run(_run())
        except KeyboardInterrupt:
            return 130

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

