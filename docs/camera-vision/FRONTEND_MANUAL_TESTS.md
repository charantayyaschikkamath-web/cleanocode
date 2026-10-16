# Account 4 CameraPanel Manual Browser Acceptance Checklist

Run after placing the component inside the real React/Vite app and connecting `/api` to the backend. Test on the target laptop/browser and any USB camera expected at the demo.

- [ ] Initial load does not request camera permission and shows no live image.
- [ ] Clicking **Start camera** triggers browser permission; clicking **Stop camera** ends every media track.
- [ ] A permission denial/device unplug produces a recovery message and unknown occupancy, not zero occupants.
- [ ] Ended/muted browser media tracks stop frame sends; frozen camera frames are not repeatedly reposted as fresh evidence.
- [ ] Multiple available webcam/USB devices appear after permission; switching devices stops the current stream and requires a clear Start action.
- [ ] Audio permission is never requested.
- [ ] No model configured: panel shows inference unavailable, does not upload frame snapshots continuously, and simulation remains clearly labelled.
- [ ] Real model configured: JPEG frames are sent one at a time; inspect network logs to verify only `image/jpeg` requests and no frame retries/buffering.
- [ ] A detected person immediately displays the person-detected signal and makes the evidence ineligible for empty timer.
- [ ] A valid no-person signal remains phrased as “No person detected”, never “room empty”; eligibility requires manual coverage attestation and Account 3's sustained dwell rule.
- [ ] Uncheck coverage while live: the UI immediately marks current evidence ineligible; next backend frame also carries `coverage_confirmed=false`.
- [ ] Stop camera / block backend / unplug device: stale or failed frame transitions UI to unknown and disables timer eligibility.
- [ ] Dark/obstructed-looking frame produces unknown with reason; no confident absence is shown.
- [ ] Simulation is neutral/clearly tagged `SIMULATED`; even a simulated zero-person result never enables empty-timer eligibility.
- [ ] Keyboard tab order, visible focus, narrow viewport, reduced-motion preference, high-contrast text, and screen-reader labels are checked.
