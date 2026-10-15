"""The website's checks, run in Node.

check_web_brain.mjs replays a Python-recorded input through the live demo's
brain (site/brain.js) and must match the Python engine spike for spike;
check_web_demo.mjs runs the live demo's sugar-cube loop (site/creature.js) with
intact and cut wiring; check_web_replays.mjs checks that the home page's recorded
replays agree with themselves. Skipped where Node is not installed.
"""

from pathlib import Path
import shutil
import subprocess

import pytest

CREATURE_DIR = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
@pytest.mark.parametrize("script", ["check_web_brain.mjs", "check_web_demo.mjs", "check_web_replays.mjs"])
def test_web_check(script):
    result = subprocess.run([NODE, str(CREATURE_DIR / "tests" / "web" / script)],
                            cwd=CREATURE_DIR, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
