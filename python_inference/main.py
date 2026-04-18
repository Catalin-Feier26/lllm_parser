from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from algorithms.knn_inference import fit_knn_reference, predict_knn
from baselines.grouped_majority import (
	fit_grouped_majority_reference,
	predict_grouped_majority,
)
from config.naples import KEEP_COLUMNS, RARE_CLASS_MAP, TARGET_FIELD
from evaluation.metrics import compute_classification_metrics, write_metrics_json
from evaluation.plots import save_confusion_matrix_plot
from preprocessing.cleaner import clean_target_column, keep_columns, normalize_strings
from preprocessing.feature_engineering import apply_feature_engineering
from preprocessing.masking import create_masked_eval_dataset


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument("--input", required=True, help="Path to input CSV")
	parser.add_argument("--source", required=True, choices=["naples"])
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

	return parser.parse_args()


def make_base_output_dir(source: str) -> Path:
	output_dir = Path("python_inference") / "output" / source
	output_dir.mkdir(parents=True, exist_ok=True)
	return output_dir


def make_preprocessing_output_paths(input_path: Path, source: str) -> tuple[Path, Path]:
	output_dir = make_base_output_dir(source)
	base_name = input_path.stem
	prepared_path = output_dir / f"{base_name}_prepared.csv"
	masked_path = output_dir / f"{base_name}_masked_eval.csv"
	return prepared_path, masked_path


def make_baseline_output_paths(input_path: Path, source: str) -> tuple[Path, Path]:
	output_dir = make_base_output_dir(source)
	base_name = input_path.stem
	predictions_path = output_dir / f"{base_name}_grouped_majority_predictions.csv"
	metrics_path = output_dir / f"{base_name}_grouped_majority_metrics.json"
	return predictions_path, metrics_path

def make_baseline_plot_path(input_path: Path, source: str) -> Path:
	output_dir = make_base_output_dir(source)
	base_name = input_path.stem
	return output_dir / f"{base_name}_grouped_majority_confusion_matrix.png"


def make_knn_plot_path(input_path: Path, source: str) -> Path:
	output_dir = make_base_output_dir(source)
	base_name = input_path.stem
	return output_dir / f"{base_name}_knn_confusion_matrix.png"


def make_knn_output_paths(input_path: Path, source: str) -> tuple[Path, Path]:
	output_dir = make_base_output_dir(source)
	base_name = input_path.stem
	predictions_path = output_dir / f"{base_name}_knn_predictions.csv"
	metrics_path = output_dir / f"{base_name}_knn_metrics.json"
	return predictions_path, metrics_path


def print_summary(df: pd.DataFrame, masked_df: pd.DataFrame) -> None:
	print("Prepared dataset rows:", len(df))
	print("Prepared dataset columns:")
	for col in df.columns:
		print("-", col)

	print("\nTarget distribution (permit_class_clean):")
	print(df["permit_class_clean"].value_counts(dropna=False).to_string())

	print("\nMasked evaluation summary:")
	print("Masked rows:", int(masked_df["is_masked"].sum()))
	print("Unmasked rows:", int((masked_df["is_masked"] == 0).sum()))


def preprocess_dataset(input_path: Path) -> pd.DataFrame:
	df = pd.read_csv(input_path, dtype=str)

	df = keep_columns(df, KEEP_COLUMNS)
	df = normalize_strings(df)
	df = clean_target_column(
		df,
		target_col=TARGET_FIELD,
		rare_class_map=RARE_CLASS_MAP,
	)
	df = apply_feature_engineering(df)

	return df


