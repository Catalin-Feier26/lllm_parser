# Thesis Implementation TODO

This file tracks the work needed to make the implementation match the thesis documentation more closely. It is intentionally detailed so it can be used as a development checklist.

Status legend:

- `DONE` - implemented enough to support the thesis claim.
- `PARTIAL` - implemented, but narrower than the thesis describes.
- `TODO` - not implemented yet.
- `OPTIONAL` - useful improvement, but not required for a credible thesis submission.

---

## 1. Documentation And Repository Hygiene

### 1.1 Update project documentation

Status: `PARTIAL`

The README has been updated to describe the current MongoDB-based architecture. Remaining documentation work:

- Add a short architecture diagram to the thesis or README showing the exact flow:
  - source file
  - Perl parser
  - generated CSV
  - MongoDB `raw_permits`
  - Python inference
  - MongoDB inference collections
  - optional `final_permits`
- Document each MongoDB collection with example documents.
- Document which parts are implemented and which are planned/future work.
- Remove or rewrite any remaining PostgreSQL references in other project notes if they are no longer accurate.

### 1.2 Clean generated files from version control

Status: `TODO`

Generated files are present in the project tree and should not usually be committed:

- Python `__pycache__/` folders.
- `.pyc` files.
- Generated inference output directories under `python_inference/output/`.
- Generated parser CSVs under `data/archive/`.
- Temporary PDF-to-XML/TXT outputs if generated during parsing.

Recommended actions:

- Add or update `.gitignore`.
- Remove generated files from Git tracking if already committed.
- Keep input samples only when they are intentionally part of the thesis dataset.

Suggested `.gitignore` entries:

```gitignore
__pycache__/
*.pyc
python_inference/output/
data/archive/
*.xml
*.tmp
```

### 1.3 Clean thesis template leftovers

Status: `TODO`

The Word thesis document still contains template text/placeholders. Remove or replace:

- Generic title placeholders.
- Generic graduate/supervisor placeholders.
- Template instructions such as "This chapter will contain...".
- Example table-of-contents chapter names if they are not final.
- Empty appendix placeholders.

---

## 2. Parser And Extraction Layer

### 2.1 Keep current source-specific parsers working

Status: `PARTIAL`

Current parser support exists for several sources:

- Naples XLSX.
- Sonoma PDF.
- Sausalito PDF.
- Hermosa Beach PDF.
- Larimer PDF.
- Temple City CSV-style input.
- East Baton Rouge CSV-style input.

Tasks:

- Run each parser against at least one representative input file.
- Record the parser command used.
- Record parsed row count and loaded row count.
- Save examples of expected output fields for each source.
- Add regression tests for at least the most important parsers.

### 2.2 Make extraction more configuration-driven

Status: `PARTIAL`

The thesis says extraction is configuration-driven. The current implementation has parser configs, but many extraction rules are still hard-coded inside parser modules.

Needed work:

- Move spreadsheet header aliases from parser modules into parser config files.
- Move required fields into parser config files.
- Move source metadata into parser config files consistently.
- Move missing-value markers into parser config files.
- For PDF parsers, consider moving coordinate ranges or field layout definitions into config where practical.
- Define a common parser config schema.
- Validate parser configs at startup and fail with clear errors if required keys are missing.

Suggested config structure:

```perl
{
  source => {
    state => 'FL',
    county => 'Collier',
    municipality => 'Naples',
    format => 'xlsx',
  },
  target_collection => 'raw_permits',
  config_version => '1.0',
  columns => [...],
  required_fields => ['permit_number'],
  missing_values => ['', '-', 'N/A', 'Not Identified'],
  extraction => {
    header_aliases => {
      permit_number => ['Permit Number', 'Permit #'],
      issued_date => ['Issued Date', 'Date Issued'],
    },
  },
}
```

### 2.3 Add extraction quality checks

Status: `TODO`

The thesis mentions evaluating extraction quality. Implement parser-level checks:

- Required field presence per record.
- Missing percentage per field.
- Duplicate permit number detection per parser run.
- Suspicious row detection, such as rows with very few populated fields.
- Parser run summary with:
  - input file name
  - parser module
  - config module
  - total parsed rows
  - total loaded rows
  - missing counts by field
  - duplicate counts
  - rejected/ignored row counts

