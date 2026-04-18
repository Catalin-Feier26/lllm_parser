from __future__ import annotations

import pandas as pd


def _to_float(value: object) -> float | None:
    if pd.isna(value):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def add_valuation_bucket(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def bucket(value: object) -> str:
        num = _to_float(value)
        if num is None:
            return "missing"
        if num <= 1:
            return "le_1"
        if 2 <= num <= 999:
            return "2_999"
        if 1000 <= num <= 9999:
            return "1000_9999"
        if 10000 <= num <= 99999:
            return "10000_99999"
        return "100000_plus"

    df["valuation_bucket"] = df["valuation"].map(bucket)
    return df


def add_total_units_group(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def group(value: object) -> str:
        num = _to_float(value)
        if num is None:
            return "missing"
        if num == 0:
            return "0"
        if num == 1:
            return "1"
        return "gt1"

    df["total_units_group"] = df["total_units"].map(group)
    return df


def add_total_sf_nonzero(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def group(value: object) -> str:
        num = _to_float(value)
        if num is None:
            return "missing"
        if num == 0:
            return "zero"
        return "nonzero"

    df["total_sf_nonzero"] = df["total_sf"].map(group)
    return df


def apply_feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    df = add_valuation_bucket(df)
    df = add_total_units_group(df)
    df = add_total_sf_nonzero(df)
    return df