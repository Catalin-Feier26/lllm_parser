# Docker Setup Instructions

## Building the Docker Image

Build the Docker image:
```bash
docker build -t thesis-parser .
```

Or using docker-compose:
```bash
docker-compose build
```

## Running the Container

### Option 1: Using docker-compose (Recommended)
Start an interactive container:
```bash
docker-compose run --rm perl-parser
```

This will drop you into a bash shell inside the container where you can run your parsing commands.

### Option 2: Using Docker directly
```bash
docker run -it --rm -v ${PWD}/data:/app/data thesis-parser
```

## Running Parsing Commands

Once inside the container, you can run your parsing commands:

```bash
perl bin/run_parsing.pl --state="CA" --county="LosAngeles" --file_name="Hermosa Beach April 2025.pdf" --name="HermosaBeach_PDF"
```

## Data Persistence

The `data/` directory is mounted as a volume, so:
- Place your input files in `data/incoming/` on your host machine
- Output CSV files will appear in `data/archive/` on your host machine
- Files persist even after the container is stopped

## One-off Commands

To run a single command without entering the shell:
```bash
docker-compose run --rm perl-parser perl bin/run_parsing.pl --state="CA" --county="LosAngeles" --file_name="Hermosa Beach April 2025.pdf" --name="HermosaBeach_PDF"
```

Or with Docker directly:
```bash
docker run --rm -v ${PWD}/data:/app/data thesis-parser perl bin/run_parsing.pl --state="CA" --county="LosAngeles" --file_name="Hermosa Beach April 2025.pdf" --name="HermosaBeach_PDF"
```
