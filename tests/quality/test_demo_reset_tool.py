import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def test_demo_reset_requires_explicit_confirmation():
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_demo.py"), "--base-url", "http://127.0.0.1:9"], capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "--confirm" in result.stderr
