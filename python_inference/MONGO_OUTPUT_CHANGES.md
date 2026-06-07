# MongoDB inference-output persistence patch

This patch stores the existing evaluation-mode inference outputs in MongoDB while preserving the existing CSV and JSON report files.

## New MongoDB collections

- `inference_runs`: one lifecycle document per Python inference execution
- `inference_predictions`: one algorithm candidate per masked row and enabled algorithm
- `inference_decisions`: one merged decision per masked row and inference target

`final_permits` is intentionally not created yet. It belongs to the later production-inference patch for genuinely missing values.

## Configuration

The source YAML file now contains:

```yaml
output:
  base_dir: python_inference/output

  mongo:
    enabled: true
    uri_env: MONGO_URI
    database_env: MONGO_DB_NAME
    server_selection_timeout_ms: 5000

    collections:
      inference_runs: inference_runs
      inference_predictions: inference_predictions
      inference_decisions: inference_decisions

inference:
  mode: evaluation
```

The Docker Compose variables already used by the Perl pipeline are reused:

```yaml
environment:
  MONGO_URI: mongodb://mongo:27017
  MONGO_DB_NAME: thesis
```

## Run

From `/app/python_inference`:

```bash
python3 main.py --config config/naples.yml
```

## Verify in mongosh

```javascript
use thesis
show collections

db.inference_runs.find().sort({ started_at: -1 }).limit(1).pretty()
db.inference_predictions.find().limit(3).pretty()
db.inference_decisions.find().limit(3).pretty()
```

Indexes can be added after the documents have been inspected.
