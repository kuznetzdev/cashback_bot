from __future__ import annotations

import tempfile
from pathlib import Path


def cleanup_file(path: Path | None) -> None:
    if path is None:
        return
    path.unlink(missing_ok=True)


def create_temp_path(suffix: str, temp_dir: Path) -> Path:
    temp_dir.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(suffix=suffix, dir=temp_dir)
    Path(raw_path).unlink(missing_ok=True)
    return Path(raw_path)
