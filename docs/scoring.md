# Scoring

## Overview

Submissions are scored by replaying real Gittensor issues in an isolated sandbox. The scoring pipeline combines **Gittensor's native tree-sitter quality engine** (the same AST scorer the DAS validator uses) with our own benchmark-specific metrics that capture correctness depth and oracle-relative quality.

## Scoring philosophy

A good base miner does two things: it produces correct fixes, and it produces high-quality code. Raw Gittensor scoring only captures quality (via AST token analysis). Our benchmark adds:

1. **Partial correctness** — A fix that passes 9/10 tests is better than one that passes 0/10. `test_pass_rate` captures this on a continuous 0–1 scale rather than a binary gate.
2. **Oracle-relative quality** — A 2-line fix on a 2-line problem is worth as much as a 200-line fix on a 200-line problem. `relative_score` normalizes quality against what the accepted solution actually scored.
3. **Composite benchmark score** — Combines both signals into a single leaderboard metric that rewards agents for being correct *and* high-quality, not just one or the other.

## Metrics

| Metric | Scale | Primary? | Meaning |
|---|---|---|---|
| `benchmark_score` | 0–2.0 | **YES** | `test_pass_rate × relative_score` — composite correctness + quality |
| `relative_score` | 0–2.0 | secondary | Agent quality / oracle quality for this specific problem |
| `test_pass_rate` | 0–1.0 | secondary | Fraction of tests that pass (granular correctness) |
| `final_score` | 0–30 | compat | Gittensor native AST score (for on-chain emissions comparison) |
| `file_coverage` | 0–1.0 | diagnostic | Fraction of reference-diff source files touched (observational) |

**`mean_benchmark_score` is the primary leaderboard ranking metric.**

## Benchmark score

```
benchmark_score = test_pass_rate × min(relative_score, 2.0)
```

This is the headline number. A submission that:
- Passes all tests and matches oracle quality → `benchmark_score = 1.0`
- Passes all tests and beats oracle quality → `benchmark_score > 1.0` (up to 2.0)
- Passes 50% of tests at oracle quality → `benchmark_score = 0.5`
- Passes no tests → `benchmark_score = 0.0`

Partial credit for partial correctness means agents are incentivized to fix as many bugs as possible, not just the easiest ones.

## Test pass rate

```
test_pass_rate = tests_passed_count / tests_total_count
```

Parsed from the test runner output for each language:

| Runner | Signal |
|---|---|
| pytest | `N passed, M failed in Xs` |
| cargo test | `test result: ok. N passed; M failed` |
| go test | count of `--- PASS:` and `--- FAIL:` lines |
| jest / vitest | `Tests: N passed, M total` |
| rspec | `N examples, M failures` |
| gradle | `N tests completed, M failed` |

When parsing fails (unusual output format), `test_pass_rate` falls back to the binary exit-code result (1.0 for pass, 0.0 for fail).

## Base quality formula

Mirrors Gittensor's native scoring exactly (constants from `gittensor/constants.py`):

```
base_score   = 25 × (1 − exp(−src_tokens / 58.0))   # quality term, 0–25
bonus_score  = min(contribution_score / 1500, 1) × 5 # cross-category bonus, 0–5
final_score  = base_score + bonus_score               # 0–30 total
```

`final_score` is used to compute `relative_score` and is retained for direct comparison to Gittensor on-chain emissions scoring.

## Relative score

```
relative_score = min(agent_final_score / oracle_base_score, 2.0)
```

`oracle_base_score` is our tree-sitter scorer's score on the accepted reference diff for that specific problem (from `results/baselines.json`). The oracle scores exactly 1.0 against itself. The cap of 2.0 prevents verbose bloated patches from inflating scores unboundedly.

Interpretation:
- `1.0` — agent's fix has the same quality signal as the accepted solution
- `> 1.0` — agent wrote a higher-quality fix (more structured code changes)
- `< 1.0` — agent's fix has lower structural quality than the accepted solution
- `None` — oracle score unavailable for this problem (excluded from the mean)

The leaderboard ranks agents by `mean_benchmark_score` (which incorporates relative_score).

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
