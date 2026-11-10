"""CLI for installation planning, verification and guarded installation."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .backends import Backends, InstallResult
from .core import Detector, build_plan, capability, host_compatible, select
from .manifest import ManifestError, load


ROOT = Path(__file__).resolve().parent.parent


def arguments(argv=None):
    parser = argparse.ArgumentParser(prog="./install.sh", description="Manifest driven macOS ARM64 installer; no C2 services are started")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list Manifest tools and current detection")
    mode.add_argument("--audit", action="store_true", help="read-only inventory of installed tools")
    mode.add_argument("--dry-run", action="store_true", help="print ordered actions without changes")
    mode.add_argument("--verify", action="store_true", help="safe metadata, format and hash checks")
    parser.add_argument("--category", action="append", default=[], help="select one category; repeatable")
    parser.add_argument("--tool", action="append", default=[], help="select one tool ID or alias; repeatable")
    parser.add_argument("--profile", default="standard", choices=["minimal", "standard", "full"])
    parser.add_argument("--yes", action="store_true", help="approve the displayed install plan in a noninteractive shell")
    parser.add_argument("--accept-unknown-size", action="store_true", help="explicitly allow actions with unknown download/build size")
    parser.add_argument("--json", action="store_true", help="machine readable read-only output")
    return parser.parse_args(argv)


def _serialize_plan(item, tool):
    return {
        "id": item.ident,
        "category": tool["category"],
        "method": item.method,
        "current": item.current.state,
        "decision": item.result,
        "action": item.action,
        "reason": item.reason,
        "source": tool["source"],
        "version": tool["version"],
        "estimated_bytes": item.estimated_bytes,
    }


def _print_rows(rows: list[dict], mode: str) -> None:
    if mode == "list":
        print("ID\tCATEGORY\tMETHOD\tCURRENT\tOPTIONAL")
        for row in rows:
            print(f"{row['id']}\t{row['category']}\t{row['method']}\t{row['current']}\t{row['optional']}")
    elif mode in ("audit", "verify"):
        print("ID\tSTATE\tVERSION\tREASON")
        for row in rows:
            print(f"{row['id']}\t{row['state']}\t{row['version']}\t{row['reason']}")
    else:
        print("ID\tCURRENT\tDECISION\tACTION\tSIZE\tREASON")
        for row in rows:
            size = str(row["estimated_bytes"]) if row["estimated_bytes"] is not None else "unknown"
            print(f"{row['id']}\t{row['current']}\t{row['decision']}\t{row['action']}\t{size}\t{row['reason']}")


def _safe_text(value: str) -> str:
    value = re.sub(r"/Users/[^/\s]+", "<home>", str(value))
    value = re.sub(r"(?i)(token|password|secret|api[_-]?key)=[^\s]+", r"\1=<redacted>", value)
    return value[:300]


def _write_log(profile: str, results: list[dict]) -> None:
    # A user-local path outside the repository, created only for actual installs.
    directory = Path.home() / "Library/Logs/RedTeam_Toolkit_for_Mac"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "installer.jsonl"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": f"{sys.platform}-{platform.machine()}",
        "profile": profile,
        "results": [{key: _safe_text(value) if isinstance(value, str) else value for key, value in item.items()} for item in results],
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        raise


def _confirm(prompt: str, expected: str) -> bool:
    try:
        return input(prompt).strip() == expected
    except EOFError:
        return False


def main(argv=None, root: Path = ROOT) -> int:
    args = arguments(argv)
    if args.category and args.tool:
        print("error: --category and --tool cannot be combined", file=sys.stderr)
        return 3
    if args.json and not (args.list or args.audit or args.verify or args.dry_run):
        print("error: --json is available only for read-only modes", file=sys.stderr)
        return 3
    try:
        manifest, lock = load(root)
        ids = select(manifest, profile=args.profile, categories=args.category, names=args.tool)
    except (ManifestError, OSError, json.JSONDecodeError) as exc:
        print(f"manifest error: {_safe_text(str(exc))}", file=sys.stderr)
        return 3
    by_id = {tool["id"]: tool for tool in manifest["tools"]}
    if args.list or args.audit or args.verify:
        if not args.category and not args.tool:
            ids = [tool["id"] for tool in manifest["tools"]]
        detector = Detector(root, manifest, lock)
        rows = []
        for ident in ids:
            tool = by_id[ident]
            found = detector.detect(tool)
            rows.append({
                "id": ident, "category": tool["category"], "method": tool["install_method"],
                "optional": tool["optional"], "state": found.state, "current": found.state,
                "version": found.version, "reason": found.reason,
            })
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            _print_rows(rows, "list" if args.list else "verify" if args.verify else "audit")
        return 2 if args.verify and any(row["state"] in ("incompatible", "broken") for row in rows) else 0
    detector = Detector(root, manifest, lock)
    plan = build_plan(root, manifest, lock, ids, detector)
    rows = [_serialize_plan(item, by_id[item.ident]) for item in plan]
    free = shutil.disk_usage(root.parent if root.name == "install" else root).free
    known = sum(item.estimated_bytes or 0 for item in plan if item.result == "ready")
    unknown = sum(item.result == "ready" and item.estimated_bytes is None for item in plan)
    summary = {"profile": args.profile, "selected_count": len(ids), "free_bytes": free, "known_required_bytes": known, "unknown_size_actions": unknown, "items": rows}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Profile={args.profile} selected={len(ids)} free={free} bytes known-minimum={known} bytes unknown-size-actions={unknown}")
        _print_rows(rows, "plan")
    if args.dry_run:
        return 0
    if not host_compatible():
        print("error: installation requires native macOS arm64", file=sys.stderr)
        return 3
    if known > free:
        print("error: insufficient free disk space for known artifacts", file=sys.stderr)
        return 3
    ready = [item for item in plan if item.result == "ready"]
    if not ready:
        return 2 if any(item.result in ("blocked", "manual-required") for item in plan) else 0
    if not args.yes and (not sys.stdin.isatty() or not _confirm("Install the READY actions shown above? Type INSTALL: ", "INSTALL")):
        print("installation cancelled; no changes made", file=sys.stderr)
        return 3
    if unknown and not args.accept_unknown_size:
        if not sys.stdin.isatty() or not _confirm("Some download/build sizes are unknown. Type UNKNOWN to continue: ", "UNKNOWN"):
            print("unknown-size actions were not approved; no changes made", file=sys.stderr)
            return 3
    backends = Backends(root, manifest, lock)
    outcomes = []
    completed = {}
    for item in plan:
        tool = by_id[item.ident]
        if item.result == "ready" and any(completed.get(dep) not in ("success", "skipped") for dep in tool["dependencies"]):
            result = InstallResult(item.ident, "blocked", "dependency did not complete")
        else:
            result = backends.execute(item, tool)
        completed[item.ident] = result.result
        outcomes.append({
            "id": item.ident, "method": item.method, "result": result.result,
            "reason": result.reason, "source": tool["source"], "version": tool["version"],
            "hash_result": result.hash_result,
        })
        print(f"{item.ident}: {result.result}: {result.reason}")
        if result.result == "failed":
            print("installation stopped after a backend failure; completed tools are preserved", file=sys.stderr)
            break
    _write_log(args.profile, outcomes)
    if any(item["result"] == "failed" for item in outcomes):
        return 1
    if any(item["result"] in ("blocked", "manual-required") for item in outcomes):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
