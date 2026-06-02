"""
Reference agent: ranked-context observe → plan → act → verify loop.

Demonstrates the scaffolding pattern — same frozen model, better wrapper.
Miners compete to outperform this baseline.

Scoring model: correctness gates quality. Tests must pass first; then the
score is driven by the number of meaningful source-code tokens in the diff
(Gittensor's src_token_score formula). This agent is tuned to produce
complete, well-structured implementations — not minimal one-liners — because
a thorough fix that passes tests scores significantly higher than a bare stub.

Improvements over a naive single-shot approach:
- Context files ranked by keyword relevance to the issue — most relevant first,
  over-long context truncated rather than blindly dumped into the prompt
- Large files windowed to relevant sections only (±40 lines around keyword hits)
  so more files fit in the context budget without blowing the token limit
- Explicit file-and-line hypothesis required plus secondary-file completeness
  check so the implementation is thorough, not minimal
- Score-aware prompting: system prompt and act prompt explain that complete
  implementations score higher than stubs
- Structural diff validation beyond the basic `@@` presence check — catches
  malformed hunk headers before committing to the result
- Wider repair window (3 attempts, up from 2) with targeted feedback per failure mode
- Verify turn also checks implementation completeness — may expand a bare fix
- Structured reasoning log for transparency
"""

from __future__ import annotations

import os
import re
import textwrap
import time

import httpx

from agent.base import BaseAgent, FileContext, Patch, Problem

DEFAULT_MODEL = os.environ.get("BENCHMARK_MODEL", "deepseek/deepseek-chat")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REFERER = "https://github.com/PunchTheDev/gittensor-base-miner"

MAX_REPAIR_ATTEMPTS = 3
# Worst-case call count: plan + act + verify + repair × MAX_REPAIR_ATTEMPTS
MAX_CALLS = 3 + MAX_REPAIR_ATTEMPTS

# Context window guards: never send more than this many files or chars of context.
MAX_CONTEXT_FILES = 20
MAX_CONTEXT_CHARS = 40_000


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert software engineer. You receive a GitHub issue and the \
relevant source files, and your job is to produce a correct, complete fix \
as a valid unified diff.

Scoring note: your patch is scored on (1) test correctness — it must pass — \
and (2) source-token quality — the number of meaningful code tokens you add \
to non-test files. A complete, well-structured implementation that covers all \
edge cases and adds clear helper logic scores higher than a one-liner that \
technically passes but leaves the fix fragile or incomplete.
"""

OBSERVE_PROMPT = """\
## Issue: {title}

{body}

## Repository: {repo}

## Scoring test command
```
{test_cmd}
```
The harness runs this command to determine correctness. Your patch must make it pass.

## File tree
```
{tree}
```
{test_section}
## Source files (ranked by relevance)
{impl_files}

---

Analyse the issue carefully. Answer in order:

1. **Root cause** — one or two sentences.
2. **Hypothesis** — which specific file(s) and line range(s) need to change?
3. **Implementation plan** — describe what you will add/change precisely, including \
   any helper functions, error handling, or edge cases needed for a complete fix.
4. **Completeness check** — what else might need to change to ensure nothing \
   related is broken? List any secondary files.
5. **Test check** — given the test above, will `{test_cmd_short}` pass? Walk through the assertion.

Be precise and thorough — a complete implementation scores higher than a minimal stub.
"""

TEST_SECTION_TEMPLATE = """\
## Test files (must pass — read these first to understand expected behaviour)
{test_files}

"""

ACT_PROMPT = """\
Based on your analysis above, produce the unified diff.

Requirements:
- Start with `diff --git a/<path> b/<path>`
- Include `--- a/<path>` and `+++ b/<path>` headers
- Each hunk starts with `@@ -<start>,<count> +<start>,<count> @@`
- Implement the fix completely — include helper functions, proper error \
  handling, and any secondary changes identified in your plan
