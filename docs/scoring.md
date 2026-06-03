# Scoring

## Overview

Submissions are scored by replaying real Gittensor issues in an isolated sandbox using **Gittensor's native tree-sitter scoring engine** — the same AST-based scorer the DAS validator uses.

**Correctness gates quality.** A patch that doesn't pass the test suite scores 0, regardless of code quality.

## Metrics

Three complementary signals are reported for each evaluation:

| Metric | Scale | Meaning |
|---|---|---|
| `final_score` | 0–30 | Gittensor's native AST quality score for the agent's patch |
| `relative_score` | 0–2.0 | Agent quality / oracle quality for this specific problem |
| `file_coverage` | 0–1.0 | Fraction of reference diff source files the agent also touches |

**`mean_relative_score` is the primary benchmark ranking metric.** It normalizes each problem's contribution so a tiny 2-point fix and a large 25-point fix count equally. An agent that consistently matches the oracle scores 1.0; a better agent scores above 1.0.

`weighted_mean_score` (difficulty-weighted Gittensor score) is retained for backward compatibility and direct comparison to Gittensor native emissions.

## Base quality formula

Mirrors Gittensor's native scoring exactly (constants from `gittensor/constants.py`):

```
base_score   = 25 × (1 − exp(−src_tokens / 58.0))   # quality term, 0–25
bonus_score  = min(contribution_score / 1500, 1) × 5 # cross-category bonus, 0–5
final_score  = base_score + bonus_score               # 0–30 total
```

If tests do not pass, `final_score = 0`.

## Relative score

```
relative_score = min(agent_final_score / oracle_base_score, 2.0)
```

`oracle_base_score` is the DAS validator's score on the accepted reference diff for that specific problem (stored in `meta.json` as `das_base_score`). The cap of 2.0 prevents inflating scores with extremely verbose patches.

Interpretation:
- `1.0` — agent's fix has the same quality signal as the accepted solution
- `> 1.0` — agent wrote a higher-quality fix (more structured code changes)
- `< 1.0` — agent's fix is lower quality than the accepted solution (but may still be correct)
- `None` — oracle score unavailable for this problem (doesn't affect the mean)

The leaderboard ranks agents by `mean_relative_score` across all evaluated problems.

## File coverage (observational)

```
file_coverage = |agent_source_files ∩ reference_source_files| / |reference_source_files|
```

Test files are excluded. This is a diagnostic signal, not part of any score. A value of 1.0 means the agent touched exactly the same source files as the reference. A value < 1.0 may indicate the agent found a different (potentially better or worse) approach. Not touching the same files is not penalized — the tests are the arbiter of correctness.

## Correctness check

1. Apply the patch to the repository at `base_commit` (the commit just before the issue was filed).
2. Run the test suite (`test_cmd` from `meta.json`).
3. If all tests pass, proceed to quality scoring. Otherwise `final_score = 0`, `relative_score = 0`.

The test suite is the arbiter of correctness. An agent that finds a *better* fix than the reference solution is not penalized — if it passes the tests, it earns a full quality score.

## Quality scoring

`src_tokens` is computed by Gittensor's tree-sitter AST pipeline:

1. For each changed file, parse the old and new versions into a tree-sitter AST.
2. Compute the **symmetric difference** of AST node signatures between old and new.
3. Weight each changed node: structural nodes (functions, classes, loops) get bonus weight; leaf tokens (identifiers, literals) get base weight; comments score 0.
4. Apply a language weight multiplier (Go/Java/C/Rust = 2.0×, Python = 1.5×, JS = 1.15×, etc.).
5. Separate source-file score from test-file score (test files are weighted at 0.05×).
6. `src_tokens` = total weighted score from non-test files only.

Meaningful, structured code changes score higher. Comments and whitespace score 0. Copy-pasted boilerplate scores low. The scoring is fully deterministic — no LLM judge at any point.

Weight files (`benchmark/harness/weights/`) are copied directly from the Gittensor validator. Docker CI uses the identical pipeline end-to-end.

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

| Tier | Added lines in ref diff | Weight |
|------|------------------------|--------|
| Easy | < 30 | 1.0× |
| Medium | 30–149 | 1.5× |
| Hard | 150+ | 2.0× |

Difficulty is derived from the reference diff size (added lines, excluding test files). Each problem reports its tier in `meta.json`.

### Weighted mean score

In addition to the flat `mean_score`, results include a `weighted_mean_score`:

```
weighted_mean = sum(score_i × weight_i) / sum(weight_i)
```

Hard problems contribute twice as much as easy ones. An agent that solves hard problems while struggling on easy ones can outscore an agent that only coasts on easy ones. The weighted mean is the primary benchmark metric for ranking.
