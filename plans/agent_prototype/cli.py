from __future__ import annotations

import argparse
import sys

from .capture import drain_queue, run_once_and_submit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mem0 Screen Ingestion Agent CLI")
    sub = parser.add_subparsers(dest="cmd")

    once = sub.add_parser("once", help="Capture once and submit")
    once.add_argument("--config", required=False, help="Path to YAML/TOML config")
    once.add_argument("--profile", required=False, help="Profile app name (e.g., work)")

    drain = sub.add_parser("drain", help="Replay queued payloads")
    drain.add_argument("--config", required=False, help="Path to YAML/TOML config")
    drain.add_argument("--batch", type=int, default=25, help="Batch size per run")

    args = parser.parse_args(argv)
    if args.cmd == "once":
        res = run_once_and_submit(config_path=args.config, profile=args.profile)
        print(res)
        return 0 if res.get("status") in {"ok", "skipped", "queued"} else 1
    elif args.cmd == "drain":
        res = drain_queue(config_path=args.config, batch_size=args.batch)
        print(res)
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


