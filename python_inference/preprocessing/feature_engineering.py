from __future__ import annotations

import re
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


def add_fee_bucket(
	df: pd.DataFrame,
	source_col: str = "fee",
	output_col: str = "fee_bucket",
) -> pd.DataFrame:
	return add_valuation_bucket(df, source_col=source_col, output_col=output_col)


def add_paid_fee_bucket(
	df: pd.DataFrame,
	source_col: str = "paid_fee",
	output_col: str = "paid_fee_bucket",
) -> pd.DataFrame:
	return add_valuation_bucket(df, source_col=source_col, output_col=output_col)


def add_permit_number_prefix(
	df: pd.DataFrame,
	source_col: str = "permit_number",
	output_col: str = "permit_number_prefix",
) -> pd.DataFrame:
	_validate_columns(df, [source_col])
	result_df = df.copy()

	def prefix(value: object) -> str:
		if pd.isna(value):
			return "missing"
		text = str(value).strip().upper()
		if not text:
			return "missing"
		match = re.match(r"([A-Z]+)", text)
		if match:
			return match.group(1)
		parts = re.split(r"[-_\s]+", text, maxsplit=1)
		return parts[0] if parts and parts[0] else "other"

	result_df[output_col] = result_df[source_col].map(prefix)
	return result_df


def add_regex_category(
	df: pd.DataFrame,
	source_col: str,
	output_col: str,
	regex: str,
	default_value: str = "other",
	missing_value: str = "missing",
	uppercase: bool = True,
) -> pd.DataFrame:
	_validate_columns(df, [source_col])
	result_df = df.copy()
	pattern = re.compile(regex)

	def extract(value: object) -> str:
		if pd.isna(value):
			return missing_value
		text = str(value).strip()
		if not text:
			return missing_value
		match = pattern.search(text)
		if not match:
			return default_value
		category = match.group(1) if match.groups() else match.group(0)
		category = str(category).strip()
		if not category:
			return default_value
		return category.upper() if uppercase else category

	result_df[output_col] = result_df[source_col].map(extract)
	return result_df


def add_description_keywords(
	df: pd.DataFrame,
	source_col: str = "description",
	output_col: str = "description_keywords",
	keywords: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
	_validate_columns(df, [source_col])
	result_df = df.copy()
	if keywords is None:
		keywords = {
			"solar": ["solar", "photovoltaic", "pv"],
			"roof": ["roof", "reroof"],
			"plumbing": ["plumbing", "water heater"],
			"electrical": ["electrical", "electric", "panel"],
			"mechanical": ["mechanical", "hvac", "furnace", "ac"],
			"remodel": ["remodel", "renovation", "alteration", "tenant improvement"],
			"addition": ["addition", "additions"],
			"demolition": ["demo", "demolition"],
			"pool": ["pool", "spa"],
		}

	def extract(value: object) -> str:
		if pd.isna(value):
			return "missing"
		text = str(value).lower()
		if not text.strip():
			return "missing"
		matches = [
			label
			for label, terms in keywords.items()
			if any(term.lower() in text for term in terms)
		]
		return "+".join(matches) if matches else "other"

	result_df[output_col] = result_df[source_col].map(extract)
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
	"fee_bucket": add_fee_bucket,
	"paid_fee_bucket": add_paid_fee_bucket,
	"permit_number_prefix": add_permit_number_prefix,
	"permit_number_category": add_regex_category,
	"regex_category": add_regex_category,
	"description_keywords": add_description_keywords,
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

		feature_fn = add_regex_category if "regex" in config else FEATURE_REGISTRY.get(feature_name)
		if feature_fn is None:
			raise ValueError(f"Unknown engineered feature: {feature_name}")

		params = {key: value for key, value in config.items() if key != "enabled"}
		result_df = feature_fn(result_df, **params)

	return result_df
