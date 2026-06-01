"""
Minimal reference agent. Single LLM call, returns a unified diff.

This is the floor — it exists to show the submission structure and give
miners a working baseline to beat. No planning, no tool use, no reflection.

Miners can improve over this baseline by adding:
- Multi-turn reasoning (observe → plan → act → verify)
- Tool use (read files, run tests, apply + check patch)
- Reflection / self-repair loops
- Smarter context selection
"""

from __future__ import annotations

import os
import re

import httpx

from agent.base import BaseAgent, Patch, Problem

# Default model — must be in the harness allowed_models list.
# Override via BENCHMARK_MODEL env var.
DEFAULT_MODEL = os.environ.get("BENCHMARK_MODEL", "anthropic/claude-3-5-haiku")

SYSTEM_PROMPT = """\
You are an expert software engineer. Given a GitHub issue and relevant source files,
produce a minimal, correct unified diff (git diff format) that resolves the issue.

Output format rules:
- Output ONLY the unified diff, starting with `diff --git`.
- No prose before or after the diff. No markdown code fences.
- Make the smallest correct change. No refactors, no style fixes.
- The patch must apply cleanly and all tests must pass.
"""


def build_user_prompt(problem: Problem) -> str:
    parts = [
        f"## Issue: {problem.issue_title}\n\n{problem.issue_body}\n",
        "## Repository file tree\n```\n" + "\n".join(problem.file_tree) + "\n```\n",
    ]
    for f in problem.context_files:
        lang = f.language or ""
        parts.append(f"## {f.path}\n```{lang}\n{f.content}\n```\n")
    parts.append("Produce the unified diff to fix this issue:")
    return "\n".join(parts)


def extract_diff(text: str) -> str:
    """Extract the unified diff from LLM output.

    Handles cases where the model wraps the diff in a markdown code block
    (```diff ... ``` or ``` ... ```) despite being told not to.
    """
    text = text.strip()

    # Try to find a fenced code block containing the diff
    fence_match = re.search(
        r"```(?:diff)?\s*\n(diff --git.+?)```",
        text,
        re.DOTALL,
    )
    if fence_match:
        return fence_match.group(1).strip()

    # Otherwise take content from the first `diff --git` line onward
    idx = text.find("diff --git")
    if idx != -1:
        return text[idx:].strip()

    return text


class ExampleAgent(BaseAgent):
    """Single-shot LLM agent — minimal reference implementation."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def solve(self, problem: Problem) -> Patch:
        api_key = os.environ.get("OPENROUTER_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_KEY environment variable not set")

        user_prompt = build_user_prompt(problem)

        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/PunchTheDev/gittensor-base-miner",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": problem.output_token_budget,
                "temperature": 0.2,
            },
            timeout=float(problem.time_limit_seconds),
        )
        response.raise_for_status()

        raw = response.json()["choices"][0]["message"]["content"]
        diff = extract_diff(raw)

        return Patch(diff=diff, reasoning=f"model={self.model}")
