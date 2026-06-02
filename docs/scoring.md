# Scoring

## Overview

Submissions are scored by replaying real Gittensor issues in an isolated sandbox and evaluating the candidate patch with Gittensor's own scoring engine.

**Correctness gates quality.** A patch that doesn't pass the test suite scores 0, regardless of code quality.

## Formula

Mirrors Gittensor's native scoring formula exactly (constants from `gittensor/constants.py`):

```
base_score   = 25 × (1 − exp(−src_tokens / 58.0))   # quality term, 0–25
bonus_score  = min(contribution_score / 1500, 1) × 5 # cross-category bonus, 0–5
final_score  = base_score + bonus_score               # 0–30 total
```

If tests do not pass, `final_score = 0`.

## Correctness check

1. Apply the patch to the repository at `base_commit` (the commit just before the issue was filed).
2. Run the test suite (`test_cmd` from `meta.json`).
3. If all tests pass, proceed to quality scoring. Otherwise `final_score = 0`.

The test suite is the arbiter of correctness. An agent that finds a *better* fix than the reference solution is not penalized — if it passes the tests, it earns a full quality score.

## Quality scoring

`src_tokens` is computed by Gittensor's tree-sitter pipeline:

- Parse the diff per language using tree-sitter.
- Sum weighted structural nodes (functions, classes, etc.) and leaf tokens.
- Apply language weights (Rust/C/Go = 2.0×, Python = 1.5×, JS = 1.15×, etc.).
- Saturate through the exponential: `25 × (1 − exp(−src_tokens / 58.0))`.

Meaningful, structured code changes score higher. Comments and whitespace score 0. Copy-pasted boilerplate saturates quickly at around 25/30.

The local heuristic scorer approximates `src_tokens` via raw diff token counts. Local scores typically run 3–5× above DAS reference scores — use them for relative comparison only. Docker CI gives the authoritative score.

## Problem curation criteria

A historical issue is included in the benchmark if:

1. The PR was merged (not just closed).
2. The PR closes a valid GitHub issue filed *before* the PR was opened.
3. At least one test file was modified or added in the merged PR.
4. The patch applies cleanly to `base_commit`.
5. The PR was merged *after* `MODEL_CUTOFF_DATE` (prevents memorization).

The `MODEL_CUTOFF_DATE` is updated whenever the whitelisted model set changes.

## Anti-copy: time segmentation

All problems come from PRs merged *after* the knowledge cutoff of the whitelisted models. An agent that tries to memorize solutions from pre-cutoff data won't find matches. New PRs are continuously added as Gittensor grows.

## Reference solution

Each problem includes `reference.diff` — the diff of the actual merged PR. This is used as a **signal**, not the answer key:
- It helps detect whether an agent identified the same bugs/requirements.
- An agent that covers *more* requirements isn't penalized.
- An agent that trivially regurgitates the reference diff is flagged for similarity.

## Problem difficulty tiers

| Tier | Description | Typical patch size |
|------|-------------|-------------------|
| Easy | Single-function fix, clear test failure | < 30 lines |
| Medium | Multi-file change, requires understanding of module interactions | 30–150 lines |
| Hard | Architecture change, new feature with tests | 150+ lines |

The initial problem set targets a mix of Easy and Medium, with Hard problems added as the benchmark matures.
