from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

import pandas as pd

ASCENDING = 1
DESCENDING = -1

from data_loading.loader_types import LoadedDataset


PROVENANCE_COLUMNS = {
    "parser_run_id": "parser_run_id",
    "input_file_id": "input_file_id",
    "output_csv_file_id": "output_csv_file_id",
    "csv_file_name": "csv_file_name",
    "csv_row_number": "csv_row_number",
    "parser_name": "parser_name",
    "config_module": "config_module",
    "config_version": "config_version",
    "loaded_at": "loaded_at",
}


def _mongo_client(config: dict[str, Any]) -> Any:
    uri_env = config.get("uri_env", "MONGO_URI")
    uri = config.get("uri") or os.getenv(uri_env)
    if not uri:
        raise ValueError(
            f"MongoDB URI is missing. Set {uri_env} or define source.input.uri in YAML."
        )

    try:
        from pymongo import MongoClient
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MongoDB loading requires pymongo. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    timeout_ms = int(config.get("server_selection_timeout_ms", 5000))
    return MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)


def _database_name(config: dict[str, Any]) -> str:
    db_name_env = config.get("database_env", "MONGO_DB_NAME")
    db_name = config.get("database") or os.getenv(db_name_env)
    if not db_name:
        raise ValueError(
            f"MongoDB database name is missing. Set {db_name_env} or define source.input.database in YAML."
        )
    return str(db_name)


def _latest_completed_parser_run_id(db: Any, config: dict[str, Any]) -> str:
    collection_name = config.get("parser_runs_collection", "parser_runs")
    run_filter = {"status": "completed", **config.get("parser_run_filter", {})}

    parser_run = db[collection_name].find_one(
        run_filter,
        sort=[("completed_at", DESCENDING), ("started_at", DESCENDING)],
    )
    if parser_run is None:
        raise ValueError(
            f"No completed parser run found in '{collection_name}' for filter: {run_filter}"
        )

    run_id = parser_run.get("run_id")
    if not run_id:
        raise ValueError("Latest completed parser run does not contain run_id")
    return str(run_id)


def _completed_parser_run_ids(db: Any, config: dict[str, Any]) -> list[str]:
    collection_name = config.get("parser_runs_collection", "parser_runs")
    run_filter = {"status": "completed", **config.get("parser_run_filter", {})}
    cursor = db[collection_name].find(
        run_filter,
        {"_id": 0, "run_id": 1},
    ).sort([("completed_at", ASCENDING), ("started_at", ASCENDING)])
    run_ids = [str(doc["run_id"]) for doc in cursor if doc.get("run_id")]
    if not run_ids:
        raise ValueError(
            f"No completed parser runs found in '{collection_name}' for filter: {run_filter}"
        )
    return run_ids


def _wants_all_parser_runs(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"all", "*", "all_completed", "all-completed"}


def _source_value(document: dict[str, Any], key: str) -> Any:
    source = document.get("source") or {}
    return source.get(key)


def _documents_to_dataframe(documents: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for document in documents:
        data = document.get("data")
        if not isinstance(data, dict):
            raise ValueError("Every raw_permits document must contain a mapping in 'data'")

        provenance = document.get("provenance") or {}
        row: dict[str, Any] = {
            "raw_permit_id": document.get("raw_permit_id"),
            "record_type": document.get("record_type"),
            "source_state": _source_value(document, "state"),
            "source_county": _source_value(document, "county"),
            "source_municipality": _source_value(document, "municipality"),
        }

        for output_col, provenance_key in PROVENANCE_COLUMNS.items():
            row[output_col] = provenance.get(provenance_key)

        collisions = sorted(set(row) & set(data))
        if collisions:
            raise ValueError(
                "Raw permit data fields collide with reserved metadata columns: "
                f"{collisions}"
            )

        row.update(data)
        rows.append(row)

    if not rows:
        raise ValueError("MongoDB query returned no raw permit documents")

    return pd.DataFrame(rows)


def load_raw_permits_from_mongo(
    config: dict[str, Any],
    parser_run_id_override: str | None = None,
) -> LoadedDataset:
    """Load one or all matching parser runs from raw_permits and flatten nested data fields."""
    client = _mongo_client(config)
    try:
        db = client[_database_name(config)]
        configured_parser_run_id = parser_run_id_override or config.get("parser_run_id")
        load_all_runs = _wants_all_parser_runs(configured_parser_run_id)
        if load_all_runs:
            parser_run_ids = _completed_parser_run_ids(db, config)
            parser_run_id: str | None = "all_completed"
            parser_run_filter: Any = {"$in": parser_run_ids}
        else:
            parser_run_id = configured_parser_run_id or _latest_completed_parser_run_id(db, config)
            parser_run_ids = [str(parser_run_id)]
            parser_run_filter = parser_run_id

        collection_name = config.get("collection", "raw_permits")
        query = {
            **config.get("raw_permits_filter", {}),
            "provenance.parser_run_id": parser_run_filter,
        }
        projection = config.get("projection")
        cursor = db[collection_name].find(query, projection).sort(
            [("provenance.parser_run_id", ASCENDING), ("provenance.csv_row_number", ASCENDING)]
        )
        dataframe = _documents_to_dataframe(cursor)

        input_name = "all_completed" if load_all_runs else str(parser_run_id)
        if load_all_runs:
            input_description = (
                f"mongo:{collection_name} parser_run_ids={len(parser_run_ids)} completed runs"
            )
        else:
            input_description = f"mongo:{collection_name} parser_run_id={parser_run_id}"

        return LoadedDataset(
            dataframe=dataframe,
            input_name=input_name,
            input_description=input_description,
            parser_run_id=str(parser_run_id),
        )
    finally:
        client.close()
