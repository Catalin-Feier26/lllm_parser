from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from types import ModuleType

import pandas as pd

from algorithms.knn_inference import fit_knn_reference, predict_knn
from algorithms.clustering_inference import fit_clustering_reference, predict_clustering

from baselines.grouped_majority import (
	fit_grouped_majority_reference,
	predict_grouped_majority,
)

from algorithms.association_rules import (
	export_top_rules,
	fit_association_rules_reference,
	predict_association_rules,
)

from evaluation.metrics import compute_classification_metrics, write_metrics_json
from evaluation.plots import save_confusion_matrix_plot
from preprocessing.cleaner import clean_target_column, keep_columns, normalize_strings
from preprocessing.feature_engineering import apply_feature_engineering
from preprocessing.masking import create_masked_eval_dataset


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument("--input", required=True, help="Path to input CSV")
	parser.add_argument("--source", required=True, help="Source config name, e.g. naples")
	parser.add_argument("--mask-rate", type=float, default=0.2)
	parser.add_argument("--seed", type=int, default=42)

	parser.add_argument(
		"--run-baseline",
		action="store_true",
		help="Run grouped-majority baseline after preprocessing",
	)
	parser.add_argument(
		"--run-knn",
		action="store_true",
		help="Run kNN inference after preprocessing",
	)
	parser.add_argument(
		"--knn-k",
		type=int,
		default=5,
		help="Number of neighbors for kNN",
	)
	parser.add_argument(
		"--knn-weights",
		choices=["uniform", "distance"],
		default="distance",
		help="Weighting strategy for kNN",
	)
	parser.add_argument(
		"--run-rules",
		action="store_true",
		help="Run association-rule mining after preprocessing",
	)
	parser.add_argument(
		"--rules-min-support",
		type=float,
		default=0.01,
		help="Minimum support for association rules",
	)
	parser.add_argument(
		"--rules-min-confidence",
		type=float,
		default=0.5,
		help="Minimum confidence for association rules",
	)
	parser.add_argument(
		"--rules-min-lift",
		type=float,
		default=1.0,
		help="Minimum lift for association rules",
	)
	parser.add_argument(
		"--run-clustering",
		action="store_true",
		help="Run clustering inference after preprocessing",
	)
	parser.add_argument(
		"--cluster-k",
		type=int,
		default=8,
		help="Number of clusters for KMeans",
	)

	return parser.parse_args()


def load_source_config(source: str) -> ModuleType:
	module_name = f"config.{source}"
	try:
		return importlib.import_module(module_name)
	except ModuleNotFoundError as exc:
		raise ValueError(f"Unknown source config: {source}") from exc


def make_base_output_dir(source: str) -> Path:
	output_dir = Path("python_inference") / "output" / source
	output_dir.mkdir(parents=True, exist_ok=True)
	return output_dir

def make_algorithm_output_dir(source: str, algorithm: str) -> Path:
	output_dir = make_base_output_dir(source) / algorithm
	output_dir.mkdir(parents=True, exist_ok=True)
	return output_dir


def make_preprocessing_output_paths(input_path: Path, source: str) -> tuple[Path, Path]:
	output_dir = make_base_output_dir(source)
	base_name = input_path.stem
	prepared_path = output_dir / f"{base_name}_prepared.csv"
	masked_path = output_dir / f"{base_name}_masked_eval.csv"
	return prepared_path, masked_path


def make_baseline_output_paths(input_path: Path, source: str) -> tuple[Path, Path]:
	output_dir = make_algorithm_output_dir(source, "baseline")
	base_name = input_path.stem
	predictions_path = output_dir / f"{base_name}_grouped_majority_predictions.csv"
	metrics_path = output_dir / f"{base_name}_grouped_majority_metrics.json"
	return predictions_path, metrics_path


def make_baseline_plot_path(input_path: Path, source: str) -> Path:
	output_dir = make_algorithm_output_dir(source, "baseline")
	base_name = input_path.stem
	return output_dir / f"{base_name}_grouped_majority_confusion_matrix.png"


