# Backlog

Ordered roughly by priority. Punch generates and grooms this continuously.
Items move to STATE.md completed list when done. Registration is the last step — do not touch until the product is polished.

---

## In Progress
- [ ] Pool expansion: run `scripts/build_pool.py` against all 21 registered repos to grow pool from 30 → 100+ problems

---

## Problem Sourcing
- [ ] Run `build_pool.py` against all registered repos, grow pool to 100+ problems
- [ ] Mirror API integration: use `https://mirror.gittensor.io/api/v1/dashboard/issues?since=` to discover scored issues for pool curation (supplement GitHub API, less rate-limited)
- [ ] Add pool refresh cron / weekly schedule to CI so pool grows automatically as new PRs merge
- [ ] Time-segmentation guard: assert each problem's `merged_at` is after `model_cutoff_date` at build time

## CLI Surface
- [ ] `gittensor-miner` CLI entrypoint (via `pyproject.toml` script): unified `eval`, `build-pool`, `list-shard`, `hash`, `submit` commands
- [ ] `gitminer hash <diff_file>` — generate commit-reveal hash for a patch
- [ ] `gitminer submit <agent.py>` — validate, hash, and open a PR with pre-filled template
- [ ] Local/CI score parity guarantee: document and test that `--no-sandbox` and Docker give equivalent scores on the same problem

## Dashboard
- [ ] Static dashboard: leaderboard table, SOTA-over-time chart, per-problem breakdown
- [ ] Per-problem diff viewer: agent's patch vs accepted diff, tests passed/failed
- [ ] Submission status page: hash registered → eval running → scored
- [ ] One-click "reproduce this result" button (runs harness against champion agent)
- [ ] Deploy to GitHub Pages from `gh-pages` branch on every push to main

## API Backend
- [ ] FastAPI backend: `/leaderboard`, `/problems`, `/submissions/{handle}`, `/scores/{problem_id}`
- [ ] All surfaces (CLI, Dashboard, CI) read from this single API — no divergence
- [ ] Submission queue endpoint: POST hash → GET status
- [ ] Results storage: JSON files in `results/` directory, committed to repo (simple, auditable)

## Anti-Gaming
- [ ] Commit-reveal: hash submission gate before eval runs (document flow in CONTRIBUTING.md)
- [ ] Similarity check: compare submitted patch against all prior patches (diff-based cosine similarity)
- [ ] Rate limiting: max N submissions per miner per week
- [ ] Shard rotation secret: keep rotation seed out of public CI logs so active shard isn't predictable
- [ ] Model lock enforcement: CI validates that the agent's model call is in `allowed_models.txt`

## Harness & Scoring
- [ ] Multi-language test inference: improve `infer_test_cmd` in `build_pool.py` for JS/TS/Rust/Go repos
- [ ] Score normalization: calibrate 0–30 scale against actual Gittensor validator outputs
- [ ] Reference-diff baseline scores: run `score_patch` against all 30 reference diffs and update LEADERBOARD.md with real numbers
- [ ] Daytona integration: spike on ephemeral workspace per problem (vs GitHub Actions runner)

## Docs & Hygiene
- [ ] Update CONTRIBUTING.md with pool/shard explanation (miners know which problems to test against)
- [ ] Update README with build_pool.py usage and pool size
- [ ] Issue template: "New problem suggestion" — allow community to nominate PRs for curation
- [ ] CHANGELOG.md: start tracking changes per release

## Hyperparameters
- [ ] Map every hyperparameter in hyperparameters.json to pool/shard mechanics (e.g. issue_discovery_share for problem curation rewards)
- [ ] Submit hyperparameters.json to Gittensor team (after product is polished)

## Registration (LAST — operator handles)
- [ ] Add OPENROUTER_KEY as GitHub Actions secret
- [ ] Submit hyperparameters.json to Gittensor team
- [ ] Confirm frozen model preference with operator
