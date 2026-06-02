from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
from sklearn.cluster import KMeans


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for clustering inference: {missing}")


def _prepare_feature_matrix(
    reference_df: pd.DataFrame,
    predict_df: pd.DataFrame,
    feature_cols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ref_features = reference_df[feature_cols].copy()
    pred_features = predict_df[feature_cols].copy()

    combined = pd.concat(
        [ref_features.assign(__split="ref"), pred_features.assign(__split="pred")],
        axis=0,
        ignore_index=True,
    )

    combined = pd.get_dummies(
        combined,
        columns=feature_cols,
        dummy_na=True,
        dtype=int,
    )

    ref_encoded = (
        combined[combined["__split"] == "ref"]
        .drop(columns="__split")
        .reset_index(drop=True)
    )
    pred_encoded = (
        combined[combined["__split"] == "pred"]
        .drop(columns="__split")
        .reset_index(drop=True)
    )

    return ref_encoded, pred_encoded


def _majority_value(values: list[str]) -> str:
    if not values:
        raise ValueError("Cannot compute majority value from empty list")
    return Counter(values).most_common(1)[0][0]


def _safe_cluster_count(n_clusters: int, n_rows: int) -> int:
    if n_rows < 2:
        raise ValueError("At least 2 reference rows are required for clustering")
    return max(2, min(n_clusters, n_rows))


def fit_clustering_reference(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "permit_class_input",
    n_clusters: int = 8,
    random_state: int = 42,
) -> dict[str, Any]:
    required_cols = feature_cols + [target_col]
    _validate_columns(df, required_cols)

    reference_df = df[df[target_col].notna()].copy()
    if reference_df.empty:
        raise ValueError("No reference rows with known target values were found")

    effective_clusters = _safe_cluster_count(n_clusters, len(reference_df))

    X_ref, _ = _prepare_feature_matrix(reference_df, reference_df.iloc[0:0], feature_cols)
    y_ref = reference_df[target_col].astype(str).reset_index(drop=True)

    model = KMeans(
        n_clusters=effective_clusters,
        random_state=random_state,
        n_init=10,
    )
    cluster_labels = model.fit_predict(X_ref)

    cluster_majority: dict[int, str] = {}
    cluster_distribution: dict[int, dict[str, int]] = {}

    cluster_df = pd.DataFrame(
        {
            "cluster": cluster_labels,
            "target": y_ref,
        }
    )

    for cluster_id, group in cluster_df.groupby("cluster"):
        values = group["target"].tolist()
        counts = Counter(values)
        cluster_majority[int(cluster_id)] = counts.most_common(1)[0][0]
        cluster_distribution[int(cluster_id)] = dict(counts)

    global_majority = _majority_value(y_ref.tolist())

    return {
        "model": model,
        "feature_cols": feature_cols,
        "target_col": target_col,
        "reference_count": len(reference_df),
        "effective_clusters": effective_clusters,
        "cluster_majority": cluster_majority,
        "cluster_distribution": cluster_distribution,
        "global_majority": global_majority,
        "random_state": random_state,
    }


def predict_clustering(
    df: pd.DataFrame,
    fitted: dict[str, Any],
) -> pd.DataFrame:
    feature_cols: list[str] = fitted["feature_cols"]
    target_col: str = fitted["target_col"]
    model: KMeans = fitted["model"]
    cluster_majority: dict[int, str] = fitted["cluster_majority"]
    cluster_distribution: dict[int, dict[str, int]] = fitted["cluster_distribution"]
    global_majority: str = fitted["global_majority"]

    required_cols = feature_cols + ["permit_class_true", "is_masked", target_col]
    _validate_columns(df, required_cols)

    result_df = df.copy()

    masked_df = result_df[result_df["is_masked"] == 1].copy()
    if masked_df.empty:
        raise ValueError("No masked rows found for clustering prediction")

    reference_df = result_df[result_df[target_col].notna()].copy()
    if reference_df.empty:
        raise ValueError("No reference rows with known target values were found")

    X_ref, X_pred = _prepare_feature_matrix(reference_df, masked_df, feature_cols)
    y_ref = reference_df[target_col].astype(str).reset_index(drop=True)

    # Re-fit for guaranteed feature alignment
    aligned_clusters = _safe_cluster_count(fitted["effective_clusters"], len(reference_df))
    model = KMeans(
        n_clusters=aligned_clusters,
        random_state=fitted["random_state"],
        n_init=10,
    )
    ref_cluster_labels = model.fit_predict(X_ref)

    # Rebuild cluster-majority mapping on aligned fit
    aligned_cluster_majority: dict[int, str] = {}
    aligned_cluster_distribution: dict[int, dict[str, int]] = {}

    cluster_df = pd.DataFrame(
        {
            "cluster": ref_cluster_labels,
            "target": y_ref,
        }
    )

    for cluster_id, group in cluster_df.groupby("cluster"):
        counts = Counter(group["target"].tolist())
        aligned_cluster_majority[int(cluster_id)] = counts.most_common(1)[0][0]
        aligned_cluster_distribution[int(cluster_id)] = dict(counts)

    pred_clusters = model.predict(X_pred)

    result_df["predicted_permit_class"] = pd.NA
    result_df["prediction_source"] = "not_applicable"
    result_df["algorithm"] = "clustering"
    result_df["confidence"] = pd.NA
    result_df["assigned_cluster"] = pd.NA

    masked_indices = masked_df.index.tolist()

    for idx, cluster_id in zip(masked_indices, pred_clusters):
        cluster_id = int(cluster_id)
        distribution = aligned_cluster_distribution.get(cluster_id, {})
        if not distribution:
            result_df.at[idx, "predicted_permit_class"] = global_majority
            result_df.at[idx, "prediction_source"] = "global_majority_fallback"
            result_df.at[idx, "confidence"] = 0.0
            result_df.at[idx, "assigned_cluster"] = cluster_id
            continue

        predicted = aligned_cluster_majority[cluster_id]
        total = sum(distribution.values())
        confidence = distribution[predicted] / total if total > 0 else 0.0

        result_df.at[idx, "predicted_permit_class"] = predicted
        result_df.at[idx, "prediction_source"] = "cluster_majority"
        result_df.at[idx, "confidence"] = float(confidence)
        result_df.at[idx, "assigned_cluster"] = cluster_id

    return result_df