def make_knn_output_paths(input_path: Path, source: str) -> tuple[Path, Path]:
	output_dir = make_algorithm_output_dir(source, "knn")
	base_name = input_path.stem
	predictions_path = output_dir / f"{base_name}_knn_predictions.csv"
	metrics_path = output_dir / f"{base_name}_knn_metrics.json"
	return predictions_path, metrics_path


def make_knn_plot_path(input_path: Path, source: str) -> Path:
	output_dir = make_algorithm_output_dir(source, "knn")
	base_name = input_path.stem
	return output_dir / f"{base_name}_knn_confusion_matrix.png"


def make_rules_output_paths(input_path: Path, source: str) -> tuple[Path, Path, Path]:
	output_dir = make_algorithm_output_dir(source, "mining")
	base_name = input_path.stem
	predictions_path = output_dir / f"{base_name}_association_rules_predictions.csv"
	metrics_path = output_dir / f"{base_name}_association_rules_metrics.json"
	rules_path = output_dir / f"{base_name}_top_rules.csv"
	return predictions_path, metrics_path, rules_path


def make_rules_plot_path(input_path: Path, source: str) -> Path:
	output_dir = make_algorithm_output_dir(source, "mining")
	base_name = input_path.stem
	return output_dir / f"{base_name}_association_rules_confusion_matrix.png"


def print_summary(df: pd.DataFrame, masked_df: pd.DataFrame, target_clean_col: str) -> None:
	print("Prepared dataset rows:", len(df))
	print("Prepared dataset columns:")
	for col in df.columns:
		print("-", col)

	print(f"\nTarget distribution ({target_clean_col}):")
	print(df[target_clean_col].value_counts(dropna=False).to_string())

	print("\nMasked evaluation summary:")
	print("Masked rows:", int(masked_df["is_masked"].sum()))
	print("Unmasked rows:", int((masked_df["is_masked"] == 0).sum()))

def make_clustering_output_paths(input_path: Path, source: str) -> tuple[Path, Path]:
	output_dir = make_algorithm_output_dir(source, "clustering")
	base_name = input_path.stem
	predictions_path = output_dir / f"{base_name}_clustering_predictions.csv"
	metrics_path = output_dir / f"{base_name}_clustering_metrics.json"
	return predictions_path, metrics_path


def make_clustering_plot_path(input_path: Path, source: str) -> Path:
	output_dir = make_algorithm_output_dir(source, "clustering")
	base_name = input_path.stem
	return output_dir / f"{base_name}_clustering_confusion_matrix.png"


def preprocess_dataset(input_path: Path, cfg: ModuleType) -> pd.DataFrame:
	df = pd.read_csv(input_path, dtype=str)

	df = keep_columns(df, cfg.KEEP_COLUMNS)
	df = normalize_strings(df)
	df = clean_target_column(
		df,
		target_col=cfg.TARGET_FIELD,
		rare_class_map=cfg.RARE_CLASS_MAP,
	)
	df = apply_feature_engineering(df)

	return df


def run_grouped_majority_baseline(
	masked_df: pd.DataFrame,
	input_path: Path,
	source: str,
	cfg: ModuleType,
) -> None:
	fitted = fit_grouped_majority_reference(masked_df, target_col=cfg.TARGET_INPUT_COLUMN)
	predictions_df = predict_grouped_majority(masked_df, fitted)

	metrics = compute_classification_metrics(
		predictions_df,
		true_col=cfg.TARGET_TRUE_COLUMN,
		pred_col="predicted_permit_class",
		masked_flag_col="is_masked",
	)

	predictions_path, metrics_path = make_baseline_output_paths(input_path, source)
	predictions_df.to_csv(predictions_path, index=False)
	write_metrics_json(metrics, metrics_path)

	plot_path = make_baseline_plot_path(input_path, source)
	save_confusion_matrix_plot(
		confusion_matrix=metrics["confusion_matrix"],
		labels=metrics["labels"],
		output_path=plot_path,
		title="Grouped Majority Confusion Matrix",
	)

	print("\nBaseline output written:")
	print(f"- Predictions: {predictions_path}")
	print(f"- Metrics: {metrics_path}")
	print(f"- Confusion matrix plot: {plot_path}")
	print("\nBaseline metrics summary:")
	print(f"- Accuracy: {metrics['accuracy']:.4f}")
	print(f"- Macro F1: {metrics['macro_f1']:.4f}")
	print(f"- Evaluated rows: {metrics['row_count_evaluated']}")


