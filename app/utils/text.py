from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Localizer:
    def __init__(self, locales_dir: Path) -> None:
        self._catalogs: dict[str, dict[str, str]] = {}
        for path in locales_dir.glob("*.json"):
            self._catalogs[path.stem] = json.loads(path.read_text(encoding="utf-8"))

    def gettext(self, language: str, key: str, **kwargs: Any) -> str:
        catalog = self._catalogs.get(language) or self._catalogs.get("ru", {})
        template = catalog.get(key, key)
        if kwargs:
            return template.format(**kwargs)
        return template


def render_item_lines(items: list[str]) -> str:
    return "\n".join(items) if items else "—"
