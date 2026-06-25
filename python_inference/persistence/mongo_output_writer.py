from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pandas as pd


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    return value


def _safe_id_part(value: Any) -> str:
    text = "none" if value is None else str(value)
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return [_safe_value(item) for item in parsed] if isinstance(parsed, list) else [_safe_value(parsed)]
    return [_safe_value(value)]


def _source_metadata(config: dict[str, Any]) -> dict[str, Any]:
    source_cfg = config.get("source", {})
    input_cfg = source_cfg.get("input", {}) if isinstance(source_cfg, dict) else {}
    raw_filter = input_cfg.get("raw_permits_filter", {}) if isinstance(input_cfg, dict) else {}

    source: dict[str, Any] = {"name": source_cfg.get("name")}
    for key in ("state", "county", "municipality"):
        value = raw_filter.get(f"source.{key}")
        if value is not None:
            source[key] = value
    return source


class MongoOutputWriter:
    """Persist evaluation and production inference outputs in MongoDB."""

    def __init__(self, config: dict[str, Any]) -> None:
        output_cfg = config.get("output", {})
        mongo_cfg = output_cfg.get("mongo", {}) if isinstance(output_cfg, dict) else {}
        self.config = mongo_cfg if isinstance(mongo_cfg, dict) else {}
        self.enabled = bool(self.config.get("enabled", False))
        self.source = _source_metadata(config)
        self._client: Any | None = None
        self._db: Any | None = None

        source_cfg = config.get("source", {})
        input_cfg = source_cfg.get("input", {}) if isinstance(source_cfg, dict) else {}
        self.raw_permits_collection = input_cfg.get("collection", "raw_permits")
        self.raw_permits_filter = input_cfg.get("raw_permits_filter", {})

        collections_cfg = self.config.get("collections", {})
        self.collections = {
            "inference_runs": collections_cfg.get("inference_runs", "inference_runs"),
            "inference_predictions": collections_cfg.get("inference_predictions", "inference_predictions"),
            "inference_decisions": collections_cfg.get("inference_decisions", "inference_decisions"),
            "validation_results": collections_cfg.get("validation_results", "validation_results"),
            "final_permits": collections_cfg.get("final_permits", "final_permits"),
        }

    def __enter__(self) -> "MongoOutputWriter":
        if self.enabled:
            self._connect()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _connect(self) -> None:
        uri_env = self.config.get("uri_env", "MONGO_URI")
        uri = self.config.get("uri") or os.getenv(uri_env)
        if not uri:
            raise ValueError(f"MongoDB URI is missing. Set {uri_env} or define output.mongo.uri in YAML.")

        database_env = self.config.get("database_env", "MONGO_DB_NAME")
        database_name = self.config.get("database") or os.getenv(database_env)
        if not database_name:
            raise ValueError(
                f"MongoDB database name is missing. Set {database_env} or define output.mongo.database in YAML."
            )

        try:
            from pymongo import MongoClient
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "MongoDB output persistence requires pymongo. Install dependencies with: pip install -r requirements.txt"
            ) from exc

        timeout_ms = int(self.config.get("server_selection_timeout_ms", 5000))
        self._client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        self._client.admin.command("ping")
        self._db = self._client[str(database_name)]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._db = None

    def _collection(self, key: str) -> Any:
        if not self.enabled:
            raise RuntimeError("MongoDB output persistence is disabled")
        if self._db is None:
            raise RuntimeError("MongoDB output writer is not connected")
        return self._db[self.collections[key]]

    def create_inference_run(
        self,
        *,
        parser_run_id: str | None,
        prepared_row_count: int,
        targets: list[str],
        algorithms: list[str],
        input_source: str,
        output_dir: str,
        mode: str = "evaluation",
    ) -> str | None:
        if not self.enabled:
            return None

        timestamp = _utc_now().strftime("%Y%m%d_%H%M%S")
        inference_run_id = f"inference_run_{timestamp}_{uuid4().hex[:8]}"
        document = {
            "inference_run_id": inference_run_id,
            "parser_run_id": parser_run_id,
            "source": self.source,
            "mode": mode,
            "status": "running",
            "targets": targets,
            "algorithms": algorithms,
            "input_source": input_source,
            "output_dir": output_dir,
            "prepared_row_count": int(prepared_row_count),
            "started_at": _utc_now(),
            "completed_at": None,
            "error_message": None,
        }
        self._collection("inference_runs").insert_one(document)
        return inference_run_id

    def insert_predictions(
        self,
        *,
        inference_run_id: str | None,
        parser_run_id: str | None,
        target_field: str,
        candidates_df: pd.DataFrame,
        mode: str = "evaluation",
    ) -> int:
        if not self.enabled or inference_run_id is None or candidates_df.empty:
            return 0

        documents: list[dict[str, Any]] = []
        created_at = _utc_now()
        for position, (_, row) in enumerate(candidates_df.iterrows(), start=1):
            raw_permit_id = _safe_value(row.get("raw_permit_id"))
            row_index = _safe_value(row.get("row_index"))
            algorithm = _safe_value(row.get("algorithm"))
            record_identity = raw_permit_id or f"row_{row_index}"
            prediction_id = (
                f"{inference_run_id}_{_safe_id_part(target_field)}_"
                f"{_safe_id_part(algorithm)}_{_safe_id_part(record_identity)}_{position:06d}"
            )
            documents.append(
                {
                    "prediction_id": prediction_id,
                    "inference_run_id": inference_run_id,
                    "parser_run_id": parser_run_id,
                    "raw_permit_id": raw_permit_id,
                    "row_index": row_index,
                    "target_field": _safe_value(row.get("target_field")) or target_field,
                    "algorithm": algorithm,
                    "predicted_value": _safe_value(row.get("predicted_value")),
                    "confidence": _safe_value(row.get("confidence")),
                    "prediction_source": _safe_value(row.get("prediction_source")),
                    "passes_threshold": bool(row.get("passes_threshold", False)),
                    "candidate_status": _safe_value(row.get("candidate_status")),
                    "rejection_reason": _safe_value(row.get("rejection_reason")),
                    "mode": mode,
                    "created_at": created_at,
                }
            )

        self._collection("inference_predictions").insert_many(documents)
        return len(documents)

    def _decision_id(self, inference_run_id: str, target_field: str, record_identity: Any) -> str:
        return f"{inference_run_id}_{_safe_id_part(target_field)}_{_safe_id_part(record_identity)}"

    def insert_decisions(
        self,
        *,
        inference_run_id: str | None,
        parser_run_id: str | None,
        target_field: str,
        merged_df: pd.DataFrame,
        true_col: str = "target_true",
        input_col: str = "target_input",
        mode: str = "evaluation",
    ) -> int:
        if not self.enabled or inference_run_id is None or merged_df.empty:
            return 0

        documents: list[dict[str, Any]] = []
        created_at = _utc_now()
        for _, row in merged_df.iterrows():
            raw_permit_id = _safe_value(row.get("raw_permit_id"))
            row_index = _safe_value(row.get("row_index"))
            record_identity = raw_permit_id or f"row_{row_index}"
            documents.append(
                {
                    "decision_id": self._decision_id(inference_run_id, target_field, record_identity),
                    "inference_run_id": inference_run_id,
                    "parser_run_id": parser_run_id,
                    "raw_permit_id": raw_permit_id,
                    "row_index": row_index,
                    "target_field": _safe_value(row.get("target_field")) or target_field,
                    "true_value": _safe_value(row.get(true_col)),
                    "input_value": _safe_value(row.get(input_col)),
                    "final_value": _safe_value(row.get("final_value")),
                    "final_confidence": _safe_value(row.get("final_confidence")),
                    "decision_status": _safe_value(row.get("decision_status")),
                    "decision_method": _safe_value(row.get("decision_method")),
                    "selected_algorithm": _safe_value(row.get("selected_algorithm")),
                    "supporting_algorithms": _json_list(row.get("supporting_algorithms")),
                    "vote_count": int(row.get("vote_count", 0)),
                    "candidate_count": int(row.get("candidate_count", 0)),
                    "accepted_candidate_count": int(row.get("accepted_candidate_count", 0)),
                    "minimum_confidence": _safe_value(row.get("minimum_confidence")),
                    "is_accepted": bool(row.get("is_accepted", False)),
                    "mode": mode,
                    "created_at": created_at,
                }
            )

        self._collection("inference_decisions").insert_many(documents)
        return len(documents)

    def insert_validation_results(
        self,
        *,
        inference_run_id: str | None,
        parser_run_id: str | None,
        prepared_df: pd.DataFrame,
        validation_col: str = "validation",
    ) -> int:
        """Persist per-record normalization and validation results for the current inference run."""
        if not self.enabled or inference_run_id is None or prepared_df.empty or validation_col not in prepared_df.columns:
            return 0

        documents: list[dict[str, Any]] = []
        created_at = _utc_now()
        for row_index, row in prepared_df.iterrows():
            validation = row.get(validation_col)
            if not isinstance(validation, dict):
                continue

            raw_permit_id = _safe_value(row.get("raw_permit_id"))
            record_identity = raw_permit_id or f"row_{row_index}"
            fields = validation.get("fields") if isinstance(validation.get("fields"), dict) else {}
            normalized_values = {
                str(field_name): _safe_value((field_result or {}).get("normalized_value"))
                for field_name, field_result in fields.items()
                if isinstance(field_result, dict)
            }
            field_statuses = {
                str(field_name): _safe_value((field_result or {}).get("status"))
                for field_name, field_result in fields.items()
                if isinstance(field_result, dict)
            }

            documents.append(
                {
                    "validation_result_id": (
                        f"{inference_run_id}_{_safe_id_part(record_identity)}"
                    ),
                    "inference_run_id": inference_run_id,
                    "parser_run_id": parser_run_id,
                    "raw_permit_id": raw_permit_id,
                    "row_index": _safe_value(row_index),
                    "record_status": _safe_value(validation.get("record_status")),
                    "field_statuses": field_statuses,
                    "normalized_values": normalized_values,
                    "validation": _safe_value(validation),
                    "source": self.source,
                    "created_at": created_at,
                }
            )

        if not documents:
            return 0

        self._collection("validation_results").insert_many(documents)
        return len(documents)

    def clone_raw_permits_to_final(
        self,
        *,
        inference_run_id: str | None,
        parser_run_id: str | None,
    ) -> int:
        """Create a complete final dataset snapshot before applying production decisions."""
        if not self.enabled or inference_run_id is None or parser_run_id is None:
            return 0

        query = {**self.raw_permits_filter}
        if str(parser_run_id).strip().lower() not in {"all_completed", "all", "*"}:
            query["provenance.parser_run_id"] = parser_run_id
        raw_documents = self._db[self.raw_permits_collection].find(query)
        now = _utc_now()
        count = 0

        for raw_document in raw_documents:
            raw_permit_id = raw_document.get("raw_permit_id")
            if not raw_permit_id:
                raise ValueError("Every raw_permits document must contain raw_permit_id")

            final_document = deepcopy(raw_document)
            final_document.pop("_id", None)
            final_document["final_permit_id"] = raw_permit_id
            final_document["raw_permit_id"] = raw_permit_id
            final_document["parser_run_id"] = raw_document.get("provenance", {}).get("parser_run_id") or parser_run_id
            final_document["latest_inference_run_id"] = inference_run_id
            final_document["inference"] = {
                "applied_fields": {},
                "inference_run_id": inference_run_id,
            }
            final_document["created_at"] = now
            final_document["updated_at"] = now

            self._collection("final_permits").replace_one(
                {"final_permit_id": raw_permit_id},
                final_document,
                upsert=True,
            )
            count += 1

        if count == 0:
            raise ValueError(f"No raw permits found for parser_run_id={parser_run_id}")
        return count

    def apply_final_decisions(
        self,
        *,
        inference_run_id: str | None,
        target_field: str,
        merged_df: pd.DataFrame,
    ) -> int:
        """Apply accepted production decisions to the cloned final dataset."""
        if not self.enabled or inference_run_id is None or merged_df.empty:
            return 0

        accepted_df = merged_df[
            merged_df["is_accepted"] & merged_df["final_value"].notna()
        ]
        updated_at = _utc_now()
        count = 0

        for _, row in accepted_df.iterrows():
            raw_permit_id = _safe_value(row.get("raw_permit_id"))
            row_index = _safe_value(row.get("row_index"))
            if not raw_permit_id:
                raise ValueError("Production final_permits requires raw_permit_id")

            record_identity = raw_permit_id or f"row_{row_index}"
            applied_field = {
                "decision_id": self._decision_id(inference_run_id, target_field, record_identity),
                "value": _safe_value(row.get("final_value")),
                "confidence": _safe_value(row.get("final_confidence")),
                "decision_status": _safe_value(row.get("decision_status")),
                "decision_method": _safe_value(row.get("decision_method")),
                "selected_algorithm": _safe_value(row.get("selected_algorithm")),
                "supporting_algorithms": _json_list(row.get("supporting_algorithms")),
            }
            result = self._collection("final_permits").update_one(
                {"final_permit_id": raw_permit_id},
                {
                    "$set": {
                        f"data.{target_field}": _safe_value(row.get("final_value")),
                        f"inference.applied_fields.{target_field}": applied_field,
                        "updated_at": updated_at,
                    }
                },
            )
            if getattr(result, "matched_count", 1) == 0:
                raise ValueError(f"No final_permits document found for raw_permit_id={raw_permit_id}")
            count += 1

        return count

    def complete_inference_run(self, *, inference_run_id: str | None, summary: dict[str, Any]) -> None:
        if not self.enabled or inference_run_id is None:
            return
        self._collection("inference_runs").update_one(
            {"inference_run_id": inference_run_id},
            {"$set": {"status": "completed", "completed_at": _utc_now(), "summary": _safe_value(summary)}},
        )

    def fail_inference_run(self, *, inference_run_id: str | None, error: Exception) -> None:
        if not self.enabled or inference_run_id is None:
            return
        self._collection("inference_runs").update_one(
            {"inference_run_id": inference_run_id},
            {"$set": {"status": "failed", "completed_at": _utc_now(), "error_message": str(error)}},
        )
