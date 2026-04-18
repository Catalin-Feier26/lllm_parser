# Naples Permit Data Analysis Summary

## Source and scope

This summary covers the exploratory analysis performed on the **FL / Collier / Naples XLSX** permit source after parsing and loading **10 runs** into MongoDB.

The loaded runs were:

- `2025-4-issued-permits.xlsx` → 5305 rows
- `2025-1-issued.xlsx` → 4650 rows
- `2025-3-issued.xlsx` → 4612 rows
- `2025-5-issued-permits.xlsx` → 4703 rows
- `2025-6-issued-permits-1.xlsx` → 4378 rows
- `2025-7-issued-permits-1.xlsx` → 4803 rows
- `2025-8-issued.xlsx` → 4590 rows
- `2025-9-issued-permits_1.xlsx` → 4822 rows
- `2025-10-issued-permits.xlsx` → 4659 rows
- `2025-12-issued.xlsx` → 3905 rows

**Total loaded permits:** 46,427

---

## Parsed schema used for profiling

The Naples parser was extended to keep the following fields:

- `permit_number`
- `valuation`
- `building_type`
- `permit_class`
- `permit_type`
- `status`
- `address`
- `parcel_number`
- `issued_date`
- `applied_date`
- `total_sf`
- `total_units`
- `const_type`
- `owner_name`
- `owner_city`
- `owner_state`
- `owner_zip`
- `owner_location`
- `contractor_type`
- `license_number`
- `contractor_name`
- `contractor_city`
- `contractor_state`
- `contractor_zip`
- `contractor_location`

---

## Missing-value profiling results

Across the 10 runs, the missingness pattern was very consistent.

### Fields with essentially no missing values

These are **not useful inference targets**, but they are strong predictor features.

- `permit_number` → 0%
- `permit_type` → 0%
- `status` → 0%
- `issued_date` → 0%
- `applied_date` → 0%
- `contractor_type` → 0%
- `building_type` → almost complete

### Field with the strongest missingness

This is the best candidate target for Naples.

- `permit_class` → about **21% to 28% missing** depending on file  
  (`"Not Identified"` treated as missing)

### Moderately missing fields

Possible secondary targets or engineered features.

- `valuation` → about **4.5% to 8.5% missing**
- `total_sf` → about **4.6% to 8.5% missing**
- `total_units` → about **4.6% to 8.5% missing**
- `license_number` → about **4.9% to 7.1% missing**
- `owner_city / owner_state / owner_zip / owner_location` → about **4% to 9% missing**
- `contractor_city / contractor_state / contractor_zip / contractor_location` → about **4% to 9% missing**

### Low-missingness fields

Probably not worth prioritizing as inference targets.

- `address`
- `parcel_number`
- `owner_name`
- `contractor_name`
- `const_type`

---

## Main target selected for Naples

## `permit_class`

This is the strongest inference target for the Naples source because it has:

- substantial missingness
- only a small number of repeated real categories
- strong correlations with other structured fields
- enough ambiguity to make inference meaningful

### Observed known classes

Among non-missing values, the distribution was:

- `Res.1&2 or Guest House` → 24,740
- `Residential-Multi-Family` → 6,856
- `Commercial` → 3,153
- `Residential-Hotel` → 48
- `Residential-Care-Assisted Living Facilities` → 16

### Interpretation

This means `permit_class` is:

- a **small-category classification problem**
- but **imbalanced**
- with two very rare classes

### Recommended practical handling

For early experiments, it is reasonable to merge the two rare classes into:

- `Other Special Residential`

This gives a more stable 4-class target:

- `Res.1&2 or Guest House`
- `Residential-Multi-Family`
- `Commercial`
- `Other Special Residential`

---

## Strongest predictor fields for `permit_class`

### 1. `building_type`

This was the strongest predictor.

Observed relation:

- `building_type = 1 to 2 Family` → almost always `Res.1&2 or Guest House`
- `building_type = Commercial` → usually one of:
  - `Residential-Multi-Family`
  - `Commercial`
  - rarely the two special residential classes

This means `building_type` alone is very powerful, but not sufficient for the `Commercial` branch.

### 2. `permit_type`

This was the second strongest predictor.

Some permit types are almost deterministic:

- `Certificate of Use` → strongly `Commercial`
- `Sign/Flagpole` → strongly `Commercial`
- `ROW Residential` → strongly `Res.1&2 or Guest House`

Other permit types are mixed:

- `Building`
- `Revision - Building`
- `Mechanical`
- `Electrical`
- `Plumbing`
- `Reroof`

