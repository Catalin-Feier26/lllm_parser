from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def make_run_dir(config: dict[str, Any], input_name: str) -> Path:
	source_name = config["source"]["name"]
	base_dir = Path(config.get("output", {}).get("base_dir", "python_inference/output"))
	run_dir = base_dir / source_name / input_name
	run_dir.mkdir(parents=True, exist_ok=True)
	return run_dir


def make_target_dir(run_dir: Path, target_field: str) -> Path:
	target_dir = run_dir / target_field
	target_dir.mkdir(parents=True, exist_ok=True)
	return target_dir


def make_algorithm_dir(target_dir: Path, folder_name: str) -> Path:
	algorithm_dir = target_dir / folder_name
	algorithm_dir.mkdir(parents=True, exist_ok=True)
	return algorithm_dir


def write_dataframe(df: pd.DataFrame, output_path: Path) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	df.to_csv(output_path, index=False)


def write_json(payload: dict[str, Any], output_path: Path) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
