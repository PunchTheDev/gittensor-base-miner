"""
Retroactively add test files to the context/ directory of existing benchmark problems.

For Python pytest problems with explicit test file paths in test_cmd, finds those
test files in two ways:
  1. Newly-added test files: extracted from reference.diff (added as new files in the PR).
  2. Pre-existing test files: fetched from GitHub at base_commit.

Test files define the requirements — agents need to see them to know what to satisfy.

Run once after upgrading select_context_files to include test files.
Usage:
    python3 scripts/enrich_test_context.py
    python3 scripts/enrich_test_context.py --dry-run
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import time
from pathlib import Path


PROBLEMS_DIR = Path(__file__).parent.parent / "benchmark" / "problems"
GH_RATE_DELAY = 0.5  # seconds between GitHub API calls


def gh_api(endpoint: str) -> dict:
    result = subprocess.run(
        ["gh", "api", f"https://api.github.com/{endpoint}",
         "-H", "User-Agent: gitminer-enrich"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def extract_added_file(diff: str, path: str) -> str | None:
    """
    Extract the full content of a newly-added file from a unified diff.
    Returns the file content (without leading '+') or None if not found.
    """
    # Match a diff block that adds 'path' as a new file (--- /dev/null)
    pattern = re.compile(
        r"diff --git a/" + re.escape(path) + r" b/" + re.escape(path) +
        r".*?(?=\ndiff --git |\Z)",
        re.DOTALL,
    )
    match = pattern.search(diff)
    if not match:
        return None

    block = match.group(0)
    # Only proceed if this is a new file (--- /dev/null)
    if "--- /dev/null" not in block:
        return None

    lines = []
    in_hunk = False
    for line in block.splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            pass  # deletion from /dev/null — shouldn't occur
        elif line.startswith("\\"):
            pass  # "No newline at end of file" marker
        elif not line.startswith("-"):
            lines.append(line)  # context line

    return "\n".join(lines) if lines else None


def enrich_problem(problem_dir: Path, dry_run: bool) -> bool:
    meta_path = problem_dir / "meta.json"
    if not meta_path.exists():
        return False

    meta = json.loads(meta_path.read_text())
    test_cmd: list[str] = meta.get("test_cmd", [])
    repo: str = meta.get("repo_name", "")
    base_commit: str = meta.get("base_commit", "")

    if not (test_cmd and test_cmd[0] == "python" and len(test_cmd) > 4):
        return False  # non-Python or no explicit test files

    test_paths = [arg for arg in test_cmd[4:] if arg.endswith(".py") and not arg.startswith("-")]
    if not test_paths:
        return False

    context_dir = problem_dir / "context"
    context_dir.mkdir(exist_ok=True)

    ref_diff_path = problem_dir / "reference.diff"
    ref_diff = ref_diff_path.read_text() if ref_diff_path.exists() else ""

    enriched = False
    for path in test_paths[:3]:
        dest = context_dir / path
        if dest.exists():
            continue  # already present

        # Strategy 1: extract from reference.diff (newly-added test file)
        content = extract_added_file(ref_diff, path)
        if content is not None:
            if dry_run:
                print(f"  [DRY] {problem_dir.name}: would extract {path} from reference.diff")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content)
                print(f"  + {problem_dir.name}: extracted {path} from reference.diff")
            enriched = True
            continue

        # Strategy 2: fetch from GitHub at base_commit (pre-existing test file)
        if dry_run:
            print(f"  [DRY] {problem_dir.name}: would fetch {path} from GitHub@{base_commit[:8]}")
            enriched = True
            continue

        try:
            time.sleep(GH_RATE_DELAY)
            data = gh_api(f"repos/{repo}/contents/{path}?ref={base_commit}")
            file_content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(file_content)
            print(f"  + {problem_dir.name}: fetched {path} from GitHub")
            enriched = True
        except Exception as exc:
            print(f"  ! {problem_dir.name}: {path} not in diff or GitHub ({exc.__class__.__name__})")

    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich benchmark problems with test file context")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing")
    args = parser.parse_args()

    problems = sorted(PROBLEMS_DIR.iterdir())
    total = len(problems)
    enriched_count = 0

    print(f"Scanning {total} problems in {PROBLEMS_DIR}...")
    for prob_dir in problems:
        if not prob_dir.is_dir():
            continue
        if enrich_problem(prob_dir, dry_run=args.dry_run):
            enriched_count += 1

    print(f"\nDone. {enriched_count}/{total} problems enriched with test file context.")


if __name__ == "__main__":
    main()
