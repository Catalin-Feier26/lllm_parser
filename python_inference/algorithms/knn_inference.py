from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.neighbors import KNeighborsClassifier

FEATURE_COLUMNS = [
    "building_type",
    "permit_type",
    "const_type",
    "valuation_bucket",
    "total_units_group",
    "total_sf_nonzero",
]

def validate_columns (df: pd.DataFrame, required_cols: list[str]) -> None:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for KNN: {missing}")

def _prepare_feature_matrix(
    reference_df: pd.DataFrame,
    predict_df: pd.DataFrame,
    feature_cols: list[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame]:

    ref_features = reference_df[feature_cols].copy()
    pred_features = predict_df[feature_cols].copy()

    combined = pd.concat(
        [ref_features.assign(__split="ref"), pred_features.assign(__split="pred")],
        axis = 0,
        ignore_index=True,
    )

    combined = pd.get_dummies(
        combined,
        columns = feature_cols,
        dummy_na = True,
        dtype = int,
    )

    ref_encoded = combined[combined["__split"] == "ref"].drop(columns="__split").reset_index(drop=True)
    pred_encoded = combined[combined["__split"] == "pred"].drop(columns="__split").reset_index(drop=True)

    return ref_encoded, pred_encoded

def fit_knn_reference(
    df: pd.DataFrame,
    target_col: str = "permit_class_input",
    feature_cols: list[str] | None = None,
    n_neighbors: int = 5,
    weights: str = "distance",
    ) -> dict[str, Any]:

    if feature_cols is None:
        feature_cols = FEATURE_COLUMNS

    required_cols = feature_cols + [target_col]
    validate_columns(df, required_cols)

    reference_df = df[df[target_col].notna()].copy()
    if reference_df.empty:
        raise ValueError("No reference rows with known target values were found")

    effective_k = min(n_neighbors, len(reference_df))
    if effective_k < 1:
        raise ValueError("At least one reference row is required to fit KNN")

    X_ref, _ = _prepare_feature_matrix(reference_df, reference_df.iloc[0:0], feature_cols)
    y_ref = reference_df[target_col].astype(str).reset_index(drop=True)

    model = KNeighborsClassifier(
        n_neighbors = effective_k,
        weights = weights,
    )

    model.fit(X_ref, y_ref)

    return {
        "model": model,
        "feature_cols": feature_cols,
        "target_col": target_col,
        "reference_count": len(reference_df),
        "effective_k": effective_k,
    }

def predict_knn(
    df: pd.DataFrame,
    fitted: dict[str, Any],
    ) -> pd.DataFrame:

    feature_cols: list[str] = fitted["feature_cols"]
    target_col: str = fitted["target_col"]
    model: KNeighborsClassifier = fitted["model"]

    required_cols = feature_cols + ["permit_class_true", "is_masked", target_col]
    validate_columns(df, required_cols)

    result_df = df.copy()

    masked_df = result_df[result_df["is_masked"] == 1].copy()

    if masked_df.empty:
        raise ValueError("No masked rows found for prediction")

    reference_df = result_df[result_df[target_col].notna()].copy()
    if reference_df.empty:
        raise ValueError("No reference rows with known target values were found")

    X_ref, X_pred = _prepare_feature_matrix(reference_df, masked_df, feature_cols)

    y_ref = reference_df[target_col].astype(str).reset_index(drop=True)

    aligned_k = min(fitted["effective_k"], len(reference_df))
    model = KNeighborsClassifier(
        n_neighbors=aligned_k,
        weights=model.weights,
    )

    model.fit(X_ref, y_ref)

    predicted = model.predict(X_pred)

    probabilities = None
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(X_pred)
        class_labels = list(model.classes_)
        max_confidences = probabilities.max(axis=1)
        predicted_class_index = probabilities.argmax(axis=1)
        predicted_from_proba = [class_labels[i] for i in predicted_class_index]
    else:
        max_confidences = [None] * len(predicted)
        predicted_from_proba = predicted

    result_df["predicted_permit_class"] = pd.NA
    result_df["prediction_source"] = "not_applicable"
    result_df["algorithm"] = "knn"
    result_df["confidence"] = pd.NA

    masked_indices = masked_df.index.tolist()

    for idx, pred_value, conf_value in zip(masked_indices, predicted_from_proba, max_confidences):
        result_df.at[idx, "predicted_permit_class"] = pred_value
        result_df.at[idx, "prediction_source"] = "knn"
        result_df.at[idx, "confidence"] = float(conf_value) if conf_value is not None else pd.NA

    return result_df