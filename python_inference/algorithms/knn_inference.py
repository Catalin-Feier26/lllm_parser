from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.neighbors import KNeighborsClassifier


ALGORITHM_NAME = "knn"


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
	missing = [col for col in required_cols if col not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns for kNN inference: {missing}")


def _prepare_feature_matrix(
	reference_df: pd.DataFrame,
	predict_df: pd.DataFrame,
	feature_cols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
	combined = pd.concat(
		[
			reference_df[feature_cols].assign(__split="ref"),
			predict_df[feature_cols].assign(__split="pred"),
		],
		axis=0,
		ignore_index=True,
	)

	encoded = pd.get_dummies(combined, columns=feature_cols, dummy_na=True, dtype=int)

	reference_encoded = encoded[encoded["__split"] == "ref"].drop(columns="__split").reset_index(drop=True)
	predict_encoded = encoded[encoded["__split"] == "pred"].drop(columns="__split").reset_index(drop=True)

	return reference_encoded, predict_encoded


def _get_config(config: dict[str, Any]) -> dict[str, Any]:
	feature_cols = config.get("feature_cols")
	if not feature_cols:
		raise ValueError("feature_cols must contain at least one feature column")

	weights = config.get("weights", "distance")
	if weights not in {"uniform", "distance"}:
		raise ValueError("weights must be either 'uniform' or 'distance'")

	return {
		"target_field": config.get("target_field", config.get("target_col", "target")),
		"target_col": config.get("target_col", "target_input"),
		"true_col": config.get("true_col", "target_true"),
		"mask_col": config.get("mask_col", "is_masked"),
		"feature_cols": feature_cols,
		"n_neighbors": int(config.get("n_neighbors", 5)),
		"weights": weights,
	}


def fit_knn_reference(
	df: pd.DataFrame,
	config: dict[str, Any],
) -> dict[str, Any]:
	cfg = _get_config(config)
	feature_cols: list[str] = cfg["feature_cols"]
	target_col: str = cfg["target_col"]

	_validate_columns(df, feature_cols + [target_col])

	reference_df = df[df[target_col].notna()].copy()
	if reference_df.empty:
		raise ValueError("No reference rows with known target values were found")

	effective_k = min(cfg["n_neighbors"], len(reference_df))
	if effective_k < 1:
		raise ValueError("At least one reference row is required to fit kNN")

	X_ref, _ = _prepare_feature_matrix(reference_df, reference_df.iloc[0:0], feature_cols)
	y_ref = reference_df[target_col].astype(str).reset_index(drop=True)

	model = KNeighborsClassifier(n_neighbors=effective_k, weights=cfg["weights"])
	model.fit(X_ref, y_ref)

	return {
		"algorithm": ALGORITHM_NAME,
		"config": cfg,
		"reference_count": len(reference_df),
		"effective_k": effective_k,
		"model": model,
	}


def predict_knn(
	df: pd.DataFrame,
	fitted: dict[str, Any],
) -> pd.DataFrame:
	cfg: dict[str, Any] = fitted["config"]
	feature_cols: list[str] = cfg["feature_cols"]
	target_col: str = cfg["target_col"]
	true_col: str = cfg["true_col"]
	mask_col: str = cfg["mask_col"]

	_validate_columns(df, feature_cols + [target_col, true_col, mask_col])

	result_df = df.copy()
	masked_df = result_df[result_df[mask_col] == 1].copy()
	if masked_df.empty:
		raise ValueError("No masked rows found for kNN prediction")

	reference_df = result_df[result_df[target_col].notna()].copy()
	if reference_df.empty:
		raise ValueError("No reference rows with known target values were found")

	X_ref, X_pred = _prepare_feature_matrix(reference_df, masked_df, feature_cols)
	y_ref = reference_df[target_col].astype(str).reset_index(drop=True)

	aligned_k = min(fitted["effective_k"], len(reference_df))
	model = KNeighborsClassifier(n_neighbors=aligned_k, weights=cfg["weights"])
	model.fit(X_ref, y_ref)

	predicted_values = model.predict(X_pred)
	confidences = model.predict_proba(X_pred).max(axis=1)

	result_df["target_field"] = cfg["target_field"]
	result_df["predicted_value"] = pd.NA
	result_df["prediction_source"] = "not_applicable"
	result_df["algorithm"] = ALGORITHM_NAME
	result_df["confidence"] = pd.NA
	result_df["n_neighbors_used"] = pd.NA

	for idx, predicted_value, confidence in zip(masked_df.index, predicted_values, confidences):
		result_df.at[idx, "predicted_value"] = predicted_value
		result_df.at[idx, "prediction_source"] = "nearest_neighbors"
		result_df.at[idx, "confidence"] = float(confidence)
		result_df.at[idx, "n_neighbors_used"] = aligned_k

	return result_df
