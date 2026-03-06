from app.services.categories import CategoryService


def test_normalize_common_aliases() -> None:
    service = CategoryService()

    assert service.normalize("АЗС").slug == "fuel"
    assert service.normalize("Fuel station").slug == "fuel"
    assert service.normalize("Кафе").slug == "restaurants"


def test_expand_query_slugs_for_broad_category() -> None:
    service = CategoryService()

    assert service.expand_query_slugs("Продукты питания") == {"groceries", "supermarkets"}
