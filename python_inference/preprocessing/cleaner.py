from __future__ import annotations

from typing import Any

import pandas as pd


def _clean_string_value(value: object) -> object:
	"""Trim repeated whitespace and convert empty strings to missing values."""
	if pd.isna(value):
		return pd.NA

	if not isinstance(value, str):
		return value

	cleaned = " ".join(value.strip().split())
	return pd.NA if cleaned == "" else cleaned


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
	missing = [col for col in required_cols if col not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns: {missing}")


def normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
	"""Normalize every object column without modifying the original DataFrame."""
	result_df = df.copy()

	for col in result_df.columns:
		if result_df[col].dtype == "object":
			result_df[col] = result_df[col].map(_clean_string_value)

	return result_df


def clean_target_column(
	df: pd.DataFrame,
	config: dict[str, Any],
) -> pd.DataFrame:
	"""
	Create a cleaned target column using source-specific configuration.

	Required config:
		source_col: original source field to clean

	Optional config:
		clean_col: output column name, defaults to '<source_col>_clean'
		missing_values: values that should be converted to pd.NA
		replacements: mapping applied after missing-value normalization
	"""
	source_col = config["source_col"]
	clean_col = config.get("clean_col", f"{source_col}_clean")
	missing_values = config.get("missing_values", [])
	replacements = config.get("replacements", {})

	_validate_columns(df, [source_col])

	result_df = df.copy()
	result_df[clean_col] = result_df[source_col].map(_clean_string_value)

	if missing_values:
		result_df.loc[result_df[clean_col].isin(missing_values), clean_col] = pd.NA

	if replacements:
		result_df[clean_col] = result_df[clean_col].replace(replacements)

	return result_df


def clean_multiple_target_columns(
	df: pd.DataFrame,
	target_configs: dict[str, dict[str, Any]],
) -> pd.DataFrame:
	"""Apply clean_target_column for each configured inference target."""
	result_df = df.copy()

	for target_name, target_config in target_configs.items():
		if not target_config.get("enabled", True):
			continue

		clean_config = target_config.get("cleaning")
		if clean_config is None:
			clean_config = {
				"source_col": target_name,
				"clean_col": f"{target_name}_clean",
			}

		result_df = clean_target_column(result_df, clean_config)

	return result_df


def keep_columns(df: pd.DataFrame, keep_cols: list[str]) -> pd.DataFrame:
	"""Return only the selected columns after validating that they exist."""
	_validate_columns(df, keep_cols)
	return df[keep_cols].copy()
