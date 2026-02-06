from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    # gsd-browser/tests/<this file>
    return Path(__file__).resolve().parents[2]


def _guard_script() -> Path:
    return _repo_root() / "infra" / "scripts" / "guard_no_secret_outputs.py"


def test_allows_access_key_id_output(tmp_path: Path) -> None:
    bicep = tmp_path / "m.bicep"
    bicep.write_text("output accessKeyId string = 'not-a-secret'\\n", encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(_guard_script()), "--paths", str(bicep)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_blocks_secretish_output_names(tmp_path: Path) -> None:
    bicep = tmp_path / "m.bicep"
    bicep.write_text("output apiKey string = 'oops'\\n", encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(_guard_script()), "--paths", str(bicep)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert "apiKey" in r.stderr
