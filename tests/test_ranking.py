from decimal import Decimal

from app.domain.services.categories import CategoryService
from app.domain.services.ranking import RankingEntry, RankingService


def test_ranking_with_ties_and_global_scoring() -> None:
    service = RankingService(CategoryService())
    entries = [
        RankingEntry(bank_id=1, bank_name="T-Bank", category_slug="fuel", percent=Decimal("5.00")),
        RankingEntry(bank_id=2, bank_name="Alpha", category_slug="fuel", percent=Decimal("5.00")),
        RankingEntry(bank_id=1, bank_name="T-Bank", category_slug="restaurants", percent=Decimal("7.00")),
    ]

    leaders = service.top_by_category(entries, language="ru")
    global_top = service.top_global(entries, language="ru")
    fuel = next(item for item in leaders if item.category_slug == "fuel")

    assert fuel.bank_names == ["Alpha", "T-Bank"]
    assert global_top[0].bank_name == "T-Bank"
    assert global_top[0].score == 2
    assert global_top[1].bank_name == "Alpha"
    assert global_top[1].score == 1
