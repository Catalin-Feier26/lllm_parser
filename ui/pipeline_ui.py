from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA_INCOMING = ROOT / "data" / "incoming"
PARSER_ROOT = ROOT / "lib" / "Parser"
CONFIG_ROOT = ROOT / "lib" / "Config" / "Parser"
INFERENCE_CONFIG_ROOT = ROOT / "python_inference" / "config"

STATE_NAMES = {
    "CA": "California",
    "CO": "Colorado",
    "FL": "Florida",
    "LA": "Louisiana",
}


def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    data = json.dumps(payload, indent=2, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _safe_int(value: Any, default: int = 25, minimum: int = 1, maximum: int = 100) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def list_incoming_files() -> list[dict[str, Any]]:
    if not DATA_INCOMING.exists():
        return []
    files = []
    for path in sorted(DATA_INCOMING.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        files.append(
            {
                "name": path.name,
                "extension": path.suffix.lower().lstrip("."),
                "size_bytes": path.stat().st_size,
            }
        )
    return files


def discover_parsers() -> list[dict[str, str]]:
    parsers: list[dict[str, str]] = []
    if not PARSER_ROOT.exists():
        return parsers

    for path in sorted(PARSER_ROOT.rglob("*.pm")):
        if path.name == "Base.pm":
            continue
        rel = path.relative_to(PARSER_ROOT)
        parts = rel.parts
        if len(parts) < 3:
            continue
        state = parts[0]
        county = parts[1]
        parser_name = path.stem
        module = "Parser::" + "::".join(rel.with_suffix("").parts)
        parsers.append(
            {
                "state": state,
                "state_label": STATE_NAMES.get(state, state),
                "county": county,
                "parser": parser_name,
                "module": module,
            }
        )
    return parsers


def _read_config_source(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    source: dict[str, str] = {}
    for key in ("state", "county", "municipality"):
        match = re.search(rf"{key}\s*=>\s*'([^']+)'", text)
        if match:
            source[key] = match.group(1)
    return source


def _source_from_config_name(name: str) -> dict[str, str]:
    parts = name.split("_")
    state = parts[0].upper() if parts else ""
    county = parts[1].title() if len(parts) > 1 else ""
    municipality = parts[2].title() if len(parts) > 2 else ""
    return {"state": state, "county": county, "municipality": municipality}


def discover_parser_configs() -> list[dict[str, str]]:
    configs: list[dict[str, str]] = []
    if not CONFIG_ROOT.exists():
        return configs

    for path in sorted(CONFIG_ROOT.glob("*.pm")):
        name = path.stem
        source = _source_from_config_name(name)
        source.update({key: value for key, value in _read_config_source(path).items() if value})
        configs.append(
            {
                "name": name,
                "state": source.get("state", ""),
                "county": source.get("county", ""),
                "municipality": source.get("municipality", ""),
            }
        )
    return configs


def discover_inference_configs() -> list[dict[str, str]]:
    if not INFERENCE_CONFIG_ROOT.exists():
        return []
    return [
        {"name": path.name, "path": str(path.relative_to(ROOT))}
        for path in sorted(INFERENCE_CONFIG_ROOT.glob("*.yml"))
        if path.name != "general_config.yml"
    ]


def discover_options() -> dict[str, Any]:
    parsers = discover_parsers()
    parser_configs = discover_parser_configs()
    states = sorted({item["state"] for item in parsers if item["state"]})
    counties = sorted({item["county"] for item in parsers if item["county"]})
    algorithms = ["all", "grouped_majority", "association_rules", "clustering", "knn"]

    return {
        "incoming_files": list_incoming_files(),
        "states": [{"value": state, "label": STATE_NAMES.get(state, state)} for state in states],
        "counties": counties,
        "parsers": parsers,
        "parser_configs": parser_configs,
        "inference_configs": discover_inference_configs(),
        "algorithms": algorithms,
    }


def run_command(command: list[str], timeout: int = 900) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "ok": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"Command timed out after {timeout} seconds",
            "ok": False,
        }


def run_parser(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["state", "county", "parser", "file_name", "config_file"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        return {"ok": False, "error": f"Missing required parser fields: {', '.join(missing)}"}

    command = [
        "perl",
        "bin/run_parsing.pl",
        "--state",
        str(payload["state"]),
        "--county",
        str(payload["county"]),
        "--name",
        str(payload["parser"]),
        "--file_name",
        str(payload["file_name"]),
        "--config_file",
        str(payload["config_file"]),
    ]
    return run_command(command)


def run_inference(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("config") or "python_inference/config/naples.yml"
    mode = payload.get("mode") or "evaluation"
    algorithm = payload.get("algorithm") or "all"
    target = payload.get("target") or ""
    parser_run_id = payload.get("parser_run_id") or ""

    command = ["python3", "python_inference/main.py", "--config", str(config), "--mode", str(mode)]
    if algorithm != "all":
        command.extend(["--algorithm", str(algorithm)])
    if target:
        command.extend(["--target", str(target)])
    if parser_run_id:
        command.extend(["--parser-run-id", str(parser_run_id)])
    return run_command(command)


def _mongo_db() -> Any:
    from pymongo import MongoClient

    uri = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
    db_name = os.environ.get("MONGO_DB_NAME", "thesis")
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    client.admin.command("ping")
    return client, client[db_name]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _build_preview_filter(collection: str, params: dict[str, list[str]]) -> dict[str, Any]:
    query: dict[str, Any] = {}

    parser_run_id = (params.get("parser_run_id", [""])[0] or "").strip()
    inference_run_id = (params.get("inference_run_id", [""])[0] or "").strip()
    target_field = (params.get("target_field", [""])[0] or "").strip()
    algorithm = (params.get("algorithm", [""])[0] or "").strip()
    decision_status = (params.get("decision_status", [""])[0] or "").strip()
    record_status = (params.get("record_status", [""])[0] or "").strip()
    search = (params.get("search", [""])[0] or "").strip()

    if parser_run_id:
        if collection == "raw_permits":
            query["provenance.parser_run_id"] = parser_run_id
        else:
            query["parser_run_id"] = parser_run_id
    if inference_run_id:
        query["inference_run_id"] = inference_run_id
    if target_field:
        query["target_field"] = target_field
    if algorithm:
        query["algorithm"] = algorithm
    if decision_status and collection in {"inference_decisions", "final_permits"}:
        if collection == "final_permits":
            query["inference.applied_fields.permit_class.decision_status"] = decision_status
        else:
            query["decision_status"] = decision_status
    if record_status and collection == "validation_results":
        query["record_status"] = record_status

    if search:
        regex = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [
            {"raw_permit_id": regex},
            {"final_permit_id": regex},
            {"parser_run_id": regex},
            {"inference_run_id": regex},
            {"data.permit_number": regex},
            {"data.address": regex},
            {"data.permit_class": regex},
            {"data.permit_type": regex},
            {"target_field": regex},
            {"algorithm": regex},
            {"decision_status": regex},
            {"record_status": regex},
        ]

    return query


def preview_collection(collection: str, limit: int = 25, params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    allowed = {
        "parser_runs",
        "raw_permits",
        "validation_results",
        "inference_runs",
        "inference_predictions",
        "inference_decisions",
        "final_permits",
    }
    if collection not in allowed:
        return {"ok": False, "error": f"Unsupported collection: {collection}"}

    try:
        client, db = _mongo_db()
        try:
            query = _build_preview_filter(collection, params or {})
            cursor = db[collection].find(query, {"_id": 0}).limit(max(1, min(limit, 100)))
            rows = [_json_safe(row) for row in cursor]
            return {
                "ok": True,
                "collection": collection,
                "rows": rows,
                "count": db[collection].count_documents(query),
                "filter": query,
            }
        finally:
            client.close()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "collection": collection, "rows": [], "count": 0}


def _latest_json_files(pattern: str, limit: int = 20) -> list[Path]:
    files = sorted(ROOT.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:limit]


def _relative_artifact(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _metrics_card(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    rel = _relative_artifact(path)
    matrix_path = path.with_name("confusion_matrix.png")
    return {
        "path": rel,
        "label": " / ".join(path.relative_to(ROOT / "python_inference" / "output").parts[-4:-1]),
        "target_field": data.get("target_field"),
        "algorithm": data.get("algorithm") or path.parent.name,
        "accuracy": data.get("accuracy") if data.get("accuracy") is not None else data.get("accuracy_on_accepted"),
        "macro_f1": data.get("macro_f1") if data.get("macro_f1") is not None else data.get("macro_f1_on_accepted"),
        "weighted_f1": data.get("weighted_f1"),
        "coverage": data.get("coverage"),
        "row_count_evaluated": data.get("row_count_evaluated"),
        "row_count_accepted": data.get("row_count_accepted"),
        "row_count_rejected": data.get("row_count_rejected"),
        "row_count_requires_review": data.get("row_count_requires_review"),
        "decision_status_counts": data.get("decision_status_counts", {}),
        "confusion_matrix": _relative_artifact(matrix_path) if matrix_path.exists() else None,
    }


def analytics_summary() -> dict[str, Any]:
    try:
        client, db = _mongo_db()
        try:
            decision_counts = list(
                db.inference_decisions.aggregate([
                    {"$group": {"_id": "$decision_status", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ])
            )
            validation_counts = list(
                db.validation_results.aggregate([
                    {"$group": {"_id": "$record_status", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ])
            )
            latest_inference_run = db.inference_runs.find_one({}, {"_id": 0}, sort=[("started_at", -1)])
        finally:
            client.close()
    except Exception as exc:
        decision_counts = []
        validation_counts = []
        latest_inference_run = None
        mongo_error = str(exc)
    else:
        mongo_error = None

    metrics: list[dict[str, Any]] = []
    for path in _latest_json_files("python_inference/output/**/metrics.json", limit=30):
        try:
            metrics.append(_metrics_card(path))
        except Exception:
            continue

    return {
        "ok": True,
        "mongo_error": mongo_error,
        "decision_status_counts": {str(item["_id"] or "unknown"): int(item["count"]) for item in decision_counts},
        "validation_record_status_counts": {str(item["_id"] or "unknown"): int(item["count"]) for item in validation_counts},
        "latest_inference_run": _json_safe(latest_inference_run),
        "metrics": metrics,
    }


def serve_artifact(handler: BaseHTTPRequestHandler, relative_path: str) -> None:
    decoded = unquote(relative_path).lstrip("/\\")
    path = (ROOT / decoded).resolve()
    allowed_root = (ROOT / "python_inference" / "output").resolve()
    if not path.is_file() or allowed_root not in path.parents:
        _json_response(handler, {"ok": False, "error": "Artifact not found"}, status=404)
        return

    data = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def mongo_summary() -> dict[str, Any]:
    collections = [
        "parser_runs",
        "raw_permits",
        "validation_results",
        "inference_runs",
        "inference_predictions",
        "inference_decisions",
        "final_permits",
    ]
    try:
        client, db = _mongo_db()
        try:
            counts = {name: db[name].count_documents({}) for name in collections}
            latest_parser_run = db.parser_runs.find_one({}, {"_id": 0}, sort=[("started_at", -1)])
            latest_inference_run = db.inference_runs.find_one({}, {"_id": 0}, sort=[("started_at", -1)])
            return {
                "ok": True,
                "counts": counts,
                "latest_parser_run": _json_safe(latest_parser_run),
                "latest_inference_run": _json_safe(latest_inference_run),
            }
        finally:
            client.close()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "counts": {}}


HTML_PAGE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Permit Pipeline Visualizer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --border: #d8dde6;
      --text: #17202a;
      --muted: #5d6d7e;
      --accent: #1f6feb;
      --good: #166534;
      --bad: #991b1b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      padding: 18px 24px;
      background: #ffffff;
      border-bottom: 1px solid var(--border);
    }
    h1 { margin: 0; font-size: 22px; }
    main {
      padding: 20px;
      display: grid;
      grid-template-columns: minmax(320px, 430px) 1fr;
      gap: 18px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
    }
    h2 { margin: 0 0 12px; font-size: 16px; }
    label {
      display: block;
      margin: 12px 0 5px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }
    select, input, button {
      width: 100%;
      padding: 9px 10px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #ffffff;
      color: var(--text);
      font-size: 14px;
    }
    button {
      margin-top: 14px;
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
      cursor: pointer;
      font-weight: 700;
    }
    button.secondary {
      background: #ffffff;
      color: var(--accent);
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .status {
      margin-top: 10px;
      padding: 10px;
      border-radius: 6px;
      background: #f1f5f9;
      color: var(--muted);
      white-space: pre-wrap;
      font-family: Consolas, monospace;
      font-size: 12px;
      max-height: 240px;
      overflow: auto;
    }
    .ok { color: var(--good); }
    .fail { color: var(--bad); }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .metric {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfe;
    }
    .metric strong { display: block; font-size: 22px; }
    .metric span { color: var(--muted); font-size: 12px; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th, td {
      border-bottom: 1px solid var(--border);
      padding: 7px;
      text-align: left;
      vertical-align: top;
      max-width: 260px;
      overflow-wrap: anywhere;
    }
    th { background: #f8fafc; position: sticky; top: 0; }
    .table-wrap {
      max-height: 540px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    .analytics {
      margin-top: 18px;
    }
    .metric-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      gap: 8px;
      margin: 10px 0;
    }
    .small-metric {
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px;
      background: #fbfcfe;
    }
    .small-metric strong { display: block; font-size: 16px; }
    .small-metric span { color: var(--muted); font-size: 11px; }
    .confusion-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }
    .confusion-card {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #ffffff;
    }
    .confusion-card img {
      width: 100%;
      height: auto;
      display: block;
      border: 1px solid var(--border);
      border-radius: 6px;
      margin-top: 8px;
    }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Permit Pipeline Visualizer</h1>
  </header>
  <main>
    <div>
      <section>
        <h2>Parser Run</h2>
        <label for="file">Input file</label>
        <select id="file"></select>
        <div class="grid">
          <div>
            <label for="state">State</label>
            <select id="state"></select>
          </div>
          <div>
            <label for="county">County</label>
            <select id="county"></select>
          </div>
        </div>
        <label for="parser">Parser</label>
        <select id="parser"></select>
        <label for="parserConfig">Parser config</label>
        <select id="parserConfig"></select>
        <button onclick="runParser()">Run Parser</button>
        <div id="parserLog" class="status">Ready.</div>
      </section>

      <section style="margin-top:18px">
        <h2>Inference Run</h2>
        <label for="inferenceConfig">Inference config</label>
        <select id="inferenceConfig"></select>
        <div class="grid">
          <div>
            <label for="mode">Mode</label>
            <select id="mode">
              <option value="evaluation">evaluation</option>
              <option value="production">production</option>
            </select>
          </div>
          <div>
            <label for="algorithm">Algorithm</label>
            <select id="algorithm"></select>
          </div>
        </div>
        <label for="target">Target field</label>
        <input id="target" value="permit_class">
        <label for="parserRunId">Parser run id override</label>
        <input id="parserRunId" placeholder="optional, or type all">
        <button onclick="runInference()">Run Inference</button>
        <div id="inferenceLog" class="status">Ready.</div>
      </section>
    </div>

    <section>
      <h2>Mongo Preview</h2>
      <div id="metrics" class="cards"></div>
      <div class="grid">
        <div>
          <label for="collection">Collection</label>
          <select id="collection">
            <option>parser_runs</option>
            <option>raw_permits</option>
            <option>validation_results</option>
            <option>inference_runs</option>
            <option>inference_predictions</option>
            <option>inference_decisions</option>
            <option>final_permits</option>
          </select>
        </div>
        <div>
          <label for="limit">Preview rows</label>
          <input id="limit" type="number" min="1" max="100" value="20">
        </div>
      </div>
      <div class="grid">
        <div>
          <label for="filterParserRun">Parser run id</label>
          <input id="filterParserRun" placeholder="optional">
        </div>
        <div>
          <label for="filterInferenceRun">Inference run id</label>
          <input id="filterInferenceRun" placeholder="optional">
        </div>
      </div>
      <div class="grid">
        <div>
          <label for="filterDecisionStatus">Decision status</label>
          <select id="filterDecisionStatus">
            <option value="">any</option>
            <option>Accepted</option>
            <option>Rejected</option>
            <option>Unresolved</option>
            <option>Requires Review</option>
            <option>Conflict</option>
          </select>
        </div>
        <div>
          <label for="filterRecordStatus">Validation status</label>
          <select id="filterRecordStatus">
            <option value="">any</option>
            <option>valid</option>
            <option>missing</option>
            <option>invalid</option>
            <option>suspicious</option>
            <option>requires_review</option>
          </select>
        </div>
      </div>
      <div class="grid">
        <div>
          <label for="filterAlgorithm">Algorithm</label>
          <select id="filterAlgorithm">
            <option value="">any</option>
            <option>grouped_majority</option>
            <option>association_rules</option>
            <option>clustering</option>
            <option>knn</option>
          </select>
        </div>
        <div>
          <label for="filterTarget">Target field</label>
          <input id="filterTarget" placeholder="optional">
        </div>
      </div>
      <label for="filterSearch">Search</label>
      <input id="filterSearch" placeholder="permit id, run id, address, status...">
      <button class="secondary" onclick="refreshPreview()">Refresh Preview</button>
      <div id="preview" class="table-wrap" style="margin-top:14px"></div>

      <div class="analytics">
        <h2>Analytics</h2>
        <button class="secondary" onclick="refreshAnalytics()">Refresh Analytics</button>
        <div id="analyticsBox" class="status">No analytics loaded yet.</div>
        <div id="metricsTable" class="table-wrap" style="margin-top:14px"></div>
        <div id="confusionMatrices" class="confusion-grid"></div>
      </div>
    </section>
  </main>

  <script>
    let options = {};

    function setOptions(id, rows, labelFn, valueFn) {
      const el = document.getElementById(id);
      el.innerHTML = "";
      for (const row of rows) {
        const opt = document.createElement("option");
        opt.value = valueFn ? valueFn(row) : row;
        opt.textContent = labelFn ? labelFn(row) : row;
        el.appendChild(opt);
      }
    }

    function selected(id) {
      return document.getElementById(id).value;
    }

    async function api(path, body) {
      const init = body ? {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      } : undefined;
      const res = await fetch(path, init);
      return await res.json();
    }

    async function loadOptions() {
      options = await api("/api/options");
      setOptions("file", options.incoming_files, f => `${f.name} (${f.extension || "file"})`, f => f.name);
      setOptions("state", options.states, s => `${s.value} - ${s.label}`, s => s.value);
      setOptions("algorithm", options.algorithms);
      setOptions("inferenceConfig", options.inference_configs, c => c.path, c => c.path);
      updateParserFilters();
      await refreshSummary();
      await refreshPreview();
      await refreshAnalytics();
    }

    function updateParserFilters() {
      const state = selected("state");
      const counties = [...new Set(options.parsers.filter(p => p.state === state).map(p => p.county))].sort();
      setOptions("county", counties);
      updateParsers();
    }

    function updateParsers() {
      const state = selected("state");
      const county = selected("county");
      const parsers = options.parsers.filter(p => p.state === state && p.county === county);
      setOptions("parser", parsers, p => p.parser, p => p.parser);
      const configs = options.parser_configs.filter(c => {
        const stateOk = !c.state || c.state === state;
        const countyOk = !c.county || c.county.toLowerCase().includes(county.toLowerCase()) || county.toLowerCase().includes(c.county.toLowerCase());
        return stateOk && countyOk;
      });
      setOptions("parserConfig", configs.length ? configs : options.parser_configs, c => {
        const where = [c.state, c.county, c.municipality].filter(Boolean).join(" / ");
        return where ? `${c.name} (${where})` : c.name;
      }, c => c.name);
    }

    async function runParser() {
      const log = document.getElementById("parserLog");
      log.textContent = "Running parser...";
      const result = await api("/api/run-parser", {
        file_name: selected("file"),
        state: selected("state"),
        county: selected("county"),
        parser: selected("parser"),
        config_file: selected("parserConfig")
      });
      log.innerHTML = `<span class="${result.ok ? "ok" : "fail"}">${result.ok ? "OK" : "FAILED"}</span>\n$ ${result.command ? result.command.join(" ") : ""}\n\n${escapeHtml(result.stdout || "")}\n${escapeHtml(result.stderr || result.error || "")}`;
      await refreshSummary();
      await refreshPreview();
    }

    async function runInference() {
      const log = document.getElementById("inferenceLog");
      log.textContent = "Running inference...";
      const result = await api("/api/run-inference", {
        config: selected("inferenceConfig"),
        mode: selected("mode"),
        algorithm: selected("algorithm"),
        target: selected("target"),
        parser_run_id: selected("parserRunId")
      });
      log.innerHTML = `<span class="${result.ok ? "ok" : "fail"}">${result.ok ? "OK" : "FAILED"}</span>\n$ ${result.command ? result.command.join(" ") : ""}\n\n${escapeHtml(result.stdout || "")}\n${escapeHtml(result.stderr || result.error || "")}`;
      await refreshSummary();
      await refreshPreview();
    }

    async function refreshSummary() {
      const result = await api("/api/summary");
      const metrics = document.getElementById("metrics");
      if (!result.ok) {
        metrics.innerHTML = `<div class="metric"><strong>!</strong><span>${escapeHtml(result.error || "Mongo unavailable")}</span></div>`;
        return;
      }
      metrics.innerHTML = Object.entries(result.counts).map(([name, count]) =>
        `<div class="metric"><strong>${count}</strong><span>${name}</span></div>`
      ).join("");
    }

    async function refreshPreview() {
      const params = new URLSearchParams({
        collection: selected("collection"),
        limit: selected("limit"),
        parser_run_id: selected("filterParserRun"),
        inference_run_id: selected("filterInferenceRun"),
        decision_status: selected("filterDecisionStatus"),
        record_status: selected("filterRecordStatus"),
        algorithm: selected("filterAlgorithm"),
        target_field: selected("filterTarget"),
        search: selected("filterSearch")
      });
      const result = await api(`/api/preview?${params}`);
      const box = document.getElementById("preview");
      if (!result.ok) {
        box.innerHTML = `<div class="status fail">${escapeHtml(result.error || "Preview failed")}</div>`;
        return;
      }
      box.innerHTML = renderTable(result.rows);
    }

    async function refreshAnalytics() {
      const result = await api("/api/analytics");
      const box = document.getElementById("analyticsBox");
      if (!result.ok) {
        box.innerHTML = `<span class="fail">${escapeHtml(result.error || "Analytics failed")}</span>`;
        return;
      }

      const validationCards = renderSmallMetrics(result.validation_record_status_counts || {}, "Validation");
      const decisionCards = renderSmallMetrics(result.decision_status_counts || {}, "Decision");
      const latest = result.latest_inference_run || {};
      const runLine = latest.inference_run_id
        ? `Latest inference run: ${escapeHtml(latest.inference_run_id)} (${escapeHtml(latest.status || "")})`
        : "Latest inference run: none";
      const mongoLine = result.mongo_error ? `\nMongo note: ${escapeHtml(result.mongo_error)}` : "";
      box.innerHTML = `${runLine}${mongoLine}<div class="metric-row">${validationCards}${decisionCards}</div>`;

      const metrics = result.metrics || [];
      document.getElementById("metricsTable").innerHTML = renderMetricsTable(metrics);
      document.getElementById("confusionMatrices").innerHTML = renderConfusionMatrices(metrics);
    }

    function renderSmallMetrics(counts, prefix) {
      const entries = Object.entries(counts);
      if (!entries.length) {
        return `<div class="small-metric"><strong>0</strong><span>${prefix}: none</span></div>`;
      }
      return entries.map(([name, count]) =>
        `<div class="small-metric"><strong>${count}</strong><span>${prefix}: ${escapeHtml(name)}</span></div>`
      ).join("");
    }

    function pct(value) {
      if (value === null || value === undefined || value === "") return "";
      const number = Number(value);
      if (Number.isNaN(number)) return escapeHtml(value);
      return (number * 100).toFixed(2) + "%";
    }

    function renderMetricsTable(metrics) {
      if (!metrics.length) return '<div class="status">No metrics JSON files found yet.</div>';
      const rows = metrics.slice(0, 12).map(item => ({
        algorithm: item.algorithm || "",
        target: item.target_field || "",
        accuracy: pct(item.accuracy),
        macro_f1: pct(item.macro_f1),
        weighted_f1: pct(item.weighted_f1),
        coverage: pct(item.coverage),
        evaluated: item.row_count_evaluated || "",
        accepted: item.row_count_accepted || "",
        rejected: item.row_count_rejected || "",
        review: item.row_count_requires_review || "",
        path: item.path || ""
      }));
      return renderTable(rows);
    }

    function renderConfusionMatrices(metrics) {
      const images = metrics.filter(item => item.confusion_matrix).slice(0, 8);
      if (!images.length) return "";
      return images.map(item => `
        <div class="confusion-card">
          <strong>${escapeHtml(item.algorithm || "metrics")}</strong>
          <div style="color:var(--muted);font-size:12px">${escapeHtml(item.target_field || "")}</div>
          <img src="/artifact?path=${encodeURIComponent(item.confusion_matrix)}" alt="Confusion matrix">
        </div>
      `).join("");
    }

    function renderTable(rows) {
      if (!rows.length) return '<div class="status">No rows found.</div>';
      const keys = [...new Set(rows.flatMap(row => Object.keys(row)))].slice(0, 18);
      const head = keys.map(k => `<th>${escapeHtml(k)}</th>`).join("");
      const body = rows.map(row => `<tr>${keys.map(k => `<td>${escapeHtml(formatCell(row[k]))}</td>`).join("")}</tr>`).join("");
      return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function formatCell(value) {
      if (value === null || value === undefined) return "";
      if (typeof value === "object") return JSON.stringify(value);
      return String(value);
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      })[ch]);
    }

    document.getElementById("state").addEventListener("change", updateParserFilters);
    document.getElementById("county").addEventListener("change", updateParsers);
    document.getElementById("collection").addEventListener("change", refreshPreview);
    for (const id of ["filterParserRun", "filterInferenceRun", "filterDecisionStatus", "filterRecordStatus", "filterAlgorithm", "filterTarget", "filterSearch", "limit"]) {
      document.getElementById(id).addEventListener("change", refreshPreview);
    }
    loadOptions();
  </script>
</body>
</html>
"""


class PipelineHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            data = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path == "/api/options":
            _json_response(self, discover_options())
            return
        if parsed.path == "/api/summary":
            _json_response(self, mongo_summary())
            return
        if parsed.path == "/api/analytics":
            _json_response(self, analytics_summary())
            return
        if parsed.path == "/artifact":
            query = parse_qs(parsed.query)
            serve_artifact(self, query.get("path", [""])[0])
            return
        if parsed.path == "/api/preview":
            query = parse_qs(parsed.query)
            collection = query.get("collection", ["raw_permits"])[0]
            limit = _safe_int(query.get("limit", ["25"])[0])
            _json_response(self, preview_collection(collection, limit, query))
            return
        _json_response(self, {"ok": False, "error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = _read_body(self)
            if parsed.path == "/api/run-parser":
                _json_response(self, run_parser(payload))
                return
            if parsed.path == "/api/run-inference":
                _json_response(self, run_inference(payload))
                return
            _json_response(self, {"ok": False, "error": "Not found"}, status=404)
        except Exception as exc:
            _json_response(self, {"ok": False, "error": str(exc)}, status=500)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the permit pipeline visualizer UI")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), PipelineHandler)
    print(f"Pipeline UI running at http://{args.host}:{args.port}")
    print(f"Workspace root: {ROOT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
