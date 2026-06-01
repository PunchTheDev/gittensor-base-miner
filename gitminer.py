#!/usr/bin/env python3
"""
gitminer — CLI for the Gittensor Base-Miner Benchmark.

Subcommands:
    eval     Score an agent against the current shard (or all problems)
    hash     Compute the commit-reveal SHA-256 hash for a patch file
    shard    Print the current week's 30-problem shard IDs
    submit   Validate an agent, generate its commit-reveal hash, and print PR instructions

Usage:
    python gitminer.py eval agent/submissions/myhandle/agent.py
    python gitminer.py eval agent/submissions/myhandle/agent.py --no-sandbox
    python gitminer.py eval agent/submissions/myhandle/agent.py --all
    python gitminer.py eval agent/submissions/myhandle/agent.py --problems 930,986
    python gitminer.py hash my_patch.diff
    python gitminer.py shard
    python gitminer.py submit agent/submissions/myhandle/agent.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))


def cmd_eval(args: argparse.Namespace) -> None:
    from benchmark.evaluate import run_evaluation

    problem_ids = args.problems.split(",") if args.problems else None
    results = run_evaluation(
        agent_path=args.agent,
        problem_ids=problem_ids,
        use_sandbox=not args.no_sandbox,
        use_all=args.all,
    )

    scores = [r["final_score"] for r in results.get("results", []) if "final_score" in r]
    if not scores:
        print("\nNo scores recorded.")
        return

    mean = sum(scores) / len(scores)
    print(f"\n{'─'*50}")
    print(f"  Problems evaluated : {len(scores)}")
    print(f"  Mean score         : {mean:.2f} / 30.00")
    print(f"  Oracle mean        : 21.60 / 30.00")
    print(f"  Gap to oracle      : {21.60 - mean:.2f}")
    print(f"{'─'*50}")

    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(results, indent=2))
        print(f"  Results saved to   : {out}")


def cmd_hash(args: argparse.Namespace) -> None:
    patch_path = Path(args.patch)
    if not patch_path.exists():
        print(f"Error: patch file not found: {patch_path}", file=sys.stderr)
        sys.exit(1)

    content = patch_path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    print(sha)
    print(f"\nCommit this hash before submitting your agent.")
    print(f"The hash proves you had the agent at this point — copy it into your PR description.")


def cmd_shard(args: argparse.Namespace) -> None:
    from benchmark.evaluate import select_shard, load_pool_config, POOL_DIR

    config = load_pool_config()
    all_problem_dirs = sorted(p.parent for p in POOL_DIR.glob("*/meta.json"))
    if not all_problem_dirs:
        print("No problems found. Run scripts/build_pool.py to populate benchmark/problems/")
        sys.exit(1)

    shard = select_shard(all_problem_dirs, config)
    print(f"Current weekly shard ({len(shard)} problems):")
    for d in shard:
        import json as _json
        meta = _json.loads((d / "meta.json").read_text())
        print(f"  {meta['id']:<32}  {meta['repo_name']}  —  {meta['issue_title'][:55]}")


def cmd_submit(args: argparse.Namespace) -> None:
    agent_path = Path(args.agent)
    if not agent_path.exists():
        print(f"Error: agent file not found: {agent_path}", file=sys.stderr)
        sys.exit(1)

    # Validate agent can be loaded
    try:
        from benchmark.evaluate import load_agent
        load_agent(str(agent_path))
        print(f"Agent loaded successfully: {agent_path}")
    except Exception as exc:
        print(f"Agent failed to load: {exc}", file=sys.stderr)
        sys.exit(1)

    # Compute hash of the agent file
    content = agent_path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()

    # Derive handle from path: agent/submissions/<handle>/agent.py
    parts = agent_path.parts
    handle = "unknown"
    if "submissions" in parts:
        idx = parts.index("submissions")
        if idx + 1 < len(parts):
            handle = parts[idx + 1]

    print(f"\nAgent SHA-256: {sha}")
    print(f"\n{'─'*60}")
    print("Next steps to submit:")
    print(f"  1. Commit your agent to: agent/submissions/{handle}/agent.py")
    print(f"  2. Include this hash in your PR description:")
    print(f"       agent-sha256: {sha}")
    print(f"  3. Open a PR to main — CI will run the benchmark and post your score.")
    print(f"  4. If you beat the leader, your entry appears in LEADERBOARD.md.")
    print(f"{'─'*60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gitminer",
        description="Gittensor Base-Miner Benchmark CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # eval
    p_eval = sub.add_parser("eval", help="Score an agent against the benchmark")
    p_eval.add_argument("agent", help="Path to the agent Python file")
    p_eval.add_argument("--no-sandbox", action="store_true",
                        help="Skip Docker sandbox (faster, less accurate — for local dev)")
    p_eval.add_argument("--all", action="store_true",
                        help="Evaluate against all 105 pool problems (default: current 30-problem shard)")
    p_eval.add_argument("--problems", metavar="IDS",
                        help="Comma-separated problem IDs to evaluate (e.g. 930,986)")
    p_eval.add_argument("--output", metavar="FILE",
                        help="Save full results JSON to FILE")
    p_eval.set_defaults(func=cmd_eval)

    # hash
    p_hash = sub.add_parser("hash", help="Compute commit-reveal SHA-256 for a patch file")
    p_hash.add_argument("patch", help="Path to the unified diff / patch file")
    p_hash.set_defaults(func=cmd_hash)

    # shard
    p_shard = sub.add_parser("shard", help="Print current week's 30-problem shard")
    p_shard.set_defaults(func=cmd_shard)

    # submit
    p_submit = sub.add_parser("submit", help="Validate agent and print PR submission instructions")
    p_submit.add_argument("agent", help="Path to the agent Python file")
    p_submit.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
