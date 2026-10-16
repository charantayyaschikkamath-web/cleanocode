# TEST-SCENARIO RESULTS

- **Status:** PASS
- **Execution mode:** ISOLATED_IN_PROCESS_TEST
- **Generated:** 2026-10-16T06:38:20.619301Z
- **Duration:** 0.237 seconds
- **Passed:** 10 / 10
- **Scope:** These synthetic scenarios validate the API workflow and invariants only. They do not measure real-campus detector accuracy, hardware control, production reliability, or real savings.

| Scenario | Expected | Actual | Provenance | Action result | Ledger before → after | Result |
|---|---|---|---|---|---:|---|
| EMPTY_ROOM_HIGH_POWER | likely_energy_waste | likely_energy_waste | SIMULATED | — | 0 → 0 | PASS |
| NIGHT_WATER_FLOW | likely_water_anomaly | likely_water_anomaly | SIMULATED | — | 0 → 0 | PASS |
| BIN_OVERFLOW | likely_bin_overflow | likely_bin_overflow | SIMULATED | — | 0 → 0 | PASS |
| INEFFICIENT_ROOM_USE | likely_inefficient_room_use | likely_inefficient_room_use | SIMULATED | — | 0 → 0 | PASS |
| NORMAL_OPERATION | no event | no event | SIMULATED | — | 0 → 0 | PASS |
| SENSOR_MISSING | evidence_insufficient | evidence_insufficient | SIMULATED | — | 0 → 0 | PASS |
| SENSOR_STALE | sensor_unavailable | sensor_unavailable | SIMULATED | — | 0 → 0 | PASS |
| COMMAND_DROPPED | likely_energy_waste | likely_energy_waste | SIMULATED | ACK_TIMEOUT | 0 → 0 | PASS |
| ACKNOWLEDGED_IGNORED | likely_energy_waste | likely_energy_waste | SIMULATED | VERIFICATION_FAILED | 0 → 0 | PASS |
| VERIFIED_RESPONSE | likely_energy_waste | likely_energy_waste | SIMULATED | VERIFIED_SUCCESS; idempotent repeat held | 0 → 1 | PASS |

## Interpretation

These synthetic scenarios validate the API workflow and invariants only. They do not measure real-campus detector accuracy, hardware control, production reliability, or real savings.
