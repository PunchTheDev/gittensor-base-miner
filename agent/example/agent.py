"""
Minimal reference agent. Sends a single prompt to the LLM and returns the diff.

This exists to show the submission structure, not to score well. It uses no
planning, no tool use, and no reflection — the floor, not the ceiling.
"""

from __future__ import annotations

import os

from agent.base import BaseAgent, Patch, Problem

# OpenRouter is the default whitelisted endpoint.
# Replace with the model listed in benchmark/harness/allowed_models.txt.
DEFAULT_MODEL = "anthropic/claude-3-5-haiku"

SYSTEM_PROMPT = """\
You are an expert software engineer. Given a GitHub issue and relevant source files,
produce a minimal, correct unified diff (git diff format) that resolves the issue.

Rules:
- Output ONLY the unified diff, starting with `diff --git`.
- Do not add explanations outside the diff.
- Make the smallest correct change — no refactors, no style fixes.
- Tests must pass after applying your patch.
"""


def build_user_prompt(problem: Problem) -> str:
    parts = [
        f"# Issue: {problem.issue_title}\n\n{problem.issue_body}\n",
        "# Repository file tree\n```\n" + "\n".join(problem.file_tree) + "\n```\n",
    ]
    for f in problem.context_files:
        parts.append(f"# {f.path}\n```{f.language}\n{f.content}\n```\n")
    parts.append("Produce the unified diff to fix the issue:")
    return "\n".join(parts)


class ExampleAgent(BaseAgent):
    """Single-shot LLM agent — minimal reference implementation."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def solve(self, problem: Problem) -> Patch:
        import httpx

        api_key = os.environ.get("OPENROUTER_KEY", "")
        user_prompt = build_user_prompt(problem)

        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": problem.output_token_budget,
            },
            timeout=problem.time_limit_seconds,
        )
        response.raise_for_status()
        diff = response.json()["choices"][0]["message"]["content"].strip()
        return Patch(diff=diff)
