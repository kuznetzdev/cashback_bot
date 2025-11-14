"""Category inference and template expansion."""
from __future__ import annotations

from typing import Dict, List

from .db import Template


class CategoryService:
    def __init__(self) -> None:
        self._manual_templates: Dict[str, Template] = {}

    def register_template(self, template: Template) -> None:
        self._manual_templates[template.template_id] = template

    def unregister_template(self, template_id: str) -> None:
        self._manual_templates.pop(template_id, None)

    def infer_category(self, description: str) -> str:
        lowered = description.lower()
        for template in self._manual_templates.values():
            if template.name.lower() in lowered:
                return template.fields.get("category", "other")
        if "аптека" in lowered:
            return "pharmacy"
        if "магазин" in lowered:
            return "groceries"
        return "other"

    def expand_templates(self) -> List[Template]:
        return list(self._manual_templates.values())
