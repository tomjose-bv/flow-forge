"""Create .venv and install flow-forge in editable mode with dev dependencies."""

import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"


def main() -> None:
    if not VENV.exists():
        venv.create(VENV, with_pip=True)
    py = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.check_call([str(py), "-m", "pip", "install", "-q", "-e", f"{ROOT}[dev]"])
    print(f"ready: {py}")


if __name__ == "__main__":
    main()
