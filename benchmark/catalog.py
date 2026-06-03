"""
Shared benchmark constants — single source of truth.

REPO_CATEGORY, DIFFICULTY_TIERS, and DEFAULT_SHARD_BUDGET were previously
duplicated across evaluate.py, api/server.py, and scripts/generate_dashboard_data.py.
All files now import from here; adding a new repo requires a single-line change.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Repo → language category
# ---------------------------------------------------------------------------
# Covers all Gittensor DAS registered repos plus external prestige repos added
# via scripts/expand_pool_external.py. Keys are lowercase "owner/repo" slugs.

REPO_CATEGORY: dict[str, str] = {
    # DAS registered repos
    "entrius/gittensor": "python",
    "entrius/allways": "python",
    "entrius/das-github-mirror": "python",
    "entrius/allways-ui": "typescript",
    "entrius/gittensor-ui": "typescript",
    "entrius/oc-1": "typescript",
    "aglover1221/product-data-extractor": "python",
    "cogniax/tao-pulse-app": "typescript",
    "e35ventura/taopedia": "python",
    "e35ventura/taopedia-articles": "python",
    "geniepod/genie-claw": "rust",
    "infiniflow/ragflow": "python",
    "jsonbored/awesome-claude": "typescript",
    "jsonbored/gittensory": "typescript",
    "mkdev11/gittensor-hub": "typescript",
    "vouchdev/vouch": "python",
    "phase-rs/phase": "rust",
    "seroperson/jvm-live-reload": "jvm",
    "touchpilot/touchpilot": "jvm",
    "we-promise/sure": "ruby",
    # External prestige repos — Python
    "pytest-dev/pytest": "python",
    "pallets/click": "python",
    "pallets/werkzeug": "python",
    "encode/starlette": "python",
    "psf/requests": "python",
    "aio-libs/aiohttp": "python",
    "pallets/flask": "python",
    "tiangolo/fastapi": "python",
    "tornadoweb/tornado": "python",
    "twisted/twisted": "python",
    "python-trio/trio": "python",
    "celery/celery": "python",
    "python/mypy": "python",
    # External prestige repos — Ruby
    "rubocop/rubocop": "ruby",
    "rubocop/rubocop-rails": "ruby",
    # External prestige repos — TypeScript
    "colinhacks/zod": "typescript",
    "vitest-dev/vitest": "typescript",
    "trpc/trpc": "typescript",
    "vuejs/core": "typescript",
    "sindresorhus/got": "typescript",
    "tanstack/query": "typescript",
    # External prestige repos — Rust
    "tokio-rs/tokio": "rust",
    "clap-rs/clap": "rust",
    "hyperium/hyper": "rust",
    "tokio-rs/axum": "rust",
    "serde-rs/serde": "rust",
    # External prestige repos — JVM
    "fasterxml/jackson-databind": "jvm",
    "square/okhttp": "jvm",
    "google/guava": "jvm",
    # External prestige repos — Go
    "gin-gonic/gin": "go",
    "labstack/echo": "go",
    "gofiber/fiber": "go",
    "grpc/grpc-go": "go",
    "spf13/cobra": "go",
}


def repo_lang(repo: str) -> str:
    """Return language category for a repo slug (case-insensitive)."""
    return REPO_CATEGORY.get(repo.lower(), "python")


# ---------------------------------------------------------------------------
# Difficulty tiers
# ---------------------------------------------------------------------------
# Each entry: (name, added_lines_threshold, score_weight)
# A problem's difficulty is the first tier whose threshold exceeds its added-line count.
# None threshold means "everything else".

DIFFICULTY_TIERS: list[tuple[str, int | None, float]] = [
    ("easy",   30,   1.0),   # < 30 added lines  → weight 1.0×
    ("medium", 150,  1.5),   # 30–149             → weight 1.5×
    ("hard",   None, 2.0),   # 150+               → weight 2.0×
]


def problem_tier(added_lines: int) -> tuple[str, float]:
    """Return (tier_name, weight) for the given added-line count."""
    for name, threshold, weight in DIFFICULTY_TIERS:
        if threshold is None or added_lines < threshold:
            return name, weight
    return "hard", 2.0


# ---------------------------------------------------------------------------
# Default per-category shard budget (authoritative fallback only)
# ---------------------------------------------------------------------------
# The live value is pool_config.json["shard_budget"] — this is used only when
# pool_config.json is unavailable (e.g., tests, fresh checkouts).
# Must sum to shard_size (30) and be proportional to pool composition.

DEFAULT_SHARD_BUDGET: dict[str, int] = {
    "python":     11,
    "rust":        7,
    "typescript":  5,
    "go":          3,
    "jvm":         2,
    "ruby":        2,
}
