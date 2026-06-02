"""
Tree-sitter AST scorer matching Gittensor's DAS scoring engine.

Adapted from gittensor/validator/utils/tree_sitter_scoring.py (MIT).
Uses the same weight JSON files as the DAS validator to produce scores
that match the authoritative DAS scores.

Score path:
  1. Parse old and new file content into tree-sitter ASTs.
  2. Compute symmetric difference of node signatures.
  3. Weight each node by structural bonus or leaf token weight.
  4. Apply language weight (Go/Java/C = 2.0, Python = 1.5, JS = 1.15…).
  5. Accumulate: source files into src_score, test files into total_score.
  6. Caller applies: 25×(1−exp(−src_score/58)) + min(total/1500,1)×5

Returns None if tree_sitter is not installed (caller falls back to heuristic).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Optional tree-sitter import — fail gracefully so score.py can fall back
# ---------------------------------------------------------------------------
try:
    from tree_sitter import Node, Parser, Tree
    from tree_sitter_language_pack import get_parser as _get_ts_parser
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _TREE_SITTER_AVAILABLE = False

_WEIGHTS_DIR = Path(__file__).parent / "weights"

# Inline-test language extensions (Rust's #[test], etc.)
_INLINE_TEST_EXTS = {"rs", "zig", "d"}
_INLINE_TEST_RE = re.compile(
    r"#\[(?:cfg\(test\)|test|tokio::test)\]|#!\[cfg\(test\)\]"
    r"|^test\s+\"[^\"]+\"\s*\{|^test\s*\{"
    r"|^unittest\s*\{",
    re.MULTILINE,
)

# Non-code extensions: use line-count scoring, not tree-sitter
_NON_CODE_EXTS = {
    "md", "mdx", "markdown", "txt", "text", "tex", "rst", "adoc", "asciidoc",
    "json", "jsonc", "yaml", "yml", "toml", "xml", "csv", "tsv",
    "ini", "cfg", "conf", "config", "properties", "plist", "erb",
}
_MAX_LINES_NON_CODE = 300

# Test file weight in DAS scorer
_TEST_FILE_WEIGHT = 0.05
_MAX_FILE_SIZE = 1_000_000  # bytes — matches gittensor constant

# Comment node types to skip in tree-sitter walk
_COMMENT_NODE_TYPES = {
    "comment", "line_comment", "block_comment", "doc_comment",
    "multiline_comment", "comment_block", "inline_comment", "shebang",
}


# ---------------------------------------------------------------------------
# Weight loading — parsed once per process
# ---------------------------------------------------------------------------

class _Weights:
    __slots__ = ("structural", "leaf", "languages")

    def __init__(self, structural: dict, leaf: dict, languages: dict) -> None:
        self.structural = structural  # node_type → float
        self.leaf = leaf             # node_type → float
        self.languages = languages   # ext → {"weight": float, "language": str|None}

    def lang_name(self, ext: str) -> Optional[str]:
        return self.languages.get(ext, {}).get("language")

    def lang_weight(self, ext: str) -> float:
        return self.languages.get(ext, {}).get("weight", 0.12)

    def supports_tree_sitter(self, ext: str) -> bool:
        return ext not in _NON_CODE_EXTS and self.lang_name(ext) is not None


_weights_cache: Optional[_Weights] = None


def _load_weights() -> _Weights:
    global _weights_cache
    if _weights_cache is not None:
        return _weights_cache

    with open(_WEIGHTS_DIR / "token_weights.json", encoding="utf-8") as f:
        tw = json.load(f)
    with open(_WEIGHTS_DIR / "programming_languages.json", encoding="utf-8") as f:
        pl = json.load(f)

    _weights_cache = _Weights(
        structural=tw.get("structural_bonus", {}),
        leaf=tw.get("leaf_tokens", {}),
        languages=pl,
    )
    return _weights_cache


# ---------------------------------------------------------------------------
# Tree-sitter parser cache
# ---------------------------------------------------------------------------

_parser_cache: dict[str, "Parser"] = {}


def _get_parser(language: str) -> Optional["Parser"]:
    if not _TREE_SITTER_AVAILABLE:
        return None
    if language in _parser_cache:
        return _parser_cache[language]
    try:
        p = _get_ts_parser(language)
        # timeout_micros attribute was removed in newer tree-sitter versions — skip
        try:
            p.timeout_micros = 5_000_000  # 5 s parse bound — same guard as DAS
        except AttributeError:
            pass
        _parser_cache[language] = p
        return p
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AST node signature collection
# ---------------------------------------------------------------------------

def _collect_signatures(tree: "Tree", weights: _Weights) -> Counter:
    """Walk AST and collect (type, kind[, text]) signatures, skipping comments."""
    sigs: Counter = Counter()
    cursor = tree.walk()

    while True:
        node: "Node" = cursor.node
        node_type = node.type

        if node_type not in _COMMENT_NODE_TYPES:
            if weights.structural.get(node_type, 0.0) > 0:
                sigs[("structural", node_type)] += 1
            if node.child_count == 0:
                sigs[("leaf", node_type, node.text or b"")] += 1
            if cursor.goto_first_child():
                continue

        if cursor.goto_next_sibling():
            continue

        while cursor.goto_parent():
            if cursor.goto_next_sibling():
                break
        else:
            return sigs


# ---------------------------------------------------------------------------
# Per-file scoring
# ---------------------------------------------------------------------------

def _score_file(
    old_content: Optional[str],
    new_content: Optional[str],
    ext: str,
    weights: _Weights,
    lang_weight: float,
) -> float:
    """Compute weighted AST symmetric-diff score for one file pair."""
    lang = weights.lang_name(ext)
    if not lang:
        return 0.0

    parser = _get_parser(lang)
    if parser is None:
        return 0.0

    old_sigs: Counter = Counter()
    new_sigs: Counter = Counter()

    if old_content:
        try:
            tree = parser.parse(old_content.encode("utf-8"))
            old_sigs = _collect_signatures(tree, weights)
        except Exception:
            pass

    if new_content:
        try:
            tree = parser.parse(new_content.encode("utf-8"))
            new_sigs = _collect_signatures(tree, weights)
        except Exception:
            pass

    added = new_sigs - old_sigs
    deleted = old_sigs - new_sigs

    score = 0.0
    for sig, count in (added + deleted).items():
        kind = sig[0]
        node_type = sig[1]
        if kind == "structural":
            score += weights.structural.get(node_type, 0.0) * count
        else:
            score += weights.leaf.get(node_type, 0.0) * count

    return score * lang_weight


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class FilePair:
    """Represents one file's old/new content for scoring."""

    __slots__ = ("path", "old_content", "new_content")

    def __init__(
        self,
        path: str,
        old_content: Optional[str],
        new_content: Optional[str],
    ) -> None:
        self.path = path
        self.old_content = old_content
        self.new_content = new_content