### 2.4 Preserve rejected or suspicious raw blocks

Status: `TODO`

Currently parsers mostly skip rows/blocks that do not look valid. For traceability, add optional diagnostics:

- Store rejected raw lines/blocks in a `parser_rejections` collection.
- Include rejection reason.
- Include page number, row number, or line number where possible.
- Make this optional through parser config to avoid storing too much noise.

---

## 3. Common Record Model

### 3.1 Define the canonical schema

Status: `PARTIAL`

The code has source-specific fields and a shared-ish target shape, but the common schema should be explicit.

Tasks:

- Create a document such as `docs/common_schema.md`.
- Define each common field:
  - `permit_number`
  - `applied_date`
  - `issued_date`
  - `finaled_date`
  - `permit_type`
  - `permit_class`
  - `address`
  - `parcel_number`
  - `owner_name`
  - `contractor_name`
  - `description`
  - `valuation`
  - `fee`
  - source/provenance fields
- For each field, document:
  - type
  - required/optional status
  - normalization rule
  - validation rule
  - whether inference is allowed

### 3.2 Store raw, normalized, and final values explicitly

Status: `PARTIAL`

The thesis describes raw, normalized, and final values. The current database stores raw parsed fields under `data`, and final inferred values can be applied in `final_permits`, but normalized field-level values are not represented as a separate layer.

Possible implementation:

```json
{
  "raw_permit_id": "...",
  "data": {
    "permit_number": {
      "raw": "BLD-123",
      "normalized": "BLD-123",
      "final": "BLD-123",
      "status": "valid",
      "source": "extracted"
    },
    "valuation": {
      "raw": "$1,250.00",
      "normalized": 1250.0,
      "final": 1250.0,
      "status": "valid",
      "source": "extracted"
    }
  }
}
```

Alternative: keep the current flat `data` object for simplicity, but add companion objects:

```json
{
  "data": { "valuation": "1250.00" },
  "normalized": { "valuation": 1250.0 },
  "validation": { "valuation": { "status": "valid" } },
  "final": { "valuation": 1250.0 }
}
```

Choose one model and make the thesis match it.

---

## 4. Normalization Layer

### 4.1 Implement field-level normalizers

Status: `PARTIAL`

Current implementation mostly normalizes strings and selected target labels. The thesis describes broader normalization.

Needed normalizers:

- Missing values:
  - Convert empty strings, whitespace-only strings, `-`, `N/A`, `NONE`, `Not Identified`, and configured markers to a shared missing representation.
- Dates:
  - Parse common formats such as `MM/DD/YYYY`, `M/D/YYYY`, `YYYY-MM-DD`, and source-specific formats.
  - Store normalized date as ISO `YYYY-MM-DD`.
  - Preserve raw value if parsing fails.
- Monetary values:
  - Remove `$`, commas, spaces.
  - Convert to numeric decimal/float.
  - Reject or flag negative values where not meaningful.
- Integer/numeric fields:
  - Normalize square footage, unit counts, fees, and valuations.
- Text fields:
  - Trim whitespace.
  - Collapse repeated spaces.
  - Normalize repeated punctuation only when safe.
- Phone numbers:
  - Strip formatting.
  - Validate digit length.
  - Preserve extension if present.
- Identifiers:
  - Preserve meaningful separators.
  - Trim and collapse whitespace.

Suggested Python module:

```text
python_inference/preprocessing/normalizers.py
```

Suggested functions:

- `normalize_missing(value, markers)`
- `normalize_date(value, formats)`
- `normalize_money(value)`
- `normalize_integer(value)`
- `normalize_text(value)`
- `normalize_phone(value)`
- `normalize_record(record, schema)`

### 4.2 Make normalization configurable

Status: `TODO`

Normalization behavior should be driven by schema/config:

```yaml
schema:
  issued_date:
    type: date
    formats: ["%m/%d/%Y", "%Y-%m-%d"]
    required: false
  valuation:
    type: money
    required: false
  permit_number:
    type: identifier
    required: true
```

