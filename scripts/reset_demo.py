#!/usr/bin/env python3
"""Safely invoke the non-destructive simulated-demo reset endpoint."""
from __future__ import annotations
import argparse, json, sys, urllib.error, urllib.request

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--api-prefix", default="/api/v1")
    p.add_argument("--reason", default="Preparing repeatable demo")
    p.add_argument("--actor", default="demo_operator")
    p.add_argument("--confirm", action="store_true", help="Required: archive active SIMULATED events. Real-source records and audit/ledger history are preserved by backend logic.")
    args = p.parse_args()
    if not args.confirm:
        p.error("Reset mutates active simulated demo state; re-run with --confirm after checking the target URL.")
    prefix = "/" + args.api_prefix.strip("/")
    body = json.dumps({"confirm":True,"reason":args.reason,"actor":args.actor}).encode()
    req = urllib.request.Request(args.base_url.rstrip("/")+prefix+"/scenarios/reset-demo", data=body, headers={"Content-Type":"application/json","Accept":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            payload = json.loads(res.read().decode())
            print(json.dumps(payload, indent=2))
            if payload.get("status") != "COMPLETED" or payload.get("audit_history_preserved") is not True:
                print("Reset response did not confirm expected safe-reset contract.", file=sys.stderr); return 1
            return 0
    except urllib.error.HTTPError as exc:
        print(f"Reset failed with HTTP {exc.code}: {exc.read().decode(errors='replace')[:800]}", file=sys.stderr); return 1
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"Reset could not be completed: {type(exc).__name__}: {exc}", file=sys.stderr); return 1
if __name__ == "__main__": raise SystemExit(main())
