from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
	missing = [col for col in required_cols if col not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns for masking: {missing}")


def create_masked_eval_dataset(
	df: pd.DataFrame,
	config: dict[str, Any],
) -> pd.DataFrame:
	"""
	Create a reproducible evaluation dataset for one inference target.

	Required config:
		target_field: canonical field being inferred
		source_col: cleaned source column to mask

	Optional config:
		target_col: working input column, defaults to 'target_input'
		true_col: preserved expected-value column, defaults to 'target_true'
		mask_col: mask-indicator column, defaults to 'is_masked'
		mask_rate: proportion of known rows to hide, defaults to 0.2
		seed: random seed, defaults to 42
	"""
	target_field = config["target_field"]
	source_col = config["source_col"]
	target_col = config.get("target_col", "target_input")
	true_col = config.get("true_col", "target_true")
	mask_col = config.get("mask_col", "is_masked")
	mask_rate = float(config.get("mask_rate", 0.2))
	seed = int(config.get("seed", 42))

	if not 0 < mask_rate < 1:
		raise ValueError("mask_rate must be between 0 and 1")

	_validate_columns(df, [source_col])

	result_df = df.copy()
	result_df["target_field"] = target_field
	result_df[true_col] = result_df[source_col]
	result_df[target_col] = result_df[source_col]
	result_df[mask_col] = 0

	eligible_idx = result_df.index[result_df[source_col].notna()].tolist()
	if not eligible_idx:
		raise ValueError(f"No non-missing rows available for masking: {source_col}")

	rng = np.random.default_rng(seed)
	mask_count = max(1, int(len(eligible_idx) * mask_rate))
	masked_idx = rng.choice(eligible_idx, size=mask_count, replace=False)

	result_df.loc[masked_idx, target_col] = pd.NA
	result_df.loc[masked_idx, mask_col] = 1

	return result_df
