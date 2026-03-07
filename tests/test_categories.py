from app.domain.services.categories import CategoryService


def test_normalize_ru_en_aliases() -> None:
    service = CategoryService()
    assert service.normalize("АЗС").slug == "fuel"
    assert service.normalize("Fuel station").slug == "fuel"
    assert service.normalize("Кафе").slug == "restaurants"
    assert service.normalize("Groceries").slug == "supermarkets"


def test_expand_query_slugs_for_broad_categories() -> None:
    service = CategoryService()
    assert service.expand_query_slugs("Супермаркеты") == {"supermarkets", "groceries"}
    assert service.expand_query_slugs("Товары для дома") == {"home_goods", "decor", "construction"}
