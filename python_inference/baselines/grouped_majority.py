from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd


def _safe_key(*values: object) -> tuple[object, ...]:
    return tuple("<MISSING>" if pd.isna(v) else v for v in values)


def _majority_value(values: list[str]) -> str:
    if not values:
        raise ValueError("Cannot compute majority value from empty list")

    counter = Counter(values)
    return counter.most_common(1)[0][0]


def fit_grouped_majority_reference(
    df: pd.DataFrame,
    target_col: str = "permit_class_input",
    ) -> dict[str, Any]:
    required_cols = ["building_type", "permit_type", target_col]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for baseline fitting: {missing}")

    reference_df = df[df[target_col].notna()].copy()
    if reference_df.empty:
        raise ValueError("No reference rows with known target values were found")

    by_pair: dict[tuple[object, object], list[str]] = defaultdict(list)
    by_building: dict[object, list[str]] = defaultdict(list)
    global_values: list[str] = []

    for _, row in reference_df.iterrows():
        target_value = row[target_col]
        if pd.isna(target_value):
            continue

        pair_key = _safe_key(row["building_type"], row["permit_type"])
        building_key = _safe_key(row["building_type"])[0]

        by_pair[pair_key].append(str(target_value))
        by_building[building_key].append(str(target_value))
        global_values.append(str(target_value))

    pair_majority = {k: _majority_value(v) for k, v in by_pair.items()}
    building_majority = {k: _majority_value(v) for k, v in by_building.items()}
    global_majority = _majority_value(global_values)

    return {
        "pair_majority": pair_majority,
        "building_majority": building_majority,
        "global_majority": global_majority,
    }


def predict_grouped_majority(
    df: pd.DataFrame,
    fitted: dict[str, Any],
    ) -> pd.DataFrame:
    required_cols = ["building_type", "permit_type", "permit_class_true", "is_masked"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for prediction: {missing}")

    result_df = df.copy()

    predictions: list[object] = []
    prediction_source: list[str] = []

    for _, row in result_df.iterrows():
        if row["is_masked"] != 1:
            predictions.append(pd.NA)
            prediction_source.append("not_applicable")
            continue

        pair_key = _safe_key(row["building_type"], row["permit_type"])
        building_key = _safe_key(row["building_type"])[0]

        if pair_key in fitted["pair_majority"]:
            predictions.append(fitted["pair_majority"][pair_key])
            prediction_source.append("pair_majority")
        elif building_key in fitted["building_majority"]:
            predictions.append(fitted["building_majority"][building_key])
            prediction_source.append("building_majority")
        else:
            predictions.append(fitted["global_majority"])
            prediction_source.append("global_majority")

    result_df["predicted_permit_class"] = predictions
    result_df["prediction_source"] = prediction_source
    result_df["algorithm"] = "grouped_majority"

    return result_df