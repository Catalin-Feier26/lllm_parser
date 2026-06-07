from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from algorithms.registry import get_algorithm_spec
from data_loading.loader import load_dataset
from data_loading.loader_types import LoadedDataset
from evaluation.metrics import compute_classification_metrics, write_metrics_json
from evaluation.plots import save_confusion_matrix_plot
from orchestration.merge_predictions import (
    compute_merge_metrics,
    compute_production_merge_summary,
    merge_predictions,
)
from orchestration.output_writer import (
    make_algorithm_dir,
    make_run_dir,
    make_target_dir,
    write_dataframe,
    write_json,
)
from persistence.mongo_output_writer import MongoOutputWriter
from preprocessing.cleaner import clean_multiple_target_columns, keep_columns, normalize_strings
from preprocessing.feature_engineering import apply_feature_engineering
from preprocessing.masking import create_masked_eval_dataset, create_missing_value_dataset


class InferenceRunner:
    """Run configured preprocessing, inference algorithms, metrics, and exports."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = deepcopy(config)

    def run(
        self,
        input_override: str | Path | None = None,
        only_targets: set[str] | None = None,
        only_algorithms: set[str] | None = None,
        parser_run_id_override: str | None = None,
        mode_override: str | None = None,
    ) -> dict[str, Any]:
        loaded_dataset = load_dataset(
            self.config,
            input_override=input_override,
            parser_run_id_override=parser_run_id_override,
        )
        run_dir = make_run_dir(self.config, loaded_dataset.input_name)

        prepared_df = self._preprocess_dataset(loaded_dataset)
        write_dataframe(prepared_df, run_dir / "prepared" / "prepared.csv")

        configured_mode = str(self.config.get("inference", {}).get("mode", "evaluation")).lower()
        mode = str(mode_override or configured_mode).lower()
        if mode not in {"evaluation", "production"}:
            raise ValueError("Inference mode must be 'evaluation' or 'production'")

        enabled_targets = self._enabled_targets(only_targets)
        enabled_algorithms = self._enabled_algorithms(enabled_targets, only_algorithms)
        summary: dict[str, Any] = {
            "source": self.config["source"]["name"],
            "input_source": loaded_dataset.input_description,
            "parser_run_id": loaded_dataset.parser_run_id,
            "mode": mode,
            "prepared_row_count": int(len(prepared_df)),
            "targets": {},
        }

        with MongoOutputWriter(self.config) as mongo_writer:
            inference_run_id = mongo_writer.create_inference_run(
                parser_run_id=loaded_dataset.parser_run_id,
                prepared_row_count=len(prepared_df),
                targets=enabled_targets,
                algorithms=enabled_algorithms,
                input_source=loaded_dataset.input_description,
                output_dir=str(run_dir),
                mode=mode,
            )
            summary["inference_run_id"] = inference_run_id

            try:
                if mode == "production":
                    summary["final_permits_cloned"] = mongo_writer.clone_raw_permits_to_final(
                        inference_run_id=inference_run_id,
                        parser_run_id=loaded_dataset.parser_run_id,
                    )

                for target_field in enabled_targets:
                    target_cfg = self.config["inference_targets"][target_field]
                    summary["targets"][target_field] = self._run_target(
                        prepared_df=prepared_df,
                        run_dir=run_dir,
                        target_field=target_field,
                        target_cfg=target_cfg,
                        only_algorithms=only_algorithms,
                        mongo_writer=mongo_writer,
                        inference_run_id=inference_run_id,
                        parser_run_id=loaded_dataset.parser_run_id,
                        mode=mode,
                    )

                write_json(summary, run_dir / "run_summary.json")
                mongo_writer.complete_inference_run(inference_run_id=inference_run_id, summary=summary)
            except Exception as exc:
                mongo_writer.fail_inference_run(inference_run_id=inference_run_id, error=exc)
                raise

        return summary

    def _enabled_targets(self, only_targets: set[str] | None) -> list[str]:
        return [
            target_field
            for target_field, target_cfg in self.config["inference_targets"].items()
            if target_cfg.get("enabled", True) and (not only_targets or target_field in only_targets)
        ]

    def _enabled_algorithms(self, enabled_targets: list[str], only_algorithms: set[str] | None) -> list[str]:
        algorithms: set[str] = set()
        for target_field in enabled_targets:
            for algorithm_name, algorithm_cfg in self.config["inference_targets"][target_field]["algorithms"].items():
                if algorithm_cfg.get("enabled", True) and (not only_algorithms or algorithm_name in only_algorithms):
                    algorithms.add(algorithm_name)
        return sorted(algorithms)

    def _preprocess_dataset(self, loaded_dataset: LoadedDataset) -> pd.DataFrame:
        preprocessing = self.config["preprocessing"]
        df = keep_columns(loaded_dataset.dataframe.copy(), preprocessing["keep_columns"])
        if preprocessing.get("normalize_strings", True):
            df = normalize_strings(df)
        df = clean_multiple_target_columns(df, self.config["inference_targets"])
        return apply_feature_engineering(df, preprocessing.get("engineered_features"))

    def _run_target(
        self,
        prepared_df: pd.DataFrame,
        run_dir: Path,
        target_field: str,
        target_cfg: dict[str, Any],
        only_algorithms: set[str] | None,
        mongo_writer: MongoOutputWriter,
        inference_run_id: str | None,
        parser_run_id: str | None,
        mode: str,
    ) -> dict[str, Any]:
        target_dir = make_target_dir(run_dir, target_field)
        masking_cfg = {"target_field": target_field, **target_cfg.get("masking", {})}
        if "source_col" not in masking_cfg:
            cleaning_cfg = target_cfg.get("cleaning", {})
            masking_cfg["source_col"] = cleaning_cfg.get("clean_col", f"{target_field}_clean")

        if mode == "evaluation":
            inference_df = create_masked_eval_dataset(prepared_df, masking_cfg)
            write_dataframe(inference_df, target_dir / "masked_eval.csv")
        else:
            inference_df = create_missing_value_dataset(prepared_df, masking_cfg)
            write_dataframe(inference_df, target_dir / "missing_values.csv")

        mask_col = masking_cfg.get("mask_col", "is_masked")
        inference_row_count = int(inference_df[mask_col].sum())
        target_summary: dict[str, Any] = {
            "inference_row_count": inference_row_count,
            "algorithms": {},
        }

        if inference_row_count == 0:
            target_summary["status"] = "skipped_no_missing_values" if mode == "production" else "skipped_no_rows"
            print(f"[{target_field}] no rows require inference; skipping algorithms")
            return target_summary

        predictions_by_algorithm: dict[str, pd.DataFrame] = {}
        for algorithm_name, algorithm_cfg in target_cfg["algorithms"].items():
            if not algorithm_cfg.get("enabled", True):
                continue
            if only_algorithms and algorithm_name not in only_algorithms:
                continue

            algorithm_summary, predictions_df = self._run_algorithm(
                inference_df=inference_df,
                target_dir=target_dir,
                target_field=target_field,
                target_cfg=target_cfg,
                masking_cfg=masking_cfg,
                algorithm_name=algorithm_name,
                algorithm_cfg=algorithm_cfg,
                mode=mode,
            )
            target_summary["algorithms"][algorithm_name] = algorithm_summary
            predictions_by_algorithm[algorithm_name] = predictions_df

        merge_cfg = {
            "target_field": target_field,
            "mask_col": mask_col,
            "true_col": masking_cfg.get("true_col", "target_true"),
            "input_col": masking_cfg.get("target_col", "target_input"),
            **target_cfg.get("merge", {}),
        }
        if not merge_cfg.get("enabled", True) or not predictions_by_algorithm:
            return target_summary

        merged_df, candidates_df = merge_predictions(predictions_by_algorithm, merge_cfg)
        merge_metrics = (
            compute_merge_metrics(merged_df, merge_cfg)
            if mode == "evaluation"
            else compute_production_merge_summary(merged_df, merge_cfg)
        )

        merged_dir = make_algorithm_dir(target_dir, merge_cfg.get("output_folder", "merged"))
        write_dataframe(merged_df, merged_dir / "final_predictions.csv")
        write_dataframe(candidates_df, merged_dir / "candidates.csv")
        write_json(merge_metrics, merged_dir / "metrics.json")

        persisted_prediction_count = mongo_writer.insert_predictions(
            inference_run_id=inference_run_id,
            parser_run_id=parser_run_id,
            target_field=target_field,
            candidates_df=candidates_df,
            mode=mode,
        )
        persisted_decision_count = mongo_writer.insert_decisions(
            inference_run_id=inference_run_id,
            parser_run_id=parser_run_id,
            target_field=target_field,
            merged_df=merged_df,
            true_col=merge_cfg["true_col"],
            input_col=merge_cfg["input_col"],
            mode=mode,
        )
        persisted_final_permit_count = 0
        if mode == "production":
            persisted_final_permit_count = mongo_writer.apply_final_decisions(
                inference_run_id=inference_run_id,
                target_field=target_field,
                merged_df=merged_df,
            )

        if mode == "evaluation" and merge_metrics.get("confusion_matrix"):
            plot_cfg = deepcopy(self.config.get("plots", {}).get("confusion_matrix", {}))
            plot_cfg.setdefault("title", f"merged — {target_field} confusion matrix")
            save_confusion_matrix_plot(
                confusion_matrix=merge_metrics["confusion_matrix"],
                labels=merge_metrics["labels"],
                output_path=merged_dir / "confusion_matrix.png",
                config=plot_cfg,
            )

        target_summary["merge"] = {
            "output_dir": str(merged_dir),
            **merge_metrics,
            "persisted_prediction_count": persisted_prediction_count,
            "persisted_decision_count": persisted_decision_count,
            "persisted_final_permit_count": persisted_final_permit_count,
        }

        message = (
            f"[{target_field}] merged: coverage={merge_metrics['coverage']:.4f}, "
            f"accepted={merge_metrics['row_count_accepted']}, rejected={merge_metrics['row_count_rejected']}"
        )
        if mode == "evaluation":
            message += f", accuracy_on_accepted={merge_metrics['accuracy_on_accepted']}"
        print(message)
        return target_summary

    def _run_algorithm(
        self,
        inference_df: pd.DataFrame,
        target_dir: Path,
        target_field: str,
        target_cfg: dict[str, Any],
        masking_cfg: dict[str, Any],
        algorithm_name: str,
        algorithm_cfg: dict[str, Any],
        mode: str,
    ) -> tuple[dict[str, Any], pd.DataFrame]:
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

        fitted = spec["fit"](inference_df, algorithm_params)
        predictions_df = spec["predict"](inference_df, fitted)
        metrics_cfg = {
            "true_col": algorithm_params["true_col"],
            "pred_col": "predicted_value",
            "mask_col": algorithm_params["mask_col"],
            "target_field": target_field,
            "algorithm": algorithm_name,
        }

        if mode == "evaluation":
            metrics = compute_classification_metrics(predictions_df, metrics_cfg)
        else:
            requested_rows = predictions_df[predictions_df[algorithm_params["mask_col"]] == 1]
            predicted_rows = requested_rows[requested_rows["predicted_value"].notna()]
            metrics = {
                "target_field": target_field,
                "algorithm": algorithm_name,
                "row_count_requested": int(len(requested_rows)),
                "row_count_predicted": int(len(predicted_rows)),
                "coverage": float(len(predicted_rows) / len(requested_rows)) if len(requested_rows) else 0.0,
            }

        metrics["algorithm_parameters"] = fitted.get("config", algorithm_params)
        metrics["reference_count"] = int(fitted.get("reference_count", 0))
        folder_name = algorithm_cfg.get("output_folder", spec["default_output_folder"])
        algorithm_dir = make_algorithm_dir(target_dir, folder_name)
        write_dataframe(predictions_df, algorithm_dir / "predictions.csv")
        write_metrics_json(metrics, algorithm_dir / "metrics.json")

        if mode == "evaluation":
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
            write_dataframe(exporter(fitted, int(algorithm_cfg.get("top_n_rules", 50))), algorithm_dir / "top_rules.csv")

        if mode == "evaluation":
            print(
                f"[{target_field}] {algorithm_name}: accuracy={metrics['accuracy']:.4f}, "
                f"macro_f1={metrics['macro_f1']:.4f}, rows={metrics['row_count_evaluated']}"
            )
            summary = {
                "output_dir": str(algorithm_dir),
                "accuracy": metrics["accuracy"],
                "macro_f1": metrics["macro_f1"],
                "row_count_evaluated": metrics["row_count_evaluated"],
            }
        else:
            print(
                f"[{target_field}] {algorithm_name}: coverage={metrics['coverage']:.4f}, "
                f"predicted={metrics['row_count_predicted']}/{metrics['row_count_requested']}"
            )
            summary = {
                "output_dir": str(algorithm_dir),
                "coverage": metrics["coverage"],
                "row_count_requested": metrics["row_count_requested"],
                "row_count_predicted": metrics["row_count_predicted"],
            }

        return summary, predictions_df
