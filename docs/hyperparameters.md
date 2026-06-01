# Gittensor Hyperparameter Configuration

This document maps every Gittensor repository hyperparameter to our configuration choice and explains the reasoning.

## Our configuration

```json
{
  "emission_share": 0.02,
  "issue_discovery_share": 0.3,
  "maintainer_cut": 0.15,
  "trusted_label_pipeline": true,
  "default_label_multiplier": 0.0,
  "label_multipliers": {
    "benchmark-problem": 2.5,
    "harness": 2.0,
    "agent-improvement": 2.0,
    "docs": 0.5,
    "bug": 1.5,
    "refactor": 0.75
  },
  "eligibility": {
    "min_valid_merged_prs": 2,
    "min_credibility": 0.75,
    "excessive_pr_penalty_base_threshold": 3,
    "open_pr_threshold_token_score": 250.0,
    "max_open_pr_threshold": 15
  },
  "scoring": {
    "pr_lookback_days": 45,
    "review_penalty_rate": 0.20,
    "standard_issue_multiplier": 1.5,
    "maintainer_issue_multiplier": 2.5,
    "src_tok_saturation_scale": 80.0,
    "time_decay": {
      "grace_period_hours": 24,
      "sigmoid_midpoint_days": 14,
      "sigmoid_steepness": 0.35,
      "min_multiplier": 0.08
    }
  }
}
```

## Rationale per field

### `emission_share: 0.02`
Starting point. We request 2% of SN74 emissions. As the benchmark proves its value (champion agent quality improves, problem set grows), we'll request an increase.

### `issue_discovery_share: 0.3`
30% of our slice rewards issue discovery. We want miners filing well-scoped, actionable benchmark problems — not just coding. This keeps the problem set alive and growing.

### `maintainer_cut: 0.15`
15% of our repo's slice goes to the maintainer. This pays for the work of reviewing submissions, running private evals, and keeping the benchmark honest. It's not a large share — contributors should earn more than the maintainer.

### `trusted_label_pipeline: true` + `default_label_multiplier: 0.0`
Every PR *must* have a maintainer-assigned label before it earns any score. This gives us editorial control — we can direct attention precisely. Unlabeled PRs earn nothing, preventing spray-and-pray contributions.

### `label_multipliers`
Calibrated to funnel effort toward benchmark work:
- `benchmark-problem` (2.5×): highest reward for contributing new curated problems.
- `harness` / `agent-improvement` (2.0×): improving the scoring pipeline or reference agents.
- `bug` (1.5×): real bugs get a decent multiplier.
- `docs` (0.5×): docs are fine but we don't want them dominating contributions.
- `refactor` (0.75×): mild discount — we want new features and fixes, not churn.

### `min_valid_merged_prs: 2`
Lower than the default 3. This repo requires a ramp-up period but we want to be welcoming to new contributors who've demonstrated basic quality.

### `min_credibility: 0.75`
Slightly below the default 0.80. We expect some PRs to be iterated (changed-requested) before merging, so a slightly softer credibility floor is appropriate.

### `src_tok_saturation_scale: 80.0`
Higher than the default 58. Our benchmark improvements tend to be substantial changes (new problem sets, harness rewrites, new agent strategies). We don't want small PRs to saturate the quality cap — we reward thoroughness here.

### `pr_lookback_days: 45`
Between the default 30 and the max 90. Benchmark work is slower-moving than product code; miners need time to build and test agents. 45 days gives a meaningful window without over-weighting ancient contributions.

### `maintainer_issue_multiplier: 2.5`
Well-scoped maintainer issues are the highest-value contributions — they define what the benchmark benchmarks. 2.5× incentivizes miners to solve the issues we file instead of making up their own.

### `review_penalty_rate: 0.20`
Slightly higher than the default 0.15. We want to strongly incentivize submitting polished PRs — each change-request cycle costs the miner 20% of their score.

### `time_decay.sigmoid_midpoint_days: 14`
Two-week half-life. Contributions should be recent but benchmark infrastructure doesn't need to turn over as fast as a product codebase.

### `time_decay.grace_period_hours: 24`
24h grace (vs. 12h default). Some benchmark problems take a full day to verify, and maintainers shouldn't lose score for the wait.

## What to change and when

| Signal | Action |
|--------|--------|
| Too many docs/refactor PRs | Lower `docs` and `refactor` label multipliers |
| Not enough new problems | Raise `benchmark-problem` multiplier, or run an issue campaign |
| Spam PRs | Lower `min_credibility`, raise `review_penalty_rate` |
| Miners are over-concentrated on easy issues | Raise `standard_issue_multiplier` so hard issues pay more relatively |
| Champion hasn't improved in a month | Lower `src_tok_saturation_scale` to make smaller improvements score better |
