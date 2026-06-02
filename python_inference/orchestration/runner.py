from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from algorithms.registry import get_algorithm_spec
from evaluation.metrics import compute_classification_metrics, write_metrics_json
from evaluation.plots import save_confusion_matrix_plot
from orchestration.output_writer import (
	make_algorithm_dir,
	make_run_dir,
	make_target_dir,
	write_dataframe,
	write_json,
)
from preprocessing.cleaner import clean_multiple_target_columns, keep_columns, normalize_strings
from preprocessing.feature_engineering import apply_feature_engineering
from preprocessing.masking import create_masked_eval_dataset


class InferenceRunner:
	"""Run configured preprocessing, masking, algorithms, metrics, and exports."""

	def __init__(self, config: dict[str, Any]) -> None:
		self.config = deepcopy(config)

	def run(
		self,
		input_override: str | Path | None = None,
		only_targets: set[str] | None = None,
		only_algorithms: set[str] | None = None,
	) -> dict[str, Any]:
		input_path = self._resolve_input_path(input_override)
		run_dir = make_run_dir(self.config, input_path)

		prepared_df = self._preprocess_dataset(input_path)
		prepared_dir = run_dir / "prepared"
		write_dataframe(prepared_df, prepared_dir / "prepared.csv")

		summary: dict[str, Any] = {
			"source": self.config["source"]["name"],
			"input_file": str(input_path),
			"prepared_row_count": int(len(prepared_df)),
			"targets": {},
		}

		for target_field, target_cfg in self.config["inference_targets"].items():
			if not target_cfg.get("enabled", True):
				continue
			if only_targets and target_field not in only_targets:
				continue

			target_result = self._run_target(
				prepared_df=prepared_df,
				run_dir=run_dir,
				target_field=target_field,
				target_cfg=target_cfg,
				only_algorithms=only_algorithms,
			)
			summary["targets"][target_field] = target_result

		write_json(summary, run_dir / "run_summary.json")
		return summary

	def _resolve_input_path(self, input_override: str | Path | None) -> Path:
		raw_path = input_override or self.config["source"].get("input_csv")
		if not raw_path:
			raise ValueError("Provide --input or define source.input_csv in the YAML config")

		input_path = Path(raw_path)
		if not input_path.exists():
			raise FileNotFoundError(f"Input CSV not found: {input_path}")
		return input_path

	def _preprocess_dataset(self, input_path: Path) -> pd.DataFrame:
		preprocessing = self.config["preprocessing"]
		df = pd.read_csv(input_path, dtype=str)
		df = keep_columns(df, preprocessing["keep_columns"])

		if preprocessing.get("normalize_strings", True):
			df = normalize_strings(df)

		df = clean_multiple_target_columns(df, self.config["inference_targets"])
		df = apply_feature_engineering(df, preprocessing.get("engineered_features"))
		return df

	def _run_target(
		self,
		prepared_df: pd.DataFrame,
		run_dir: Path,
		target_field: str,
		target_cfg: dict[str, Any],
		only_algorithms: set[str] | None,
	) -> dict[str, Any]:
		target_dir = make_target_dir(run_dir, target_field)

		masking_cfg = {
			"target_field": target_field,
			**target_cfg.get("masking", {}),
		}
		if "source_col" not in masking_cfg:
			cleaning_cfg = target_cfg.get("cleaning", {})
			masking_cfg["source_col"] = cleaning_cfg.get("clean_col", f"{target_field}_clean")

		masked_df = create_masked_eval_dataset(prepared_df, masking_cfg)
		write_dataframe(masked_df, target_dir / "masked_eval.csv")

		target_summary: dict[str, Any] = {
			"masked_row_count": int(masked_df[masking_cfg.get("mask_col", "is_masked")].sum()),
			"algorithms": {},
		}

		for algorithm_name, algorithm_cfg in target_cfg["algorithms"].items():
			if not algorithm_cfg.get("enabled", True):
				continue
			if only_algorithms and algorithm_name not in only_algorithms:
				continue

			target_summary["algorithms"][algorithm_name] = self._run_algorithm(
				masked_df=masked_df,
				target_dir=target_dir,
				target_field=target_field,
				target_cfg=target_cfg,
				masking_cfg=masking_cfg,
				algorithm_name=algorithm_name,
				algorithm_cfg=algorithm_cfg,
			)

		return target_summary

	def _run_algorithm(
		self,
		masked_df: pd.DataFrame,
		target_dir: Path,
		target_field: str,
		target_cfg: dict[str, Any],
		masking_cfg: dict[str, Any],
		algorithm_name: str,
		algorithm_cfg: dict[str, Any],
	) -> dict[str, Any]:
		spec = get_algorithm_spec(algorithm_name)
		algorithm_params = {
			"target_field": target_field,
			"target_col": masking_cfg.get("target_col", "target_input"),
			"true_col": masking_cfg.get("true_col", "target_true"),
			"mask_col": masking_cfg.get("mask_col", "is_masked"),
			"feature_cols": target_cfg["feature_cols"],
			**{
				key: value
				for key, value in algorithm_cfg.items()
				if key not in {"enabled", "output_folder", "top_n_rules"}
			},
		}

		fitted = spec["fit"](masked_df, algorithm_params)
		predictions_df = spec["predict"](masked_df, fitted)

		metrics_cfg = {
			"true_col": algorithm_params["true_col"],
			"pred_col": "predicted_value",
			"mask_col": algorithm_params["mask_col"],
			"target_field": target_field,
			"algorithm": algorithm_name,
		}
		metrics = compute_classification_metrics(predictions_df, metrics_cfg)
		metrics["algorithm_parameters"] = fitted.get("config", algorithm_params)
		metrics["reference_count"] = int(fitted.get("reference_count", 0))

		folder_name = algorithm_cfg.get("output_folder", spec["default_output_folder"])
		algorithm_dir = make_algorithm_dir(target_dir, folder_name)
		write_dataframe(predictions_df, algorithm_dir / "predictions.csv")
		write_metrics_json(metrics, algorithm_dir / "metrics.json")

		plot_cfg = deepcopy(self.config.get("plots", {}).get("confusion_matrix", {}))
		plot_cfg.setdefault("title", f"{algorithm_name} — {target_field} confusion matrix")
		save_confusion_matrix_plot(
			confusion_matrix=metrics["confusion_matrix"],
			labels=metrics["labels"],
			output_path=algorithm_dir / "confusion_matrix.png",
			config=plot_cfg,
		)

		exporter = spec.get("export_top_rules")
		if exporter is not None:
			top_n = int(algorithm_cfg.get("top_n_rules", 50))
			write_dataframe(exporter(fitted, top_n), algorithm_dir / "top_rules.csv")

		print(
			f"[{target_field}] {algorithm_name}: "
			f"accuracy={metrics['accuracy']:.4f}, "
			f"macro_f1={metrics['macro_f1']:.4f}, "
			f"rows={metrics['row_count_evaluated']}"
		)

		return {
			"output_dir": str(algorithm_dir),
			"accuracy": metrics["accuracy"],
			"macro_f1": metrics["macro_f1"],
			"row_count_evaluated": metrics["row_count_evaluated"],
		}
