from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService


def test_parse_manual_lines_supports_required_formats() -> None:
    parser = ParserService(CategoryService())
    items = parser.parse_manual_lines("АЗС 5%\nRestaurants - 7.5%\nMovies 10\nАптеки 3")
    assert len(items) == 4
    assert {item.normalized_category for item in items} == {"fuel", "restaurants", "movies", "pharmacy"}


def test_understand_delete_command_ru_en() -> None:
    parser = ParserService(CategoryService())
    delete_bank = parser.understand_delete_command("удали банк Т-Банк")
    delete_category = parser.understand_delete_command("delete category fuel")
    assert delete_bank is not None
    assert delete_bank.kind == "bank"
    assert delete_category is not None
    assert delete_category.kind == "category"


def test_understand_best_query_ru_en() -> None:
    parser = ParserService(CategoryService())
    ru = parser.understand_best_query("где лучше рестораны")
    en = parser.understand_best_query("best cashback for fuel")
    assert ru is not None
    assert ru.normalized_category == "restaurants"
    assert en is not None
    assert en.normalized_category == "fuel"
