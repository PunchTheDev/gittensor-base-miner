# Punch Log — Gittensor Base-Miner Flywheel

Milestone trail for the base-miner benchmark. Discord is the primary channel; this file is the audit trail.

---

## 2026-06-01 — Repo scaffold live

**Milestone: Initial repo structure created and pushed to GitHub.**

What was built:
- `agent/base.py`: `BaseAgent` interface (Problem → Patch)
- `agent/example/`: minimal single-shot reference agent
- `benchmark/harness/score.py`: local scoring approximation (correctness gate + quality heuristic)
- `benchmark/evaluate.py`: full evaluation runner
- `scripts/curate_problems.py`: tooling to pull benchmark problems from real Gittensor merged PRs
- `docs/scoring.md`: scoring mechanics
- `docs/hyperparameters.md`: full hyperparameter config rationale
- `docs/threat_model.md`: anti-gaming threat model (6 threats, 18 mitigations)
- `hyperparameters.json`: live Gittensor repo config (ready for registration submission)
- `.github/` templates: PR template with commit-reveal, issue templates

**Next steps:**
1. Curate the first batch of ~30 benchmark problems from real Gittensor merged PRs.
2. Run `scripts/curate_problems.py --repo entrius/gittensor` once GitHub API access is confirmed.
3. Test the harness end-to-end with the example agent on one problem.
4. Post Discord milestone once first agent scores across problems.

**Open decision (non-blocking, going with defaults):**
- Frozen model: defaulting to `anthropic/claude-3-5-haiku` via OpenRouter. If a different model or Chutes/whitelist is preferred, please confirm.
- Gittensor scoring engine: using an approximation for local dev. Need location of the validator's native scoring engine to wire it in for CI. Going with approximation until then.

---
