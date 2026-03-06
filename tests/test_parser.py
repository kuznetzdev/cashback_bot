from app.services.categories import CategoryService
from app.services.parser import ParserService


def test_parse_manual_lines_supports_multiple_formats() -> None:
    parser = ParserService(CategoryService())

    items = parser.parse_manual_lines("АЗС 5%\nRestaurants - 7.5%\nMovies 10")

    assert len(items) == 3
    assert items[0].normalized_category == "movies"
    assert items[1].normalized_category == "restaurants"
    assert items[2].normalized_category == "fuel"


def test_understand_delete_and_best_queries() -> None:
    parser = ParserService(CategoryService())

    delete_intent = parser.understand_delete_command("удали банк Т-Банк")
    best_intent = parser.understand_best_query("best cashback for fuel")

    assert delete_intent is not None and delete_intent.kind == "bank"
    assert best_intent is not None and best_intent.normalized_category == "fuel"
