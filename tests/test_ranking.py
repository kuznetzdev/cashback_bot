from decimal import Decimal

from app.schemas.cashback_item import RankingEntry
from app.services.categories import CategoryService
from app.services.ranking import RankingService


def test_ranking_supports_ties_and_global_score() -> None:
    service = RankingService(CategoryService())
    entries = [
        RankingEntry(bank_id=1, bank_name="T-Bank", normalized_category="fuel", percent=Decimal("5")),
        RankingEntry(bank_id=2, bank_name="Alpha", normalized_category="fuel", percent=Decimal("5")),
        RankingEntry(bank_id=1, bank_name="T-Bank", normalized_category="restaurants", percent=Decimal("7")),
    ]

    leaders = service.top_by_category(entries, "ru")
    global_rating = service.top_global(entries)

    fuel_leader = next(item for item in leaders if item.category_slug == "fuel")
    assert fuel_leader.bank_names == ["Alpha", "T-Bank"]
    assert global_rating[0].score == 2
    assert global_rating[1].score == 1
