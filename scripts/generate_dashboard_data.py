"""Generate data.json for the static dashboard from the current problem pool."""

import json
import pathlib
import sys
from datetime import date

PROBLEMS_DIR = pathlib.Path(__file__).parent.parent / "benchmark" / "problems"
LEADERBOARD_DATA = [
    {
        "rank": None,
        "agent": "Oracle (accepted solution)",
        "score": 21.60,
        "model": "—",
        "date": "—",
        "note": "Upper bound",
    },
    {
        "rank": 1,
        "agent": "ExampleAgent",
        "score": None,
        "model": "claude-3-5-haiku",
        "date": "—",
        "note": "Reference observe→plan→act→verify loop",
    },
]


def load_problems():
    problems = []
    for p in sorted(PROBLEMS_DIR.iterdir()):
        meta_file = p / "meta.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text())
        except Exception:
            continue
        das = meta.get("das_score")
        das_f = float(das) if das is not None else None
        repo = meta.get("repo_name", "")
        pr = meta.get("pr_number")
        issue = meta.get("issue_number")
        problems.append(
            {
                "id": meta.get("id"),
                "repo": repo,
                "pr": pr,
                "issue": issue,
                "title": (meta.get("issue_title") or "")[:120],
                "merged_at": meta.get("merged_at", ""),
                "das_score": das_f,
                "das_base_score": float(meta.get("das_base_score") or 0),
                "das_token_score": float(meta.get("das_token_score") or 0),
                "pr_url": f"https://github.com/{repo}/pull/{pr}",
                "issue_url": f"https://github.com/{repo}/issues/{issue}" if issue else None,
            }
        )
    return problems


def main(out_path: str | None = None):
    problems = load_problems()

    by_repo: dict[str, int] = {}
    for p in problems:
        by_repo[p["repo"]] = by_repo.get(p["repo"], 0) + 1

    # Try to load real leaderboard results if they exist
    results_file = pathlib.Path(__file__).parent.parent / "results" / "leaderboard.json"
    leaderboard = LEADERBOARD_DATA
    if results_file.exists():
        try:
            leaderboard = json.loads(results_file.read_text())
        except Exception:
            pass

    data = {
        "generated_at": date.today().isoformat(),
        "pool_size": len(problems),
        "shard_size": 30,
        "oracle_score": 21.60,
        "repos": by_repo,
        "leaderboard": leaderboard,
        "problems": problems,
    }

    dest = pathlib.Path(out_path) if out_path else pathlib.Path("dashboard_data.json")
    dest.write_text(json.dumps(data, indent=2))
    print(f"Wrote {len(problems)} problems to {dest}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
