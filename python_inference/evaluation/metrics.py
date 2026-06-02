from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
	missing = [c for c in required_cols if c not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns for metrics: {missing}")


def compute_classification_metrics(
	predictions_df: pd.DataFrame,
	config: dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""Compute classification metrics for masked inference predictions.

	Expected configurable columns:
	- true_col: original value kept for evaluation
	- pred_col: algorithm prediction
	- mask_col: flag indicating which rows were deliberately masked

	The defaults match the generalized inference pipeline.
	"""
	config = config or {}

	true_col = config.get("true_col", "target_true")
	pred_col = config.get("pred_col", "predicted_value")
	mask_col = config.get("mask_col", "is_masked")
	target_field = config.get("target_field")
	algorithm = config.get("algorithm")

	_validate_columns(predictions_df, [true_col, pred_col, mask_col])

	eval_df = predictions_df[
		(predictions_df[mask_col] == 1)
		& predictions_df[true_col].notna()
		& predictions_df[pred_col].notna()
	].copy()

	if eval_df.empty:
		raise ValueError("No valid masked prediction rows found for evaluation")

	y_true = eval_df[true_col].astype(str)
	y_pred = eval_df[pred_col].astype(str)

	labels = sorted(set(y_true.unique()) | set(y_pred.unique()))

	accuracy = accuracy_score(y_true, y_pred)
	macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
	weighted_f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)

	report = classification_report(
		y_true,
		y_pred,
		labels=labels,
		output_dict=True,
		zero_division=0,
	)

	cm = confusion_matrix(y_true, y_pred, labels=labels)

	metrics: dict[str, Any] = {
		"row_count_evaluated": int(len(eval_df)),
		"accuracy": float(accuracy),
		"macro_f1": float(macro_f1),
		"weighted_f1": float(weighted_f1),
		"labels": labels,
		"classification_report": report,
		"confusion_matrix": cm.tolist(),
	}

	if target_field is not None:
		metrics["target_field"] = target_field

	if algorithm is not None:
		metrics["algorithm"] = algorithm

	if "confidence" in eval_df.columns:
		confidence_values = pd.to_numeric(eval_df["confidence"], errors="coerce").dropna()
		if not confidence_values.empty:
			metrics["average_confidence"] = float(confidence_values.mean())
			metrics["minimum_confidence"] = float(confidence_values.min())
			metrics["maximum_confidence"] = float(confidence_values.max())

	return metrics


def write_metrics_json(metrics: dict[str, Any], output_path: Path) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	output_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
