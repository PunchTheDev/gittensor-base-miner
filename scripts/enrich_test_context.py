"""
Retroactively add test files to the context/ directory of existing benchmark problems.

Two enrichment passes:
  1. Python pytest with explicit test file paths in test_cmd — targeted extraction.
  2. All languages (npm, cargo, gradlew, Python) — scans reference.diff for test files
     (paths containing "test" or "spec") and extracts newly-added ones from the diff or
     fetches pre-existing ones from GitHub at base_commit.

Test files define the requirements — agents need to see them to know what to satisfy.

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


def find_test_paths_in_diff(diff: str) -> list[tuple[str, bool]]:
    """
    Scan a unified diff and return test file paths with whether they are newly added.

    Returns a list of (path, is_new) tuples. is_new=True means the file was created by
    the PR (--- /dev/null), so content can be extracted directly from the diff.
    """
    results: list[tuple[str, bool]] = []
    current_path: str | None = None
    current_is_new = False

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            if current_path is not None:
                results.append((current_path, current_is_new))
            m = re.search(r" b/(.+)$", line)
            if m:
                path = m.group(1)
                fname = path.rsplit("/", 1)[-1]
                if (
                    "test" in fname.lower()
                    or "spec" in fname.lower()
                    or "/tests/" in path
                    or "/test/" in path
                    or path.startswith("tests/")
                    or path.startswith("test/")
                ):
                    current_path = path
                    current_is_new = False
                else:
                    current_path = None
            else:
                current_path = None
        elif current_path and line.startswith("--- /dev/null"):
            current_is_new = True
        elif current_path and line.startswith("--- a/"):
            current_is_new = False

    if current_path is not None:
        results.append((current_path, current_is_new))

    return results


def enrich_problem_general(problem_dir: Path, dry_run: bool) -> bool:
    """
    Second-pass enrichment: scan the reference diff for test files across all languages.
    Skips problems where test files are already present in context/.
    """
    meta_path = problem_dir / "meta.json"
    ref_diff_path = problem_dir / "reference.diff"
    if not meta_path.exists() or not ref_diff_path.exists():
        return False

    meta = json.loads(meta_path.read_text())
    repo: str = meta.get("repo_name", "")
    base_commit: str = meta.get("base_commit", "")
    context_dir = problem_dir / "context"

    # Check if test files already present
    if context_dir.exists():
        for f in context_dir.rglob("*"):
            if f.is_file() and "test" in f.name.lower():
                return False  # already enriched

    ref_diff = ref_diff_path.read_text(errors="replace")
    test_paths = find_test_paths_in_diff(ref_diff)
    if not test_paths:
        return False

    enriched = False
    for path, is_new in test_paths[:3]:  # cap at 3 test files per problem
        dest = context_dir / path
        if dest.exists():
            continue

        if is_new:
            content = extract_added_file(ref_diff, path)
            if content is not None:
                if dry_run:
                    print(f"  [DRY] {problem_dir.name}: would extract {path} from diff")
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(content)
                    print(f"  + {problem_dir.name}: extracted {path} from diff")
                enriched = True
                continue

        # Pre-existing test file — fetch from GitHub at base_commit
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
            print(f"  ! {problem_dir.name}: {path} ({exc.__class__.__name__})")

    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich benchmark problems with test file context")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing")
    args = parser.parse_args()

    problems = sorted(PROBLEMS_DIR.iterdir())
    total = len(problems)

    print(f"Pass 1: Python pytest explicit test paths ({total} problems)...")
    enriched_p1 = 0
    for prob_dir in problems:
        if not prob_dir.is_dir():
            continue
        if enrich_problem(prob_dir, dry_run=args.dry_run):
            enriched_p1 += 1

    print(f"\nPass 2: All languages — scanning diffs for test files ({total} problems)...")
    enriched_p2 = 0
    for prob_dir in problems:
        if not prob_dir.is_dir():
            continue
        if enrich_problem_general(prob_dir, dry_run=args.dry_run):
            enriched_p2 += 1

    print(f"\nDone. Pass 1: {enriched_p1} problems | Pass 2: {enriched_p2} problems | "
          f"Total enriched: {enriched_p1 + enriched_p2}/{total}")


if __name__ == "__main__":
    main()