Tasks:

- Add schema config to YAML or parser config.
- Make normalizers read field type and options.
- Include normalized outputs in prepared data or MongoDB.

---

## 5. Validation Layer

### 5.1 Implement validation statuses

Status: `TODO`

The thesis describes these statuses:

- `valid`
- `missing`
- `invalid`
- `suspicious`
- `requires_review`

Implement this explicitly.

Suggested Python module:

```text
python_inference/preprocessing/validation.py
```

Suggested objects:

```python
{
  "field": "valuation",
  "status": "valid",
  "raw_value": "$1,250.00",
  "normalized_value": 1250.0,
  "messages": []
}
```

### 5.2 Add field-level validation rules

Status: `TODO`

Rules to implement:

- `permit_number`
  - Required for most sources.
  - Must not be empty after normalization.
  - Optional source-specific pattern validation.
- `issued_date`, `applied_date`, `finaled_date`
  - Must parse as date if present.
  - Flag future dates if inappropriate for dataset.
  - Flag impossible dates.
- `valuation`, `fee`
  - Must be numeric if present.
  - Flag negative values.
  - Flag extremely high values as suspicious, not automatically invalid.
- `parcel_number`
  - Must be non-empty if source treats it as required.
  - Optional pattern checks per municipality.
- `address`
  - Missing allowed for some sources, but record may be weaker.
- `phone`
  - Validate digit count.
- categorical fields:
  - Optionally validate against allowed values or known values from training data.

### 5.3 Add record-level validation

Status: `TODO`

Rules:

- A record should usually have `permit_number`.
- A record should have at least one useful locator:
  - address
  - parcel number
  - owner
  - source row identity
- A record should not be only headers/footers/noise.
- Duplicate records in the same parser run should be flagged.
- Records with too many missing required/important fields should be marked `requires_review`.

### 5.4 Persist validation results

Status: `TODO`

Add validation results to MongoDB. Options:

- Store inside `raw_permits`.
- Store in a separate `validation_results` collection.
- Store inside `final_permits`.

Recommended simple approach:

```json
{
  "raw_permit_id": "...",
  "validation": {
    "record_status": "valid",
    "fields": {
      "permit_number": {
        "status": "valid",
        "messages": []
      },
      "valuation": {
        "status": "suspicious",
        "messages": ["Value is above configured warning threshold"]
      }
    }
  }
}
```

### 5.5 Use validation before inference

Status: `TODO`

The thesis says inference should use validated records as evidence.

Tasks:

- Exclude invalid field values from inference training/reference rows.
- Allow missing values to become inference targets only when the field is configured as inferable.
- Do not infer values for records whose supporting features are invalid or too incomplete.
- Include validation status in inference decisions.

---

## 6. Missing-Value Inference Layer

### 6.1 Existing inference methods

Status: `DONE`

Implemented:

- Grouped-majority baseline.
- Association rules.
- Clustering.
- kNN.
- Merged decision layer.
- Evaluation mode with artificial masking.
- Production mode for genuinely missing values.
- Confidence scores for candidate predictions.
- Confusion matrix plots and metrics.

### 6.2 Improve confidence threshold configuration

Status: `PARTIAL`

The merge layer supports `minimum_confidence`, but Naples currently uses `0.0`, which accepts any valid prediction.

Tasks:

- Set meaningful thresholds per target.
- Consider per-algorithm thresholds.
- Document why each threshold was chosen.
- Report accepted/rejected counts in thesis results.

Example:

```yaml
merge:
  enabled: true
  strategy: majority_then_confidence
  minimum_confidence: 0.65
```

### 6.3 Add manual-review status for rejected predictions

Status: `PARTIAL`

Rejected predictions exist as `rejected_no_candidate_above_threshold`, but there is no review workflow.

Tasks:

- Add explicit `requires_review` or `unresolved_low_confidence` status.
- Store rejected candidates with reason.
- Include rejected values in UI/manual review view.
- Report unresolved rate in metrics.

### 6.4 Add more inference targets

Status: `TODO`

Currently Naples inference appears centered on `permit_class`.

Possible additional targets:

