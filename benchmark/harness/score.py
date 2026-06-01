"""
Scores a candidate patch against a benchmark problem.

Mirrors Gittensor's native scoring logic:
  1. Apply patch to the repo at base_commit in a sandbox.
  2. Run the test suite — correctness gates everything.
  3. If tests pass, compute code quality score via AST token analysis.
  4. Final score = correctness_score * quality_score.

Usage:
    python benchmark/harness/score.py --problem benchmark/problems/001/ --patch my.diff
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def load_problem_meta(problem_dir: Path) -> dict:
    meta_path = problem_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json not found in {problem_dir}")
    return json.loads(meta_path.read_text())


def apply_patch(repo_dir: Path, patch_path: Path) -> bool:
    """Apply a unified diff. Returns True if apply succeeded."""
    abs_patch = str(patch_path.resolve())
    result = subprocess.run(
        ["git", "apply", "--check", abs_patch],
        cwd=repo_dir,
        capture_output=True,
    )
    if result.returncode != 0:
        return False
    subprocess.run(
        ["git", "apply", abs_patch],
        cwd=repo_dir,
        check=True,
    )
    return True


def run_tests(repo_dir: Path, test_cmd: list[str]) -> tuple[bool, str]:
    """Run the test suite. Returns (passed, output)."""
    result = subprocess.run(
        test_cmd,
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    passed = result.returncode == 0
    output = result.stdout + result.stderr
    return passed, output


def compute_quality_score(patch_path: Path) -> float:
    """
    Approximate Gittensor's AST token scoring on the patch diff.
    Returns a normalized quality score in [0.0, 1.0].

    Full Gittensor scoring requires the validator's tree-sitter pipeline.
    This is a fast approximation used for local development. The official
    score is computed by the CI harness via the Gittensor scoring engine.
    """
    diff_text = patch_path.read_text()
    added_lines = [l[1:] for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++")]

    # Rough token heuristic: count meaningful code lines
    # Structural keywords get higher weight (approximates AST scoring)
    structural_keywords = {
        "def ": 2.0, "class ": 2.5, "async def ": 1.5,
        "fn ": 2.0, "impl ": 1.75, "struct ": 1.75,
        "func ": 2.0, "interface ": 1.75,
        "for ": 0.5, "while ": 0.5, "if ": 0.35,
        "return ": 0.35, "import ": 0.2,
    }

    token_score = 0.0
    for line in added_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        weight = 0.07  # base identifier weight
        for kw, kw_weight in structural_keywords.items():
            if kw in stripped:
                weight = max(weight, kw_weight)
        token_score += weight

    # Sigmoid saturation matching Gittensor's src_tok_saturation_scale=58.0
    import math
    saturation = 58.0
    quality = 1.0 - math.exp(-token_score / saturation)
    return round(quality, 4)


def score_patch(problem_dir: Path, patch_path: Path) -> dict:
    meta = load_problem_meta(problem_dir)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "repo"

        # Clone repo at base commit
        subprocess.run(
            ["git", "clone", meta["repo_url"], str(repo_dir)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", meta["base_commit"]],
            cwd=repo_dir, check=True, capture_output=True,
        )

        # Apply patch
        patch_applied = apply_patch(repo_dir, patch_path)
        if not patch_applied:
            return {
                "problem_id": meta["id"],
                "patch_applied": False,
                "tests_passed": False,
                "correctness_score": 0.0,
                "quality_score": 0.0,
                "final_score": 0.0,
            }

        # Run tests
        raw_cmd = meta.get("test_cmd", ["python3", "-m", "pytest", "--tb=short", "-q"])
        # Normalize: use python3 if python binary is absent
        import shutil as _shutil
        test_cmd = [("python3" if c == "python" and not _shutil.which("python") else c) for c in raw_cmd]
        tests_passed, test_output = run_tests(repo_dir, test_cmd)
        correctness_score = 1.0 if tests_passed else 0.0

        # Quality score (only meaningful if tests pass)
        quality_score = compute_quality_score(patch_path) if tests_passed else 0.0

        # Gittensor base score formula: MERGED_PR_BASE_SCORE * (1 - exp(-x/scale))
        # We use correctness as a gate and quality as the primary signal
        final_score = correctness_score * (0.5 + 0.5 * quality_score)

        return {
            "problem_id": meta["id"],
            "patch_applied": True,
            "tests_passed": tests_passed,
            "test_output": test_output[-2000:] if not tests_passed else "",
            "correctness_score": correctness_score,
            "quality_score": quality_score,
            "final_score": round(final_score, 4),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a patch against a benchmark problem")
    parser.add_argument("--problem", required=True, help="Path to problem directory")
    parser.add_argument("--patch", required=True, help="Path to unified diff file")
    args = parser.parse_args()

    result = score_patch(Path(args.problem), Path(args.patch))
    print(json.dumps(result, indent=2))

    if not result["tests_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
