"""
Agent interface for the Gittensor Base-Miner Benchmark.

Implement BaseAgent.solve() to participate. Your agent receives a Problem
(issue + repo context) and must return a Patch (unified diff string).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class FileContext:
    """A single file's content, provided as read-only context."""
    path: str
    content: str
    language: str = ""


@dataclass
class Problem:
    """A benchmark problem derived from a real Gittensor issue."""

    # Unique identifier, e.g. "001"
    id: str

    # The GitHub issue body (markdown)
    issue_title: str
    issue_body: str

    # Repository info
    repo_name: str          # e.g. "entrius/gittensor"
    base_commit: str        # SHA of the commit just before the issue was filed

    # Relevant file contents at base_commit (pre-filtered for context window)
    context_files: list[FileContext] = field(default_factory=list)

    # Full file tree at base_commit (paths only)
    file_tree: list[str] = field(default_factory=list)

    # Test command used to score the patch — agents can use this to understand
    # which test files their fix must satisfy (e.g. ["python", "-m", "pytest",
    # "--tb=short", "-q", "tests/validator/test_repo_scan.py"])
    test_cmd: list[str] = field(default_factory=list)

    # Hard constraints enforced by the harness
    allowed_models: list[str] = field(default_factory=list)
    time_limit_seconds: int = 120
    output_token_budget: int = 50_000


@dataclass
class Patch:
    """A candidate solution produced by an agent."""

    # Unified diff string (git diff format)
    diff: str

    # Optional: agent's internal reasoning log (not scored, for transparency)
    reasoning: str = ""


class BaseAgent(abc.ABC):
    """
    Base class for benchmark agents.

    Subclass this, implement solve(), and register your agent in CONTRIBUTING.md.
    """

    @abc.abstractmethod
    def solve(self, problem: Problem) -> Patch:
        """
        Produce a patch for the given problem.

        Called once per problem. Must return within problem.time_limit_seconds.
        May use only models in problem.allowed_models.
        Network is blocked during evaluation — no external calls except to the
        whitelisted model API.
        """
        raise NotImplementedError
