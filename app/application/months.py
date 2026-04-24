from __future__ import annotations

from datetime import date, datetime


def current_month_key(reference: date | datetime | None = None) -> str:
    if reference is None:
        current = datetime.now()
    elif isinstance(reference, datetime):
        current = reference
    else:
        return reference.strftime("%Y-%m")
    return current.strftime("%Y-%m")


def normalize_month_key(month_key: str | None) -> str:
    if month_key is None:
        return current_month_key()
    cleaned = month_key.strip()
    try:
        parsed = datetime.strptime(cleaned, "%Y-%m")
    except ValueError as error:
        raise ValueError(f"Invalid month key: {month_key}") from error
    return parsed.strftime("%Y-%m")


def shift_month_key(month_key: str, offset: int) -> str:
    normalized = normalize_month_key(month_key)
    year_str, month_str = normalized.split("-")
    year = int(year_str)
    month = int(month_str)
    absolute = year * 12 + (month - 1) + offset
    shifted_year, shifted_month_zero_based = divmod(absolute, 12)
    return f"{shifted_year:04d}-{shifted_month_zero_based + 1:02d}"


def format_month_label(month_key: str | None) -> str:
    normalized = normalize_month_key(month_key)
    year_str, month_str = normalized.split("-")
    return f"{month_str}.{year_str}"


def sort_month_keys(months: list[str]) -> list[str]:
    normalized = {normalize_month_key(month) for month in months}
    return sorted(normalized)
