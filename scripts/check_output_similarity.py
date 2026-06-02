"""
Compare a new agent's output behavior against all previously stored fingerprints.

"Behavior" means the per-problem diff hashes the agent produced during evaluation.
Two agents that produce the same diffs on the same problems are functionally
identical regardless of how different their source code looks.

This catches:
  - Agents that call another submission's API or forward its output
  - Agents with entirely renamed/reformatted code but unchanged logic
  - Sybil submissions running the same underlying prompt

The similarity score is:
    overlap = problems both agents were evaluated on
    matches = problems in the overlap where both diff hashes are identical
    score   = matches / overlap  (undefined if overlap < MIN_OVERLAP)

Exit codes:
  0  — all similarities below threshold (clean)
  1  — at least one stored agent is too similar (flag for review)
  2  — usage error (fingerprint file not found, etc.)

Usage:
    # After eval writes a fingerprint
    python scripts/check_output_similarity.py --fingerprint behaviors/new_handle.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BEHAVIORS_DIR = REPO_ROOT / "results" / "behaviors"

DEFAULT_THRESHOLD = 0.70   # 70% of overlapping problems produce identical diffs
MIN_OVERLAP = 5            # need at least 5 shared problems to make a comparison


# ---------------------------------------------------------------------------
# CI reporting helper
# ---------------------------------------------------------------------------

def write_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fingerprint", required=True,
        help="Path to the new agent's behavior fingerprint JSON",
    )
    parser.add_argument(
        "--behaviors-dir",
        default=str(BEHAVIORS_DIR),
        help="Directory containing stored behavior fingerprints",
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help=f"Matching-diff fraction above which a pair is flagged (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--min-overlap", type=int, default=MIN_OVERLAP,
        help=f"Minimum shared problems required for a comparison (default: {MIN_OVERLAP})",
    )
    args = parser.parse_args()

    fp_path = Path(args.fingerprint)
    if not fp_path.exists():
        print(f"ERROR: fingerprint file not found: {fp_path}", file=sys.stderr)
        sys.exit(2)

    new_fp = json.loads(fp_path.read_text())
    new_handle = new_fp.get("handle", fp_path.stem)
    new_diffs: dict[str, str] = new_fp.get("diffs", {})

    if not new_diffs:
        print("No diff hashes in fingerprint — skipping output similarity check.")
        sys.exit(0)

    behaviors_dir = Path(args.behaviors_dir)
    flagged: list[tuple[str, int, float]] = []
    checked = 0

    if behaviors_dir.exists():
        for stored_path in sorted(behaviors_dir.glob("*.json")):
            stored_fp = json.loads(stored_path.read_text())
            stored_handle = stored_fp.get("handle", stored_path.stem)

            if stored_handle == new_handle:
                continue  # skip self (re-submissions)

            stored_diffs: dict[str, str] = stored_fp.get("diffs", {})
            overlap_ids = set(new_diffs) & set(stored_diffs)

            if len(overlap_ids) < args.min_overlap:
                continue  # not enough shared problems to compare

            matches = sum(
                1 for pid in overlap_ids
                if new_diffs[pid] == stored_diffs[pid] and new_diffs[pid]
            )
            similarity = matches / len(overlap_ids)
            checked += 1

            if similarity >= args.threshold:
                flagged.append((stored_handle, len(overlap_ids), similarity))

    report: list[str] = []
    report.append("## Output Behavior Similarity Check")
    report.append(
        f"Compared `{new_handle}` against **{checked}** stored fingerprint(s) "
        f"(per-problem diff-hash matching, min overlap: {args.min_overlap})."
    )
    report.append(f"Threshold: {args.threshold:.0%} matching diffs on overlapping problems")
    report.append("")

    if flagged:
        report.append(
            f"> **WARNING** — {len(flagged)} agent(s) flagged as behaviorally too similar:"
        )
        report.append("")
        report.append("| Existing handle | Overlap | Match rate |")
        report.append("|----------------|---------|------------|")
        for handle, overlap, sim in sorted(flagged, key=lambda x: -x[2]):
            report.append(f"| `{handle}` | {overlap} problems | {sim:.1%} |")
        report.append("")
        report.append(
            "These agents produce nearly identical patches on the same problems. "
            "A maintainer should inspect before merging."
        )
        write_summary(report)
        print("\n".join(report), file=sys.stderr)
        sys.exit(1)
    else:
        msg = f"Output similarity: {checked} comparison(s) — all below {args.threshold:.0%}"
        if checked == 0:
            msg = "Output similarity: no stored fingerprints yet — skipping (clean)"
        report.append(f"✓ {msg}")
        write_summary(report)
        print(msg)
        sys.exit(0)


if __name__ == "__main__":
    main()
