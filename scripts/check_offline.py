#!/usr/bin/env python3
"""Audit whether the prepared app can be served without network dependencies."""
from __future__ import annotations
import argparse, json, re, sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

@dataclass
class Result:
    name: str
    status: str
    details: str
    repair: str = ""

def inspect(root: Path) -> list[Result]:
    out: list[Result] = []
    frontend = root / "frontend"
    lock = next((frontend / x for x in ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock") if (frontend / x).is_file()), None)
    out.append(Result("frontend_lockfile", "PASS" if lock else "FAIL", f"Found {lock.name}." if lock else "No lockfile is present; exact frontend dependency resolution is not reproducible.", "Generate and review package-lock.json, then run npm ci before preparing offline mode." if not lock else ""))
    index = frontend / "dist" / "index.html"
    if not index.is_file():
        out.append(Result("frontend_build", "FAIL", "frontend/dist/index.html is missing.", "Run npm ci and npm run build after a lockfile is committed."))
        html = ""
    else:
        html = index.read_text(encoding="utf-8", errors="replace")
        out.append(Result("frontend_build", "PASS", "Built frontend entry point exists."))
    remote_patterns = [
        re.compile(r"https?://(?:fonts\.googleapis\.com|fonts\.gstatic\.com|cdnjs\.cloudflare\.com|unpkg\.com|cdn\.)[^\s\"')>]*", re.I),
        re.compile(r"https?://[^\s\"')>]+\.(?:js|css|woff2?|ttf|otf|png|jpe?g|svg)(?:\?[^\s\"')>]*)?", re.I),
        re.compile(r"@import\s+(?:url\()?['\"]?https?://[^\s\"')]+", re.I),
    ]
    styles = sorted((frontend / "dist" / "assets").glob("*.css")) if (frontend / "dist" / "assets").is_dir() else []
    audited_content = [html] + [path.read_text(encoding="utf-8", errors="replace") for path in styles]
    found_remote = sorted({m.group(0) for content in audited_content for pattern in remote_patterns for m in pattern.finditer(content)})
    out.append(Result("external_assets", "FAIL" if found_remote else ("PASS" if html else "WARN"), f"Detected external asset references in built HTML/CSS: {', '.join(found_remote[:8])}." if found_remote else (f"No common external JS/CSS/font/CDN references detected in built HTML and {len(styles)} CSS assets." if html else "Cannot audit external assets until frontend is built."), "Bundle fonts/scripts/styles locally and rebuild; do not rely on CDN or remote map tiles." if found_remote else ""))
    python_req = root / "backend" / "requirements.txt"
    out.append(Result("python_requirements", "PASS" if python_req.is_file() else "FAIL", "Backend requirements file exists." if python_req.is_file() else "backend/requirements.txt is missing.", "Restore the backend requirements file." if not python_req.is_file() else ""))
    wheelhouse = root / "wheelhouse"
    wheel_files = list(wheelhouse.glob("*")) if wheelhouse.is_dir() else []
    out.append(Result("python_wheelhouse", "PASS" if wheel_files else "WARN", f"Wheelhouse contains {len(wheel_files)} files." if wheel_files else "No prepared offline Python wheelhouse was found.", "Run scripts/prepare_offline.py --prepare-python after network-connected dependency review." if not wheel_files else "",))
    venv_deps = frontend / "node_modules"
    out.append(Result("frontend_node_modules", "PASS" if venv_deps.is_dir() else "WARN", "Frontend node_modules directory exists." if venv_deps.is_dir() else "Frontend dependencies are not installed in this workspace.", "Use npm ci while online, then test a clean offline start." if not venv_deps.is_dir() else ""))
    model_path = root / "vision" / "models"
    if model_path.is_dir() and any(p.is_file() for p in model_path.rglob("*")):
        model_info = "Local vision files are present; confirm their license/hash in docs/camera-vision/MODEL_LICENSES.md."
        model_status = "WARN"
    else:
        model_info = "No local vision model file found; offline camera inference is unavailable. Simulated mode must be labelled, and camera status must remain UNKNOWN when evidence is unavailable."
        model_status = "WARN"
    out.append(Result("vision_weights", model_status, model_info, "Only add reviewed/licensed model weights intentionally; never download model weights automatically at startup."))
    return out

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--json-out", type=Path)
    args = p.parse_args()
    root = args.root.resolve(); results = inspect(root)
    fails = sum(x.status == "FAIL" for x in results); warns = sum(x.status == "WARN" for x in results)
    status = "FAIL" if fails else ("WARN" if warns else "PASS")
    report = {"report_type":"OFFLINE_READINESS_AUDIT", "generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"), "root":str(root), "status":status, "counts":{"PASS":sum(x.status=="PASS" for x in results),"WARN":warns,"FAIL":fails}, "checks":[asdict(x) for x in results], "offline_ready":status=="PASS"}
    print(f"Offline readiness: {status} | PASS {report['counts']['PASS']} WARN {warns} FAIL {fails}")
    for r in results:
        print(f"[{r.status}] {r.name}: {r.details}")
        if r.repair and r.status != "PASS": print(f"       Fix: {r.repair}")
    if args.json_out:
        target = args.json_out if args.json_out.is_absolute() else root / args.json_out
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); print(f"JSON: {target}")
    return 1 if fails else 0
if __name__ == "__main__": raise SystemExit(main())
