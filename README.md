# Job Market Intelligence Pipeline

A data engineering project that collects, processes, and filters job postings to identify relevant Senior Data Engineer and Analytics Engineer roles.

## Why I built this

Searching job boards manually is time-consuming and creates a lot of noise.

The goal of this project is to automate job collection and progressively build a decision engine that helps identify which roles are worth applying to.

## Architecture

Job API
→ Python ingestion
→ Raw JSON
→ Deduplication and transformation
→ Job classification
→ Curated jobs
→ Actionable jobs
→ Run metadata

Airflow orchestrates the pipeline.
Docker provides a reproducible runtime environment.

## Current capabilities

- Job ingestion from API
- Multiple search queries
- Raw data persistence
- Deduplication
- Job classification
- Curated and actionable job datasets
- Schema validation
- Run metadata and traceability
- Airflow scheduling and retries
- Dockerized execution

## Tech stack

- Python
- Airflow
- Docker
- Git / GitHub
- uv

## Project structure

```text
dags/
    job_radar_dag.py

src/job_market_intelligence/
    __main__.py
    job_api_client.py

Dockerfile
pyproject.toml
README.md