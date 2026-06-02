from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules


ALGORITHM_NAME = "association_rules"


def _validate_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
	missing = [col for col in required_cols if col not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns for association-rule inference: {missing}")


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


def _majority_summary(reference_df: pd.DataFrame, target_col: str) -> dict[str, Any]:
	counts = Counter(reference_df[target_col].astype(str).tolist())
	value, support_count = counts.most_common(1)[0]
	total = sum(counts.values())
	return {
		"value": value,
		"confidence": support_count / total,
		"support_count": support_count,
		"group_size": total,
	}


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
		"min_support": float(config.get("min_support", 0.01)),
		"min_confidence": float(config.get("min_confidence", 0.50)),
		"min_lift": float(config.get("min_lift", 1.00)),
		"use_global_fallback": bool(config.get("use_global_fallback", True)),
	}


def fit_association_rules_reference(
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

	transactions = _build_reference_transactions(reference_df, feature_cols, target_col)
	all_items = sorted({item for tx in transactions for item in tx})

	one_hot = pd.DataFrame(
		[{item: item in tx for item in all_items} for tx in transactions],
		columns=all_items,
		dtype=bool,
	)

	frequent_itemsets = apriori(one_hot, min_support=cfg["min_support"], use_colnames=True)
	if frequent_itemsets.empty:
		raise ValueError("No frequent itemsets found. Try lowering min_support.")

	rules = association_rules(
		frequent_itemsets,
		metric="confidence",
		min_threshold=cfg["min_confidence"],
	)
	if rules.empty:
		raise ValueError("No association rules found. Try lowering the thresholds.")

	def is_target_consequent(consequents: frozenset[str]) -> bool:
		if len(consequents) != 1:
			return False
		return next(iter(consequents)).startswith(f"{target_col}=")

	rules = rules[rules["consequents"].apply(is_target_consequent)].copy()
	rules = rules[rules["lift"] >= cfg["min_lift"]].copy()
	if rules.empty:
		raise ValueError("No target-consequent rules passed the configured thresholds.")

	rules["predicted_target"] = rules["consequents"].apply(
		lambda consequents: _extract_target_value(next(iter(consequents)), target_col)
	)
	rules["antecedent_len"] = rules["antecedents"].apply(len)
	rules = rules.sort_values(
		by=["confidence", "lift", "support", "antecedent_len"],
		ascending=[False, False, False, False],
	).reset_index(drop=True)

	return {
		"algorithm": ALGORITHM_NAME,
		"config": cfg,
		"reference_count": len(reference_df),
		"rules_df": rules,
		"global_summary": _majority_summary(reference_df, target_col),
	}


def predict_association_rules(
	df: pd.DataFrame,
	fitted: dict[str, Any],
) -> pd.DataFrame:
	cfg: dict[str, Any] = fitted["config"]
	feature_cols: list[str] = cfg["feature_cols"]
	target_col: str = cfg["target_col"]
	true_col: str = cfg["true_col"]
	mask_col: str = cfg["mask_col"]
	rules_df: pd.DataFrame = fitted["rules_df"]

	_validate_columns(df, feature_cols + [target_col, true_col, mask_col])

	result_df = df.copy()
	result_df["target_field"] = cfg["target_field"]
	result_df["predicted_value"] = pd.NA
	result_df["prediction_source"] = "not_applicable"
	result_df["algorithm"] = ALGORITHM_NAME
	result_df["confidence"] = pd.NA
	result_df["matched_rule_support"] = pd.NA
	result_df["matched_rule_lift"] = pd.NA
	result_df["matched_rule_antecedent_len"] = pd.NA

	masked_indices = result_df.index[result_df[mask_col] == 1].tolist()
	if not masked_indices:
		raise ValueError("No masked rows found for association-rule prediction")

	for idx in masked_indices:
		row_items = _make_row_feature_items(result_df.loc[idx], feature_cols)
		matched_rules = rules_df[
			rules_df["antecedents"].apply(lambda antecedents: set(antecedents).issubset(row_items))
		]

		if matched_rules.empty:
			if cfg["use_global_fallback"]:
				summary = fitted["global_summary"]
				result_df.at[idx, "predicted_value"] = summary["value"]
				result_df.at[idx, "confidence"] = float(summary["confidence"])
				result_df.at[idx, "prediction_source"] = "global_majority_fallback"
			else:
				result_df.at[idx, "prediction_source"] = "no_matching_rule"
				result_df.at[idx, "confidence"] = 0.0
			continue

		candidate_scores: dict[str, dict[str, float]] = {}

		for _, rule in matched_rules.iterrows():
			predicted_value = str(rule["predicted_target"])
			score = float(rule["confidence"]) * float(rule["lift"])
			current = candidate_scores.get(predicted_value)

			if current is None or score > current["score"]:
				candidate_scores[predicted_value] = {
					"score": score,
					"confidence": float(rule["confidence"]),
					"support": float(rule["support"]),
					"lift": float(rule["lift"]),
					"antecedent_len": int(rule["antecedent_len"]),
				}

		best_value, best_info = max(
			candidate_scores.items(),
			key=lambda item: (
				item[1]["score"],
				item[1]["confidence"],
				item[1]["lift"],
				item[1]["support"],
				item[1]["antecedent_len"],
			),
		)

		result_df.at[idx, "predicted_value"] = best_value
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
	rules_df: pd.DataFrame = fitted["rules_df"].copy().head(top_n)
	rules_df["antecedents"] = rules_df["antecedents"].apply(lambda values: ", ".join(sorted(values)))
	rules_df["consequents"] = rules_df["consequents"].apply(lambda values: ", ".join(sorted(values)))

	return rules_df[
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
