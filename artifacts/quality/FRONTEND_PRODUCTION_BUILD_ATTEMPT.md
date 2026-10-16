# Frontend Production Build Attempt

**Attempted:** 16 October 2026  
**Environment:** Node.js 22.16.0, npm 10.9.2, Linux  
**Result:** **BLOCKED — dependencies could not be installed in this environment**

## Commands and observed results

1. `npm install --no-audit --no-fund --fetch-retries=0 --fetch-timeout=20000` in `frontend/` — failed with npm `EAI_AGAIN` while resolving `registry.npmjs.org`. No dependencies were installed and no lockfile was generated.
2. `tsc -b --pretty false` — attempted using the globally available TypeScript compiler. It exited non-zero because the project-local `react`, `react-dom`, `lucide-react`, React type declarations and `react/jsx-runtime` packages are absent; JSX/implicit-any diagnostics cascade from those missing packages. This does not determine whether a clean type-check passes after dependencies are installed.
3. `npm run typecheck` — exited 1 on missing `react`, `lucide-react`, and `react/jsx-runtime` packages.
4. `npm run build` — exited 1 at the `tsc -b` stage for the same missing dependencies. The chained `vite build` stage was not reached, and no production bundle was created.

These errors do **not** establish that the application has source-level type errors; the required dependencies were unavailable. They also do not count as a successful build. No fake `dist/` output or fabricated `package-lock.json` was created.

## Additional source-only validation

- 33 TypeScript/TSX files parsed through the globally available TypeScript transpiler with **0 syntax diagnostics**.
- 62 relative import references checked; **0 missing local targets**.
- This is a syntax/path scan only. It does not replace dependency-backed TypeScript type checking, Vite bundling, or browser testing. See `RELEASE_VERIFICATION.md` for the fresh backend test, scenario, persistence/restart and current preflight results.

## Next steps on a network-connected machine

From the project root:

```powershell
cd frontend
npm install
npm run typecheck
npm run build
```

Review and commit the generated `frontend/package-lock.json`. If `npm run typecheck` or `npm run build` identifies genuine source errors after dependencies are installed, fix those errors and rerun the checks. Confirm `frontend/dist/index.html` exists, then run the integrated preflight and test the browser UI—including uploaded-video sampling—against the backend.

## Usable fallback while this build is blocked

The backend now serves a separately labelled, dependency-free local rehearsal UI at `/demo`. The launch scripts choose that fallback when Vite dependencies are missing. Its page route is covered by pytest, and its inline JavaScript passes `node --check`; a real-browser walkthrough is still not claimed. This fallback does not fabricate `frontend/dist` output and does not change the React/Vite build status above.
