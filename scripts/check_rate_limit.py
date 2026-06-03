"""
Check submission rate limit for a handle.

Counts merged commits touching agent/submissions/{handle}/agent.py
in the past 7 days. If count >= max_per_week, exits 1 (rate-limited).

Exit codes:
  0  — under limit (or within limit)
  1  — rate limit exceeded
  2  — usage error (no handle, bad args)

Usage:
    python scripts/check_rate_limit.py --handle myhandle [--max-per-week 5]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_MAX_PER_WEEK = 5


def count_recent_merges(handle: str, since: str = "7 days ago") -> int:
    """Return number of commits on main in the last `since` period touching this handle's agent.py.

    Counts only commits reachable from origin/main so that iterative pushes to an open PR
    don't prematurely count against the limit before a single submission is merged.
    """
    agent_path = f"agent/submissions/{handle}/agent.py"
    # Use origin/main (the upstream merged state) not HEAD (which includes PR branch commits).
    result = subprocess.run(
        ["git", "log", "origin/main", f"--since={since}", "--oneline", "--", agent_path],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    lines = [l for l in result.stdout.strip().splitlines() if l]
    return len(lines)


def write_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handle", required=True, help="Miner handle to check")
    parser.add_argument(
        "--max-per-week",
        type=int,
        default=DEFAULT_MAX_PER_WEEK,
        help=f"Max merged submissions per 7-day window (default: {DEFAULT_MAX_PER_WEEK})",
    )
    args = parser.parse_args()

    handle = args.handle.strip()
    if not handle:
        print("ERROR: empty handle", file=sys.stderr)
        sys.exit(2)

    count = count_recent_merges(handle)
    remaining = max(0, args.max_per_week - count)
    over_limit = count >= args.max_per_week

    report: list[str] = []
    report.append("## Rate Limit Check")
    report.append(f"Handle: `{handle}` | Window: 7 days | Limit: {args.max_per_week}")
    report.append("")
    report.append(f"Merged submissions this week: **{count}**")

    if over_limit:
        report.append(f"> **RATE LIMIT EXCEEDED** — {handle} has {count} merged submission(s) in the last 7 days (limit: {args.max_per_week}).")
        report.append("")
        report.append("A maintainer should not merge this PR until the window resets.")
        write_summary(report)
        print(
            f"Rate limit: {handle} has {count}/{args.max_per_week} submissions this week — EXCEEDED.",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        report.append(f"✓ Under limit — {remaining} submission(s) remaining this week.")
        write_summary(report)
        print(f"Rate limit: {handle} has {count}/{args.max_per_week} submissions this week — OK.")
        sys.exit(0)


if __name__ == "__main__":
    main()
