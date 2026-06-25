from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Mapping

import pandas as pd

from preprocessing.normalization import (
    DEFAULT_MISSING_VALUES,
    is_missing,
    normalize_value,
)

VALID = "valid"
MISSING = "missing"
INVALID = "invalid"
SUSPICIOUS = "suspicious"
REQUIRES_REVIEW = "requires_review"

FIELD_STATUSES = {VALID, MISSING, INVALID, SUSPICIOUS, REQUIRES_REVIEW}


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy/date values to MongoDB/JSON-friendly Python values."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    return value


def _missing_values(validation_cfg: Mapping[str, Any], field_cfg: Mapping[str, Any] | None = None) -> list[Any]:
    markers = list(DEFAULT_MISSING_VALUES)
    markers.extend(validation_cfg.get("missing_values", []) or [])
    if field_cfg:
        markers.extend(field_cfg.get("missing_values", []) or [])
    return markers


def _parse_date_for_comparison(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _check_required(
    raw_value: Any,
    normalized_value: Any,
    validation_cfg: Mapping[str, Any],
    field_cfg: Mapping[str, Any],
) -> tuple[str | None, list[str]]:
    missing_values = _missing_values(validation_cfg, field_cfg)
    if is_missing(raw_value, missing_values):
        message = "Required field is missing" if field_cfg.get("required", False) else "Field is missing"
        return MISSING, [message]
    return None, []


def _check_pattern(normalized_value: Any, field_cfg: Mapping[str, Any]) -> list[str]:
    pattern = field_cfg.get("pattern")
    if not pattern or normalized_value is None:
        return []

    if re.fullmatch(str(pattern), str(normalized_value)):
        return []

    return [f"Value does not match expected pattern: {pattern}"]


def _check_allowed_values(normalized_value: Any, field_cfg: Mapping[str, Any]) -> list[str]:
    allowed_values = field_cfg.get("allowed_values")
    if not allowed_values or normalized_value is None:
        return []

    allowed_as_text = {str(value).strip().lower() for value in allowed_values}
    if str(normalized_value).strip().lower() in allowed_as_text:
        return []

    return ["Value is not in the configured allowed values"]


def _check_numeric_range(normalized_value: Any, field_cfg: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    if normalized_value is None:
        return None, []

    field_type = str(field_cfg.get("type", "text")).lower()
    if field_type not in {"money", "number", "numeric", "float", "integer", "int"}:
        return None, []

    try:
        number = float(normalized_value)
    except (TypeError, ValueError):
        return INVALID, ["Value could not be interpreted as a number"]

    messages: list[str] = []

    min_value = field_cfg.get("min")
    max_value = field_cfg.get("max")
    suspicious_min = field_cfg.get("suspicious_min")
    suspicious_max = field_cfg.get("suspicious_max")

    if min_value is not None and number < float(min_value):
        messages.append(f"Value is below minimum allowed value {min_value}")
        return INVALID, messages

    if max_value is not None and number > float(max_value):
        messages.append(f"Value is above maximum allowed value {max_value}")
        return INVALID, messages

    if suspicious_min is not None and number < float(suspicious_min):
        messages.append(f"Value is below suspicious threshold {suspicious_min}")
        return SUSPICIOUS, messages

    if suspicious_max is not None and number > float(suspicious_max):
        messages.append(f"Value is above suspicious threshold {suspicious_max}")
        return SUSPICIOUS, messages

    return None, []


def _check_date_rules(normalized_value: Any, field_cfg: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    if normalized_value is None:
        return None, []

    field_type = str(field_cfg.get("type", "text")).lower()
    if field_type != "date":
        return None, []

    parsed_date = _parse_date_for_comparison(normalized_value)
    if parsed_date is None:
        return INVALID, ["Value could not be interpreted as a valid date"]

    messages: list[str] = []
    today = datetime.now(timezone.utc).date()

    if field_cfg.get("allow_future", True) is False and parsed_date > today:
        messages.append("Date is in the future")
        return SUSPICIOUS, messages

    min_date_value = field_cfg.get("min_date")
    max_date_value = field_cfg.get("max_date")

    min_date = _parse_date_for_comparison(min_date_value)
    max_date = _parse_date_for_comparison(max_date_value)

    if min_date is not None and parsed_date < min_date:
        messages.append(f"Date is before minimum allowed date {min_date.isoformat()}")
        return INVALID, messages

    if max_date is not None and parsed_date > max_date:
        messages.append(f"Date is after maximum allowed date {max_date.isoformat()}")
        return INVALID, messages

    return None, []


def validate_field(
    field_name: str,
    raw_value: Any,
    field_cfg: Mapping[str, Any],
    validation_cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one field and return its status, normalized value, and messages."""
    validation_cfg = validation_cfg or {}
    field_type = str(field_cfg.get("type", "text")).lower()
    missing_values = _missing_values(validation_cfg, field_cfg)

    normalized_value = normalize_value(
        raw_value,
        field_type=field_type,
        options=dict(field_cfg),
        missing_values=missing_values,
    )

    missing_status, messages = _check_required(raw_value, normalized_value, validation_cfg, field_cfg)
    if missing_status is not None:
        return {
            "status": missing_status,
            "raw_value": _json_safe(raw_value),
            "normalized_value": None,
            "messages": messages,
        }

    # If a non-missing value could not be normalized for a typed field, it is invalid.
    if normalized_value is None and not is_missing(raw_value, missing_values):
        return {
            "status": INVALID,
            "raw_value": _json_safe(raw_value),
            "normalized_value": None,
            "messages": [f"Value could not be normalized as {field_type}"],
        }

    invalid_messages: list[str] = []
    invalid_messages.extend(_check_pattern(normalized_value, field_cfg))
    invalid_messages.extend(_check_allowed_values(normalized_value, field_cfg))

    if invalid_messages:
        return {
            "status": INVALID,
            "raw_value": _json_safe(raw_value),
            "normalized_value": _json_safe(normalized_value),
            "messages": invalid_messages,
        }

    numeric_status, numeric_messages = _check_numeric_range(normalized_value, field_cfg)
    if numeric_status is not None:
        return {
            "status": numeric_status,
            "raw_value": _json_safe(raw_value),
            "normalized_value": _json_safe(normalized_value),
            "messages": numeric_messages,
        }

    date_status, date_messages = _check_date_rules(normalized_value, field_cfg)
    if date_status is not None:
        return {
            "status": date_status,
            "raw_value": _json_safe(raw_value),
            "normalized_value": _json_safe(normalized_value),
            "messages": date_messages,
        }

    custom_messages = list(field_cfg.get("messages", []) or [])
    return {
        "status": VALID,
        "raw_value": _json_safe(raw_value),
        "normalized_value": _json_safe(normalized_value),
        "messages": custom_messages,
    }


def _record_status(field_results: Mapping[str, dict[str, Any]], validation_cfg: Mapping[str, Any]) -> str:
    if not field_results:
        return REQUIRES_REVIEW

    statuses = {result.get("status") for result in field_results.values()}

    required_fields = [
        field_name
        for field_name, field_cfg in (validation_cfg.get("fields", {}) or {}).items()
        if field_cfg.get("required", False)
    ]
    required_bad = any(
        field_results.get(field_name, {}).get("status") in {MISSING, INVALID}
        for field_name in required_fields
    )
    if required_bad:
        return REQUIRES_REVIEW

    if INVALID in statuses:
        return REQUIRES_REVIEW

    if SUSPICIOUS in statuses:
        return SUSPICIOUS

    important_fields = validation_cfg.get("important_fields", []) or []
    if important_fields:
        has_important_value = any(
            field_results.get(field_name, {}).get("status") in {VALID, SUSPICIOUS}
            for field_name in important_fields
        )
        if not has_important_value:
            return REQUIRES_REVIEW

    return VALID


def validate_record(record: Mapping[str, Any], validation_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one flattened raw permit record using a validation config."""
    fields_cfg = validation_cfg.get("fields", {}) or {}
    field_results: dict[str, dict[str, Any]] = {}

    for field_name, field_cfg in fields_cfg.items():
        field_results[field_name] = validate_field(
            field_name=field_name,
            raw_value=record.get(field_name),
            field_cfg=field_cfg or {},
            validation_cfg=validation_cfg,
        )

    return {
        "record_status": _record_status(field_results, validation_cfg),
        "fields": field_results,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_dataframe(
    df: pd.DataFrame,
    validation_cfg: Mapping[str, Any],
    output_col: str = "validation",
) -> pd.DataFrame:
    """Attach a validation object to each DataFrame row."""
    if not validation_cfg.get("enabled", True):
        return df.copy()

    result_df = df.copy()
    result_df[output_col] = [
        validate_record(row.to_dict(), validation_cfg)
        for _, row in result_df.iterrows()
    ]
    return result_df


def validation_summary(validated_df: pd.DataFrame, validation_col: str = "validation") -> dict[str, Any]:
    """Create simple counts that are useful for logs, summaries, and thesis metrics."""
    if validation_col not in validated_df.columns:
        return {"record_count": int(len(validated_df)), "record_status_counts": {}, "field_status_counts": {}}

    record_status_counts: dict[str, int] = {}
    field_status_counts: dict[str, dict[str, int]] = {}

    for validation in validated_df[validation_col]:
        if not isinstance(validation, dict):
            continue

        record_status = str(validation.get("record_status") or "unknown")
        record_status_counts[record_status] = record_status_counts.get(record_status, 0) + 1

        fields = validation.get("fields") or {}
        if not isinstance(fields, dict):
            continue

        for field_name, field_result in fields.items():
            status = str((field_result or {}).get("status") or "unknown")
            field_counts = field_status_counts.setdefault(field_name, {})
            field_counts[status] = field_counts.get(status, 0) + 1

    return {
        "record_count": int(len(validated_df)),
        "record_status_counts": record_status_counts,
        "field_status_counts": field_status_counts,
    }


def normalized_values_from_validation(validation: Mapping[str, Any]) -> dict[str, Any]:
    """Extract normalized values from one validation object."""
    fields = validation.get("fields") or {}
    if not isinstance(fields, dict):
        return {}

    return {
        field_name: field_result.get("normalized_value")
        for field_name, field_result in fields.items()
        if isinstance(field_result, dict)
    }


def add_validation_status_columns(
    df: pd.DataFrame,
    validation_col: str = "validation",
    prefix: str = "validation_",
) -> pd.DataFrame:
    """Add lightweight status columns that can be used by later inference steps."""
    if validation_col not in df.columns:
        return df.copy()

    result_df = df.copy()
    result_df[f"{prefix}record_status"] = result_df[validation_col].map(
        lambda item: item.get("record_status") if isinstance(item, dict) else None
    )

    field_names: set[str] = set()
    for validation in result_df[validation_col]:
        if isinstance(validation, dict) and isinstance(validation.get("fields"), dict):
            field_names.update(validation["fields"].keys())

    for field_name in sorted(field_names):
        result_df[f"{prefix}{field_name}_status"] = result_df[validation_col].map(
            lambda item, name=field_name: (
                item.get("fields", {}).get(name, {}).get("status")
                if isinstance(item, dict)
                else None
            )
        )

    return result_df
