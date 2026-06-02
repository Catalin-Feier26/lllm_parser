from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import pandas as pd


SUPPORTED_STRATEGIES = {"majority_then_confidence"}


def _validate_columns(df: pd.DataFrame, required_cols: list[str], algorithm_name: str) -> None:
    missing = [column for column in required_cols if column not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns in predictions for algorithm '{algorithm_name}': {missing}"
        )


def _to_float(value: object, default: float = 0.0) -> float:
    if pd.isna(value):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass
    return value


def _get_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}

    strategy = config.get("strategy", "majority_then_confidence")
    if strategy not in SUPPORTED_STRATEGIES:
        supported = ", ".join(sorted(SUPPORTED_STRATEGIES))
        raise ValueError(f"Unsupported merge strategy '{strategy}'. Supported strategies: {supported}")

    minimum_confidence = float(config.get("minimum_confidence", 0.0))
    if not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError("minimum_confidence must be between 0 and 1")

    return {
        "strategy": strategy,
        "minimum_confidence": minimum_confidence,
        "mask_col": config.get("mask_col", "is_masked"),
        "true_col": config.get("true_col", "target_true"),
        "input_col": config.get("input_col", "target_input"),
        "target_field": config.get("target_field"),
        "record_id_col": config.get("record_id_col"),
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, str]:
    return (-candidate["confidence"], candidate["algorithm"])


def _group_sort_key(group: dict[str, Any]) -> tuple[int, float, float, str]:
    return (
        -group["vote_count"],
        -group["average_confidence"],
        -group["maximum_confidence"],
        str(group["predicted_value"]),
    )


