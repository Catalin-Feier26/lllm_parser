# Production inference mode

This patch adds:

- `inference.mode: production`
- optional CLI override: `--mode production`
- selection of genuinely missing cleaned target values
- production coverage summaries without artificial accuracy metrics
- cloning all selected `raw_permits` into `final_permits`
- applying only accepted merged decisions to the cloned final documents

Evaluation mode remains available and unchanged in purpose.

## Run production mode

```bash
cd /app/python_inference
python3 main.py --config config/naples.yml --mode production
```

## Run evaluation mode

```bash
python3 main.py --config config/naples.yml --mode evaluation
```
