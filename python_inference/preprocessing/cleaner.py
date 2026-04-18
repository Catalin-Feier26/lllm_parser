from __future__ import annotations

import pandas as pd


def _clean_string_value(value: object) -> object:
    if pd.isna(value):
        return pd.NA

    if not isinstance(value, str):
        return value

    cleaned = " ".join(value.strip().split())
    return pd.NA if cleaned == "" else cleaned


def normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].map(_clean_string_value)

    return df


def clean_target_column(
    df: pd.DataFrame,
    target_col: str,
    rare_class_map: dict[str, str] | None = None,
    ) -> pd.DataFrame:
    df = df.copy()

    if target_col not in df.columns:
        raise ValueError(f"Missing target column: {target_col}")

    df["permit_class_clean"] = df[target_col]

    df.loc[df["permit_class_clean"] == "Not Identified", "permit_class_clean"] = pd.NA

    if rare_class_map:
        df["permit_class_clean"] = df["permit_class_clean"].replace(rare_class_map)

    return df


def keep_columns(df: pd.DataFrame, keep_cols: list[str]) -> pd.DataFrame:
    missing = [c for c in keep_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return df[keep_cols].copy()