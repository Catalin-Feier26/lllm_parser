# Docker Setup Instructions

This project runs the Perl permit parsers inside Docker and (optionally) loads the generated CSV output into a PostgreSQL staging table.

Your current `docker-compose.yml` provides two services:

* **db**: PostgreSQL 16 (container: `thesis-db`)
* **perl-parser**: Perl 5.30 parser runner (container: `thesis-parser`)

---

## Prerequisites

* Docker Desktop (or Docker Engine) installed
* Docker Compose available as `docker compose`
* (Optional) DataGrip / DBeaver / pgAdmin for inspecting the database

---

## Quick Start

### 1) Build

```bash
docker compose build
```

### 2) Start services

```bash
docker compose up -d
```

### 3) Open a shell in the parser container

```bash
docker exec -it thesis-parser bash
```

---

## Project Folders (Persistence)

The whole project directory is mounted into the container at `/app`:

* Put input files in: `data/incoming/`
* Parsers write CSV output to: `data/archive/`

Because the folder is mounted, files persist on your host machine.

---

## Running Parsers (CSV output only)

Inside the container:

```bash
perl bin/run_parsing.pl \
  --state CA \
  --county Sonoma \
  --name Sonoma_PDF \
  --file_name "Construction-Applications-2025-07.pdf"
```

This produces a CSV in `data/archive/` with the same base filename.

---

## Running Parsers + Loading into PostgreSQL (recommended)

To automatically load the produced CSV into a staging table, pass a config name:

```bash
perl bin/run_parsing.pl \
  --state CA \
  --county Sonoma \
  --name Sonoma_PDF \
  --file_name "Construction-Applications-2025-07.pdf" \
  --config_file ca_sonoma_pdf
```

What happens:

1. The parser generates the CSV in `data/archive/`.
2. The loader builds (or reuses) a staging table based on `lib/Config/Parser/<config>.pm`.
3. Rows are inserted into the table.
4. The loader also adds these metadata columns automatically:

   * `run_id`
   * `source_file` (format: `YYYY_MM_DD_<CsvFilename>`)
   * `loaded_at`

---

## Loading a CSV manually into PostgreSQL

If you already have a CSV and want to load it:

```bash
perl bin/load_csv_to_staging.pl \
  --config_file ca_sonoma_pdf \
  --csv "data/archive/Construction-Applications-2025-07.csv"
```

Optional args (normally the runner passes these automatically):

```bash
perl bin/load_csv_to_staging.pl \
  --config_file ca_sonoma_pdf \
  --csv "data/archive/Construction-Applications-2025-07.csv" \
  --run_id "run_20260222_123000" \
  --source_file "2026_02_22_Construction-Applications-2025-07.csv"
```

---

## PostgreSQL Connection Details

Your `docker-compose.yml` maps Postgres to host port **5433**:

* **Host (from your computer):** `localhost`
* **Port:** `5433`
* **Database:** `thesis`
* **User:** `thesis`
* **Password:** `thesis`

### DataGrip

Create a new **PostgreSQL** data source:

* Host: `localhost`
* Port: `5433`
* User: `thesis`
* Password: `thesis`
* Database: `thesis`

If you ever get an authentication error and you previously had another Postgres on port 5432, keep using **5433** to avoid conflicts.

---

## Verifying Data Loaded

Run from the **db** container:

```bash
docker exec -it thesis-db psql -U thesis -d thesis -c "\\dn"
```

Example queries:

```bash
docker exec -it thesis-db psql -U thesis -d thesis -c "SELECT count(*) FROM staging.stg_ca_sonoma_pdf;"

docker exec -it thesis-db psql -U thesis -d thesis -c "SELECT run_id, source_file, count(*) FROM staging.stg_ca_sonoma_pdf GROUP BY 1,2 ORDER BY 3 DESC;"
```

---

## One-off Commands (no interactive shell)

Run a parser (CSV only):

```bash
docker compose run --rm perl-parser \
  perl bin/run_parsing.pl --state CA --county Sonoma --name Sonoma_PDF --file_name "Construction-Applications-2025-07.pdf"
```

Run a parser + auto-load:

```bash
docker compose run --rm perl-parser \
  perl bin/run_parsing.pl --state CA --county Sonoma --name Sonoma_PDF --file_name "Construction-Applications-2025-07.pdf" --config_file ca_sonoma_pdf
```

---

## Stop / Reset

Stop containers:

```bash
docker compose down
```

Stop and remove volumes (deletes the DB data):

```bash
docker compose down -v
```

---

## Notes

* The Perl container connects to Postgres using the internal Docker hostname `db:5432` (as configured in `environment:`).
* Your host connects to Postgres using `localhost:5433` (as configured in `ports:`).
* If you need to change the host port, update `ports:` in `docker-compose.yml` (e.g., `"5440:5432"`) and update your DB client accordingly.