def run_grouped_majority_baseline(
	masked_df: pd.DataFrame,
	input_path: Path,
	source: str,
) -> None:
	fitted = fit_grouped_majority_reference(masked_df, target_col="permit_class_input")
	predictions_df = predict_grouped_majority(masked_df, fitted)

	metrics = compute_classification_metrics(
		predictions_df,
		true_col="permit_class_true",
		pred_col="predicted_permit_class",
		masked_flag_col="is_masked",
	)

	predictions_path, metrics_path = make_baseline_output_paths(input_path, source)

	predictions_df.to_csv(predictions_path, index=False)
	write_metrics_json(metrics, metrics_path)

	print("\nBaseline output written:")
	print(f"- Predictions: {predictions_path}")
	print(f"- Metrics: {metrics_path}")
	print("\nBaseline metrics summary:")
	print(f"- Accuracy: {metrics['accuracy']:.4f}")
	print(f"- Macro F1: {metrics['macro_f1']:.4f}")
	print(f"- Evaluated rows: {metrics['row_count_evaluated']}")

	plot_path = make_baseline_plot_path(input_path, source)
	save_confusion_matrix_plot(
		confusion_matrix=metrics["confusion_matrix"],
		labels=metrics["labels"],
		output_path=plot_path,
		title="Grouped Majority Confusion Matrix",
	)
	print(f"- Confusion matrix plot: {plot_path}")


def run_knn_inference(
	masked_df: pd.DataFrame,
	input_path: Path,
	source: str,
	knn_k: int,
	knn_weights: str,
) -> None:
	fitted = fit_knn_reference(
		masked_df,
		target_col="permit_class_input",
		n_neighbors=knn_k,
		weights=knn_weights,
	)
	predictions_df = predict_knn(masked_df, fitted)

	metrics = compute_classification_metrics(
		predictions_df,
		true_col="permit_class_true",
		pred_col="predicted_permit_class",
		masked_flag_col="is_masked",
	)

	metrics["knn_parameters"] = {
		"n_neighbors": fitted["effective_k"],
		"weights": knn_weights,
		"reference_count": fitted["reference_count"],
	}

	predictions_path, metrics_path = make_knn_output_paths(input_path, source)

	predictions_df.to_csv(predictions_path, index=False)
	write_metrics_json(metrics, metrics_path)

	print("\nkNN output written:")
	print(f"- Predictions: {predictions_path}")
	print(f"- Metrics: {metrics_path}")
	print("\nkNN metrics summary:")
	print(f"- Accuracy: {metrics['accuracy']:.4f}")
	print(f"- Macro F1: {metrics['macro_f1']:.4f}")
	print(f"- Evaluated rows: {metrics['row_count_evaluated']}")
	print(f"- Effective k: {fitted['effective_k']}")
	print(f"- Weights: {knn_weights}")

	plot_path = make_knn_plot_path(input_path, source)
	save_confusion_matrix_plot(
		confusion_matrix=metrics["confusion_matrix"],
		labels=metrics["labels"],
		output_path=plot_path,
		title="kNN Confusion Matrix",
	)
	print(f"- Confusion matrix plot: {plot_path}")


def main() -> None:
	args = parse_args()

	input_path = Path(args.input)
	if not input_path.exists():
		raise FileNotFoundError(f"Input CSV not found: {input_path}")

	df = preprocess_dataset(input_path)

	masked_df = create_masked_eval_dataset(
		df,
		target_clean_col="permit_class_clean",
		mask_rate=args.mask_rate,
		seed=args.seed,
	)

	prepared_path, masked_path = make_preprocessing_output_paths(input_path, args.source)

	df.to_csv(prepared_path, index=False)
	masked_df.to_csv(masked_path, index=False)

	print(f"Prepared dataset written to: {prepared_path}")
	print(f"Masked evaluation dataset written to: {masked_path}")
	print()
	print_summary(df, masked_df)

	if args.run_baseline:
		run_grouped_majority_baseline(masked_df, input_path, args.source)

	if args.run_knn:
		run_knn_inference(
			masked_df,
			input_path,
			args.source,
			knn_k=args.knn_k,
			knn_weights=args.knn_weights,
		)


if __name__ == "__main__":
	main()