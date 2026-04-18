from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score


def compute_classification_metrics(
    predictions_df: pd.DataFrame,
    true_col: str = "permit_class_true",
    pred_col: str = "predicted_permit_class",
    masked_flag_col: str = "is_masked",
    ) -> dict:
    required_cols = [true_col, pred_col, masked_flag_col]
    missing = [c for c in required_cols if c not in predictions_df.columns]
    if missing:
        raise ValueError(f"Missing required columns for metrics: {missing}")

    eval_df = predictions_df[
        (predictions_df[masked_flag_col] == 1)
        & predictions_df[true_col].notna()
        & predictions_df[pred_col].notna()
    ].copy()

    if eval_df.empty:
        raise ValueError("No valid masked prediction rows found for evaluation")

    y_true = eval_df[true_col].astype(str)
    y_pred = eval_df[pred_col].astype(str)

    labels = sorted(set(y_true.unique()) | set(y_pred.unique()))

    accuracy = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, average="macro")

    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        output_dict=True,
        zero_division=0,
    )

    cm = confusion_matrix(y_true, y_pred, labels=labels)

    return {
        "row_count_evaluated": int(len(eval_df)),
        "accuracy": float(accuracy),
        "macro_f1": float(macro_f1),
        "labels": labels,
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
    }


def write_metrics_json(metrics: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")