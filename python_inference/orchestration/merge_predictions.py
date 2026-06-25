from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import pandas as pd


SUPPORTED_STRATEGIES = {"majority_then_confidence"}

STATUS_ACCEPTED = "Accepted"
STATUS_REJECTED = "Rejected"
STATUS_UNRESOLVED = "Unresolved"
STATUS_REQUIRES_REVIEW = "Requires Review"
STATUS_CONFLICT = "Conflict"


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
        "auto_accept_single_candidate": bool(config.get("auto_accept_single_candidate", True)),
        "require_majority": bool(config.get("require_majority", False)),
        "validation_record_status_col": config.get("validation_record_status_col", "validation_record_status"),
        "review_validation_statuses": {
            str(status).strip().lower()
            for status in config.get("review_validation_statuses", ["suspicious", "requires_review"])
        },
        "reject_validation_statuses": {
            str(status).strip().lower()
            for status in config.get("reject_validation_statuses", [])
        },
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
    has_conflict = False

    if len(group_summaries) == 1:
        decision_method = "unanimous_vote" if winner["vote_count"] > 1 else "single_candidate"
    else:
        second = group_summaries[1]
        if winner["vote_count"] > second["vote_count"]:
            decision_method = "majority_vote"
        elif winner["average_confidence"] > second["average_confidence"]:
            decision_method = "average_confidence_tiebreak"
        elif winner["maximum_confidence"] > second["maximum_confidence"]:
            decision_method = "highest_confidence_tiebreak"
        elif winner["vote_count"] == 1:
            decision_method = "unresolved_conflict"
            has_conflict = True
        else:
            decision_method = "unresolved_conflict"
            has_conflict = True

    best_candidate = winner["candidates"][0]
    return {
        "final_value": winner["predicted_value"],
        "final_confidence": float(winner["average_confidence"]),
        "vote_count": int(winner["vote_count"]),
        "decision_method": decision_method,
        "has_conflict": has_conflict,
        "candidate_value_count": len(group_summaries),
        "selected_algorithm": best_candidate["algorithm"],
        "supporting_algorithms": winner["supporting_algorithms"],
    }


def _status_counts(values: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in values.value_counts(dropna=False).items()}


