from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd


ALGORITHM_NAME = "grouped_majority"


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
	missing = [col for col in required_cols if col not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns for grouped-majority inference: {missing}")


def _safe_key(values: list[object]) -> tuple[object, ...]:
	return tuple("<MISSING>" if pd.isna(value) else value for value in values)


def _majority_summary(values: list[str]) -> dict[str, Any]:
	if not values:
		raise ValueError("Cannot compute majority value from an empty list")

	counts = Counter(values)
	majority_value, majority_count = counts.most_common(1)[0]
	total_count = len(values)

	return {
		"value": majority_value,
		"confidence": majority_count / total_count,
		"support_count": majority_count,
		"group_size": total_count,
		"distribution": dict(counts),
	}


def _get_common_config(config: dict[str, Any]) -> dict[str, Any]:
	group_levels = config.get("group_levels")
	if not group_levels:
		raise ValueError("group_levels must contain at least one grouping level")

	normalized_levels: list[list[str]] = []
	for level in group_levels:
		if not isinstance(level, list) or not level:
			raise ValueError("Each group_levels entry must be a non-empty list of column names")
		normalized_levels.append(level)

	return {
		"target_field": config.get("target_field", config.get("target_col", "target")),
		"target_col": config.get("target_col", "target_input"),
		"true_col": config.get("true_col", "target_true"),
		"mask_col": config.get("mask_col", "is_masked"),
		"group_levels": normalized_levels,
	}


def fit_grouped_majority_reference(
	df: pd.DataFrame,
	config: dict[str, Any],
) -> dict[str, Any]:
	cfg = _get_common_config(config)
	target_col: str = cfg["target_col"]
	group_levels: list[list[str]] = cfg["group_levels"]

	required_cols = sorted({target_col, *(col for level in group_levels for col in level)})
	_validate_columns(df, required_cols)

	reference_df = df[df[target_col].notna()].copy()
	if reference_df.empty:
		raise ValueError("No reference rows with known target values were found")

	level_summaries: list[dict[str, Any]] = []

	for level_cols in group_levels:
		grouped_values: dict[tuple[object, ...], list[str]] = defaultdict(list)

		for _, row in reference_df.iterrows():
			key = _safe_key([row[col] for col in level_cols])
			grouped_values[key].append(str(row[target_col]))

		level_summaries.append(
			{
				"columns": level_cols,
				"groups": {key: _majority_summary(values) for key, values in grouped_values.items()},
			}
		)

	global_summary = _majority_summary(reference_df[target_col].astype(str).tolist())

	return {
		"algorithm": ALGORITHM_NAME,
		"config": cfg,
		"reference_count": len(reference_df),
		"level_summaries": level_summaries,
		"global_summary": global_summary,
	}


def predict_grouped_majority(
	df: pd.DataFrame,
	fitted: dict[str, Any],
) -> pd.DataFrame:
	cfg: dict[str, Any] = fitted["config"]
	true_col: str = cfg["true_col"]
	mask_col: str = cfg["mask_col"]
	target_field: str = cfg["target_field"]
	level_summaries: list[dict[str, Any]] = fitted["level_summaries"]

	required_cols = [true_col, mask_col]
	required_cols.extend(col for level in cfg["group_levels"] for col in level)
	_validate_columns(df, sorted(set(required_cols)))

	result_df = df.copy()
	result_df["target_field"] = target_field
	result_df["predicted_value"] = pd.NA
	result_df["prediction_source"] = "not_applicable"
	result_df["algorithm"] = ALGORITHM_NAME
	result_df["confidence"] = pd.NA
	result_df["matched_group_columns"] = pd.NA
	result_df["matched_group_size"] = pd.NA
	result_df["matched_support_count"] = pd.NA

	masked_indices = result_df.index[result_df[mask_col] == 1].tolist()
	if not masked_indices:
		raise ValueError("No masked rows found for grouped-majority prediction")

	for idx in masked_indices:
		row = result_df.loc[idx]
		selected_summary: dict[str, Any] | None = None
		selected_columns: list[str] | None = None

		for level in level_summaries:
			level_cols: list[str] = level["columns"]
			key = _safe_key([row[col] for col in level_cols])
			if key in level["groups"]:
				selected_summary = level["groups"][key]
				selected_columns = level_cols
				break

		if selected_summary is None:
			selected_summary = fitted["global_summary"]
			source = "global_majority_fallback"
			matched_columns = "<GLOBAL>"
		else:
			source = "group_majority"
			matched_columns = ",".join(selected_columns or [])

		result_df.at[idx, "predicted_value"] = selected_summary["value"]
		result_df.at[idx, "prediction_source"] = source
		result_df.at[idx, "confidence"] = float(selected_summary["confidence"])
		result_df.at[idx, "matched_group_columns"] = matched_columns
		result_df.at[idx, "matched_group_size"] = int(selected_summary["group_size"])
		result_df.at[idx, "matched_support_count"] = int(selected_summary["support_count"])

	return result_df
