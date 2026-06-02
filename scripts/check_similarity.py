"""
Compare a submitted agent.py against all existing submissions.

Uses two complementary signals:
  1. AST structural fingerprint — node-type bigrams from a normalized AST.
     Catches structural copies even when all identifiers are renamed.
  2. Token-level Jaccard — lowercased identifier set.
     Catches copy-paste with minor edits.

A submission is flagged if EITHER signal exceeds the threshold.

Exit codes:
  0  — all similarities below threshold (clean)
  1  — at least one submission is too similar (flag for review)
  2  — usage error (agent file not found, etc.)

Usage:
    python scripts/check_similarity.py --agent agent/submissions/handle/agent.py
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# AST structural fingerprint
# ---------------------------------------------------------------------------

def ast_bigrams(source: str) -> frozenset[str]:
    """Return a set of parent→child node-type bigrams from the source AST.

    Identifiers and string literals are stripped — only the structural shape
    of the code is captured. Two files with the same logic but renamed
    variables will produce nearly identical bigrams.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return frozenset()

    bigrams: set[str] = set()
    for node in ast.walk(tree):
        parent_type = type(node).__name__
        for child in ast.iter_child_nodes(node):
            child_type = type(child).__name__
            bigrams.add(f"{parent_type}>{child_type}")

    return frozenset(bigrams)


# ---------------------------------------------------------------------------
# Token fingerprint (original signal)
# ---------------------------------------------------------------------------

def tokenize(text: str) -> frozenset[str]:
    """Split source into a token set (lowercased identifiers/keywords)."""
    return frozenset(t.lower() for t in re.split(r"[^a-zA-Z0-9_]", text) if len(t) > 1)


# ---------------------------------------------------------------------------
# Similarity metric
# ---------------------------------------------------------------------------

def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


# ---------------------------------------------------------------------------
# CI reporting
# ---------------------------------------------------------------------------

def write_summary(lines: list[str]) -> None:
    """Write to $GITHUB_STEP_SUMMARY if running in CI, otherwise print."""
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
    parser.add_argument("--agent", required=True, help="Path to submitted agent.py")
    parser.add_argument(
        "--submissions-dir",
        default=str(REPO_ROOT / "agent" / "submissions"),
        help="Directory containing all agent submissions",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Jaccard similarity threshold for flagging (default: {DEFAULT_THRESHOLD})",
    )
    args = parser.parse_args()

    new_path = Path(args.agent)
    if not new_path.exists():
        print(f"ERROR: agent file not found: {new_path}", file=sys.stderr)
        sys.exit(2)

    new_source = new_path.read_text()
    new_tokens = tokenize(new_source)
    new_bigrams = ast_bigrams(new_source)

    new_handle = new_path.parent.name
    submissions_dir = Path(args.submissions_dir)

    flagged: list[tuple[str, float, float, str]] = []  # handle, token_sim, ast_sim, reason
    checked = 0

    for existing in sorted(submissions_dir.glob("*/agent.py")):
        handle = existing.parent.name
        if handle == new_handle:
            continue  # skip self (re-submissions)

        source = existing.read_text()
        token_sim = jaccard(new_tokens, tokenize(source))
        ast_sim = jaccard(new_bigrams, ast_bigrams(source))
        checked += 1

        if token_sim >= args.threshold:
            flagged.append((handle, token_sim, ast_sim, "token"))
        elif ast_sim >= args.threshold:
            flagged.append((handle, token_sim, ast_sim, "structure"))

    report: list[str] = []
    report.append("## Similarity Check")
    report.append(
        f"Compared `{new_handle}` against **{checked}** existing submission(s) "
        f"(token + AST structural fingerprint)."
    )
    report.append(f"Threshold: {args.threshold:.0%} on either signal")
    report.append("")

    if flagged:
        report.append(f"> **WARNING** — {len(flagged)} submission(s) flagged as too similar:")
        report.append("")
        report.append("| Existing handle | Token sim | AST sim | Flagged by |")
        report.append("|----------------|----------|---------|------------|")
        for handle, tsim, asim, reason in sorted(flagged, key=lambda x: -max(x[1], x[2])):
            report.append(f"| `{handle}` | {tsim:.1%} | {asim:.1%} | {reason} |")
        report.append("")
        report.append("A maintainer should inspect this before merging.")
        write_summary(report)
        print("\n".join(report), file=sys.stderr)
        sys.exit(1)
    else:
        report.append("✓ No similar submissions found — clean.")
        write_summary(report)
        print(f"Similarity check: {checked} comparison(s) — all below {args.threshold:.0%}")
        sys.exit(0)


if __name__ == "__main__":
    main()
