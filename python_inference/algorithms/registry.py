from __future__ import annotations

from importlib import import_module
from typing import Any, Callable

import pandas as pd


FitFunction = Callable[[pd.DataFrame, dict[str, Any]], dict[str, Any]]
PredictFunction = Callable[[pd.DataFrame, dict[str, Any]], pd.DataFrame]
ArtifactExporter = Callable[[dict[str, Any], int], pd.DataFrame]


# Keep imports lazy: an optional dependency used by one algorithm should not
# prevent the remaining algorithms from running.
ALGORITHM_REGISTRY: dict[str, dict[str, Any]] = {
    "grouped_majority": {
        "module": "baselines.grouped_majority",
        "fit_name": "fit_grouped_majority_reference",
        "predict_name": "predict_grouped_majority",
        "default_output_folder": "baseline",
    },
    "association_rules": {
        "module": "algorithms.association_rules",
        "fit_name": "fit_association_rules_reference",
        "predict_name": "predict_association_rules",
        "export_top_rules_name": "export_top_rules",
        "default_output_folder": "association_rules",
    },
    "clustering": {
        "module": "algorithms.clustering_inference",
        "fit_name": "fit_clustering_reference",
        "predict_name": "predict_clustering",
        "default_output_folder": "clustering",
    },
    "knn": {
        "module": "algorithms.knn_inference",
        "fit_name": "fit_knn_reference",
        "predict_name": "predict_knn",
        "default_output_folder": "knn",
    },
}


def get_algorithm_spec(name: str) -> dict[str, Any]:
    raw_spec = ALGORITHM_REGISTRY.get(name)
    if raw_spec is None:
        available = ", ".join(sorted(ALGORITHM_REGISTRY))
        raise ValueError(f"Unknown algorithm '{name}'. Available algorithms: {available}")

    try:
        module = import_module(raw_spec["module"])
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            f"Could not load algorithm '{name}'. Missing dependency or module: {exc.name}"
        ) from exc

    spec = {
        "fit": getattr(module, raw_spec["fit_name"]),
        "predict": getattr(module, raw_spec["predict_name"]),
        "default_output_folder": raw_spec["default_output_folder"],
    }

    exporter_name = raw_spec.get("export_top_rules_name")
    if exporter_name:
        spec["export_top_rules"] = getattr(module, exporter_name)

    return spec
