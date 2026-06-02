from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd


def _to_float(value: object) -> float | None:
	if pd.isna(value):
		return None

	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
	missing = [col for col in required_cols if col not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns for feature engineering: {missing}")


def add_valuation_bucket(
	df: pd.DataFrame,
	source_col: str = "valuation",
	output_col: str = "valuation_bucket",
) -> pd.DataFrame:
	_validate_columns(df, [source_col])
	result_df = df.copy()

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

	result_df[output_col] = result_df[source_col].map(bucket)
	return result_df


def add_total_units_group(
	df: pd.DataFrame,
	source_col: str = "total_units",
	output_col: str = "total_units_group",
) -> pd.DataFrame:
	_validate_columns(df, [source_col])
	result_df = df.copy()

	def group(value: object) -> str:
		num = _to_float(value)
		if num is None:
			return "missing"
		if num == 0:
			return "0"
		if num == 1:
			return "1"
		return "gt1"

	result_df[output_col] = result_df[source_col].map(group)
	return result_df


def add_total_sf_nonzero(
	df: pd.DataFrame,
	source_col: str = "total_sf",
	output_col: str = "total_sf_nonzero",
) -> pd.DataFrame:
	_validate_columns(df, [source_col])
	result_df = df.copy()

	def group(value: object) -> str:
		num = _to_float(value)
		if num is None:
			return "missing"
		if num == 0:
			return "zero"
		return "nonzero"

	result_df[output_col] = result_df[source_col].map(group)
	return result_df


FEATURE_REGISTRY: dict[str, Callable[..., pd.DataFrame]] = {
	"valuation_bucket": add_valuation_bucket,
	"total_units_group": add_total_units_group,
	"total_sf_nonzero": add_total_sf_nonzero,
}


def apply_feature_engineering(
	df: pd.DataFrame,
	feature_configs: dict[str, dict[str, Any]] | None = None,
) -> pd.DataFrame:
	"""
	Apply only the engineered features enabled for the current source.

	Example config:
		{
			"valuation_bucket": {"enabled": True},
			"total_units_group": {"enabled": True},
			"total_sf_nonzero": {
				"enabled": True,
				"source_col": "square_feet",
				"output_col": "total_sf_nonzero",
			},
		}

	If feature_configs is omitted, the original three Naples features are applied.
	"""
	if feature_configs is None:
		feature_configs = {
			"valuation_bucket": {"enabled": True},
			"total_units_group": {"enabled": True},
			"total_sf_nonzero": {"enabled": True},
		}

	result_df = df.copy()

	for feature_name, config in feature_configs.items():
		if not config.get("enabled", True):
			continue

		feature_fn = FEATURE_REGISTRY.get(feature_name)
		if feature_fn is None:
			raise ValueError(f"Unknown engineered feature: {feature_name}")

		params = {key: value for key, value in config.items() if key != "enabled"}
		result_df = feature_fn(result_df, **params)

	return result_df
