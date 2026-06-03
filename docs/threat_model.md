# Anti-Gaming Threat Model

## Threat 1: Copying the current champion

**Attack**: Miner reads the champion agent's code in `agent/champion/` and submits it with minor cosmetic edits.

**Mitigations**:
- **Commit-reveal**: Miner must submit a hash before the private eval. The source is not visible until after scoring.
- **Marginal reward**: Rewards are proportional to margin over the current leader. A perfect copy earns ~0 margin.
- **Similarity check**: Submissions are diffed against all prior submissions. Near-duplicates (> 85% Jaccard similarity on normalized token sequences) are flagged for manual review.
- **First-to-commit credit**: In a tie, the earlier submission wins.

**Residual risk**: Low. A copy that truly adds nothing earns nothing.

---

## Threat 2: Overfitting to visible test problems

**Attack**: Miner hardcodes solutions to the visible benchmark problems.

**Mitigations**:
- **Unpredictable shard selection**: All 441 problems are public, but official evals score only the current 30-problem shard. The shard is selected using `SHARD_SECRET` (a GitHub Actions secret), so miners cannot predict which 30 problems will be evaluated without the secret. Pre-computing solutions for all 441 problems is expensive and still yields no guarantee about the shard.
- **Time segmentation**: Problems are only drawn from PRs merged *after* the model knowledge cutoff. The set grows continuously — yesterday's overfitting target is tomorrow's stale problem.
- **Randomized evaluation order**: Problems are evaluated in a deterministic but SHARD_SECRET-seeded order. Hardcoded per-problem solutions require knowing the shard.

**Residual risk**: Medium. A well-resourced miner could pre-compute all 441 solutions and just serve them. Mitigated by time segmentation (new problems constantly added) and the fact that a good general agent likely outperforms 441 hardcoded patches as the pool grows.

---

## Threat 3: Using a non-whitelisted frontier model

**Attack**: Miner uses GPT-5 or Claude 4 (frontier, unlisted) to solve problems, then wraps the result as if it came from a whitelisted model.

**Mitigations**:
- **Sandbox network control**: During evaluation, only whitelisted model API endpoints are reachable. All other outbound connections are blocked by the Daytona sandbox.
- **Model logging**: The harness logs every API call (model name, prompt hash, response hash) during evaluation. Discrepancies are detectable.

**Residual risk**: A miner who proxies a frontier model through a whitelisted endpoint could evade detection. This requires deliberate infrastructure effort — it's not a casual attack. Monitoring for unusual latency and response-length distributions helps.

---

## Threat 4: Sybil submissions

**Attack**: Miner creates multiple identities and submits essentially the same agent from each to accumulate leaderboard positions.

**Mitigations**:
- **Similarity check across all submissions** (not just vs. champion): near-duplicate submissions across different handles are flagged.
- **Gittensor credibility gate**: Each submitter must have ≥ 2 merged PRs and ≥ 75% credibility. Building fake credibility requires real merged code contributions, which is expensive.

**Residual risk**: Low. Building multiple credible Gittensor identities is expensive.

---

## Threat 5: LLM variance gaming

**Attack**: Miner submits many times, exploiting randomness in the model's output to get a lucky high score.

**Mitigations**:
- **Rate limiting**: Each submitter can only submit once per 48 hours. New submissions require closing the previous open PR.
- **Deterministic eval seeds**: The harness seeds all random number generators with `problem_id + submission_id`. Same agent always produces the same score.
- **Reward decay for repeated submissions**: If a new submission scores less than the miner's previous best, their effective score doesn't decrease (no punishment), but the submission earns 0 marginal reward.

**Residual risk**: Low given deterministic seeds.

---

## Threat 6: Issue-linked PR manipulation

**Attack**: Miner creates fake issues, then closes them with their own PRs to earn the issue multiplier.

**Mitigations**:
- Gittensor's native engine already rejects self-authored linked issues.
- Maintainer-authored issues earn the `maintainer_issue_multiplier` (2.5×) — much higher than the `standard_issue_multiplier` (1.5×). Well-scoped maintainer issues are more valuable, which directs miner effort toward solving the right problems.

**Residual risk**: None beyond what Gittensor natively blocks.

---

## Threat 7: Behavioral cloning (output forwarding)

**Attack**: Miner writes an agent that calls a prior champion's API, wraps its output, or is functionally identical despite looking structurally different. Source-level similarity checks cannot catch this if the wrapper code is sufficiently different.

**Mitigations**:
- **Output behavior fingerprinting**: Every evaluated submission generates a fingerprint — a per-problem SHA-256 of the normalized diff the agent produced. These fingerprints are stored in `results/behaviors/` and compared on every new submission.
- **Matching threshold**: If ≥ 70% of overlapping evaluated problems produce identical diff hashes, the submission is flagged. This threshold catches near-exact forwarding while tolerating coincidental matches on simple problems.
- **Minimum overlap requirement**: Comparisons require ≥ 5 shared problems to be meaningful. Agents evaluated in different weeks share fewer problems — the threshold still applies to the overlap window.

**Residual risk**: A miner who deliberately varies their outputs problem-by-problem while using the same underlying agent could stay below the threshold. Rate limiting limits how many calibration runs they can make. Marginal-reward design means a forwarded output earns ~0 above the champion's baseline anyway.

---

## Summary

| Threat | Severity | Mitigation strength |
|--------|----------|---------------------|
| Copying champion | High | Strong (commit-reveal + marginal reward) |
| Overfitting to known problems | Medium | Medium (secret shard + time-segmentation) |
| Frontier model smuggling | Medium | Medium (sandbox + logging) |
| Sybil submissions | Low | Strong (credibility gate + similarity check) |
| LLM variance gaming | Low | Strong (deterministic seeds + rate limiting) |
| Issue manipulation | Low | Strong (Gittensor native + multiplier design) |
| Behavioral cloning / output forwarding | Medium | Medium (behavior fingerprint + 70% match threshold) |