- `permit_type`
- `building_type`
- `const_type`
- `contractor_type`
- maybe `valuation_bucket`, but avoid pretending exact monetary values can be safely inferred unless justified.

For each target:

- Define whether inference is appropriate.
- Define feature columns.
- Define cleaning rules.
- Define thresholds.
- Add evaluation results.

### 6.5 Prevent leakage in evaluation

Status: `TODO`

Review whether engineered features or feature columns leak information about the target.

Tasks:

- For each inference target, audit feature columns.
- Ensure target-derived columns are not used as features.
- Document the audit in the thesis.

---

## 7. MongoDB Storage Model

### 7.1 Keep current parser and inference collections

Status: `DONE`

Current collections are reasonable:

- `source_files`
- `parser_runs`
- `parser_analytics`
- `raw_permits`
- `inference_runs`
- `inference_predictions`
- `inference_decisions`
- `final_permits`

### 7.2 Add indexes

Status: `TODO`

Add indexes for common lookup paths:

- `source_files.file_id`
- `parser_runs.run_id`
- `parser_runs.status`
- `parser_runs.completed_at`
- `raw_permits.raw_permit_id`
- `raw_permits.provenance.parser_run_id`
- `raw_permits.source.state`
- `raw_permits.source.county`
- `raw_permits.source.municipality`
- `inference_runs.inference_run_id`
- `inference_predictions.inference_run_id`
- `inference_predictions.raw_permit_id`
- `inference_decisions.inference_run_id`
- `inference_decisions.raw_permit_id`
- `final_permits.final_permit_id`

Indexes can be created during startup, parser run initialization, or through a setup script.

### 7.3 Add schema examples

Status: `TODO`

Create documentation with one example document for:

- source file
- parser run
- raw permit
- inference prediction
- inference decision
- final permit

This will make Chapter 5 easier to defend.

---

## 8. User Interface

### 8.1 Decide whether UI is in scope

Status: `TODO`

The thesis currently claims that users can inspect/filter/analyze records through a user interface. No UI implementation was found.

You have two realistic choices:

1. Implement a small UI.
2. Change the thesis to say inspection is done through MongoDB/output files and that a UI is future work.

If you keep the UI claim, implement at least a minimal interface.

### 8.2 Minimal UI option

Status: `TODO`

Fastest credible UI: Streamlit.

Suggested features:

- Connect to MongoDB.
- Select parser run.
- Show raw permits table.
- Filter by municipality/source.
- Filter by missing fields.
- Show inference runs.
- Show inference decisions.
- Filter decisions by:
  - target field
  - accepted/rejected
  - confidence range
  - selected algorithm
- Detail view for a permit:
  - raw data
  - validation statuses
  - inference candidates
  - final decision
  - provenance metadata

Suggested files:

```text
ui/
  app.py
  requirements.txt
```

Example command:

```bash
streamlit run ui/app.py
```

### 8.3 UI screenshots for thesis

Status: `TODO`

If UI is implemented, add screenshots to Chapter 7:

- Parser run list.
- Raw permit table.
- Inference decision table.
- Permit detail page.
- Filter examples.

---

## 9. Testing And Validation

### 9.1 Add parser regression tests

Status: `TODO`

Current tests do not appear to validate parser outputs against expected records.

Add small fixture files or trimmed samples for:

- Naples XLSX.
- One PDF parser.
- One CSV-style parser.

For each parser test:

- Run parser on fixture.
- Compare row count.
- Compare key fields from first/middle/last records.
- Verify generated CSV columns.
- Verify parser analytics.

### 9.2 Add Python unit tests

Status: `TODO`

Add tests for:

- Normalizers.
- Validation rules.
- Masking.
- Feature engineering.
- Each inference algorithm on a tiny deterministic dataset.
- Merge decision logic.
- Mongo document builders, ideally with mocking.

Recommended framework:

```text
pytest
```

Suggested structure:

```text
python_inference/tests/
  test_cleaner.py
  test_normalizers.py
  test_validation.py
  test_masking.py
  test_merge_predictions.py
  test_grouped_majority.py
  test_knn.py
  test_clustering.py
  test_association_rules.py
```