- Do NOT change unrelated logic, but do implement the full fix as described
- Higher-quality, complete implementations score better than minimal stubs
- Output ONLY the diff — no markdown fences, no prose
"""

VERIFY_PROMPT = """\
Issue: {title}

{body}

Test command that must pass: `{test_cmd}`

You produced this diff:

```diff
{diff}
```

Check it against these criteria:
1. Does the diff address the root cause described in the issue above?
2. Is every `@@` hunk header syntactically correct (line numbers make sense)?
3. Are there missing changes or accidental deletions?
4. Will running `{test_cmd}` pass after applying this diff?
5. Is the implementation complete — does it handle edge cases, or is it a bare stub?

If the diff is correct and complete, respond with exactly: LGTM

If it needs fixing, respond with the corrected diff only (no prose, starts with `diff --git`).
If the implementation is a bare minimum that should be more thorough, expand it and respond with the improved diff.
"""

REPAIR_FORMAT_PROMPT = """\
The diff you produced is not a valid unified diff.

Problem: {problem}

Please output a valid unified diff starting with `diff --git` and containing \
at least one `@@` hunk. Nothing else.
"""


# ---------------------------------------------------------------------------
# Context ranking
# ---------------------------------------------------------------------------


def _is_test_file(f: FileContext) -> bool:
    """Return True if this file is a test/spec file (not source to modify)."""
    p = f.path.lower()
    name = p.rsplit("/", 1)[-1]
    return (
        "/test/" in p or "/tests/" in p or "/spec/" in p or "/specs/" in p
        or name.startswith("test_") or name.endswith("_test.py")
        or ".test." in name or ".spec." in name
        or name.startswith("spec_") or name.endswith("_spec.rb")
    )


def _rank_files(files: list[FileContext], issue_title: str, issue_body: str) -> list[FileContext]:
    """Return files sorted by keyword relevance to the issue, most relevant first.

    Test files are excluded here — they're shown in a separate section.
    """
    issue_text = (issue_title + " " + issue_body).lower()

    # Explicit file paths mentioned in the issue — strong relevance signal
    mentioned_paths = set(re.findall(r"[\w/.-]+\.(?:py|ts|js|rs|go|java|kt|rb|cpp|c|h)", issue_text))

    # Identifier tokens from the issue (snake_case, camelCase, UPPER_CASE)
    raw_tokens = re.findall(r"\b([a-z_][a-z0-9_]{3,}|[A-Z][A-Za-z0-9]{3,})\b", issue_title + " " + issue_body)
    keywords = {t.lower() for t in raw_tokens}

    def score(f: FileContext) -> float:
        path_lower = f.path.lower()
        # High bonus if the file is explicitly mentioned
        path_score = 20.0 * sum(1 for mp in mentioned_paths if mp in path_lower)
        # Keyword density in file content (identifiers > 4 chars to reduce noise)
        content_lower = f.content.lower()
        keyword_hits = sum(1 for kw in keywords if len(kw) > 4 and kw in content_lower)
        return path_score + keyword_hits

    return sorted(files, key=score, reverse=True)


def _truncate_context(files: list[FileContext]) -> list[FileContext]:
    """Limit files sent to the LLM: at most MAX_CONTEXT_FILES files,
    or until cumulative character count hits MAX_CONTEXT_CHARS."""
    selected: list[FileContext] = []
    total_chars = 0
    for f in files:
        if len(selected) >= MAX_CONTEXT_FILES:
            break
        file_chars = len(f.path) + len(f.content)
        if total_chars + file_chars > MAX_CONTEXT_CHARS and selected:
            break
        selected.append(f)
        total_chars += file_chars
    return selected


def _window_file(content: str, keywords: set[str], context_lines: int = 40) -> str:
    """Return only the sections of a file that contain issue-relevant keywords.

    For files over 300 lines, finds all lines containing keyword hits and
    emits a ±context_lines window around each hit cluster. Unshown regions
    are replaced with an omission marker. Full content is returned for small files.
    """
    lines = content.splitlines(keepends=True)
    if len(lines) <= 300:
        return content

    # Mark which lines contain a keyword hit
    hit = [False] * len(lines)
    for i, line in enumerate(lines):
        l = line.lower()
        if any(kw in l for kw in keywords if len(kw) > 3):
            hit[i] = True

    if not any(hit):
        # No hits — return first N lines as a peek
        peek = min(80, len(lines))
        suffix = f"\n... [{len(lines) - peek} more lines omitted — no keyword hits]"
        return "".join(lines[:peek]) + suffix

    # Expand each hit into a window and merge overlapping windows
    windows: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if hit[i]:
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            if windows and start <= windows[-1][1]:
                windows[-1] = (windows[-1][0], end)
            else:
                windows.append((start, end))
        i += 1

    parts = []
    prev_end = 0
    for start, end in windows:
        if start > prev_end:
            omitted = start - prev_end
            parts.append(f"... [{omitted} lines omitted]\n")
        parts.append("".join(lines[start:end]))
        prev_end = end
    if prev_end < len(lines):
        parts.append(f"... [{len(lines) - prev_end} lines omitted]\n")

    return "".join(parts)


def _format_files(files: list[FileContext], keywords: set[str] | None = None) -> str:
    parts = []
    for f in files:
        lang = f.language or ""
        content = _window_file(f.content, keywords or set()) if keywords else f.content
        parts.append(f"### {f.path}\n```{lang}\n{content}\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Diff validation
# ---------------------------------------------------------------------------


def _looks_valid(diff: str) -> bool:
    """Must start with `diff --git` and contain at least one hunk."""
    return diff.startswith("diff --git") and "@@" in diff


def _diagnose_diff(diff: str) -> str:
    """Return a short description of the first structural problem found."""
    if not diff.strip():
        return "empty output — no diff produced"
    if not diff.startswith("diff --git"):
        return "does not start with `diff --git a/... b/...`"
    if "@@" not in diff:
        return "missing hunk header — no `@@ -N,N +N,N @@` line found"
    # Check that every `@@` line has the expected format
    for line in diff.splitlines():
        if line.startswith("@@"):
            if not re.match(r"@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", line):
                return f"malformed hunk header: {line!r}"
    return ""


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------


def _call(
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int,
    timeout: float,
    temperature: float = 0.2,
) -> str:
    """Call the OpenRouter API. Retries once on 429 (rate limit)."""
    for attempt in range(2):
        resp = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": REFERER,
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=timeout,
        )
        if resp.status_code == 429 and attempt == 0:
            retry_after = int(resp.headers.get("retry-after", "5"))
            time.sleep(min(retry_after, 10))
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    resp.raise_for_status()
    return ""


def _extract_diff(text: str) -> str:
    """Pull the unified diff out of LLM output, stripping markdown fences."""
    text = text.strip()
    fence = re.search(r"```(?:diff)?\s*\n(diff --git.+?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    idx = text.find("diff --git")
    if idx != -1:
        return text[idx:].strip()
    return text


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ExampleAgent(BaseAgent):
    """
    Ranked-context observe → plan → act → verify agent.

    Turn 1: rank context files by relevance, then analyse the issue to produce
            an explicit file-and-line hypothesis.
    Turn 2: produce the unified diff targeting the hypothesis.
    Turn 3+: verify structural correctness; repair with targeted feedback if wrong
             (up to MAX_REPAIR_ATTEMPTS).
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def solve(self, problem: Problem) -> Patch:
        api_key = os.environ.get("OPENROUTER_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_KEY environment variable not set")

        if problem.allowed_models and self.model not in problem.allowed_models:
            raise RuntimeError(
                f"Model '{self.model}' is not in the allowed list: {problem.allowed_models}"
            )

        # Distribute wall-clock budget across all calls so we never exceed the limit
        # even in the worst case.
        timeout = float(problem.time_limit_seconds) / MAX_CALLS
        token_budget = problem.output_token_budget
        plan_tokens = token_budget // 3
        act_tokens = token_budget // 2
        verify_tokens = token_budget // 4

        log: list[str] = []

        # --- Split and rank context files ---
        test_files = [f for f in problem.context_files if _is_test_file(f)]
        impl_files = [f for f in problem.context_files if not _is_test_file(f)]
        ranked_impl = _rank_files(impl_files, problem.issue_title, problem.issue_body)
        selected_impl = _truncate_context(ranked_impl)
        dropped = len(impl_files) - len(selected_impl)
        if dropped > 0:
            log.append(f"[context] {len(selected_impl)}/{len(impl_files)} impl files selected (dropped {dropped} low-relevance)")
        if test_files:
            log.append(f"[context] {len(test_files)} test file(s) shown separately")

        # Build keyword set for windowing large files
        raw_tokens = re.findall(r"\b([a-z_][a-z0-9_]{3,}|[A-Z][A-Za-z0-9]{3,})\b", problem.issue_title + " " + problem.issue_body)
        keywords = {t.lower() for t in raw_tokens}

        # Build test section — always shown in full (usually small)
        test_section = (
            TEST_SECTION_TEMPLATE.format(test_files=_format_files(test_files))
            if test_files else ""
        )

        # --- Turn 1: Observe + Plan ---
        test_cmd_str = " ".join(problem.test_cmd) if problem.test_cmd else "pytest"
        test_cmd_short = problem.test_cmd[-1] if problem.test_cmd else "pytest"
        observe_user = OBSERVE_PROMPT.format(
            title=problem.issue_title,
            body=problem.issue_body,
            repo=problem.repo_name,
            test_cmd=test_cmd_str,
            test_cmd_short=test_cmd_short,
            tree="\n".join(problem.file_tree),
            test_section=test_section,
            impl_files=_format_files(selected_impl, keywords),
        )
        history: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": observe_user},
        ]
        plan = _call(history, self.model, api_key, plan_tokens, timeout)
        log.append(f"[plan]\n{plan}")
        history.append({"role": "assistant", "content": plan})

        # --- Turn 2: Act ---
        # temperature=0 for diff generation: format precision matters more than creativity
        history.append({"role": "user", "content": ACT_PROMPT})
        raw_diff = _call(history, self.model, api_key, act_tokens, timeout, temperature=0)
        diff = _extract_diff(raw_diff)
        log.append(f"[diff v0]\n{diff}")
        history.append({"role": "assistant", "content": raw_diff})

        # --- Turn 3+: Verify + Repair ---
        for attempt in range(MAX_REPAIR_ATTEMPTS):
            problem_desc = _diagnose_diff(diff)

            if problem_desc:
                # Structural problem — give targeted feedback before asking for repair
                repair_msg = REPAIR_FORMAT_PROMPT.format(problem=problem_desc)
                history.append({"role": "user", "content": repair_msg})
                raw_diff = _call(history, self.model, api_key, act_tokens, timeout, temperature=0)
                diff = _extract_diff(raw_diff)
                log.append(f"[repair {attempt} (format)]\n{diff}")
                history.append({"role": "assistant", "content": raw_diff})
                continue

            # Diff looks structurally valid — ask for semantic verification
            body_snippet = (problem.issue_body or "")[:1500]
            verify_user = VERIFY_PROMPT.format(
                diff=diff,
                title=problem.issue_title,
                body=body_snippet,
                test_cmd=test_cmd_str,
            )
            history.append({"role": "user", "content": verify_user})
            verdict = _call(history, self.model, api_key, verify_tokens, timeout)
            log.append(f"[verify {attempt}]\n{verdict}")

            if verdict.strip().upper().startswith("LGTM"):
                break

            repaired = _extract_diff(verdict)
            if _looks_valid(repaired):
                diff = repaired
                log.append(f"[diff v{attempt + 1}]\n{diff}")
                history.append({"role": "assistant", "content": verdict})
            else:
                # Prose critique without a new diff — accept current result
                break

        reasoning = f"model={self.model}\n\n" + "\n\n".join(log)
        return Patch(diff=diff, reasoning=reasoning)
