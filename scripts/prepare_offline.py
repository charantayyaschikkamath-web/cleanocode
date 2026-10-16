#!/usr/bin/env python3
"""Prepare local dependency caches for an offline rehearsal; never fetch model weights."""
from __future__ import annotations
import argparse, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def run(command: list[str], cwd: Path) -> int:
    print("$ " + " ".join(command), flush=True)
    return subprocess.call(command, cwd=str(cwd))

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--prepare-python", action="store_true", help="Download wheels for the pinned backend requirement file into wheelhouse/ (requires network).")
    p.add_argument("--build-frontend", action="store_true", help="Run npm ci and npm run build (requires a committed lockfile and installed npm).")
    p.add_argument("--check-only", action="store_true", help="Only report prerequisites; do not run commands.")
    args = p.parse_args(); root = args.root.resolve(); failures = []
    py_req = root / "backend" / "requirements.txt"
    lock = root / "frontend" / "package-lock.json"
    if not py_req.is_file(): failures.append("backend/requirements.txt is missing")
    if args.prepare_python:
        if args.check_only: print("CHECK ONLY: would prepare Python wheelhouse")
        elif py_req.is_file():
            dest = root / "wheelhouse"; dest.mkdir(exist_ok=True)
            rc = run([sys.executable, "-m", "pip", "download", "--requirement", str(py_req), "--dest", str(dest)], root)
            if rc: failures.append(f"pip download exited {rc}")
    if args.build_frontend:
        if not lock.is_file(): failures.append("frontend/package-lock.json is missing; refusing a non-reproducible npm install")
        elif not shutil.which("npm"): failures.append("npm was not found on PATH")
        elif args.check_only: print("CHECK ONLY: would run npm ci and npm run build")
        else:
            for command in (["npm", "ci"], ["npm", "run", "build"]):
                if run(command, root / "frontend") != 0:
                    failures.append("Command failed: " + " ".join(command)); break
    if not (args.prepare_python or args.build_frontend):
        print("Nothing requested. Choose --prepare-python and/or --build-frontend; these commands need internet on first preparation.")
    if failures:
        print("PREPARATION NOT READY:")
        for f in failures: print("- " + f)
        return 1
    print("Preparation command sequence finished without a reported command error.")
    print("This is not proof of offline readiness: disable Wi-Fi and run scripts/check_offline.py, preflight, tests, and browser walkthrough separately.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
