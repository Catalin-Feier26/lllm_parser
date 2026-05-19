from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for association-rule mining: {missing}")


def _make_item(col_name: str, value: object) -> str:
    if pd.isna(value):
        return f"{col_name}=<MISSING>"
    return f"{col_name}={value}"


def _target_item(target_col: str, value: object) -> str:
    return f"{target_col}={value}"


def _build_reference_transactions(
    reference_df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
) -> list[list[str]]:
    transactions: list[list[str]] = []

    for _, row in reference_df.iterrows():
        items = [_make_item(col, row[col]) for col in feature_cols]
        items.append(_target_item(target_col, row[target_col]))
        transactions.append(items)

    return transactions


def _make_row_feature_items(row: pd.Series, feature_cols: list[str]) -> set[str]:
    return {_make_item(col, row[col]) for col in feature_cols}


def _extract_target_value(target_item: str, target_col: str) -> str:
    prefix = f"{target_col}="
    if not target_item.startswith(prefix):
        raise ValueError(f"Consequent item does not match target column: {target_item}")
    return target_item[len(prefix):]


def _build_global_majority(reference_df: pd.DataFrame, target_col: str) -> str:
    counts = Counter(reference_df[target_col].astype(str).tolist())
    return counts.most_common(1)[0][0]


def fit_association_rules_reference(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "permit_class_input",
    min_support: float = 0.01,
    min_confidence: float = 0.5,
    min_lift: float = 1.0,
) -> dict[str, Any]:
    required_cols = feature_cols + [target_col]
    _validate_columns(df, required_cols)

    reference_df = df[df[target_col].notna()].copy()
    if reference_df.empty:
        raise ValueError("No reference rows with known target values were found")

    transactions = _build_reference_transactions(reference_df, feature_cols, target_col)

    all_items = sorted({item for tx in transactions for item in tx})

    one_hot = pd.DataFrame(
        [
            {item: (item in tx) for item in all_items}
            for tx in transactions
        ],
        columns=all_items,
        dtype=bool,
    )

    frequent_itemsets = apriori(one_hot, min_support=min_support, use_colnames=True)
    if frequent_itemsets.empty:
        raise ValueError("No frequent itemsets found. Try lowering min_support.")

    rules = association_rules(
        frequent_itemsets,
        metric="confidence",
        min_threshold=min_confidence,
    )

    if rules.empty:
        raise ValueError("No association rules found. Try lowering thresholds.")

    # Keep only rules whose consequent is exactly one target item
    def is_target_consequent(consequents: frozenset[str]) -> bool:
        if len(consequents) != 1:
            return False
        item = next(iter(consequents))
        return item.startswith(f"{target_col}=")

    rules = rules[rules["consequents"].apply(is_target_consequent)].copy()
    if rules.empty:
        raise ValueError("No target-consequent rules found.")

    rules = rules[rules["lift"] >= min_lift].copy()
    if rules.empty:
        raise ValueError("No target-consequent rules passed the lift threshold.")

    rules["predicted_target"] = rules["consequents"].apply(
        lambda s: _extract_target_value(next(iter(s)), target_col)
    )
    rules["antecedent_len"] = rules["antecedents"].apply(len)

    rules = rules.sort_values(
        by=["confidence", "lift", "support", "antecedent_len"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    global_majority = _build_global_majority(reference_df, target_col)

    return {
        "rules_df": rules,
        "feature_cols": feature_cols,
        "target_col": target_col,
        "reference_count": len(reference_df),
        "global_majority": global_majority,
        "min_support": min_support,
        "min_confidence": min_confidence,
        "min_lift": min_lift,
    }


def predict_association_rules(
    df: pd.DataFrame,
    fitted: dict[str, Any],
) -> pd.DataFrame:
    feature_cols: list[str] = fitted["feature_cols"]
    target_col: str = fitted["target_col"]
    rules_df: pd.DataFrame = fitted["rules_df"]
    global_majority: str = fitted["global_majority"]

    required_cols = feature_cols + ["permit_class_true", "is_masked", target_col]
    _validate_columns(df, required_cols)

    result_df = df.copy()

    result_df["predicted_permit_class"] = pd.NA
    result_df["prediction_source"] = "not_applicable"
    result_df["algorithm"] = "association_rules"
    result_df["confidence"] = pd.NA
    result_df["matched_rule_support"] = pd.NA
    result_df["matched_rule_lift"] = pd.NA
    result_df["matched_rule_antecedent_len"] = pd.NA

    masked_df = result_df[result_df["is_masked"] == 1].copy()
    if masked_df.empty:
        raise ValueError("No masked rows found for rule-based prediction")

    for idx, row in masked_df.iterrows():
        row_items = _make_row_feature_items(row, feature_cols)

        matched_rules = rules_df[
            rules_df["antecedents"].apply(lambda ants: set(ants).issubset(row_items))
        ].copy()

        if matched_rules.empty:
            result_df.at[idx, "predicted_permit_class"] = global_majority
            result_df.at[idx, "prediction_source"] = "global_majority_fallback"
            result_df.at[idx, "confidence"] = 0.0
            continue

        # Aggregate best score per candidate class
        candidate_scores: dict[str, dict[str, float]] = {}

        for _, rule in matched_rules.iterrows():
            pred = rule["predicted_target"]
            score = float(rule["confidence"]) * float(rule["lift"])

            current = candidate_scores.get(pred)
            if current is None or score > current["score"]:
                candidate_scores[pred] = {
                    "score": score,
                    "confidence": float(rule["confidence"]),
                    "support": float(rule["support"]),
                    "lift": float(rule["lift"]),
                    "antecedent_len": int(rule["antecedent_len"]),
                }

        best_pred, best_info = max(
            candidate_scores.items(),
            key=lambda x: (
                x[1]["score"],
                x[1]["confidence"],
                x[1]["lift"],
                x[1]["support"],
                x[1]["antecedent_len"],
            ),
        )

        result_df.at[idx, "predicted_permit_class"] = best_pred
        result_df.at[idx, "prediction_source"] = "matched_rules"
        result_df.at[idx, "confidence"] = best_info["confidence"]
        result_df.at[idx, "matched_rule_support"] = best_info["support"]
        result_df.at[idx, "matched_rule_lift"] = best_info["lift"]
        result_df.at[idx, "matched_rule_antecedent_len"] = best_info["antecedent_len"]

    return result_df


def export_top_rules(
    fitted: dict[str, Any],
    top_n: int = 50,
) -> pd.DataFrame:
    rules_df: pd.DataFrame = fitted["rules_df"].copy()

    export_df = rules_df.head(top_n).copy()
    export_df["antecedents"] = export_df["antecedents"].apply(
        lambda s: ", ".join(sorted(list(s)))
    )
    export_df["consequents"] = export_df["consequents"].apply(
        lambda s: ", ".join(sorted(list(s)))
    )

    return export_df[
        [
            "antecedents",
            "consequents",
            "support",
            "confidence",
            "lift",
            "antecedent_len",
            "predicted_target",
        ]
    ].reset_index(drop=True)