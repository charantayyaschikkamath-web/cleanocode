# Release Checklist

Check an item only when a teammate has verified it on the release candidate. This list starts unchecked intentionally.

## Runtime and integration
- [ ] Clean install completes from documented steps.
- [ ] `GET /api/v1/health` and `GET /api/v1/preflight` reflect the actual database state.
- [ ] Account 3 action/scenario routers are registered in canonical `backend/app/main.py`.
- [ ] Account 4 vision router/service is integrated; model/device failure remains non-fatal and unknown.
- [ ] Account 7 copilot, reports and what-if routers are registered and the facts provider reads persisted records.
- [ ] Frontend navigation routes to real feature components and uses the integrated typed API client.
- [ ] Frontend lockfile is committed; `npm ci`, typecheck and production build pass.

## Data integrity and trust
- [ ] Unknown/stale camera/sensor evidence cannot create a confident empty-room claim.
- [ ] Action history is append-only and repeated approval is idempotent.
- [ ] `ACKED` does not count as success.
- [ ] Failed, ignored, rejected or timed-out commands leave savings unchanged.
- [ ] Verified simulated ledger entries are distinct from measured real values.
- [ ] Missing tariff/CO₂ factor/baseline remains unavailable.
- [ ] Frames and secrets are absent from DB rows, logs, reports and LLM requests.

## Quality
- [ ] `python -m compileall -q backend scripts tests` passes.
- [ ] `python -m pytest -q backend/tests tests` passes.
- [ ] `python scripts/evaluate_scenarios.py --output-dir artifacts/quality` passes all synthetic scenarios.
- [ ] `python scripts/preflight.py --json-out artifacts/quality/preflight.json` has no release-blocking failures.
- [ ] `python scripts/check_offline.py --json-out artifacts/quality/offline-readiness.json` passes after preparation.
- [ ] Actual frontend browser smoke/E2E tests are completed on the release candidate.
- [ ] Persistence across a full backend restart was verified with a throwaway database.
- [ ] Offline walkthrough succeeded with Wi-Fi disabled on the target machine.

## Demo and evidence
- [ ] Official rubric, limits and required deliverables are verified from official source.
- [ ] Three-minute path rehearsed at least twice.
- [ ] Success and failure paths are both demonstrated.
- [ ] Preflight, synthetic evaluation JSON/Markdown and logs are saved from the actual run.
- [ ] Screenshots are from the actual release candidate (not a mockup called live output).
- [ ] Every claim in the deck and spoken pitch traces to a source, formula, test output or explicitly marked estimate.
- [ ] Fallback demo is rehearsed and states the true state if live execution fails.
