"""
Main evaluation entry point for the Gittensor Base-Miner Benchmark.

Runs an agent against all (or selected) benchmark problems and reports scores.

Usage:
    python benchmark/evaluate.py --agent agent/example/agent.py
    python benchmark/evaluate.py --agent agent/example/agent.py --problems 001,002,005
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path


PROBLEMS_DIR = Path(__file__).parent / "problems"


def load_agent(agent_path: str):
    """Dynamically load an agent class from a file path."""
    spec = importlib.util.spec_from_file_location("submission", agent_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Find the BaseAgent subclass
    from agent.base import BaseAgent
    for name in dir(module):
        obj = getattr(module, name)
        try:
            if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent:
                return obj()
        except TypeError:
            pass

    raise ValueError(f"No BaseAgent subclass found in {agent_path}")


def load_problem(problem_dir: Path):
    """Load a Problem from a problem directory."""
    from agent.base import FileContext, Problem

    meta = json.loads((problem_dir / "meta.json").read_text())
    context_files = []
    context_dir = problem_dir / "context"
    if context_dir.exists():
        for f in sorted(context_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(context_dir)
                ext = f.suffix.lstrip(".")
                context_files.append(FileContext(
                    path=str(rel),
                    content=f.read_text(errors="replace"),
                    language=ext,
                ))

    file_tree = meta.get("file_tree", [])
    allowed_models_path = Path(__file__).parent / "harness" / "allowed_models.txt"
    allowed_models = [
        line.strip() for line in allowed_models_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    return Problem(
        id=meta["id"],
        issue_title=meta["issue_title"],
        issue_body=meta["issue_body"],
        repo_name=meta["repo_name"],
        base_commit=meta["base_commit"],
        context_files=context_files,
        file_tree=file_tree,
        allowed_models=allowed_models,
        time_limit_seconds=meta.get("time_limit_seconds", 120),
        output_token_budget=meta.get("output_token_budget", 50_000),
    )


def run_evaluation(agent_path: str, problem_ids: list[str] | None = None) -> dict:
    agent = load_agent(agent_path)

    all_problems = sorted(PROBLEMS_DIR.glob("*/meta.json"))
    if not all_problems:
        print("No problems found. Run scripts/curate_problems.py to populate benchmark/problems/")
        sys.exit(1)

    if problem_ids:
        all_problems = [p for p in all_problems if p.parent.name in problem_ids]

    results = []
    for meta_path in all_problems:
        problem_dir = meta_path.parent
        problem = load_problem(problem_dir)

        print(f"  [{problem.id}] {problem.issue_title[:60]}...")
        start = time.time()
        try:
            patch = agent.solve(problem)
            elapsed = time.time() - start

            # Write patch to temp file for scoring
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".diff", mode="w", delete=False) as f:
                f.write(patch.diff)
                patch_path = Path(f.name)

            from benchmark.harness.score import score_patch
            score = score_patch(problem_dir, patch_path)
            patch_path.unlink()

            score["elapsed_seconds"] = round(elapsed, 2)
            results.append(score)
            status = "PASS" if score["tests_passed"] else "FAIL"
            print(f"       {status}  final_score={score['final_score']}  ({elapsed:.1f}s)")

        except Exception as e:
            elapsed = time.time() - start
            results.append({
                "problem_id": problem.id,
                "error": str(e),
                "final_score": 0.0,
                "elapsed_seconds": round(elapsed, 2),
            })
            print(f"       ERROR: {e}")

    total = sum(r["final_score"] for r in results)
    mean = total / len(results) if results else 0.0
    return {"mean_score": round(mean, 4), "problems": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an agent on the base-miner benchmark")
    parser.add_argument("--agent", required=True, help="Path to agent .py file")
    parser.add_argument("--problems", help="Comma-separated list of problem IDs (default: all)")
    parser.add_argument("--output", help="Write JSON results to this file")
    args = parser.parse_args()

    problem_ids = args.problems.split(",") if args.problems else None

    print(f"Evaluating: {args.agent}")
    results = run_evaluation(args.agent, problem_ids)
    print(f"\nMean score: {results['mean_score']} / 1.0")

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results written to {args.output}")

    sys.exit(0 if results["mean_score"] > 0 else 1)


if __name__ == "__main__":
    main()
