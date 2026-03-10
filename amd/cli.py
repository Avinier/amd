from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from .core import (
    DEFAULT_STALE_AFTER_HOURS,
    add_caveat,
    add_event,
    add_signal,
    create_artifact,
    derive_skill_artifact,
    parse_scalar,
    refresh_artifact,
    refresh_tree,
    scan_artifact,
    set_manual_priority,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Adaptive Markdown artifact manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a new AMD artifact")
    init_parser.add_argument("path")
    init_parser.add_argument("--title")
    init_parser.add_argument(
        "--kind",
        default="task",
        choices=["task", "report", "mental-model", "skill-derived"],
    )
    init_parser.add_argument(
        "--persistence",
        default="persistent",
        choices=["persistent", "ephemeral"],
    )
    init_parser.add_argument("--stale-after-hours", type=int, default=DEFAULT_STALE_AFTER_HOURS)
    init_parser.add_argument("--priority", type=int, default=50)
    init_parser.add_argument("--agent", default="system")

    event_parser = subparsers.add_parser("event", help="append a timeline event")
    event_parser.add_argument("path")
    event_parser.add_argument("--agent", required=True)
    event_parser.add_argument("--kind", required=True)
    event_parser.add_argument("--summary", required=True)
    event_parser.add_argument("--details")

    caveat_parser = subparsers.add_parser("caveat", help="add a caveat rule")
    caveat_parser.add_argument("path")
    caveat_parser.add_argument("--text", required=True)
    caveat_parser.add_argument("--severity", default="medium", choices=["low", "medium", "high"])
    caveat_parser.add_argument("--expires-at")
    caveat_parser.add_argument("--agent", default="system")

    signal_parser = subparsers.add_parser("signal", help="append a timeseries datapoint")
    signal_parser.add_argument("path")
    signal_parser.add_argument("--metric", required=True)
    signal_parser.add_argument("--value", required=True)
    signal_parser.add_argument("--unit")
    signal_parser.add_argument("--timestamp")
    signal_parser.add_argument("--agent", default="system")

    refresh_parser = subparsers.add_parser("refresh", help="refresh one artifact")
    refresh_parser.add_argument("path")
    refresh_parser.add_argument("--agent", default="system")

    refresh_all_parser = subparsers.add_parser("refresh-all", help="refresh all AMD artifacts under a root")
    refresh_all_parser.add_argument("root", nargs="?", default=".")
    refresh_all_parser.add_argument("--agent", default="system")

    scan_parser = subparsers.add_parser("scan", help="print AMD metadata summaries")
    scan_parser.add_argument("target", nargs="?", default=".")

    derive_parser = subparsers.add_parser("derive-skill", help="derive a skill artifact from a mental model")
    derive_parser.add_argument("source")
    derive_parser.add_argument("output")
    derive_parser.add_argument("--title")
    derive_parser.add_argument("--agent", default="system")

    priority_parser = subparsers.add_parser("set-priority", help="set manual update priority")
    priority_parser.add_argument("path")
    priority_parser.add_argument("value", type=int)
    priority_parser.add_argument("--agent", default="system")

    watch_parser = subparsers.add_parser("watch", help="periodically refresh all AMD artifacts")
    watch_parser.add_argument("root", nargs="?", default=".")
    watch_parser.add_argument("--interval", type=int, default=60)
    watch_parser.add_argument("--agent", default="watcher")

    return parser


def format_scan(summary: dict[str, object]) -> str:
    parts = [
        f"{summary['path']}",
        f"  title: {summary['title']}",
        f"  kind: {summary['kind']}  status: {summary['status']}  persistence: {summary['persistence']}",
        f"  priority: {summary['priority']}  stale: {summary['stale']}",
        f"  priority_reasons: {', '.join(summary['priority_reasons']) if summary['priority_reasons'] else 'none'}",
        f"  stale_reasons: {', '.join(summary['stale_reasons']) if summary['stale_reasons'] else 'none'}",
        f"  active_caveats: {len(summary['active_caveats'])}",
        f"  timeseries: {summary['timeseries_points']} points latest={summary['timeseries_latest_at']}",
        f"  contributors: {', '.join(summary['contributors']) if summary['contributors'] else 'none'}",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        path = create_artifact(
            args.path,
            title=args.title,
            kind=args.kind,
            persistence=args.persistence,
            stale_after_hours=args.stale_after_hours,
            manual_priority=args.priority,
            agent=args.agent,
        )
        print(path)
        return 0

    if args.command == "event":
        add_event(args.path, agent=args.agent, kind=args.kind, summary=args.summary, details=args.details)
        print(args.path)
        return 0

    if args.command == "caveat":
        add_caveat(
            args.path,
            text=args.text,
            severity=args.severity,
            agent=args.agent,
            expires_at=args.expires_at,
        )
        print(args.path)
        return 0

    if args.command == "signal":
        add_signal(
            args.path,
            metric=args.metric,
            value=parse_scalar(args.value),
            unit=args.unit,
            timestamp=args.timestamp,
            agent=args.agent,
        )
        print(args.path)
        return 0

    if args.command == "refresh":
        print(json.dumps(refresh_artifact(args.path, agent=args.agent), indent=2, sort_keys=True))
        return 0

    if args.command == "refresh-all":
        print(json.dumps(refresh_tree(args.root, agent=args.agent), indent=2, sort_keys=True))
        return 0

    if args.command == "scan":
        target = Path(args.target)
        if target.is_file():
            print(format_scan(scan_artifact(target)))
            return 0
        matches = list(sorted(target.rglob("*.amd.md")))
        if not matches:
            print("No AMD artifacts found.", file=sys.stderr)
            return 1
        for index, match in enumerate(matches):
            if index:
                print()
            print(format_scan(scan_artifact(match)))
        return 0

    if args.command == "derive-skill":
        output = derive_skill_artifact(args.source, args.output, title=args.title, agent=args.agent)
        print(output)
        return 0

    if args.command == "set-priority":
        set_manual_priority(args.path, value=args.value, agent=args.agent)
        print(args.path)
        return 0

    if args.command == "watch":
        while True:
            results = refresh_tree(args.root, agent=args.agent)
            print(json.dumps(results, indent=2, sort_keys=True))
            sys.stdout.flush()
            time.sleep(args.interval)

    parser.print_help()
    return 1
