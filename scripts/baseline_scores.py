"""
Score all 325 reference diffs and write results/baselines.json.

Reference diffs are known-correct (merged PRs), so we skip the test-running
phase and score only on diff quality using the local heuristic scorer.
Scores are on the 0-30 Gittensor scale and carry the same 3-5x inflation
caveat as all local scores — use for relative comparison per-problem, not
as absolute Gittensor validator output.

Baselines serve two purposes:
  1. Upper bound per problem: any agent submission scoring above the baseline
     on the same problem is either better or exploiting the heuristic.
  2. Aggregate oracle score: the mean baseline tells us the average quality
     of the accepted solutions in our pool.

Usage:
    python scripts/baseline_scores.py [--out results/baselines.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROBLEMS_DIR = REPO_ROOT / "benchmark" / "problems"
RESULTS_DIR = REPO_ROOT / "results"

sys.path.insert(0, str(REPO_ROOT))
from benchmark.harness.score import (
    SRC_TOK_SATURATION_SCALE,
    approximate_src_token_score,
    compute_base_score,
)


def score_reference(problem_dir: Path) -> dict | None:
    meta_path = problem_dir / "meta.json"
    ref_path = problem_dir / "reference.diff"
    if not meta_path.exists() or not ref_path.exists():
        return None

    meta = json.loads(meta_path.read_text())
    saturation_scale = float(meta.get("src_tok_saturation_scale", SRC_TOK_SATURATION_SCALE))
    diff_text = ref_path.read_text()

    src_tok, total_tok = approximate_src_token_score(diff_text, saturation_scale)
    base_score = compute_base_score(src_tok, total_tok, saturation_scale)

    return {
        "id": meta["id"],
        "repo": meta.get("repo_name", ""),
        "pr": meta.get("pr_number"),
        "source_token_score": round(src_tok, 2),
        "total_token_score": round(total_tok, 2),
        "base_score": base_score,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score all reference diffs")
    parser.add_argument("--out", default=str(RESULTS_DIR / "baselines.json"))
    args = parser.parse_args()

    baselines = []
    skipped = 0
    for problem_dir in sorted(PROBLEMS_DIR.iterdir()):
        if not problem_dir.is_dir():
            continue
        result = score_reference(problem_dir)
        if result is None:
            skipped += 1
            continue
        baselines.append(result)

    if not baselines:
        print("No problems found.", file=sys.stderr)
        sys.exit(1)

    scores = [b["base_score"] for b in baselines]
    mean_score = round(sum(scores) / len(scores), 2)
    median_scores = sorted(scores)
    median_score = round(median_scores[len(median_scores) // 2], 2)

    out = {
        "count": len(baselines),
        "mean_score": mean_score,
        "median_score": median_score,
        "max_score": round(max(scores), 2),
        "min_score": round(min(scores), 2),
        "scoring_note": (
            "Local heuristic scorer — 3-5x inflation vs Gittensor tree-sitter pipeline. "
            "Use for relative per-problem comparison only."
        ),
        "problems": baselines,
    }

    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))

    print(f"Scored {len(baselines)} problems (skipped {skipped})")
    print(f"Mean baseline: {mean_score:.2f} | Median: {median_score:.2f} | "
          f"Max: {out['max_score']:.2f} | Min: {out['min_score']:.2f}")
    print(f"Written to {dest}")


if __name__ == "__main__":
    main()
