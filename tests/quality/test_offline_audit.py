from pathlib import Path
from scripts.check_offline import inspect

def test_offline_audit_detects_remote_assets_and_missing_lock(tmp_path):
    front = tmp_path / "frontend"
    (front / "dist").mkdir(parents=True)
    (front / "dist" / "index.html").write_text('<script src="https://cdn.example.com/app.js"></script>', encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "requirements.txt").write_text("fastapi==1.0\n", encoding="utf-8")
    results = {r.name: r for r in inspect(tmp_path)}
    assert results["frontend_lockfile"].status == "FAIL"
    assert results["external_assets"].status == "FAIL"
    assert results["python_requirements"].status == "PASS"

def test_offline_audit_warns_when_build_is_missing(tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend").mkdir()
    results = {r.name: r for r in inspect(tmp_path)}
    assert results["frontend_build"].status == "FAIL"
    assert results["external_assets"].status == "WARN"

def test_offline_audit_checks_built_css_for_remote_font_imports(tmp_path):
    front = tmp_path / "frontend"
    assets = front / "dist" / "assets"
    assets.mkdir(parents=True)
    (front / "package-lock.json").write_text("{}", encoding="utf-8")
    (front / "dist" / "index.html").write_text('<script src="/assets/index.js"></script>', encoding="utf-8")
    (assets / "index.css").write_text('@import url("https://fonts.googleapis.com/css?family=Example");', encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "requirements.txt").write_text("fastapi==1.0\n", encoding="utf-8")
    results = {r.name: r for r in inspect(tmp_path)}
    assert results["external_assets"].status == "FAIL"
    assert "fonts.googleapis.com" in results["external_assets"].details