These mixed groups are exactly where more advanced methods should help.

### 3. `const_type`

Useful as a supporting feature, but not strong enough by itself.

Examples:

- `Alteration/Remodel` occurs across all major classes
- `New Construction` occurs across all major classes
- `Addition` is mostly residential, but still mixed

Conclusion: `const_type` should be used as an additional feature, not the main driver.

---

## Commercial branch analysis

A targeted query for `building_type = Commercial` showed:

- `Residential-Multi-Family` → 6855
- `Commercial` → 3153
- `Residential-Hotel` → 48
- `Residential-Care-Assisted Living Facilities` → 16
- `Res.1&2 or Guest House` → 3

### Interpretation

This is very important:

- the `Commercial` building type does **not** mean the class is `Commercial`
- it is actually more often `Residential-Multi-Family`

So the real ambiguity is inside the **Commercial building-type branch**, and this is where inference methods matter most.

---

## Numeric field observations

### `valuation`

Most frequent values included:

- `1`
- `1000`
- `1200`
- `2000`
- `50`
- `10000`
- `950`
- `1500`
- `5000`
- `15000`

### Interpretation

`valuation` is too noisy and too skewed to use directly as an exact-value target in the first experiment.

Recommended treatment:

- convert to **valuation buckets**

Example bucket scheme:

- `<=1`
- `2-999`
- `1000-9999`
- `10000-99999`
- `100000+`

### `total_sf`

Most frequent value:

- `0` → 36,913 rows

This means `total_sf` is dominated by zero and is not a good first target.

Recommended treatment:

- use as a weak derived feature such as:
  - `total_sf_nonzero` = yes/no

### `total_units`

Most frequent values:

- `1` → 32,143
- `0` → 11,141
- all other values are rare

Recommended treatment:

- group into:
  - `0`
  - `1`
  - `gt1`

This is much more useful than the raw field.

---

## Best first experiment design for Naples

## Target

- `permit_class`

## Core predictors

- `building_type`
- `permit_type`
- `const_type`

## Engineered supporting predictors

- `valuation_bucket`
- `total_units_group`
- `total_sf_nonzero`

## Excluded for version 1

These should not be primary inference targets or core first-pass predictors:

- `owner_name`
- `contractor_name`
- `address` full text
- `parcel_number`
- owner/contractor location fields

They may still be explored later, but they are not needed for the first Naples experiment.

---

## Recommended methods

Three unsupervised approaches were selected for the thesis:

### 1. Association Rule Mining

Best for:

- interpretable patterns
- strong repeated relationships such as:
  - `building_type + permit_type -> permit_class`

Expected strength:
- very good on obvious cases
- useful for explainability

### 2. Clustering-based inference

Best for:

- ambiguous groups, especially inside `building_type = Commercial`
- separating similar permit records using multiple features together

Expected strength:
- helpful where direct rules are not clean

### 3. Similarity-based imputation with kNN

Best for:

- practical classification of missing `permit_class`
- using similarity over several structured features

Expected strength:
- likely the strongest practical method for Naples

---

## Recommended baselines

The thesis experiments should include simple baselines for comparison.

### Baseline A

Always predict the majority class:

- `Res.1&2 or Guest House`

### Baseline B

Predict the majority class by `building_type`

Example:
- `1 to 2 Family` → `Res.1&2 or Guest House`
- `Commercial` → `Residential-Multi-Family`

### Baseline C

Predict the majority class by `(building_type, permit_type)`

This is expected to be the strongest simple baseline and should be compared against the three unsupervised methods.

---

## Evaluation strategy

Because naturally missing `permit_class` values do not have a known ground truth, evaluation should use **artificial masking**:

1. take rows where `permit_class` is known
2. hide a portion of those values
3. run the inference algorithm
4. compare predicted vs actual value

### Recommended metrics

Because the target is imbalanced:

- accuracy
- macro F1
- per-class recall
- confusion matrix

Accuracy alone is not enough.

---

## Final conclusion

For the Naples source, the exploratory analysis strongly supports the following design:

- use **`permit_class`** as the primary inference target
- use **`building_type`**, **`permit_type`**, and **`const_type`** as the main structured predictors
- engineer **`valuation_bucket`**, **`total_units_group`**, and **`total_sf_nonzero`**
- compare:
  - simple baselines
  - association rules
  - clustering
  - kNN similarity-based inference

This source is a strong first candidate for implementation because it is:

- structured
- large enough
- not trivial
- and has a clear, meaningful missing categorical field to infer.