def run_knn_inference(
	masked_df: pd.DataFrame,
	input_path: Path,
	source: str,
	cfg: ModuleType,
	knn_k: int,
	knn_weights: str,
) -> None:
	fitted = fit_knn_reference(
		masked_df,
		feature_cols=cfg.FEATURE_COLUMNS,
		target_col=cfg.TARGET_INPUT_COLUMN,
		n_neighbors=knn_k,
		weights=knn_weights,
	)
	predictions_df = predict_knn(masked_df, fitted)

	metrics = compute_classification_metrics(
		predictions_df,
		true_col=cfg.TARGET_TRUE_COLUMN,
		pred_col="predicted_permit_class",
		masked_flag_col="is_masked",
	)

	metrics["knn_parameters"] = {
		"n_neighbors": fitted["effective_k"],
		"weights": knn_weights,
		"reference_count": fitted["reference_count"],
		"feature_columns": cfg.FEATURE_COLUMNS,
	}

	predictions_path, metrics_path = make_knn_output_paths(input_path, source)
	predictions_df.to_csv(predictions_path, index=False)
	write_metrics_json(metrics, metrics_path)

	plot_path = make_knn_plot_path(input_path, source)
	save_confusion_matrix_plot(
		confusion_matrix=metrics["confusion_matrix"],
		labels=metrics["labels"],
		output_path=plot_path,
		title="kNN Confusion Matrix",
	)

	print("\nkNN output written:")
	print(f"- Predictions: {predictions_path}")
	print(f"- Metrics: {metrics_path}")
	print(f"- Confusion matrix plot: {plot_path}")
	print("\nkNN metrics summary:")
	print(f"- Accuracy: {metrics['accuracy']:.4f}")
	print(f"- Macro F1: {metrics['macro_f1']:.4f}")
	print(f"- Evaluated rows: {metrics['row_count_evaluated']}")
	print(f"- Effective k: {fitted['effective_k']}")
	print(f"- Weights: {knn_weights}")


def run_association_rules_inference(
	masked_df: pd.DataFrame,
	input_path: Path,
	source: str,
	cfg: ModuleType,
	min_support: float,
	min_confidence: float,
	min_lift: float,
) -> None:
	fitted = fit_association_rules_reference(
		masked_df,
		feature_cols=cfg.FEATURE_COLUMNS,
		target_col=cfg.TARGET_INPUT_COLUMN,
		min_support=min_support,
		min_confidence=min_confidence,
		min_lift=min_lift,
	)

	predictions_df = predict_association_rules(masked_df, fitted)
	metrics = compute_classification_metrics(
		predictions_df,
		true_col=cfg.TARGET_TRUE_COLUMN,
		pred_col="predicted_permit_class",
		masked_flag_col="is_masked",
	)

	metrics["association_rules_parameters"] = {
		"min_support": min_support,
		"min_confidence": min_confidence,
		"min_lift": min_lift,
		"reference_count": fitted["reference_count"],
		"feature_columns": cfg.FEATURE_COLUMNS,
		"rule_count": int(len(fitted["rules_df"])),
	}

	predictions_path, metrics_path, rules_path = make_rules_output_paths(input_path, source)
	predictions_df.to_csv(predictions_path, index=False)
	write_metrics_json(metrics, metrics_path)

	top_rules_df = export_top_rules(fitted, top_n=50)
	top_rules_df.to_csv(rules_path, index=False)

	plot_path = make_rules_plot_path(input_path, source)
	save_confusion_matrix_plot(
		confusion_matrix=metrics["confusion_matrix"],
		labels=metrics["labels"],
		output_path=plot_path,
		title="Association Rules Confusion Matrix",
	)

	print("\nAssociation-rules output written:")
	print(f"- Predictions: {predictions_path}")
	print(f"- Metrics: {metrics_path}")
	print(f"- Top rules: {rules_path}")
	print(f"- Confusion matrix plot: {plot_path}")
	print("\nAssociation-rules metrics summary:")
	print(f"- Accuracy: {metrics['accuracy']:.4f}")
	print(f"- Macro F1: {metrics['macro_f1']:.4f}")
	print(f"- Evaluated rows: {metrics['row_count_evaluated']}")
	print(f"- Rule count: {len(fitted['rules_df'])}")

