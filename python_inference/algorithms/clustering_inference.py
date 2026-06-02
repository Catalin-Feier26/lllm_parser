from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
from sklearn.cluster import KMeans


ALGORITHM_NAME = "clustering"


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
	missing = [col for col in required_cols if col not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns for clustering inference: {missing}")


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


def _safe_cluster_count(requested_clusters: int, n_rows: int) -> int:
	if n_rows < 2:
		raise ValueError("At least two reference rows are required for clustering")
	return max(2, min(requested_clusters, n_rows))


def _majority_summary(values: list[str]) -> dict[str, Any]:
	counts = Counter(values)
	value, support_count = counts.most_common(1)[0]
	total = sum(counts.values())
	return {
		"value": value,
		"confidence": support_count / total,
		"support_count": support_count,
		"group_size": total,
		"distribution": dict(counts),
	}


def _build_cluster_summaries(cluster_labels: list[int], targets: pd.Series) -> dict[int, dict[str, Any]]:
	cluster_df = pd.DataFrame({"cluster": cluster_labels, "target": targets})
	summaries: dict[int, dict[str, Any]] = {}

	for cluster_id, group in cluster_df.groupby("cluster"):
		summaries[int(cluster_id)] = _majority_summary(group["target"].tolist())

	return summaries


def _get_config(config: dict[str, Any]) -> dict[str, Any]:
	feature_cols = config.get("feature_cols")
	if not feature_cols:
		raise ValueError("feature_cols must contain at least one feature column")

	return {
		"target_field": config.get("target_field", config.get("target_col", "target")),
		"target_col": config.get("target_col", "target_input"),
		"true_col": config.get("true_col", "target_true"),
		"mask_col": config.get("mask_col", "is_masked"),
		"feature_cols": feature_cols,
		"n_clusters": int(config.get("n_clusters", 8)),
		"random_state": int(config.get("random_state", 42)),
		"n_init": int(config.get("n_init", 10)),
	}


def fit_clustering_reference(
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

	effective_clusters = _safe_cluster_count(cfg["n_clusters"], len(reference_df))
	X_ref, _ = _prepare_feature_matrix(reference_df, reference_df.iloc[0:0], feature_cols)
	y_ref = reference_df[target_col].astype(str).reset_index(drop=True)

	model = KMeans(
		n_clusters=effective_clusters,
		random_state=cfg["random_state"],
		n_init=cfg["n_init"],
	)
	cluster_labels = model.fit_predict(X_ref)

	return {
		"algorithm": ALGORITHM_NAME,
		"config": cfg,
		"reference_count": len(reference_df),
		"effective_clusters": effective_clusters,
		"model": model,
		"cluster_summaries": _build_cluster_summaries(cluster_labels.tolist(), y_ref),
		"global_summary": _majority_summary(y_ref.tolist()),
	}


def predict_clustering(
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
		raise ValueError("No masked rows found for clustering prediction")

	reference_df = result_df[result_df[target_col].notna()].copy()
	if reference_df.empty:
		raise ValueError("No reference rows with known target values were found")

	X_ref, X_pred = _prepare_feature_matrix(reference_df, masked_df, feature_cols)
	y_ref = reference_df[target_col].astype(str).reset_index(drop=True)

	aligned_clusters = _safe_cluster_count(fitted["effective_clusters"], len(reference_df))
	model = KMeans(
		n_clusters=aligned_clusters,
		random_state=cfg["random_state"],
		n_init=cfg["n_init"],
	)
	reference_cluster_labels = model.fit_predict(X_ref)
	cluster_summaries = _build_cluster_summaries(reference_cluster_labels.tolist(), y_ref)
	predicted_clusters = model.predict(X_pred)

	result_df["target_field"] = cfg["target_field"]
	result_df["predicted_value"] = pd.NA
	result_df["prediction_source"] = "not_applicable"
	result_df["algorithm"] = ALGORITHM_NAME
	result_df["confidence"] = pd.NA
	result_df["assigned_cluster"] = pd.NA
	result_df["cluster_size"] = pd.NA
	result_df["cluster_support_count"] = pd.NA

	for idx, cluster_id in zip(masked_df.index, predicted_clusters):
		cluster_id = int(cluster_id)
		summary = cluster_summaries.get(cluster_id)

		if summary is None:
			summary = fitted["global_summary"]
			source = "global_majority_fallback"
		else:
			source = "cluster_majority"

		result_df.at[idx, "predicted_value"] = summary["value"]
		result_df.at[idx, "prediction_source"] = source
		result_df.at[idx, "confidence"] = float(summary["confidence"])
		result_df.at[idx, "assigned_cluster"] = cluster_id
		result_df.at[idx, "cluster_size"] = int(summary["group_size"])
		result_df.at[idx, "cluster_support_count"] = int(summary["support_count"])

	return result_df
