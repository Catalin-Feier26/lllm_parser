from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from data_loading.loader_types import LoadedDataset


def _load_csv(input_path: Path) -> LoadedDataset:
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    return LoadedDataset(
        dataframe=pd.read_csv(input_path, dtype=str),
        input_name=input_path.stem,
        input_description=str(input_path),
    )


def load_dataset(
    config: dict[str, Any],
    input_override: str | Path | None = None,
    parser_run_id_override: str | None = None,
) -> LoadedDataset:
    """Load a DataFrame from CSV or from MongoDB raw_permits.

    CSV remains supported for reproducible local experiments. MongoDB is the
    preferred path after the Perl ingestion pipeline has populated raw_permits.
    """
    if input_override is not None:
        return _load_csv(Path(input_override))

    source_cfg = config["source"]
    input_cfg = source_cfg.get("input")

    # Backward compatibility with the earlier CSV-only YAML files.
    if input_cfg is None:
        raw_path = source_cfg.get("input_csv")
        if not raw_path:
            raise ValueError("Define source.input or source.input_csv, or pass --input")
        return _load_csv(Path(raw_path))

    input_type = str(input_cfg.get("type", "csv")).lower()
    if input_type == "csv":
        raw_path = input_cfg.get("path") or source_cfg.get("input_csv")
        if not raw_path:
            raise ValueError("CSV input requires source.input.path or source.input_csv")
        return _load_csv(Path(raw_path))

    if input_type == "mongo":
        from data_loading.mongo_raw_permits import load_raw_permits_from_mongo

        return load_raw_permits_from_mongo(
            input_cfg,
            parser_run_id_override=parser_run_id_override,
        )

    raise ValueError(f"Unsupported source.input.type: {input_type}")