def run_clustering_inference(
	masked_df: pd.DataFrame,
	input_path: Path,
	source: str,
	cfg: ModuleType,
	cluster_k: int,
	seed: int,
) -> None:
	fitted = fit_clustering_reference(
		masked_df,
		feature_cols=cfg.FEATURE_COLUMNS,
		target_col=cfg.TARGET_INPUT_COLUMN,
		n_clusters=cluster_k,
		random_state=seed,
	)
	predictions_df = predict_clustering(masked_df, fitted)

	metrics = compute_classification_metrics(
		predictions_df,
		true_col=cfg.TARGET_TRUE_COLUMN,
		pred_col="predicted_permit_class",
		masked_flag_col="is_masked",
	)

	metrics["clustering_parameters"] = {
		"n_clusters": fitted["effective_clusters"],
		"reference_count": fitted["reference_count"],
		"feature_columns": cfg.FEATURE_COLUMNS,
	}

	predictions_path, metrics_path = make_clustering_output_paths(input_path, source)
	predictions_df.to_csv(predictions_path, index=False)
	write_metrics_json(metrics, metrics_path)

	plot_path = make_clustering_plot_path(input_path, source)
	save_confusion_matrix_plot(
		confusion_matrix=metrics["confusion_matrix"],
		labels=metrics["labels"],
		output_path=plot_path,
		title="Clustering Confusion Matrix",
	)

	print("\nClustering output written:")
	print(f"- Predictions: {predictions_path}")
	print(f"- Metrics: {metrics_path}")
	print(f"- Confusion matrix plot: {plot_path}")
	print("\nClustering metrics summary:")
	print(f"- Accuracy: {metrics['accuracy']:.4f}")
	print(f"- Macro F1: {metrics['macro_f1']:.4f}")
	print(f"- Evaluated rows: {metrics['row_count_evaluated']}")
	print(f"- Effective clusters: {fitted['effective_clusters']}")

def main() -> None:
	args = parse_args()

	input_path = Path(args.input)
	if not input_path.exists():
		raise FileNotFoundError(f"Input CSV not found: {input_path}")

	cfg = load_source_config(args.source)

	df = preprocess_dataset(input_path, cfg)

	masked_df = create_masked_eval_dataset(
		df,
		target_clean_col=cfg.TARGET_CLEAN_COLUMN,
		mask_rate=args.mask_rate,
		seed=args.seed,
	)

	prepared_path, masked_path = make_preprocessing_output_paths(input_path, args.source)
	df.to_csv(prepared_path, index=False)
	masked_df.to_csv(masked_path, index=False)

	print(f"Prepared dataset written to: {prepared_path}")
	print(f"Masked evaluation dataset written to: {masked_path}")
	print()
	print_summary(df, masked_df, cfg.TARGET_CLEAN_COLUMN)

	if args.run_baseline:
		run_grouped_majority_baseline(masked_df, input_path, args.source, cfg)

	if args.run_knn:
		run_knn_inference(
			masked_df,
			input_path,
			args.source,
			cfg,
			knn_k=args.knn_k,
			knn_weights=args.knn_weights,
		)
	
	if args.run_rules:
		run_association_rules_inference(
			masked_df,
			input_path,
			args.source,
			cfg,
			min_support=args.rules_min_support,
			min_confidence=args.rules_min_confidence,
			min_lift=args.rules_min_lift,
		)

	if args.run_clustering:
		run_clustering_inference(
			masked_df,
			input_path,
			args.source,
			cfg,
			cluster_k=args.cluster_k,
			seed=args.seed,
		)


if __name__ == "__main__":
	main()