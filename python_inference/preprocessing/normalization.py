from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd


DEFAULT_MISSING_VALUES = {
    "",
    "-",
    "--",
    "---",
    "n/a",
    "na",
    "none",
    "null",
    "not identified",
    "not available",
    "unknown",
}

DEFAULT_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%m-%d-%Y",
    "%m-%d-%y",
    "%d/%m/%Y",
    "%d/%m/%y",
]


def is_missing(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> bool:
    """Return True when a value should be treated as missing."""
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass

    markers = {str(item).strip().lower() for item in DEFAULT_MISSING_VALUES}
    if missing_values:
        markers.update(str(item).strip().lower() for item in missing_values)

    if isinstance(value, str):
        return value.strip().lower() in markers

    return False


def normalize_missing(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> Any | None:
    """Convert configured missing markers to None and leave other values unchanged."""
    return None if is_missing(value, missing_values) else value


def normalize_text(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> str | None:
    """Trim whitespace, collapse repeated spaces, and normalize missing values."""
    if is_missing(value, missing_values):
        return None

    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def normalize_identifier(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> str | None:
    """Normalize identifiers while preserving meaningful separators."""
    text = normalize_text(value, missing_values)
    if text is None:
        return None
    return re.sub(r"\s+", "", text)


def normalize_phone(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> str | None:
    """Normalize phone numbers to digits, preserving a trailing extension when present."""
    text = normalize_text(value, missing_values)
    if text is None:
        return None

    extension = None
    extension_match = re.search(r"(?:ext\.?|x)\s*(\d+)$", text, flags=re.IGNORECASE)
    if extension_match:
        extension = extension_match.group(1)
        text = text[: extension_match.start()]

    digits = re.sub(r"\D+", "", text)
    if not digits:
        return None

    return f"{digits}x{extension}" if extension else digits


def _clean_numeric_text(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> str | None:
    text = normalize_text(value, missing_values)
    if text is None:
        return None

    # Accept values such as "$1,250.00", "(125.00)", and "1 250".
    is_parenthesized_negative = bool(re.fullmatch(r"\(.*\)", text))
    text = text.strip("()")
    text = text.replace("$", "")
    text = text.replace(",", "")
    text = text.replace(" ", "")

    if is_parenthesized_negative and not text.startswith("-"):
        text = f"-{text}"

    return text or None


def normalize_decimal(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> Decimal | None:
    """Normalize numeric values to Decimal."""
    if isinstance(value, Decimal):
        return value

    if isinstance(value, int):
        return Decimal(value)

    if isinstance(value, float):
        if math.isnan(value):
            return None
        return Decimal(str(value))

    text = _clean_numeric_text(value, missing_values)
    if text is None:
        return None

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def normalize_money(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> float | None:
    """Normalize monetary values to float for DataFrame/MongoDB compatibility."""
    number = normalize_decimal(value, missing_values)
    return None if number is None else float(number)


def normalize_number(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> float | None:
    """Normalize generic numeric values to float."""
    return normalize_money(value, missing_values)


def normalize_integer(value: Any, missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None) -> int | None:
    """Normalize integer-like values."""
    number = normalize_decimal(value, missing_values)
    if number is None:
        return None

    try:
        return int(number)
    except (ValueError, OverflowError):
        return None


def normalize_date(
    value: Any,
    formats: list[str] | tuple[str, ...] | None = None,
    missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None,
) -> str | None:
    """Normalize dates to ISO YYYY-MM-DD strings."""
    if is_missing(value, missing_values):
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    text = normalize_text(value, missing_values)
    if text is None:
        return None

    # Remove common time part, for example "2025-04-01 00:00:00".
    text = re.sub(r"\s+00:00:00$", "", text)

    for fmt in list(formats or DEFAULT_DATE_FORMATS):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def normalize_value(
    value: Any,
    field_type: str = "text",
    options: dict[str, Any] | None = None,
    missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None,
) -> Any:
    """Normalize a single value according to a schema/config field type."""
    options = options or {}
    field_missing_values = options.get("missing_values") or missing_values
    field_type = str(field_type or "text").lower()

    if field_type == "date":
        return normalize_date(value, options.get("formats"), field_missing_values)
    if field_type == "money":
        return normalize_money(value, field_missing_values)
    if field_type in {"integer", "int"}:
        return normalize_integer(value, field_missing_values)
    if field_type in {"number", "numeric", "float"}:
        return normalize_number(value, field_missing_values)
    if field_type == "phone":
        return normalize_phone(value, field_missing_values)
    if field_type in {"identifier", "id"}:
        return normalize_identifier(value, field_missing_values)

    return normalize_text(value, field_missing_values)


def normalize_record(
    record: dict[str, Any],
    schema: dict[str, dict[str, Any]],
    missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    """Normalize configured fields from one record."""
    normalized: dict[str, Any] = {}

    for field_name, field_cfg in schema.items():
        field_type = field_cfg.get("type", "text")
        normalized[field_name] = normalize_value(
            record.get(field_name),
            field_type=field_type,
            options=field_cfg,
            missing_values=missing_values,
        )

    return normalized


def normalize_dataframe(
    df: pd.DataFrame,
    schema: dict[str, dict[str, Any]],
    missing_values: list[Any] | set[Any] | tuple[Any, ...] | None = None,
    suffix: str = "_normalized",
) -> pd.DataFrame:
    """Add normalized companion columns for configured fields."""
    result_df = df.copy()

    for field_name, field_cfg in schema.items():
        if field_name not in result_df.columns:
            continue

        field_type = field_cfg.get("type", "text")
        output_col = field_cfg.get("normalized_col", f"{field_name}{suffix}")
        result_df[output_col] = result_df[field_name].map(
            lambda value: normalize_value(
                value,
                field_type=field_type,
                options=field_cfg,
                missing_values=missing_values,
            )
        )

    return result_df
