# Contributing

## Submitting an agent

1. **Fork** this repository.
2. Implement `BaseAgent` in a new directory under `agent/submissions/<your-handle>/`.
3. Run the benchmark locally to verify your agent scores: `python scripts/run_eval.py --agent agent/submissions/<your-handle>/agent.py`
4. Open a pull request targeting `main`. Use the PR template — it walks you through the commit-reveal flow.

## Commit-reveal flow

To prevent copying, we use a two-phase submission:

1. **Hash commit**: In your PR description, include `reveal-hash: <sha256>` where the hash is `sha256(agent_source_code + secret_salt)`. You set the salt; keep it private.
2. **Private eval**: Maintainers run your agent against the held-out problem set and publish your score.
3. **Reveal**: After scoring, you share the salt so anyone can verify the hash. If the revealed source matches the hash and the score is genuine, your submission is accepted.

The reveal step must happen within 7 days of the private eval.

## Constraints

- **Frozen model**: Your agent must use only the whitelisted models listed in `benchmark/harness/allowed_models.txt`. Model-shopping is not the game — scaffolding is.
- **Time limit**: 120 seconds per problem.
- **Token budget**: 50,000 output tokens per problem.
- **No external state**: Your agent cannot read from or write to external services during evaluation. Network is blocked in the sandbox.
- **No problem-set memorization**: The harness detects agents that hardcode known solutions. Don't.

## Code standards

- Keep your agent directory self-contained.
- A `requirements.txt` in your agent directory is fine for extra dependencies.
- No shell scripts that bypass the agent interface.

## Adding problems

If you want to propose a new benchmark problem (a real Gittensor issue with a merged PR), open an issue with the template `Problem Proposal`. Maintainers will review and add it if it meets the curation criteria in `docs/scoring.md`.
