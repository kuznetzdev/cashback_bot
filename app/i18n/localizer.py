from __future__ import annotations

import json
from pathlib import Path


class Localizer:
    def __init__(self, locales_dir: Path, default_language: str = "ru") -> None:
        self.default_language = default_language
        self._catalogs: dict[str, dict[str, object]] = {}
        self._catalogs["ru"] = self._load_catalog(locales_dir / "ru.json")
        self._catalogs["en"] = self._load_catalog(locales_dir / "en.json")

    @staticmethod
    def _load_catalog(path: Path) -> dict[str, object]:
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if isinstance(raw, dict):
            return raw
        return {}

    def t(self, key: str, language: str, params: dict[str, object] | None = None) -> str:
        if key.startswith("bank:"):
            return key.replace("bank:", "", 1)
        resolved_language = language if language in self._catalogs else self.default_language
        message = self._lookup(self._catalogs[resolved_language], key)
        if message is None and resolved_language != self.default_language:
            message = self._lookup(self._catalogs[self.default_language], key)
        if message is None:
            return key
        resolved = str(message)
        render_params = self._resolve_params(params or {}, resolved_language)
        try:
            return resolved.format(**render_params)
        except KeyError:
            return resolved

    def has_key(self, key: str, language: str) -> bool:
        resolved_language = language if language in self._catalogs else self.default_language
        return self._lookup(self._catalogs[resolved_language], key) is not None

    def _resolve_params(self, params: dict[str, object], language: str) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in params.items():
            if isinstance(value, str) and "." in value and self.has_key(value, language):
                result[key] = self.t(value, language)
            else:
                result[key] = value
        return result

    @staticmethod
    def _lookup(data: dict[str, object], dotted_key: str) -> object | None:
        current: object = data
        for part in dotted_key.split("."):
            if not isinstance(current, dict):
                return None
            if part not in current:
                return None
            current = current[part]
        return current