def is_test_file(path: str, new_content: Optional[str] = None, ext: str = "") -> bool:
    """Return True if this file should be weighted as a test file."""
    name = path.lower()
    parts = name.split("/")
    filename = parts[-1]

    if (
        "_test." in filename
        or filename.startswith("test_")
        or "/test/" in name
        or "/tests/" in name
        or "/spec/" in name
        or "/specs/" in name
        or "spec." in filename
        or filename.endswith(".test.ts")
        or filename.endswith(".test.js")
        or filename.endswith(".spec.ts")
        or filename.endswith(".spec.js")
    ):
        return True

    # Inline test detection (Rust #[test], etc.)
    if ext in _INLINE_TEST_EXTS and new_content and _INLINE_TEST_RE.search(new_content):
        return True

    return False


def score_file_pairs(pairs: list[FilePair]) -> Optional[tuple[float, float]]:
    """
    Score a list of file pairs using tree-sitter AST comparison.

    Returns (src_score, total_score) where:
      - src_score:   contribution from non-test source files (feeds main exponential)
      - total_score: contribution from all files (feeds cross-category bonus)

    Returns None if tree_sitter is unavailable (caller should fall back to heuristic).
    """
    if not _TREE_SITTER_AVAILABLE:
        return None

    weights = _load_weights()

    src_score = 0.0
    total_score = 0.0

    for pair in pairs:
        # Determine extension
        ext = Path(pair.path).suffix.lstrip(".").lower()
        if not ext:
            # Dockerfile, Makefile, etc.
            ext = Path(pair.path).name.lower()

        # Skip files that are too large
        old_bytes = pair.old_content.encode("utf-8") if pair.old_content else b""
        new_bytes = pair.new_content.encode("utf-8") if pair.new_content else b""
        if len(old_bytes) > _MAX_FILE_SIZE or len(new_bytes) > _MAX_FILE_SIZE:
            continue

        file_is_test = is_test_file(pair.path, pair.new_content, ext)
        file_weight = _TEST_FILE_WEIGHT if file_is_test else 1.0

        # Non-code extensions: line-count scoring on changed lines (matches DAS file.changes)
        if ext in _NON_CODE_EXTS:
            lang_w = weights.lang_weight(ext)
            # Count changed lines (additions + deletions) — matches `file.changes` from GitHub API.
            if pair.old_content is None:
                change_lines = len((pair.new_content or "").splitlines())
            elif pair.new_content is None:
                change_lines = len(pair.old_content.splitlines())
            else:
                import difflib
                old_lines = pair.old_content.splitlines()
                new_lines = pair.new_content.splitlines()
                change_lines = sum(
                    (j2 - j1) + (i2 - i1)
                    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes()
                    if op != "equal"
                )
            line_score = lang_w * min(change_lines, _MAX_LINES_NON_CODE) * file_weight
            total_score += line_score
            if not file_is_test:
                src_score += line_score
            continue

        if not weights.supports_tree_sitter(ext):
            continue

        lang_w = weights.lang_weight(ext)
        file_score = _score_file(pair.old_content, pair.new_content, ext, weights, lang_w * file_weight)

        total_score += file_score
        if not file_is_test:
            src_score += file_score

    return src_score, total_score


def available() -> bool:
    """Return True if tree_sitter is importable."""
    return _TREE_SITTER_AVAILABLE