def merge_predictions(
    predictions_by_algorithm: dict[str, pd.DataFrame],
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge candidate predictions for masked or genuinely missing rows."""
    cfg = _get_config(config)
    if not predictions_by_algorithm:
        raise ValueError("No algorithm predictions were supplied for merging")

    mask_col = cfg["mask_col"]
    true_col = cfg["true_col"]
    input_col = cfg["input_col"]
    record_id_col = cfg["record_id_col"]
    minimum_confidence = cfg["minimum_confidence"]
    auto_accept_single_candidate = cfg["auto_accept_single_candidate"]
    require_majority = cfg["require_majority"]
    validation_record_status_col = cfg["validation_record_status_col"]
    review_validation_statuses = cfg["review_validation_statuses"]
    reject_validation_statuses = cfg["reject_validation_statuses"]

    first_algorithm, first_df = next(iter(predictions_by_algorithm.items()))
    required_columns = [mask_col, true_col, "predicted_value", "confidence", "algorithm"]
    _validate_columns(first_df, required_columns, first_algorithm)

    masked_indices = first_df.index[first_df[mask_col] == 1].tolist()
    candidates_by_index: dict[object, list[dict[str, Any]]] = defaultdict(list)
    candidate_rows: list[dict[str, Any]] = []

    for configured_algorithm_name, predictions_df in predictions_by_algorithm.items():
        _validate_columns(predictions_df, required_columns, configured_algorithm_name)
        current_masked_indices = predictions_df.index[predictions_df[mask_col] == 1].tolist()
        if current_masked_indices != masked_indices:
            raise ValueError("All merged predictions must originate from the same inference dataset.")

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
            if not is_valid_prediction:
                candidate_status = STATUS_REJECTED
                rejection_reason = "no_candidate_generated"
            elif not passes_threshold:
                candidate_status = STATUS_REJECTED
                rejection_reason = "below_confidence_threshold"
            else:
                candidate_status = STATUS_ACCEPTED
                rejection_reason = None

            candidate = {
                "row_index": _safe_json_value(row_index),
                "target_field": row.get("target_field", cfg["target_field"]),
                "algorithm": algorithm,
                "predicted_value": _safe_json_value(predicted_value),
                "confidence": float(confidence),
                "prediction_source": row.get("prediction_source", "unknown"),
                "passes_threshold": bool(passes_threshold),
                "candidate_status": candidate_status,
                "rejection_reason": rejection_reason,
                "validation_record_status": row.get(validation_record_status_col)
                if validation_record_status_col in row.index
                else None,
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
        generated_candidates = [
            candidate
            for candidate in all_candidates
            if candidate["predicted_value"] is not None
        ]

        merged_row: dict[str, Any] = {
            "row_index": _safe_json_value(row_index),
            "target_field": base_row.get("target_field", cfg["target_field"]),
            true_col: base_row[true_col],
            mask_col: int(base_row[mask_col]),
            "final_value": pd.NA,
            "final_confidence": pd.NA,
            "decision_status": STATUS_UNRESOLVED if not generated_candidates else STATUS_REJECTED,
            "decision_method": "no_candidate_generated" if not generated_candidates else "rejected_no_candidate_above_threshold",
            "selected_algorithm": pd.NA,
            "supporting_algorithms": "[]",
            "vote_count": 0,
            "candidate_count": len(all_candidates),
            "generated_candidate_count": len(generated_candidates),
            "accepted_candidate_count": len(accepted_candidates),
            "minimum_confidence": minimum_confidence,
            "validation_record_status": base_row.get(validation_record_status_col)
            if validation_record_status_col in base_row.index
            else None,
            "is_accepted": False,
            "candidates_json": json.dumps(all_candidates, ensure_ascii=False),
        }
        if input_col in first_df.columns:
            merged_row[input_col] = base_row[input_col]
        if record_id_col:
            merged_row[record_id_col] = base_row.get(record_id_col)

        if accepted_candidates:
            winner = _select_winner(accepted_candidates)
            validation_status = str(merged_row.get("validation_record_status") or "").strip().lower()
            validation_rejected = validation_status in reject_validation_statuses
            validation_requires_review = validation_status in review_validation_statuses
            should_accept = (
                not winner["has_conflict"]
                and not validation_rejected
                and not validation_requires_review
                and (
                    winner["decision_method"] in {"unanimous_vote", "majority_vote"}
                    or (
                        auto_accept_single_candidate
                        and not require_majority
                        and winner["candidate_value_count"] == 1
                        and winner["decision_method"] == "single_candidate"
                    )
                )
            )
            if winner["has_conflict"]:
                decision_status = STATUS_CONFLICT
                final_value = pd.NA
                final_confidence = pd.NA
                is_accepted = False
            elif validation_rejected:
                decision_status = STATUS_REJECTED
                final_value = pd.NA
                final_confidence = winner["final_confidence"]
                is_accepted = False
                winner["decision_method"] = "rejected_validation_status"
            elif validation_requires_review:
                decision_status = STATUS_REQUIRES_REVIEW
                final_value = pd.NA
                final_confidence = winner["final_confidence"]
                is_accepted = False
                winner["decision_method"] = "requires_review_validation_status"
            elif should_accept:
                decision_status = STATUS_ACCEPTED
                final_value = winner["final_value"]
                final_confidence = winner["final_confidence"]
                is_accepted = True
            else:
                decision_status = STATUS_REQUIRES_REVIEW
                final_value = pd.NA
                final_confidence = winner["final_confidence"]
                is_accepted = False

            merged_row.update(
                {
                    "final_value": final_value,
                    "final_confidence": final_confidence,
                    "decision_status": decision_status,
                    "decision_method": winner["decision_method"],
                    "selected_algorithm": winner["selected_algorithm"],
                    "supporting_algorithms": json.dumps(winner["supporting_algorithms"]),
                    "vote_count": winner["vote_count"],
                    "is_accepted": is_accepted,
                }
            )
        merged_rows.append(merged_row)

    return pd.DataFrame(merged_rows), pd.DataFrame(candidate_rows)


def _classification_metrics_for_accepted(
    accepted_df: pd.DataFrame,
    true_col: str,
) -> tuple[float | None, float | None, list[object], list[list[int]]]:
    if accepted_df.empty:
        return None, None, [], []

    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

    y_true = accepted_df[true_col].astype(str)
    y_pred = accepted_df["final_value"].astype(str)
    labels = sorted(set(y_true) | set(y_pred))
    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    return (
        float(accuracy_score(y_true, y_pred)),
        float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        labels,
        matrix.tolist(),
    )


def compute_merge_metrics(
    merged_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute evaluation metrics for merged predictions with known true values."""
    cfg = _get_config(config)
    true_col = cfg["true_col"]
    accepted_df = merged_df[
        (merged_df["decision_status"] == STATUS_ACCEPTED)
        & merged_df[true_col].notna()
        & merged_df["final_value"].notna()
    ].copy()

    accuracy, macro_f1, labels, matrix = _classification_metrics_for_accepted(accepted_df, true_col)
    total_rows = int(len(merged_df))
    accepted_rows = int((merged_df["decision_status"] == STATUS_ACCEPTED).sum())
    rejected_rows = int((merged_df["decision_status"] == STATUS_REJECTED).sum())

    return {
        "target_field": cfg["target_field"],
        "strategy": cfg["strategy"],
        "minimum_confidence": cfg["minimum_confidence"],
        "row_count_total": total_rows,
        "row_count_accepted": accepted_rows,
        "row_count_rejected": rejected_rows,
        "row_count_requires_review": int((merged_df["decision_status"] == STATUS_REQUIRES_REVIEW).sum()),
        "row_count_conflict": int((merged_df["decision_status"] == STATUS_CONFLICT).sum()),
        "row_count_unresolved": int((merged_df["decision_status"] == STATUS_UNRESOLVED).sum()),
        "coverage": float(accepted_rows / total_rows) if total_rows else 0.0,
        "accuracy_on_accepted": accuracy,
        "macro_f1_on_accepted": macro_f1,
        "labels": labels,
        "confusion_matrix": matrix,
        "decision_method_counts": {
            str(key): int(value)
            for key, value in merged_df["decision_method"].value_counts(dropna=False).items()
        },
        "decision_status_counts": _status_counts(merged_df["decision_status"]),
    }


def compute_production_merge_summary(
    merged_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute coverage and confidence summaries when no true values exist."""
    cfg = _get_config(config)
    accepted_df = merged_df[
        (merged_df["decision_status"] == STATUS_ACCEPTED) & merged_df["final_value"].notna()
    ].copy()

    total_rows = int(len(merged_df))
    accepted_rows = int((merged_df["decision_status"] == STATUS_ACCEPTED).sum())
    rejected_rows = int((merged_df["decision_status"] == STATUS_REJECTED).sum())
    confidence_values = pd.to_numeric(accepted_df["final_confidence"], errors="coerce").dropna()

    return {
        "target_field": cfg["target_field"],
        "strategy": cfg["strategy"],
        "minimum_confidence": cfg["minimum_confidence"],
        "row_count_total": total_rows,
        "row_count_accepted": accepted_rows,
        "row_count_rejected": rejected_rows,
        "row_count_requires_review": int((merged_df["decision_status"] == STATUS_REQUIRES_REVIEW).sum()),
        "row_count_conflict": int((merged_df["decision_status"] == STATUS_CONFLICT).sum()),
        "row_count_unresolved": int((merged_df["decision_status"] == STATUS_UNRESOLVED).sum()),
        "coverage": float(accepted_rows / total_rows) if total_rows else 0.0,
        "average_final_confidence": (
            float(confidence_values.mean()) if not confidence_values.empty else None
        ),
        "decision_method_counts": {
            str(key): int(value)
            for key, value in merged_df["decision_method"].value_counts(dropna=False).items()
        },
        "decision_status_counts": _status_counts(merged_df["decision_status"]),
    }
