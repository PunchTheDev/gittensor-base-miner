"""
Build and refresh the benchmark problem pool from all registered Gittensor repos.

Fetches merged PRs with linked issues from every repo in pool_config.json,
applying the same curation criteria as the original curate_problems.py but
across the full registered-repo corpus.

Problem IDs: <owner>_<repo>_<pr_number> for multi-repo entries.
Legacy problems from entrius/gittensor use their PR number directly (backward compat).

Usage:
    # Refresh all repos (adds new problems, skips existing ones)
    python scripts/build_pool.py

    # Single repo, useful for targeted updates
    python scripts/build_pool.py --repo entrius/allways

    # Dry run: show what would be curated without writing
    python scripts/build_pool.py --dry-run

    # Override output directory
    python scripts/build_pool.py --output benchmark/problems

    # Limit how many new problems are added per repo
    python scripts/build_pool.py --limit-per-repo 10
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
POOL_CONFIG_PATH = REPO_ROOT / "benchmark" / "pool_config.json"


def load_pool_config() -> dict:
    return json.loads(POOL_CONFIG_PATH.read_text())


def gh_get(endpoint: str) -> dict | list:
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def extract_issue_numbers(body: str) -> list[int]:
    pattern = r"(?:fixes|closes|resolves)\s+#(\d+)"
    return [int(m) for m in re.findall(pattern, body or "", re.IGNORECASE)]


def get_pr_diff(repo: str, pr_number: int) -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{pr_number}",
         "--header", "Accept: application/vnd.github.diff"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def has_test_files(diff: str) -> bool:
    return bool(
        re.search(r"^diff --git a/test", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/test_", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/tests?/", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/spec/", diff, re.MULTILINE)
    )


def get_file_tree(repo: str, commit: str) -> list[str]:
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/git/trees/{commit}?recursive=1"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)
        return [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]
    except Exception:
        return []


def select_context_files(repo: str, base_commit: str, diff: str, max_files: int = 15) -> list[dict]:
    changed_paths = re.findall(r"^diff --git a/(.+) b/", diff, re.MULTILINE)
    context_files = []
    fetched: set[str] = set()

    for path in changed_paths[:max_files]:
        if path in fetched:
            continue
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{repo}/contents/{path}?ref={base_commit}"],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            context_files.append({"path": path, "content": content})
            fetched.add(path)
        except Exception:
            pass

    return context_files


def make_problem_id(repo: str, pr_number: int) -> str:
    """Generate a globally unique problem ID across all registered repos."""
    owner, name = repo.split("/", 1)
    slug = f"{owner}_{name}"
    # Legacy compat: entrius/gittensor keeps the bare PR number format
    if repo == "entrius/gittensor":
        return f"{pr_number:04d}"
    return f"{slug}_{pr_number}"


def infer_test_cmd(repo: str, diff: str) -> list[str]:
    """Guess the right test command based on repo language/structure."""
    # Look for changed test files in the diff
    test_files = re.findall(
        r"^diff --git a/((?:[^/]+/)*test[^/\s]*|(?:[^/]+/)*/test_[^/\s]*)", diff, re.MULTILINE
    )
    specific_files = [f for f in test_files if f.endswith(".py")][:5]

    if specific_files:
        return ["python", "-m", "pytest", "--tb=short", "-q"] + specific_files

    # Language heuristics
    if re.search(r"\.(rs)\b", diff):
        return ["cargo", "test"]
    if re.search(r"\.(ts|tsx|js|jsx)\b", diff):
        return ["npm", "test", "--", "--passWithNoTests"]
    if re.search(r"\.(java|kt)\b", diff):
        return ["./gradlew", "test"]
    if re.search(r"\.(go)\b", diff):
        return ["go", "test", "./..."]

    return ["python", "-m", "pytest", "--tb=short", "-q"]


def curate_pr(
    repo: str,
    pr_number: int,
    output_dir: Path,
    cutoff_date: str,
    dry_run: bool = False,
) -> bool:
    problem_id = make_problem_id(repo, pr_number)
    problem_out = output_dir / problem_id

    if (problem_out / "meta.json").exists():
        print(f"  Skip #{pr_number} ({repo}): already in pool")
        return False  # Not new, but not an error

    try:
        pr_data = gh_get(f"repos/{repo}/pulls/{pr_number}")
    except subprocess.CalledProcessError:
        print(f"  Skip #{pr_number} ({repo}): PR fetch failed")
        return False

    if pr_data.get("state") != "closed" or not pr_data.get("merged_at"):
        print(f"  Skip #{pr_number} ({repo}): not merged")
        return False

    merged_at = pr_data["merged_at"]
    if merged_at < cutoff_date:
        print(f"  Skip #{pr_number} ({repo}): merged before cutoff ({merged_at[:10]})")
        return False

    issue_numbers = extract_issue_numbers(pr_data.get("body", ""))
    if not issue_numbers:
        print(f"  Skip #{pr_number} ({repo}): no linked issue")
        return False

    try:
        issue_data = gh_get(f"repos/{repo}/issues/{issue_numbers[0]}")
    except subprocess.CalledProcessError:
        print(f"  Skip #{pr_number} ({repo}): issue fetch failed")
        return False

    if issue_data.get("created_at", "") >= pr_data.get("created_at", ""):
        print(f"  Skip #{pr_number} ({repo}): issue created after PR")
        return False

    diff = get_pr_diff(repo, pr_number)
    if not has_test_files(diff):
        print(f"  Skip #{pr_number} ({repo}): no test files in diff")
        return False

    if dry_run:
        print(f"  [DRY RUN] Would curate #{pr_number} ({repo}): {issue_data['title'][:60]}")
        return True

    base_commit = pr_data["base"]["sha"]
    file_tree = get_file_tree(repo, base_commit)
    context_files = select_context_files(repo, base_commit, diff)
    test_cmd = infer_test_cmd(repo, diff)

    problem_out.mkdir(parents=True, exist_ok=True)
    context_out = problem_out / "context"
    context_out.mkdir(exist_ok=True)

    meta = {
        "id": problem_id,
        "repo_name": repo,
        "repo_url": f"https://github.com/{repo}",
        "base_commit": base_commit,
        "pr_number": pr_number,
        "issue_number": issue_numbers[0],
        "issue_title": issue_data["title"],
        "issue_body": issue_data["body"] or "",
        "merged_at": merged_at,
        "test_cmd": test_cmd,
        "time_limit_seconds": 120,
        "output_token_budget": 50_000,
        "file_tree": file_tree[:500],
    }
    (problem_out / "meta.json").write_text(json.dumps(meta, indent=2))

    for cf in context_files:
        out_path = context_out / cf["path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(cf["content"])

    (problem_out / "reference.diff").write_text(diff)

    print(f"  + #{pr_number} ({repo}): {issue_data['title'][:60]}")
    return True


def build_repo(
    repo: str,
    output_dir: Path,
    cutoff_date: str,
    limit_per_repo: int,
    dry_run: bool,
) -> int:
    print(f"\n--- {repo} ---")
    added = 0
    for page in range(1, 11):  # up to 1000 PRs
        try:
            prs = gh_get(
                f"repos/{repo}/pulls?state=closed&per_page=100&page={page}"
                f"&sort=updated&direction=desc"
            )
        except subprocess.CalledProcessError as e:
            print(f"  API error: {e}")
            break

        if not prs:
            break

        merged = [pr for pr in prs if pr.get("merged_at")]
        for pr in merged:
            if added >= limit_per_repo:
                return added
            if curate_pr(repo, pr["number"], output_dir, cutoff_date, dry_run):
                added += 1

        if len(prs) < 100:
            break  # last page

    return added


def main() -> None:
    cfg = load_pool_config()

    parser = argparse.ArgumentParser(description="Build/refresh the benchmark problem pool")
    parser.add_argument("--repo", help="Curate a single repo (default: all registered repos)")
    parser.add_argument("--output", default=cfg["pool_dir"], help="Pool output directory")
    parser.add_argument("--limit-per-repo", type=int, default=50,
                        help="Max new problems to add per repo (default: 50)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without writing files")
    args = parser.parse_args()

    output_dir = REPO_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    cutoff = cfg["model_cutoff_date"]

    repos = [args.repo] if args.repo else cfg["registered_repos"]
    total = 0
    for repo in repos:
        added = build_repo(repo, output_dir, cutoff, args.limit_per_repo, args.dry_run)
        total += added

    existing = len(list(output_dir.glob("*/meta.json")))
    print(f"\nPool: {existing} total problems ({total} newly added)")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
