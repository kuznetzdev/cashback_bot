"""Utility to auto-install requirements when running in ephemeral environments."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    requirements = Path(__file__).with_name("requirements.txt")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(requirements)])


if __name__ == "__main__":
    main()
