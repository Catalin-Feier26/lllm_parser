# MongoDB Loading Integration

The Python inference module can now load permits directly from the MongoDB
`raw_permits` collection produced by the Perl pipeline.

## Default Naples flow

The Naples YAML selects the latest completed parser run matching:

- `source.state = FL`
- `source.county = Collier`
- `parser.config_module = Config::Parser::fl_collier_naples_xlsx`

It then loads only `raw_permits` documents linked to that parser run and flattens
the nested `data` object into a Pandas DataFrame.

Metadata such as `raw_permit_id`, `parser_run_id`, `input_file_id`,
`output_csv_file_id`, and `csv_row_number` is preserved beside the extracted
permit fields.

## Environment variables

Use the same variables as the Perl MongoDB connection:

```bash
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DB_NAME="your_database_name"
```

When running inside Docker Compose, the URI will commonly use the Mongo service
name instead of localhost:

```bash
export MONGO_URI="mongodb://mongo:27017"
```

## Run inference from the latest completed Naples parser run

From the directory containing `main.py`:

```bash
python main.py --config config/naples.yml
```

## Re-run inference for a specific historical parser run

```bash
python main.py \
  --config config/naples.yml \
  --parser-run-id run_20260607_153000_42
```

## CSV fallback

CSV mode remains available for local experiments. Either pass an override:

```bash
python main.py \
  --config config/naples.yml \
  --input data/archive/2025-4-issued-permits.csv
```

or define this in a source YAML file:

```yaml
source:
  name: example
  input:
    type: csv
    path: data/archive/example.csv
```

## Scope of this change

This update only changes dataset loading and provenance preservation. The
existing evaluation workflow still masks a reproducible subset of known target
values and computes metrics. Writing inference runs, candidates, decisions, and
final permit records back into MongoDB is the next step.