def _select_winner(accepted_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[object, list[dict[str, Any]]] = defaultdict(list)
    for candidate in accepted_candidates:
        grouped[candidate["predicted_value"]].append(candidate)

    group_summaries: list[dict[str, Any]] = []
    for predicted_value, candidates in grouped.items():
        confidences = [candidate["confidence"] for candidate in candidates]
        algorithms = sorted({candidate["algorithm"] for candidate in candidates})

        group_summaries.append(
            {
                "predicted_value": predicted_value,
                "vote_count": len(algorithms),
                "average_confidence": sum(confidences) / len(confidences),
                "maximum_confidence": max(confidences),
                "supporting_algorithms": algorithms,
                "candidates": sorted(candidates, key=_candidate_sort_key),
            }
        )

    group_summaries.sort(key=_group_sort_key)
    winner = group_summaries[0]

    if len(group_summaries) == 1:
        decision_method = "unanimous_vote" if winner["vote_count"] > 1 else "single_candidate"
    else:
        second = group_summaries[1]

        if winner["vote_count"] > second["vote_count"]:
            decision_method = "majority_vote"
        elif winner["vote_count"] == 1:
            decision_method = "highest_confidence_no_majority"
        elif winner["average_confidence"] > second["average_confidence"]:
            decision_method = "average_confidence_tiebreak"
        elif winner["maximum_confidence"] > second["maximum_confidence"]:
            decision_method = "highest_confidence_tiebreak"
        else:
            decision_method = "deterministic_value_tiebreak"

    best_candidate = winner["candidates"][0]

    return {
        "final_value": winner["predicted_value"],
        "final_confidence": float(winner["average_confidence"]),
        "vote_count": int(winner["vote_count"]),
        "decision_method": decision_method,
        "selected_algorithm": best_candidate["algorithm"],
        "supporting_algorithms": winner["supporting_algorithms"],
        "candidate_groups": group_summaries,
    }


def merge_predictions(
    predictions_by_algorithm: dict[str, pd.DataFrame],
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge algorithm predictions for one inference target.

    The runner should call this after every enabled algorithm has predicted the
    same masked rows. Rows are aligned using the original DataFrame index.

    Returns:
        merged_df: one final decision per masked row
        candidates_df: one auditable candidate row per algorithm prediction
    """
    if not predictions_by_algorithm:
        raise ValueError("At least one algorithm prediction DataFrame is required for merging")

    cfg = _get_config(config)
    mask_col: str = cfg["mask_col"]
    true_col: str = cfg["true_col"]
    input_col: str = cfg["input_col"]
    record_id_col: str | None = cfg["record_id_col"]
    minimum_confidence: float = cfg["minimum_confidence"]

    first_algorithm, first_df = next(iter(predictions_by_algorithm.items()))
    required_base_cols = [mask_col, true_col]
    if input_col in first_df.columns:
        required_base_cols.append(input_col)
    if record_id_col:
        required_base_cols.append(record_id_col)
    _validate_columns(first_df, required_base_cols, first_algorithm)

    masked_indices = first_df.index[first_df[mask_col] == 1].tolist()
    if not masked_indices:
        raise ValueError("No masked rows found for merge")

    candidates_by_index: dict[object, list[dict[str, Any]]] = defaultdict(list)
    candidate_rows: list[dict[str, Any]] = []

    for configured_algorithm_name, predictions_df in predictions_by_algorithm.items():
        _validate_columns(
            predictions_df,
            [mask_col, true_col, "predicted_value", "algorithm", "confidence"],
            configured_algorithm_name,
        )

        algorithm_masked_indices = predictions_df.index[predictions_df[mask_col] == 1].tolist()
        if algorithm_masked_indices != masked_indices:
            raise ValueError(
                f"Masked row indices differ for algorithm '{configured_algorithm_name}'. "
                "All merged predictions must originate from the same masked dataset."
            )

        for row_index in masked_indices:
            row = predictions_df.loc[row_index]
            predicted_value = row["predicted_value"]
            confidence = _to_float(row["confidence"])
            raw_algorithm = row["algorithm"]
            algorithm = (
                configured_algorithm_name
                if pd.isna(raw_algorithm) or str(raw_algorithm).strip() == ""
                else str(raw_algorithm)
            )
            is_valid_prediction = not pd.isna(predicted_value)
            passes_threshold = is_valid_prediction and confidence >= minimum_confidence

            candidate = {
                "row_index": _safe_json_value(row_index),
                "target_field": row.get("target_field", cfg["target_field"]),
                "algorithm": algorithm,
                "predicted_value": _safe_json_value(predicted_value),
                "confidence": float(confidence),
                "prediction_source": row.get("prediction_source", "unknown"),
                "passes_threshold": bool(passes_threshold),
            }

            if record_id_col:
                candidate[record_id_col] = row.get(record_id_col)

            candidate_rows.append(candidate)
            candidates_by_index[row_index].append(candidate)

    merged_rows: list[dict[str, Any]] = []

    for row_index in masked_indices:
        base_row = first_df.loc[row_index]
        all_candidates = candidates_by_index[row_index]
        accepted_candidates = [candidate for candidate in all_candidates if candidate["passes_threshold"]]

        merged_row: dict[str, Any] = {
            "row_index": _safe_json_value(row_index),
            "target_field": base_row.get("target_field", cfg["target_field"]),
            true_col: base_row[true_col],
            mask_col: int(base_row[mask_col]),
            "final_value": pd.NA,
            "final_confidence": pd.NA,
            "decision_method": "rejected_no_candidate_above_threshold",
            "selected_algorithm": pd.NA,
            "supporting_algorithms": "[]",
            "vote_count": 0,
            "candidate_count": len(all_candidates),
            "accepted_candidate_count": len(accepted_candidates),
            "minimum_confidence": minimum_confidence,
            "is_accepted": False,
            "candidates_json": json.dumps(all_candidates, ensure_ascii=False),
        }

        if input_col in first_df.columns:
            merged_row[input_col] = base_row[input_col]

        if record_id_col:
            merged_row[record_id_col] = base_row.get(record_id_col)

        if accepted_candidates:
            winner = _select_winner(accepted_candidates)
            merged_row.update(
                {
                    "final_value": winner["final_value"],
                    "final_confidence": winner["final_confidence"],
                    "decision_method": winner["decision_method"],
                    "selected_algorithm": winner["selected_algorithm"],
                    "supporting_algorithms": json.dumps(
                        winner["supporting_algorithms"], ensure_ascii=False
                    ),
                    "vote_count": winner["vote_count"],
                    "is_accepted": True,
                }
            )

        merged_rows.append(merged_row)

    merged_df = pd.DataFrame(merged_rows)
    candidates_df = pd.DataFrame(candidate_rows)
    return merged_df, candidates_df


def compute_merge_metrics(
    merged_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute coverage and classification metrics for merged evaluation rows."""
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

    cfg = _get_config(config)
    true_col: str = cfg["true_col"]

    required_cols = [true_col, "final_value", "is_accepted", "decision_method"]
    missing = [column for column in required_cols if column not in merged_df.columns]
    if missing:
        raise ValueError(f"Missing required columns for merge metrics: {missing}")

    total_rows = int(len(merged_df))
    accepted_df = merged_df[
        merged_df["is_accepted"]
        & merged_df[true_col].notna()
        & merged_df["final_value"].notna()
    ].copy()

    accepted_rows = int(len(accepted_df))
    rejected_rows = total_rows - accepted_rows

    decision_counts = {
        str(key): int(value)
        for key, value in merged_df["decision_method"].value_counts(dropna=False).items()
    }

    metrics: dict[str, Any] = {
        "target_field": cfg["target_field"],
        "strategy": cfg["strategy"],
        "minimum_confidence": cfg["minimum_confidence"],
        "row_count_total": total_rows,
        "row_count_accepted": accepted_rows,
        "row_count_rejected": rejected_rows,
        "coverage": float(accepted_rows / total_rows) if total_rows else 0.0,
        "decision_method_counts": decision_counts,
    }

    if accepted_df.empty:
        metrics.update(
            {
                "accuracy_on_accepted": None,
                "macro_f1_on_accepted": None,
                "weighted_f1_on_accepted": None,
                "average_final_confidence": None,
                "labels": [],
                "classification_report": {},
                "confusion_matrix": [],
            }
        )
        return metrics

    y_true = accepted_df[true_col].astype(str)
    y_pred = accepted_df["final_value"].astype(str)
    confidences = pd.to_numeric(accepted_df["final_confidence"], errors="coerce").dropna()
    labels = sorted(set(y_true.unique()) | set(y_pred.unique()))

    metrics.update(
        {
            "accuracy_on_accepted": float(accuracy_score(y_true, y_pred)),
            "macro_f1_on_accepted": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "weighted_f1_on_accepted": float(
                f1_score(y_true, y_pred, average="weighted", zero_division=0)
            ),
            "average_final_confidence": float(confidences.mean()) if not confidences.empty else None,
            "labels": labels,
            "classification_report": classification_report(
                y_true, y_pred, labels=labels, output_dict=True, zero_division=0
            ),
            "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        }
    )

    return metrics
