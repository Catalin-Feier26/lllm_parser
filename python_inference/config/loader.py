from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _require_mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
	value = config.get(key)
	if not isinstance(value, dict):
		raise ValueError(f"Config section '{key}' must be a mapping")
	return value


def validate_config(config: dict[str, Any]) -> None:
	source = _require_mapping(config, "source")
	if not source.get("name"):
		raise ValueError("Config value 'source.name' is required")

	preprocessing = _require_mapping(config, "preprocessing")
	keep_columns = preprocessing.get("keep_columns")
	if not isinstance(keep_columns, list) or not keep_columns:
		raise ValueError("Config value 'preprocessing.keep_columns' must be a non-empty list")

	targets = _require_mapping(config, "inference_targets")
	enabled_targets = [name for name, cfg in targets.items() if cfg.get("enabled", True)]
	if not enabled_targets:
		raise ValueError("At least one inference target must be enabled")

	for target_name in enabled_targets:
		target_cfg = targets[target_name]
		if not isinstance(target_cfg, dict):
			raise ValueError(f"Inference target '{target_name}' must be a mapping")

		cleaning = target_cfg.get("cleaning", {})
		if not cleaning.get("source_col", target_name):
			raise ValueError(f"Target '{target_name}' must define cleaning.source_col")

		feature_cols = target_cfg.get("feature_cols")
		if not isinstance(feature_cols, list) or not feature_cols:
			raise ValueError(f"Target '{target_name}' must define a non-empty feature_cols list")

		algorithms = target_cfg.get("algorithms")
		if not isinstance(algorithms, dict):
			raise ValueError(f"Target '{target_name}' must define an algorithms mapping")

		if not any(cfg.get("enabled", True) for cfg in algorithms.values()):
			raise ValueError(f"Target '{target_name}' must enable at least one algorithm")


def load_config(config_path: str | Path) -> dict[str, Any]:
	path = Path(config_path)
	if not path.exists():
		raise FileNotFoundError(f"Config file not found: {path}")

	with path.open("r", encoding="utf-8") as handle:
		config = yaml.safe_load(handle)

	if not isinstance(config, dict):
		raise ValueError("The YAML config root must be a mapping")

	validate_config(config)
	return config
