from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.services.catalog import CatalogService
from app.services.categories import CategoryService
from app.services.ocr import OCRService
from app.services.parser import ParserService
from app.services.ranking import RankingService
from app.utils.text import Localizer


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    localizer: Localizer
    category_service: CategoryService
    parser_service: ParserService
    ranking_service: RankingService
    catalog_service: CatalogService
    ocr_service: OCRService


def build_container(settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> AppContainer:
    localizer = Localizer(Path(__file__).resolve().parent.parent / "locales")
    category_service = CategoryService()
    parser_service = ParserService(category_service)
    ranking_service = RankingService(category_service)
    catalog_service = CatalogService(category_service)
    ocr_service = OCRService(settings)
    return AppContainer(
        settings=settings,
        session_factory=session_factory,
        localizer=localizer,
        category_service=category_service,
        parser_service=parser_service,
        ranking_service=ranking_service,
        catalog_service=catalog_service,
        ocr_service=ocr_service,
    )