### 9.3 Add end-to-end smoke test

Status: `TODO`

Test the whole path:

1. Start MongoDB.
2. Run one parser fixture.
3. Confirm `parser_runs` completed.
4. Confirm `raw_permits` rows were loaded.
5. Run Python inference.
6. Confirm `inference_runs` completed.
7. Confirm predictions and decisions were written.

This could be a script:

```text
scripts/smoke_test.sh
```

or a documented manual test for thesis validation.

### 9.4 Add Chapter 6 metrics

Status: `TODO`

For the thesis, collect and report:

- Parser row counts per source/file.
- Missing percentages per important field.
- Inference accuracy per algorithm.
- Macro F1 / weighted F1 per algorithm.
- Confusion matrices.
- Accepted prediction count.
- Rejected/unresolved prediction count.
- Accuracy on accepted merged predictions.
- Coverage.
- Runtime, if useful.

---

## 10. Security, Robustness, And Maintainability

### 10.1 Avoid shell-command string construction in parsers

Status: `TODO`

Some PDF conversion code builds shell commands as strings. Prefer list-form system calls where possible to avoid quoting problems with filenames.

Example improvement:

```perl
system('pdftohtml', '-xml', '-nodrm', '-q', $self->{file}, $xml_file) == 0
    or die "Failed to convert PDF to XML";
```

### 10.2 Improve parser error reporting

Status: `PARTIAL`

Parser runs store failure state, which is good. More detail would help:

- Include parser stage where failure happened.
- Include source page/row/line if known.
- Include config file version.
- Store partial analytics if possible.

### 10.3 Add dependency/version documentation

Status: `TODO`

Document:

- Perl version.
- Python version.
- MongoDB version.
- Important Perl modules.
- Important Python packages.
- External tools such as `pdftohtml`.

The Dockerfile already installs these, but the thesis/user manual should list them.

---

## 11. Thesis Text Alignment

### 11.1 Claims that are currently supported

Status: `DONE`

These thesis claims are broadly supported by code:

- Source-specific permit parsers exist.
- Parsed rows are stored in MongoDB.
- Parser runs and source files have provenance metadata.
- Missing-value inference exists.
- Multiple inference methods are implemented.
- Evaluation through artificial masking exists.
- Confidence scores are produced.
- Candidate predictions are merged.
- Inference predictions and decisions are persisted.

### 11.2 Claims that should be softened unless implemented

Status: `TODO`

Soften or implement these before final submission:

- Full user interface for inspection/filtering/analysis.
- Full field-level validation model.
- Rich normalized/validated/final value model per field.
- Fully configuration-driven extraction.
- Manual inspection workflow.
- Validation metrics based on malformed/suspicious/requires-review statuses.

### 11.3 Recommended thesis wording if implementation remains as-is

Status: `OPTIONAL`

If there is not enough time to implement everything, use more precise wording:

- Instead of "the system validates each field and assigns statuses", say "the current implementation performs configurable cleaning and missing-value preparation, while the validation model is designed as an extension."
- Instead of "users inspect records through a user interface", say "records can currently be inspected through MongoDB collections and generated output files; a dedicated UI is proposed as future work."
- Instead of "extraction is configuration-driven", say "the system combines source-specific parser modules with configuration files for schema mapping, source metadata, and loading behavior."

---

## 12. Suggested Implementation Order

If the goal is to make the project match the thesis with the best time-to-value ratio, use this order:

1. Clean documentation and remove template leftovers from the thesis.
2. Add `.gitignore` and remove generated Python cache/output artifacts from tracking.
3. Implement validation statuses and basic field-level validation.
4. Persist validation results in MongoDB.
5. Raise `minimum_confidence` above `0.0` and report accepted/rejected predictions.
6. Add parser and Python regression tests for the main happy path.
7. Decide UI scope:
   - either implement a small Streamlit UI,
   - or move UI to future work in the thesis.
8. Improve parser config-driven behavior where easiest, especially spreadsheet header aliases and required fields.
9. Add Mongo indexes/setup script.
10. Collect final Chapter 6 metrics and screenshots/output examples.
